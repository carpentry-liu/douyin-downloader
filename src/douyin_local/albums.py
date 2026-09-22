"""下载图文/实况的原始素材；manifest 可用于完全离线处理。"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import Request, urlopen

import imageio_ffmpeg

from . import DownloadError
from .download import safe_name, sha256, validate_video
from .posts import media_urls


def local_file(folder, name):
    if not isinstance(name, str) or not name or Path(name).name != name or name in {".", ".."} or ":" in name:
        raise DownloadError("素材清单含非法文件路径。")
    folder = Path(folder).resolve()
    path = (folder / name).resolve()
    if path.parent != folder or not path.is_file():
        raise DownloadError(f"素材文件不存在或不在所选目录：{name}")
    return path


def load_album(folder):
    folder = Path(folder).resolve()
    try:
        data = json.loads((folder / "作品信息.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not re.fullmatch(r"\d{10,25}", str(data.get("id", ""))) or not isinstance(data.get("files"), list) or not data["files"]:
            raise ValueError("invalid manifest")
        if not all(isinstance(item, dict) and item.get("type") in {"image", "video", "audio"} for item in data["files"]):
            raise ValueError("invalid media record")
        if len({item["file"] for item in data["files"]}) != len(data["files"]):
            raise ValueError("duplicate file")
        for item in data["files"]:
            path = local_file(folder, item["file"])
            if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
                raise DownloadError(f"素材校验失败：{path.name}，请重新下载或恢复原文件。")
        return data
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DownloadError("请选择包含「作品信息.json」和完整原素材的下载目录。") from exc


def decode_media(path):
    try:
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
                                capture_output=True, timeout=180,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DownloadError("媒体解码未完成。") from exc
    if result.returncode:
        raise DownloadError("下载内容无法完整解码。")


def extension_for(data, kind):
    if kind == "image":
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return ".webp"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
    elif kind == "video" and data[4:8] == b"ftyp":
        return ".mp4"
    elif kind == "audio":
        if data[4:8] == b"ftyp":
            return ".m4a"
        if data.startswith(b"ID3") or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224):
            return ".mp3"
    raise DownloadError("媒体格式与预期不一致，可能是错误页面。")


def download_asset(kind, stem, urls, folder, headers, index=None, expected_duration=None):
    for url in urls:
        part = folder / (stem + ".part")
        final = None
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response, part.open("wb") as target:
                expected = response.headers.get("Content-Length")
                while block := response.read(256 * 1024):
                    target.write(block)
            if expected and part.stat().st_size != int(expected):
                raise DownloadError("媒体下载长度不完整。")
            with part.open("rb") as source:
                extension = extension_for(source.read(16), kind)
            final = folder / (stem + extension)
            part.rename(final)
            record = {"file": final.name, "type": kind, "bytes": final.stat().st_size,
                      "sha256": sha256(final), "full_decode_verified": True}
            if index is not None:
                record["index"] = index
            if kind == "video":
                record.update(validate_video(final, expected_duration=expected_duration))
            else:
                decode_media(final)
                if kind == "image":
                    reader = imageio_ffmpeg.read_frames(str(final))
                    try:
                        record["width"], record["height"] = next(reader)["source_size"]
                    finally:
                        reader.close()
            return record
        except (OSError, ValueError, RuntimeError, DownloadError):
            part.unlink(missing_ok=True)
            if final is not None:
                final.unlink(missing_ok=True)
    raise DownloadError(f"{stem} 下载失败，平台媒体地址可能已过期，请重试。")


def save_album(post, output, log=print):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{post['id']}_{safe_name(post.get('author'), 20)}"
    if destination.exists():
        existing = load_album(destination)
        if existing["id"] != post["id"]:
            raise DownloadError("已有目录包含其他作品，停止以免覆盖。")
        return destination, existing
    with tempfile.TemporaryDirectory(prefix=f".{post['id']}-", dir=output) as temp:
        staging = Path(temp) / "album"
        staging.mkdir()
        files = []
        for item in post["images"]:
            index = item["index"]
            log(f"保存图片 {index}/{len(post['images'])}…")
            files.append(download_asset("image", f"{index:02}", item["urls"], staging, post["headers"], index))
            clip = item.get("video")
            if clip:
                log(f"保存对应实况 {index}…")
                duration = clip.get("duration")
                files.append(download_asset("video", f"{index:02}_实况", media_urls(clip.get("play_addr")), staging,
                                            post["headers"], index, duration / 1000 if duration else None))
        if post["audio_urls"]:
            log("保存原声…")
            files.append(download_asset("audio", "原声", post["audio_urls"], staging, post["headers"]))
        manifest = {"id": post["id"], "title": post["title"], "author": post["author"],
                    "type": "live_photo_album" if any(item["type"] == "video" for item in files) else "image_album",
                    "source_url": post["source_url"], "audio_title": post.get("audio_title"),
                    "downloaded_at": datetime.now(timezone.utc).isoformat(), "files": files,
                    "image_count": len(post["images"]), "media_unchanged": True}
        (staging / "作品信息.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if destination.exists():
            raise DownloadError("输出目录已存在，请检查其他下载任务。")
        staging.rename(destination)
    return destination, manifest
