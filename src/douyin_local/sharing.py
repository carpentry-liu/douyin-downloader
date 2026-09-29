"""双平台分享文案；平台解析器各自保留域名边界。"""
import html
import re

from . import DownloadError
from .links import check_url as check_douyin
from .xiaohongshu import check_url as check_xhs


def extract_urls(text):
    found = []
    for match in re.finditer(r"https?://[^\s<>\[\]（）()，。；！、\"'\u200b]+", html.unescape(text).replace("\\_", "_")):
        url = match.group(0).rstrip(".,;!?")
        for check in (check_douyin, check_xhs):
            try:
                check(url)
            except DownloadError:
                continue
            if url not in found:
                found.append(url)
            break
    if not found:
        raise DownloadError("没有找到抖音或小红书链接，请粘贴链接或完整分享文案。")
    return found
