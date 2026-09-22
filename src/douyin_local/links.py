"""分享文案和受支持的抖音作品 URL。"""
import html
import re
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.error import URLError

from . import DownloadError

HOSTS = {"douyin.com", "www.douyin.com", "v.douyin.com", "iesdouyin.com", "www.iesdouyin.com"}
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"


def check_url(url):
    try:
        parts = urlsplit(url)
        valid = (parts.scheme in {"https", "http"} and parts.hostname in HOSTS
                 and not parts.username and not parts.password
                 and parts.port in {None, 80, 443})
    except ValueError:
        valid = False
    if not valid:
        raise DownloadError("请提供 douyin.com 或 iesdouyin.com 的视频分享链接。")
    return url


def extract_url(text):
    for match in re.finditer(r"https?://[^\s<>\[\]（）()，。；！、\"'\u200b]+", html.unescape(text)):
        url = match.group(0).rstrip(".,;!?")
        try:
            return check_url(url)
        except DownloadError:
            continue
    raise DownloadError("没有找到抖音链接，请粘贴链接或完整分享文案。")


def video_id_from_url(url):
    check_url(url)
    parts = urlsplit(url)
    match = re.fullmatch(r"/(?:share/)?video/(\d{10,25})/?", parts.path)
    if match:
        return match.group(1)
    for key in ("modal_id", "aweme_id"):
        value = parse_qs(parts.query).get(key, [""])[0]
        if re.fullmatch(r"\d{10,25}", value):
            return value
    return None


class DouyinRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def resolve_id(url, timeout=20):
    direct = video_id_from_url(url)
    if direct:
        return direct
    if urlsplit(url).hostname != "v.douyin.com":
        raise DownloadError("该链接不是单条视频；当前不支持主页、图集或直播。")
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with build_opener(DouyinRedirect()).open(request, timeout=timeout) as response:
            video_id = video_id_from_url(response.url)
    except (URLError, OSError) as exc:
        raise DownloadError("短链访问失败，请检查网络，或从抖音重新复制视频链接。") from exc
    if not video_id:
        raise DownloadError("短链没有跳转到单条视频，可能已失效或是其他内容类型。")
    return video_id
