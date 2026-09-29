"""GUI/打包命令共用的任务入口。"""
from pathlib import Path
import sys

from .albums import save_album
from .compose import compose_album
from .download import create_download_folder, save_video
from .posts import read_post, resolve_post_url
from .resolver import item_to_info
from .sharing import extract_urls
from .xiaohongshu import is_xhs


def default_output():
    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    return base / "downloads"


def download_one(url, output, make_video=True, log=print, *, profile_limit=20, read_only=False):
    if is_xhs(url):
        from .xhs_service import process_xhs
        return process_xhs(url, output, make_video, log, profile_limit, read_only)
    if read_only:
        from . import DownloadError
        raise DownloadError('仅读取目前支持小红书主页和笔记；抖音请使用下载功能。')
    output = Path(output).resolve()
    log("正在识别作品链接（需要联网）…")
    post_id, route = resolve_post_url(url)
    log("通过独立浏览器读取作品…")
    post = read_post(post_id, route)
    log(f"作者：{post.get('author') or '未知'}\n作品：{post['title']}")
    folder = create_download_folder(output, post.get("author"))
    log(f"本次保存目录：{folder}")
    if post["kind"] == "video":
        info = item_to_info({"aweme_id": post_id, "desc": post["title"], "author": {"nickname": post["author"]}, "video": post["video"]}, post_id)
        info["http_headers"] = post["headers"]
        path, record = save_video(info, folder, "browser", log)
        return {"kind": "video", "path": str(path), "folder": str(folder), "record": record}
    folder, album = save_album(post, folder, log, in_place=True)
    log(f"原素材已保存：{folder}")
    if make_video:
        path, record = compose_album(folder, folder, log)
        log("图文/实况播放版由本地合成，原素材另存保留。")
        return {"kind": "album", "path": str(path), "folder": str(folder), "record": record}
    return {"kind": "album", "path": str(folder), "folder": str(folder), "record": album}


def download_text(text, output, make_video=True, log=print, *, profile_limit=20, read_only=False):
    urls = extract_urls(text)
    results = []
    for index, url in enumerate(urls, 1):
        log(f"处理 {index}/{len(urls)}")
        try:
            result = download_one(url, output, make_video, log, profile_limit=profile_limit, read_only=read_only)
            log(f"{'完成' if result.get('success', True) else '部分完成'}：{result['path']}")
            results.append({"success": True, **result})
        except Exception as exc:
            from . import DownloadError
            message = str(exc) if isinstance(exc, DownloadError) else "操作失败，请检查本地文件、磁盘空间或网络后重试。"
            log(f"未完成：{message}")
            results.append({"success": False, "error": message})
    return results
