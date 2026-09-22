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
    parser = argparse.ArgumentParser(description="抖音素材助手：联网下载，离线合成与校验")
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--self-test", action="store_true")
    commands.add_argument("--download", metavar="SHARE_TEXT")
    commands.add_argument("--compose", metavar="FOLDER")
    commands.add_argument("--verify", metavar="MP4")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--offline", action="store_true", help="阻断本进程的网络连接，用于离线验收")
    parser.add_argument("--originals-only", action="store_true")
    args = parser.parse_args()
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
        if args.offline and args.download:
            raise DownloadError("离线模式不能下载新作品。请联网后下载，或选择本地素材合成/校验。")
        with block_network() if args.offline else nullcontext():
            if args.self_test:
                result = offline_selftest()
            elif args.download:
                results = download_text(args.download, output, not args.originals_only)
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
