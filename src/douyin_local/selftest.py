"""发行包的离线自检，不修改系统网络设置。"""
from contextlib import contextmanager
import ipaddress
from pathlib import Path
import socket
import sys
import tempfile

import imageio_ffmpeg

from .compose import run_ffmpeg
from .download import validate_video


@contextmanager
def block_network():
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_create_connection = socket.create_connection

    def denied(*args, **kwargs):
        raise OSError("Offline test: network disabled for this process")

    def is_local(host):
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return host == "localhost"

    def connect(sock, address):
        # Windows asyncio 使用 loopback socketpair 唤醒事件循环。
        if isinstance(address, tuple) and is_local(address[0]):
            return original_connect(sock, address)
        return denied()

    def connect_ex(sock, address):
        if isinstance(address, tuple) and is_local(address[0]):
            return original_connect_ex(sock, address)
        return denied()

    def getaddrinfo(host, *args, **kwargs):
        if is_local(host):
            return original_getaddrinfo(host, *args, **kwargs)
        return denied()

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo
    # HTTP 可能借助 127.0.0.1 代理出网；socketpair 不使用此函数。
    socket.create_connection = denied
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.socket.connect_ex = original_connect_ex
        socket.getaddrinfo = original_getaddrinfo
        socket.create_connection = original_create_connection


def offline_selftest():
    with block_network():
        import tkinter as tk
        from .desktop import Desktop
        root = tk.Tk()
        root.withdraw()
        app = Desktop(root, offline=True)
        root.update()
        app.close()
        with tempfile.TemporaryDirectory(prefix="douyin-offline-check-") as temp:
            target = Path(temp) / "check.mp4"
            run_ffmpeg(["-f", "lavfi", "-i", "color=c=blue:s=160x120:r=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                        "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(target)])
            media = validate_video(target, expected_duration=1)
        from playwright.sync_api import sync_playwright
        from .posts import launch_browser
        browser_ok = False
        with sync_playwright() as playwright:
            try:
                browser = launch_browser(playwright)
            except Exception:
                browser = None
            if browser:
                context = browser.new_context(offline=True)
                page = context.new_page()
                page.set_content("<title>Offline browser check</title><p>local</p>")
                browser_ok = page.title() == "Offline browser check"
                browser.close()
    return {"success": True, "frozen": bool(getattr(sys, "frozen", False)), "python": sys.version.split()[0],
            "python_external_network_blocked": True, "tk_started": True, "ffmpeg_decode": media["full_decode_verified"],
            "ffmpeg_path": imageio_ffmpeg.get_ffmpeg_exe(), "browser_started_offline": browser_ok,
            "note": "Blocks external Python sockets (allows local IPC) and uses an offline browser context; does not disconnect the computer."}
