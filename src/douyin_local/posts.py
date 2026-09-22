"""统一解析公开视频、图文与实况图文，不保存会话与临时签名。"""
import html
import json
import re
import time
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, build_opener
from urllib.error import URLError

from playwright.sync_api import Error as BrowserError, sync_playwright

from . import DownloadError
from .links import DouyinRedirect, USER_AGENT, check_url


def extract_urls(text):
    found = []
    for match in re.finditer(r"https?://[^\s<>\[\]（）()，。；！、\"'\u200b]+", html.unescape(text).replace("\\_", "_")):
        url = match.group(0).rstrip(".,;!?")
        try:
            check_url(url)
        except DownloadError:
            continue
        if url not in found:
            found.append(url)
    if not found:
        raise DownloadError("没有找到抖音链接，请粘贴链接或完整分享文案。")
    return found


def identify(url):
    check_url(url)
    parts = urlsplit(url)
    match = re.fullmatch(r"/(?:share/)?(video|note|slides)/(\d{10,25})/?", parts.path)
    if match:
        return match.group(2), "video" if match.group(1) == "video" else "note"
    for key in ("modal_id", "aweme_id"):
        value = parse_qs(parts.query).get(key, [""])[0]
        if re.fullmatch(r"\d{10,25}", value):
            return value, "video"
    return None


def resolve_post_url(url, timeout=20):
    direct = identify(url)
    if direct:
        return direct
    if urlsplit(url).hostname != "v.douyin.com":
        raise DownloadError("请提供单篇作品链接，当前不支持主页和直播。")
    try:
        with build_opener(DouyinRedirect()).open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout) as response:
            target = identify(response.url)
    except (URLError, OSError) as exc:
        raise DownloadError("无法访问短链。下载新的抖音内容需要联网；离线时请使用本地素材功能。") from exc
    if not target:
        raise DownloadError("短链未指向可识别的作品，请重新复制链接。")
    return target


def find_target(value, post_id):
    if isinstance(value, dict):
        identity = value.get("aweme_id") or value.get("awemeId")
        if str(identity) == post_id and (isinstance(value.get("video"), dict) or isinstance(value.get("images"), list)):
            return value
        for child in value.values():
            result = find_target(child, post_id)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in value:
            result = find_target(child, post_id)
            if result is not None:
                return result
    return None


def parse_flight(document, post_id):
    # 解码公开页面中序列化的 JSON，绝不执行提取出的 JavaScript。
    decoder = json.JSONDecoder()
    for match in re.finditer(r"(?:self|window)\.__pace_f\.push\(", document):
        try:
            outer = decoder.raw_decode(document[match.end():])[0]
            if not isinstance(outer, list) or len(outer) < 2 or not isinstance(outer[1], str):
                continue
            chunk = outer[1]
            if chunk.startswith("%7B"):
                payload = json.loads(unquote(chunk))
            else:
                prefix = re.match(r"[0-9a-f]+:", chunk)
                if not prefix:
                    continue
                payload = decoder.raw_decode(chunk[prefix.end():])[0]
            result = find_target(payload, post_id)
            if result is not None:
                return result
        except (ValueError, TypeError, RecursionError):
            continue
    return None


def media_urls(value):
    if isinstance(value, str):
        return [value] if urlsplit(value).scheme in {"http", "https"} else []
    if isinstance(value, list):
        urls = [url for child in value for url in media_urls(child)]
        return list(dict.fromkeys(urls))
    if isinstance(value, dict):
        return media_urls(value.get("url_list") or value.get("urlList") or value.get("src") or [])
    return []


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def normalize_video(video):
    video = video or {}
    if "play_addr" in video:
        return video

    def address(key, size_key):
        return {"url_list": media_urls(video.get(key)), "data_size": number(video.get(size_key)),
                "width": number(video.get("width")), "height": number(video.get("height"))}

    result = {"width": number(video.get("width")), "height": number(video.get("height")),
              "duration": number(video.get("duration")), "play_addr": address("playAddr", "playAddrSize"),
              "play_addr_h264": address("playAddr", "playAddrSize"),
              "play_addr_265": address("playAddrH265", "playAddrH265Size")}
    return result


def normalize_post(item, post_id):
    if str(item.get("aweme_id") or item.get("awemeId")) != post_id:
        raise DownloadError("作品 ID 不一致，停止处理。")
    images = []
    for index, source in enumerate(item.get("images") or [], 1):
        clip = normalize_video(source.get("video"))
        images.append({"index": index, "urls": media_urls(source), "width": number(source.get("width")),
                       "height": number(source.get("height")),
                       "video": clip if media_urls(clip.get("play_addr")) else None})
    author = item.get("author") or item.get("authorInfo") or {}
    music = item.get("music") or {}
    kind = "album" if images else "video"
    return {"id": post_id, "title": item.get("desc") or post_id, "author": author.get("nickname"),
            "kind": kind, "images": images, "video": normalize_video(item.get("video")),
            "audio_urls": media_urls(music.get("play_url") or music.get("playUrl")),
            "audio_title": music.get("title"), "source_url": f"https://www.douyin.com/{'note' if images else 'video'}/{post_id}"}


def launch_browser(playwright, channel="auto"):
    for choice in (["msedge", "chrome", "chromium"] if channel == "auto" else [channel]):
        try:
            return playwright.chromium.launch(headless=True, **({} if choice == "chromium" else {"channel": choice}))
        except BrowserError:
            continue
    raise DownloadError("未找到可启动的 Edge/Chrome。请使用本机已安装的浏览器；离线合成不需要浏览器。")


def read_post(post_id, route="video", timeout=45, channel="auto"):
    with sync_playwright() as playwright:
        browser = launch_browser(playwright, channel)
        try:
            page = browser.new_page(locale="zh-CN", viewport={"width": 1280, "height": 900})
            found = []

            def on_response(response):
                parts = urlsplit(response.url)
                if (parts.hostname or "").endswith(".douyin.com") and parts.path.rstrip("/") == "/aweme/v1/web/aweme/detail" and response.status == 200:
                    try:
                        target = find_target(response.json(), post_id)
                        if target is not None:
                            found.append(target)
                    except (ValueError, BrowserError):
                        pass

            page.on("response", on_response)
            deadline = time.monotonic() + timeout
            try:
                page.goto(f"https://www.douyin.com/{route}/{post_id}", wait_until="domcontentloaded", timeout=timeout * 1000)
            except BrowserError:
                pass
            item = found[0] if found else None
            while item is None and time.monotonic() < deadline:
                item = found[0] if found else parse_flight(page.content(), post_id)
                if item is None:
                    page.wait_for_timeout(500)
            if item is None:
                raise DownloadError("未取得作品数据。请检查网络和原链接；站点可能要求登录/验证码，或作品已不可用。")
            post = normalize_post(item, post_id)
            post["headers"] = {"User-Agent": page.evaluate("navigator.userAgent"), "Referer": "https://www.douyin.com/"}
            return post
        except BrowserError as exc:
            raise DownloadError("浏览器解析失败，请检查网络后重试。") from exc
        finally:
            browser.close()
