"""成熟下载引擎、真实媒体校验和本地完成记录。"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone

import imageio_ffmpeg
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtdlpError

from . import DownloadError
from .resolver import QuietLogger, canonical_url


def safe_name(value, limit=48):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value or "")
    value = re.sub(r"\s+", " ", value).strip(" .")[:limit].rstrip(" .")
    if not value:
        return "video"
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", value):
        value = "_" + value
    return value


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate_video(path, expected_size=None, expected_duration=None):
    if not path.is_file() or path.stat().st_size < 1024:
        raise DownloadError("下载文件为空或过小，没有完成。")
    with path.open("rb") as source:
        if source.read(12)[4:8] != b"ftyp":
            raise DownloadError("下载内容不是 MP4，可能是站点错误页面。")
    if expected_size and path.stat().st_size != expected_size:
        raise DownloadError("下载大小与媒体信息不一致，文件可能不完整。")
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-xerror", "-i", str(path),
               "-map", "0:v:0", "-map", "0:a?", "-f", "null", "-"]
    try:
        decoded = subprocess.run(command, capture_output=True, timeout=max(60, (expected_duration or 120) * 3),
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DownloadError("视频完整解码校验未完成。") from exc
    if decoded.returncode:
        raise DownloadError("视频完整解码失败，文件没有标记为完成。")
    # 先排除损坏文件，避免上游元信息生成器在打开坏文件时泄漏管道句柄。
    reader = imageio_ffmpeg.read_frames(str(path))
    try:
        metadata = next(reader)
    except (OSError, RuntimeError, StopIteration) as exc:
        raise DownloadError("FFmpeg 无法读取该视频。") from exc
    finally:
        reader.close()
    duration = metadata.get("duration")
    if not duration or duration <= 0:
        raise DownloadError("视频没有有效时长。")
    if expected_duration and abs(duration - expected_duration) > max(1.0, expected_duration * 0.02):
        raise DownloadError("视频时长与目标作品不一致，可能只下载了预览片。")
    width, height = metadata["source_size"]
    return {"duration_seconds": duration, "width": width, "height": height,
            "video_codec": metadata.get("codec"), "audio_codec": metadata.get("audio_codec"),
            "fps": metadata.get("fps"), "bytes": path.stat().st_size,
            "sha256": sha256(path), "full_decode_verified": True}


def find_existing(output, video_id):
    output = Path(output).resolve()
    for record in output.glob(f"{video_id}_*.json"):
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
            name = data["file"]
            if not isinstance(name, str) or Path(name).name != name:
                continue
            path = output / name
            if data.get("id") == video_id and path.is_file() and path.stat().st_size == data["bytes"] and sha256(path) == data["sha256"] and data.get("full_decode_verified") is True:
                return path, data
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def save_video(info, output, engine, log=print):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    video_id = info["id"]
    filename = f"{video_id}_{safe_name(info.get('uploader'), 20)}.mp4"
    destination = output / filename
    if destination.exists() or destination.with_suffix(".json").exists():
        raise DownloadError("目标文件已存在但没有匹配的有效完成记录。为避免覆盖，请换一个输出目录或移走旧文件。")

    last_percent = [-10]

    def progress(data):
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        if data.get("status") == "downloading" and total:
            percent = int(data.get("downloaded_bytes", 0) * 100 / total)
            if percent >= last_percent[0] + 10:
                last_percent[0] = percent
                log(f"下载进度：{min(percent, 100)}%")

    # 暂存目录与目标同卷；失败不留下看似完成的 MP4。
    with tempfile.TemporaryDirectory(prefix=f".{video_id}-", dir=output) as staging:
        temporary = Path(staging) / "video.mp4"
        options = {"outtmpl": str(temporary), "format": "best[vcodec^=h264]/best",
                   "format_sort": ["res", "tbr"], "quiet": True, "no_warnings": True,
                   "logger": QuietLogger(), "progress_hooks": [progress],
                   "socket_timeout": 25, "retries": 3, "continuedl": True,
                   "noplaylist": True, "overwrites": False}
        try:
            with YoutubeDL(options) as ydl:
                downloaded = ydl.process_ie_result(dict(info), download=True)
        except YtdlpError as exc:
            raise DownloadError("媒体下载失败，地址可能过期或网络异常。重新运行可重新解析。") from exc
        log("正在检查 MP4 格式、大小、时长和完整解码…")
        verification = validate_video(temporary, downloaded.get("filesize"), info.get("duration"))
        record = {"id": video_id, "title": info.get("title"), "author": info.get("uploader"),
                  "source_url": canonical_url(video_id), "engine": engine,
                  "downloaded_at": datetime.now(timezone.utc).isoformat(), "file": filename,
                  "format_id": downloaded.get("format_id"), **verification}
        record_path = Path(staging) / "record.json"
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Windows rename 不覆盖目标，兼容 NTFS/exFAT；其他系统保留硬链接发布。
        try:
            if os.name == "nt":
                temporary.rename(destination)
                record_path.rename(destination.with_suffix(".json"))
            else:
                os.link(temporary, destination)
                os.link(record_path, destination.with_suffix(".json"))
        except FileExistsError as exc:
            raise DownloadError("另一个下载已创建同名文件，已停止发布，请检查输出目录。") from exc
    return destination, record
