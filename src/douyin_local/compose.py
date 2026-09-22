"""仅使用本地素材合成图文/实况播放版，不访问网络。"""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave

import imageio_ffmpeg

from . import DownloadError
from .albums import load_album, local_file
from .download import safe_name, sha256, validate_video


def run_ffmpeg(args, timeout=300):
    try:
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-nostdin", *args],
                                capture_output=True, timeout=timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DownloadError("媒体处理未完成，可能是磁盘空间不足或处理超时。") from exc
    if result.returncode:
        raise DownloadError("FFmpeg 处理失败，请检查素材文件与输出磁盘空间。")


def item_index(item, fallback):
    if isinstance(item.get("index"), int):
        return item["index"]
    match = re.match(r"(\d+)", item["file"])
    return int(match.group(1)) if match else fallback


def compose_album(folder, output, log=print):
    folder = Path(folder).resolve()
    album = load_album(folder)
    images = [item for item in album["files"] if item["type"] == "image"]
    videos = {item_index(item, index): item for index, item in enumerate(album["files"], 1) if item["type"] == "video"}
    audio_item = next((item for item in album["files"] if item["type"] == "audio"), None)
    if not images:
        raise DownloadError("素材目录没有可用于播放的图片。")
    ordered = [videos.get(item_index(item, index), item) for index, item in enumerate(images, 1)]
    try:
        width = math.ceil(max(item["width"] for item in ordered) / 2) * 2
        height = math.ceil(max(item["height"] for item in ordered) / 2) * 2
        if not (0 < width <= 8192 and 0 < height <= 8192):
            raise ValueError("unsupported dimensions")
    except (KeyError, TypeError, ValueError) as exc:
        raise DownloadError("素材分辨率缺失或超出当前支持范围。") from exc
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{album['id']}_{safe_name(album.get('author'), 20)}_完整播放版.mp4"
    record_path = destination.with_suffix(".json")
    # 内容指纹避免把同 ID 但已更换素材的旧合成当作新结果。
    fingerprint = hashlib.sha256(json.dumps([(item["file"], item["sha256"]) for item in album["files"]], ensure_ascii=False).encode()).hexdigest()
    if destination.exists() or record_path.exists():
        try:
            existing = json.loads(record_path.read_text(encoding="utf-8"))
            if existing.get("source_fingerprint") == fingerprint and existing.get("composition_version") == 1 and sha256(destination) == existing.get("sha256"):
                log("已有播放版校验通过，直接使用。")
                return destination, existing
        except (OSError, ValueError):
            pass
        raise DownloadError("同名播放版已存在且不匹配，请选择另一个输出目录，避免覆盖。")
    with tempfile.TemporaryDirectory(prefix=f".{album['id']}-compose-", dir=output) as temp:
        staging = Path(temp)
        audio_duration = None
        local_audio = None
        if audio_item:
            local_audio = staging / ("audio" + Path(audio_item["file"]).suffix)
            shutil.copyfile(local_file(folder, audio_item["file"]), local_audio)
            decoded = staging / "audio.wav"
            run_ffmpeg(["-i", str(local_audio), "-map", "0:a:0", "-c:a", "pcm_s16le", str(decoded)])
            with wave.open(str(decoded), "rb") as source:
                audio_duration = source.getnframes() / source.getframerate()
            if audio_duration <= 0:
                raise DownloadError("原声音频没有有效时长。")
        fps = 30
        frames = math.ceil((audio_duration or len(ordered) * 5) * fps / len(ordered))
        slot = frames / fps
        duration = slot * len(ordered)
        segments = []
        for index, item in enumerate(ordered, 1):
            log(f"离线合成 {index}/{len(ordered)}：{'实况视频' if item['type'] == 'video' else '图片'}…")
            source = staging / (f"input-{index}" + Path(item["file"]).suffix)
            shutil.copyfile(local_file(folder, item["file"]), source)
            segment = staging / f"segment-{index}.mp4"
            args = ["-stream_loop", "-1"] if item["type"] == "video" else ["-loop", "1", "-framerate", str(fps)]
            args += ["-i", str(source), "-map", "0:v:0", "-an", "-vf",
                     f"fps={fps},pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p",
                     "-frames:v", str(frames), "-c:v", "libx264", "-preset", "fast", "-crf", "18", str(segment)]
            run_ffmpeg(args, max(300, slot * 10))
            segments.append(segment)
        listing = staging / "segments.ffconcat"
        # 仅引用同一临时目录的内部 ASCII 文件名，兼容用户路径中的引号。
        listing.write_text("ffconcat version 1.0\n" + "".join(f"file '{segment.name}'\n" for segment in segments), encoding="utf-8")
        temporary = staging / "complete.mp4"
        args = ["-f", "concat", "-safe", "1", "-i", str(listing)]
        if local_audio:
            args += ["-i", str(local_audio), "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-af", "apad"]
        else:
            args += ["-map", "0:v:0", "-an"]
        args += ["-c:v", "copy", "-t", str(duration), "-movflags", "+faststart", str(temporary)]
        run_ffmpeg(args, max(300, duration * 4))
        log("正在完整解码校验播放版…")
        verification = validate_video(temporary, expected_duration=duration)
        record = {"id": album["id"], "title": album.get("title"), "author": album.get("author"),
                  "file": destination.name, "type": "live_photo_compilation" if videos else "image_album_slideshow",
                  "locally_generated": True, "composition_version": 1, "source_fingerprint": fingerprint,
                  "image_count": len(images), "clip_count": len(videos), "media_order": [item["file"] for item in ordered],
                  "seconds_per_item": slot, "full_background_audio_used": bool(local_audio),
                  "background_audio_duration_seconds": audio_duration, "source_url": album.get("source_url"),
                  "created_at": datetime.now(timezone.utc).isoformat(), **verification}
        temp_record = staging / "record.json"
        temp_record.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if destination.exists() or record_path.exists():
            raise DownloadError("其他操作已创建同名文件，请检查输出目录。")
        # Windows rename 对已存在的目标报错，支持 NTFS/exFAT，不依赖硬链接。
        temporary.rename(destination)
        temp_record.rename(record_path)
    return destination, record
