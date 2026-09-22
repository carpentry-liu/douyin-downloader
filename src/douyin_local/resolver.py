"""平台适配：直接提取，或让独立浏览器正常加载作品页面。"""
import time
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtdlpError
from playwright.sync_api import sync_playwright, Error as BrowserError

from . import DownloadError


class QuietLogger:
    # 上游错误可能含媒体签名 URL，CLI 只输出自己的归纳信息。
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def canonical_url(video_id):
    return f"https://www.douyin.com/video/{video_id}"


def find_item(data, video_id):
    if isinstance(data, dict):
        if str(data.get("aweme_id")) == video_id and isinstance(data.get("video"), dict):
            return data
        for value in data.values():
            found = find_item(value, video_id)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = find_item(value, video_id)
            if found:
                return found
    return None


def item_to_info(item, video_id):
    if str(item.get("aweme_id")) != video_id:
        raise DownloadError("解析出的作品 ID 不一致，已停止下载。")
    if item.get("images"):
        raise DownloadError("该作品是图集，当前版本只下载视频。")
    video = item.get("video") or {}
    formats, seen = [], set()

    def add(address, label, codec, bitrate=None, fps=None):
        if not isinstance(address, dict):
            return
        for index, url in enumerate(address.get("url_list") or []):
            if not isinstance(url, str) or url in seen or urlsplit(url).scheme not in {"http", "https"}:
                continue
            seen.add(url)
            formats.append({
                "format_id": f"{label}-{index}", "url": url, "ext": "mp4", "protocol": "https" if url.startswith("https:") else "http",
                "width": address.get("width"), "height": address.get("height"),
                "filesize": address.get("data_size") or None, "vcodec": codec,
                "tbr": bitrate / 1000 if bitrate else None, "fps": fps,
                "source_preference": -index,
            })

    # 先读取详细档位，防止基本 play_addr 去重后丢失码率/编码信息。
    for index, rate in enumerate(video.get("bit_rate") or []):
        if isinstance(rate, dict):
            codec = "h265" if rate.get("is_h265") or rate.get("is_bytevc1") else "h264"
            add(rate.get("play_addr"), f"rate-{index}", codec, rate.get("bit_rate"), rate.get("FPS"))
    add(video.get("play_addr_h264"), "h264", "h264")
    add(video.get("play_addr"), "play", "h265" if video.get("is_h265") else "h264")
    add(video.get("play_addr_265"), "h265", "h265")
    if not formats:
        raise DownloadError("作品数据没有可用播放地址，可能已下架或需要登录。")
    return {
        "id": video_id, "title": item.get("desc") or video_id,
        "description": item.get("desc"), "uploader": (item.get("author") or {}).get("nickname"),
        "duration": video["duration"] / 1000 if video.get("duration") else None,
        "timestamp": item.get("create_time"), "formats": formats,
        "webpage_url": canonical_url(video_id), "extractor": "douyin-local",
    }


def direct_info(video_id, timeout):
    try:
        with YoutubeDL({"quiet": True, "logger": QuietLogger(), "noplaylist": True,
                        "socket_timeout": timeout, "extractor_retries": 0}) as ydl:
            info = ydl.extract_info(canonical_url(video_id), download=False)
    except YtdlpError as exc:
        raise DownloadError("yt-dlp 直接解析未取得作品数据，站点可能需要新鲜 Cookie。") from exc
    if not info or str(info.get("id")) != video_id:
        raise DownloadError("yt-dlp 未返回匹配的作品。")
    return info


def browser_info(video_id, timeout, channel="auto"):
    with sync_playwright() as playwright:
        browser = None
        for choice in (["msedge", "chrome", "chromium"] if channel == "auto" else [channel]):
            try:
                options = {} if choice == "chromium" else {"channel": choice}
                browser = playwright.chromium.launch(headless=True, **options)
                break
            except BrowserError:
                continue
        if browser is None:
            raise DownloadError("无法启动浏览器。安装 Edge/Chrome，或运行 .venv\\Scripts\\python.exe -m playwright install chromium。")
        try:
            context = browser.new_context(locale="zh-CN", viewport={"width": 1280, "height": 900})
            page = context.new_page()
            found = []

            def on_response(response):
                parts = urlsplit(response.url)
                # 不使用页面中任意 video 标签：其中可能是占位片、广告、推荐视频。
                if (parts.hostname == "douyin.com" or (parts.hostname or "").endswith(".douyin.com")) and parts.path.rstrip("/") == "/aweme/v1/web/aweme/detail":
                    if response.status == 200:
                        try:
                            item = find_item(response.json(), video_id)
                            if item:
                                found.append(item)
                        except (ValueError, BrowserError):
                            pass

            page.on("response", on_response)
            deadline = time.monotonic() + timeout
            try:
                page.goto(canonical_url(video_id), wait_until="domcontentloaded", timeout=timeout * 1000)
            except BrowserError:
                # 导航超时仍可能已经取得目标详情响应。
                pass
            while not found and time.monotonic() < deadline:
                page.wait_for_timeout(250)
            if not found:
                raise DownloadError("浏览器未取得该视频数据。可能遇到登录/验证码、作品不可用或网络限制；可在 Edge 打开原链接确认后重试。")
            info = item_to_info(found[0], video_id)
            info["http_headers"] = {
                "User-Agent": page.evaluate("navigator.userAgent"),
                "Referer": "https://www.douyin.com/",
            }
            return info
        except BrowserError as exc:
            raise DownloadError("浏览器加载失败或被关闭，请重试。") from exc
        finally:
            browser.close()


def resolve_info(video_id, engine="auto", timeout=45, channel="auto", log=print):
    if engine in {"auto", "yt-dlp"}:
        log("正在尝试 yt-dlp 解析…")
        try:
            return direct_info(video_id, min(timeout, 15)), "yt-dlp"
        except DownloadError:
            if engine == "yt-dlp":
                raise
            log("直接解析不可用，正在通过独立浏览器加载视频…")
    else:
        log("正在通过独立浏览器加载视频…")
    return browser_info(video_id, timeout, channel), "browser"
