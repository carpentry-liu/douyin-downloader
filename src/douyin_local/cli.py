import argparse
import json
from pathlib import Path
import sys

from . import DownloadError
from .download import create_download_folder, save_video
from .links import extract_url, resolve_id
from .resolver import resolve_info


def main(argv=None):
    parser = argparse.ArgumentParser(description="抖音视频下载到本地：支持完整分享文案、短链和视频长链。")
    parser.add_argument("text", nargs="?", help="链接或分享文案；省略时进入粘贴模式")
    parser.add_argument("-o", "--output", type=Path, default=Path("downloads"), help="输出目录，默认 ./downloads")
    parser.add_argument("--engine", choices=["auto", "browser", "yt-dlp"], default="auto")
    parser.add_argument("--browser", choices=["auto", "msedge", "chrome", "chromium"], default="auto")
    parser.add_argument("--timeout", type=int, default=45, help="浏览器解析超时秒数，默认 45")
    parser.add_argument("--info", action="store_true", help="只查看作品信息，不下载")
    args = parser.parse_args(argv)
    if args.timeout < 1 or args.timeout > 300:
        parser.error("--timeout 应在 1 到 300 秒之间")
    try:
        text = args.text
        if text is None:
            print("粘贴抖音分享文案（可以多行），再输入一个空行开始：", flush=True)
            lines = []
            while True:
                line = input()
                if not line.strip():
                    break
                lines.append(line)
            text = "\n".join(lines)
        url = extract_url(text)
        print("正在识别视频链接…", flush=True)
        video_id = resolve_id(url, min(args.timeout, 20))
        output = args.output.resolve()
        info, engine = resolve_info(video_id, args.engine, args.timeout, args.browser,
                                    log=lambda text: print(text, flush=True))
        print(f"作者：{info.get('uploader') or '未知'}\n作品：{info['title']}", flush=True)
        if args.info:
            print(json.dumps({"id": video_id, "title": info["title"], "author": info.get("uploader"),
                              "duration_seconds": info.get("duration"), "engine": engine}, ensure_ascii=False, indent=2))
            return 0
        folder = create_download_folder(output, info.get("uploader"))
        print(f"本次保存目录：{folder}", flush=True)
        path, record = save_video(info, folder, engine, log=lambda text: print(text, flush=True))
        print(f"下载完成：{path}\n{record['width']}×{record['height']} · {record['duration_seconds']:.2f} 秒 · {record['bytes'] / 1024 / 1024:.2f} MiB\n完整解码校验通过。")
        return 0
    except (DownloadError, OSError, EOFError) as exc:
        message = str(exc) if isinstance(exc, DownloadError) else "读取输入或本地文件失败，请检查路径、权限和磁盘空间。"
        print(f"未完成：{message}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130
