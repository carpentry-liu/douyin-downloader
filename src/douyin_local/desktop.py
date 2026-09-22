"""桌面任务控制器：单工作线程，所有控件更新回到 Tk 主线程。"""
from datetime import datetime
import logging
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from . import DownloadError
from . import desktop_view as view
from .compose import compose_album
from .download import validate_video
from .posts import extract_urls
from .service import default_output, download_text


class Desktop:
    def __init__(self, root, output=None, offline=False):
        self.root = root
        self.offline = offline
        self.events = queue.Queue(maxsize=1000)
        self.busy = False
        self.controls = []
        self.count_timer = None
        self.output = tk.StringVar(value=str(Path(output or default_output()).resolve()))
        self.folder = tk.StringVar()
        self.make_video = tk.BooleanVar(value=True)
        root.title("抖音素材助手 · 本地工作台")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self.callback_error
        view.build(self)
        self.show_page("local" if offline else "download")
        self.set_controls(False)
        self.append("就绪。选择下载作品，或使用已有素材。")
        if offline:
            self.append("当前为离线模式，新作品下载已关闭。")
        root.bind("<Control-Return>", self.shortcut)
        self.poll_timer = root.after(100, self.poll)

    def show_page(self, page):
        self.page = page
        self.pages[page].tkraise()
        for key, item in self.nav.items():
            item.configure(bg=view.PANEL if key == page else view.SIDE,
                           fg=view.ACCENT if key == page else view.MUTED)
        local = page == "local"
        self.heading.configure(text="让素材，再出发。" if local else "留住每一帧。")
        self.description.configure(text="用已有图片、实况和原声制作播放版，离线也能继续。" if local else
                                   "把分享链接变成自己的素材库。视频、图片、实况，一次保存。")

    def append(self, message, kind=None):
        self.log.configure(state="normal")
        self.log.insert("end", datetime.now().strftime("%H:%M") + "  ", "time")
        self.log.insert("end", str(message) + "\n\n", kind or "")
        if int(self.log.index("end-1c").split(".")[0]) > 600:
            self.log.delete("1.0", "200.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, state, title, detail):
        colors = {"working": view.AMBER, "success": view.ACCENT, "partial": view.AMBER, "error": view.RED}
        self.status_label.configure(text="●  " + title, fg=colors.get(state, view.ACCENT))
        self.status_detail.configure(text=detail)

    def set_controls(self, busy):
        for item in self.controls:
            item.configure(state="disabled" if busy else "normal")
        if self.offline:
            self.download_button.configure(state="disabled", text="离线模式 · 下载不可用")

    def poll(self):
        for _ in range(100):
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append(payload)
            else:
                self.busy = False
                self.progress.stop()
                self.set_controls(False)
                self.set_status(*payload)
                self.append(payload[1] + "。" + payload[2], "error" if payload[0] == "error" else "success")
        self.poll_timer = self.root.after(100, self.poll)

    def start(self, title, function):
        if self.busy:
            return
        self.busy = True
        self.set_controls(True)
        self.set_status("working", title, "处理完成后会自动校验。请保持窗口开启。")
        self.progress.start(14)

        def worker():
            try:
                result = function(lambda text: self.events.put(("log", text)))
            except Exception as exc:
                message = str(exc) if isinstance(exc, DownloadError) else "请检查素材、保存位置和磁盘空间后重试。"
                logging.error("Desktop operation failed: %s", type(exc).__name__)
                result = ("error", "未能完成", message)
            self.events.put(("done", result))

        threading.Thread(target=worker, name="media-worker", daemon=True).start()

    def download(self):
        if self.busy:
            return
        if self.offline:
            self.set_status("error", "当前处于离线模式", "下载新作品需要联网，请重新正常启动程序。")
            return
        text = self.input.get("1.0", "end").strip()
        try:
            extract_urls(text)
        except DownloadError as exc:
            self.set_status("error", "还没有可用链接", str(exc))
            self.input.focus_set()
            return
        output, make_video = self.output.get().strip(), self.make_video.get()
        if not self.check_output(output):
            return

        def job(log):
            results = download_text(text, output, make_video, log)
            good = sum(item["success"] for item in results)
            if good == len(results):
                return "success", "作品已保存", f"{good} 个作品处理完成，文件已校验。可打开保存目录查看。"
            return ("partial" if good else "error", "部分完成" if good else "下载未完成",
                    f"成功 {good} / {len(results)} 个作品，原因见运行日志。")

        self.start("正在保存作品", job)

    def compose(self):
        if self.busy:
            return
        folder, output = self.folder.get().strip(), self.output.get().strip()
        if not folder:
            self.set_status("error", "请选择素材目录", "目录内需要有作品信息.json 和完整原素材。")
            return
        if not self.check_output(output):
            return

        def job(log):
            path, record = compose_album(folder, output, log)
            log(f"已保存：{path}")
            return "success", "播放版已生成", f"{record['width']} × {record['height']} · {record['duration_seconds']:.2f} 秒\n本地合成，原素材保留。"

        self.start("正在合成播放版", job)

    def verify(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self.root, title="选择要校验的 MP4", filetypes=[("MP4 视频", "*.mp4")])
        if not path:
            return

        def job(log):
            record = validate_video(Path(path))
            log(f"完整解码通过：{path}\nSHA-256 {record['sha256']}")
            return "success", "视频校验通过", f"{record['width']} × {record['height']} · {record['duration_seconds']:.2f} 秒\n视频可以完整解码。"

        self.start("正在校验视频", job)

    def check_output(self, value):
        if not value:
            self.set_status("error", "请选择保存位置", "填写或选择一个本地目录后继续。")
            return False
        return True

    def choose_folder(self):
        if not self.busy:
            path = filedialog.askdirectory(parent=self.root, title="选择已下载的素材目录")
            if path:
                self.folder.set(path)

    def choose_output(self):
        if not self.busy:
            path = filedialog.askdirectory(parent=self.root, title="选择保存目录")
            if path:
                self.output.set(path)

    def open_output(self):
        value = self.output.get().strip()
        if not self.check_output(value):
            return
        try:
            path = Path(value).resolve()
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        except OSError:
            self.set_status("error", "无法打开目录", "请检查路径与访问权限。")

    def paste(self):
        if self.busy:
            return
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            self.set_status("error", "剪贴板没有文字", "请先复制作品链接或分享文案。")
            return
        self.input.insert("insert", text)
        self.input.focus_set()

    def clear(self):
        if not self.busy:
            self.input.delete("1.0", "end")
            self.input.focus_set()

    def input_changed(self, _event=None):
        if not self.input.edit_modified():
            return
        self.input.edit_modified(False)
        if self.count_timer:
            self.root.after_cancel(self.count_timer)
        self.count_timer = self.root.after(180, self.count_links)

    def count_links(self):
        self.count_timer = None
        try:
            count = len(extract_urls(self.input.get("1.0", "end")))
        except DownloadError:
            count = 0
        self.link_count.configure(text=f"{count} 条链接" if count else "等待链接")

    def shortcut(self, _event=None):
        if self.page == "download":
            self.download()
        return "break"

    def close(self):
        if self.busy:
            messagebox.showinfo("任务正在进行", "请等待当前任务结束后关闭窗口。", parent=self.root)
            return
        self.root.after_cancel(self.poll_timer)
        if self.count_timer:
            self.root.after_cancel(self.count_timer)
        self.root.destroy()

    def callback_error(self, kind, value, traceback):
        logging.error("Tk callback failed: %s", kind.__name__)
        self.append("界面操作未完成，请重试。", "error")


def main(output=None, offline=False):
    root = tk.Tk()
    Desktop(root, output, offline)
    root.mainloop()
