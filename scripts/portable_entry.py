"""PyInstaller 窗口入口，同时提供可记录结果的验收命令。"""
import argparse
import json
import logging
import os
from pathlib import Path
import sys


def main():
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="本地素材助手：抖音 / 小红书读取下载，离线合成与校验")
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--self-test", action="store_true")
    commands.add_argument("--download", metavar="SHARE_TEXT")
    commands.add_argument("--read", metavar="SHARE_TEXT", help="只读取小红书笔记正文或主页列表，不下载媒体")
    commands.add_argument("--compose", metavar="FOLDER")
    commands.add_argument("--verify", metavar="MP4")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--offline", action="store_true", help="阻断本进程的网络连接，用于离线验收")
    parser.add_argument("--originals-only", action="store_true")
    parser.add_argument("--profile-limit", type=int, default=20, help="小红书主页最多读取篇数，1–200，默认 20")
    args = parser.parse_args()
    if not 1 <= args.profile_limit <= 200:
        parser.error('--profile-limit 应在 1 到 200 之间')
    from douyin_local import DownloadError
    from douyin_local.service import default_output, download_text
    from douyin_local.selftest import block_network, offline_selftest
    from contextlib import nullcontext
    output = args.output or default_output()
    log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DouyinLocal"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(log_dir / "app.log"), encoding="utf-8", level=logging.ERROR)
    result = None
    try:
        if args.offline and (args.download or args.read):
            raise DownloadError("离线模式不能读取或下载新内容。请联网后重试，或选择本地素材合成/校验。")
        with block_network() if args.offline else nullcontext():
            if args.self_test:
                result = offline_selftest()
            elif args.download or args.read:
                results = download_text(args.download or args.read, output, not args.originals_only,
                                        profile_limit=args.profile_limit, read_only=bool(args.read))
                result = {"success": all(item["success"] for item in results), "results": results}
            elif args.compose:
                from douyin_local.compose import compose_album
                path, record = compose_album(args.compose, output)
                result = {"success": True, "path": str(path), "record": record}
            elif args.verify:
                from douyin_local.download import validate_video
                result = {"success": True, "record": validate_video(Path(args.verify))}
            else:
                from douyin_local.desktop import main as gui_main
                gui_main(output, offline=args.offline)
                return 0
    except Exception as exc:
        logging.error("Operation failed: %s", type(exc).__name__)
        result = {"success": False, "error": str(exc) if isinstance(exc, DownloadError) else f"处理失败：{type(exc).__name__}"}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
