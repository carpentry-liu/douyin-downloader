"""抖音作品本地下载与离线媒体处理。"""

class DownloadError(Exception):
    """可直接展示的操作错误，不含会话或签名。"""
