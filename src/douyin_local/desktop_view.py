"""原生桌面视图；不包含下载或文件处理逻辑。"""
import tkinter as tk
from tkinter import scrolledtext, ttk

BG = "#14191d"
SIDE = "#0e1317"
PANEL = "#1b2228"
FIELD = "#11171c"
LINE = "#333e47"
TEXT = "#f3f2eb"
MUTED = "#b0bcc3"
ACCENT = "#a6e5bd"
INK = "#11261a"
AMBER = "#f0cd85"
RED = "#f3a5a3"
FONT = "Microsoft YaHei UI"


def label(parent, text="", size=10, color=TEXT, bold=False, **kwargs):
    return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                    font=(FONT, size, "bold" if bold else "normal"), anchor="w", **kwargs)


def button(parent, text, command, accent=False, **kwargs):
    padx = kwargs.pop("padx", 16)
    return tk.Button(parent, text=text, command=command, font=(FONT, 10, "bold"),
                     bg=ACCENT if accent else LINE, fg=INK if accent else TEXT,
                     activebackground="#c7f1d6" if accent else "#47555f",
                     activeforeground=INK if accent else TEXT, disabledforeground="#77858b",
                     relief="flat", borderwidth=0, padx=padx, pady=11, cursor="hand2",
                     highlightthickness=1, highlightbackground=parent.cget("bg"),
                     highlightcolor=ACCENT, **kwargs)


def entry(parent, variable):
    return tk.Entry(parent, textvariable=variable, font=(FONT, 10), bg=FIELD, fg=TEXT,
                    insertbackground=ACCENT, selectbackground=ACCENT, selectforeground=INK,
                    disabledbackground=FIELD, disabledforeground=MUTED, relief="flat",
                    highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT)


def card(parent, title, eyebrow):
    box = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=LINE, padx=22, pady=20)
    label(box, eyebrow, size=9, color=ACCENT).pack(anchor="w")
    label(box, title, size=16, bold=True).pack(anchor="w", pady=(7, 14))
    return box


def dark_scrollbar(widget):
    widget.vbar.pack_forget()
    bar = ttk.Scrollbar(widget.frame, orient="vertical", command=widget.yview, style="Studio.Vertical.TScrollbar")
    bar.pack(side="right", fill="y")
    widget.configure(yscrollcommand=bar.set)


def build(app):
    root = app.root
    root.configure(bg=BG)
    root.geometry("1180x790")
    root.minsize(1000, 710)
    root.columnconfigure(1, weight=1)
    root.rowconfigure(0, weight=1)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Studio.Horizontal.TProgressbar", troughcolor=LINE, background=ACCENT,
                    borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT)
    style.configure("Studio.Vertical.TScrollbar", troughcolor=FIELD, background=LINE,
                    arrowcolor=MUTED, bordercolor=FIELD, lightcolor=LINE, darkcolor=LINE, arrowsize=12)
    style.layout("Studio.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.map("Studio.Vertical.TScrollbar", background=[("active", "#586873"), ("!active", LINE)])

    rail = tk.Frame(root, bg=SIDE, width=178, padx=18, pady=28)
    rail.grid(row=0, column=0, sticky="nsew")
    rail.grid_propagate(False)
    rail.columnconfigure(0, weight=1)
    rail.rowconfigure(5, weight=1)
    mark = tk.Canvas(rail, width=44, height=40, bg=SIDE, highlightthickness=0)
    mark.grid(row=0, column=0, sticky="w")
    mark.create_rectangle(2, 2, 35, 34, outline=ACCENT, width=2)
    mark.create_rectangle(11, 10, 44, 40, fill=ACCENT, outline=ACCENT)
    mark.create_polygon(22, 17, 22, 33, 33, 25, fill=INK)
    label(rail, "抖音素材助手", size=13, bold=True).grid(row=1, column=0, sticky="w", pady=(16, 5))
    label(rail, "DOUYIN / LOCAL", size=8, color=MUTED).grid(row=2, column=0, sticky="w", pady=(0, 35))
    app.nav = {}
    for row, (key, title) in enumerate((("download", "01   下载作品"), ("local", "02   本地工具")), 3):
        item = button(rail, title, lambda key=key: app.show_page(key), anchor="w", padx=12)
        item.grid(row=row, column=0, sticky="ew", pady=4)
        app.nav[key] = item
    footer = tk.Frame(rail, bg=SIDE)
    footer.grid(row=6, column=0, sticky="sew")
    label(footer, "素材留在本地", size=10, color=ACCENT, bold=True).pack(anchor="w")
    label(footer, "离线合成 · 完整校验\n无需安装运行环境", size=9, color=MUTED,
          justify="left").pack(anchor="w", pady=(8, 20))
    label(footer, "DESKTOP   /   0.3", size=8, color=MUTED).pack(anchor="w")

    main = tk.Frame(root, bg=BG, padx=28, pady=25)
    main.grid(row=0, column=1, sticky="nsew")
    main.columnconfigure(0, weight=1)
    main.rowconfigure(1, weight=1)
    header = tk.Frame(main, bg=BG)
    header.grid(row=0, column=0, sticky="ew", pady=(0, 22))
    label(header, "YOUR MEDIA, AT HOME.", size=9, color=ACCENT).pack(anchor="w")
    app.heading = label(header, "留住每一帧。", size=28, bold=True)
    app.heading.pack(anchor="w", pady=(5, 7))
    app.description = label(header, "把分享链接变成自己的素材库。视频、图片、实况，一次保存。", color=MUTED)
    app.description.pack(anchor="w")

    body = tk.Frame(main, bg=BG)
    body.grid(row=1, column=0, sticky="nsew")
    body.columnconfigure(0, weight=3, minsize=430)
    body.columnconfigure(1, weight=2, minsize=280)
    body.rowconfigure(0, weight=1)
    page_host = tk.Frame(body, bg=BG)
    page_host.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
    page_host.columnconfigure(0, weight=1)
    page_host.rowconfigure(0, weight=1)
    app.pages = {}

    download = card(page_host, "粘贴作品链接", "01 / COLLECT")
    download.grid(row=0, column=0, sticky="nsew")
    app.pages["download"] = download
    # 先分配底部操作区，输入框使用剩余空间，小窗口也不会裁掉主按钮。
    actions = tk.Frame(download, bg=PANEL)
    actions.pack(side="bottom", fill="x", pady=(12, 0))
    app.make_check = tk.Checkbutton(actions, text="图文 / 实况同时生成完整播放版", variable=app.make_video,
        bg=PANEL, fg=TEXT, activebackground=PANEL, activeforeground=TEXT, selectcolor=FIELD,
        disabledforeground=MUTED, font=(FONT, 10), highlightthickness=0, anchor="w")
    app.make_check.pack(fill="x", pady=(0, 5))
    app.controls.append(app.make_check)
    label(actions, "原图、原声和实况片段另外保留。", size=9, color=MUTED).pack(anchor="w", pady=(0, 12))
    app.download_button = button(actions, "开始下载   →", app.download, accent=True)
    app.download_button.pack(fill="x")
    app.controls.append(app.download_button)
    label(actions, "需要联网与 Edge / Chrome   ·   Ctrl + Enter", size=9, color=MUTED).pack(anchor="w", pady=(8, 0))
    tools = tk.Frame(download, bg=PANEL)
    tools.pack(side="bottom", fill="x", pady=(10, 0))
    app.paste_button = button(tools, "粘贴", app.paste)
    app.paste_button.pack(side="left")
    app.controls.append(app.paste_button)
    app.clear_button = button(tools, "清空", app.clear)
    app.clear_button.pack(side="left", padx=8)
    app.controls.append(app.clear_button)
    app.link_count = label(tools, "等待输入", size=9, color=MUTED)
    app.link_count.pack(side="right")
    label(download, "短链接或整段分享文案，支持多个作品。", color=MUTED).pack(anchor="w", pady=(0, 12))
    app.input = scrolledtext.ScrolledText(download, width=1, height=7, wrap="word", font=(FONT, 11),
        bg=FIELD, fg=TEXT, insertbackground=ACCENT, selectbackground=ACCENT, selectforeground=INK,
        relief="flat", padx=14, pady=14, highlightthickness=1, highlightbackground=LINE,
        highlightcolor=ACCENT, undo=True)
    app.input.pack(fill="both", expand=True)
    dark_scrollbar(app.input)
    app.input.bind("<<Modified>>", app.input_changed)
    app.controls.append(app.input)

    local = card(page_host, "让素材继续发生", "02 / CREATE OFFLINE")
    local.grid(row=0, column=0, sticky="nsew")
    app.pages["local"] = local
    verify_area = tk.Frame(local, bg=PANEL)
    verify_area.pack(side="bottom", fill="x")
    tk.Frame(verify_area, bg=LINE, height=1).pack(fill="x", pady=(16, 14))
    verify = button(verify_area, "选择 MP4 · 完整性校验", app.verify)
    verify.pack(fill="x")
    app.controls.append(verify)
    label(local, "选择含「作品信息.json」的原素材目录。", color=MUTED).pack(anchor="w", pady=(0, 12))
    folder_row = tk.Frame(local, bg=PANEL)
    folder_row.pack(fill="x", pady=(0, 20))
    folder_row.columnconfigure(0, weight=1)
    app.folder_entry = entry(folder_row, app.folder)
    app.folder_entry.grid(row=0, column=0, sticky="ew", ipady=11)
    app.controls.append(app.folder_entry)
    pick = button(folder_row, "浏览", app.choose_folder)
    pick.grid(row=0, column=1, padx=(8, 0))
    app.controls.append(pick)
    label(local, "图片按顺序展示，实况保留动态。\n搭配完整原声，原始素材保持不变。", color=MUTED,
          justify="left").pack(anchor="w", pady=(0, 16))
    compose = button(local, "生成播放版   →", app.compose, accent=True)
    compose.pack(fill="x")
    app.controls.append(compose)
    label(local, "本地合成、视频校验均不需要网络。", size=9, color=ACCENT).pack(anchor="w", pady=(12, 0))

    monitor = tk.Frame(body, bg=PANEL, padx=20, pady=20, highlightthickness=1, highlightbackground=LINE)
    monitor.grid(row=0, column=1, sticky="nsew")
    label(monitor, "ACTIVITY / 执行记录", size=9, color=MUTED).pack(anchor="w")
    app.status_label = label(monitor, "●  等待任务", size=18, color=ACCENT, bold=True)
    app.status_label.pack(anchor="w", pady=(24, 10))
    app.status_detail = label(monitor, "任务开始后，进度与结果会出现在这里。", color=MUTED, justify="left", wraplength=265)
    app.status_detail.pack(fill="x")
    app.progress = ttk.Progressbar(monitor, mode="indeterminate", style="Studio.Horizontal.TProgressbar")
    app.progress.pack(fill="x", pady=(20, 22))
    label(monitor, "运行日志", size=10, bold=True).pack(anchor="w", pady=(0, 9))
    app.log = scrolledtext.ScrolledText(monitor, width=1, height=8, wrap="word", state="disabled",
        font=(FONT, 9), bg=PANEL, fg=MUTED, relief="flat", borderwidth=0, padx=0, pady=0,
        selectbackground=ACCENT, selectforeground=INK)
    app.log.pack(fill="both", expand=True)
    dark_scrollbar(app.log)
    app.log.tag_configure("time", foreground="#a0aeb6")
    app.log.tag_configure("success", foreground=ACCENT)
    app.log.tag_configure("error", foreground=RED)
    app.status_detail.bind("<Configure>", lambda e: app.status_detail.configure(wraplength=max(120, e.width)))

    dest = tk.Frame(main, bg=BG)
    dest.grid(row=2, column=0, sticky="ew", pady=(20, 0))
    dest.columnconfigure(0, weight=1)
    label(dest, "保存位置", size=9, color=MUTED).grid(row=0, column=0, sticky="w", pady=(0, 8))
    app.output_entry = entry(dest, app.output)
    app.output_entry.grid(row=1, column=0, sticky="ew", ipady=10)
    app.controls.append(app.output_entry)
    choose = button(dest, "更改", app.choose_output)
    choose.grid(row=1, column=1, padx=(10, 8))
    app.controls.append(choose)
    button(dest, "打开目录 ↗", app.open_output).grid(row=1, column=2)
    label(main, "新内容需要联网下载  /  本地合成和校验支持离线", size=9, color=MUTED).grid(row=3, column=0, sticky="w", pady=(13, 0))
