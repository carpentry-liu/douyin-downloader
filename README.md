# 本地素材助手 · 抖音 / 小红书

**把分享链接，变成本地素材。**

Windows 桌面工具，支持抖音视频、图文和实况，以及小红书笔记与作者主页。保存文字、图片和视频，按需合成播放版；已有素材可以离线处理。

[![Windows tests](https://github.com/carpentry-liu/douyin-downloader/actions/workflows/test.yml/badge.svg)](https://github.com/carpentry-liu/douyin-downloader/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-a6e5bd)](LICENSE)

![本地工作台](docs/assets/workspace.png)

## 能做什么

| 输入 | 保存结果 |
|---|---|
| 抖音普通视频 | MP4 + 完整性校验记录 |
| 抖音图文 | 每张平台原图、原声、作品信息清单 |
| 抖音实况图文 | 原图、每张对应的实况 MP4、原声和清单 |
| 小红书单篇笔记 | 正文、精选元数据、静态图片或视频与封面 |
| 小红书作者主页 | 主页摘要、笔记索引、逐篇下载结果；默认上限 20 篇 |
| 本地素材目录 | 配上完整原声的 H.264/AAC 播放版 |
| 本地 MP4 | 完整解码、时长、分辨率和 SHA-256 校验 |

- 支持整段分享文案和多个链接，自动去重、串行处理。
- 图文按原顺序展示，实况保持动态并循环，完整保留原声时长；无原声时每项 5 秒。
- 合成版明确标记为本地生成，原始文件另外保留，画面留边不裁剪。
- 每条链接每次下载新建「时间戳_作者昵称」目录；同秒重名自动加序号，重复下载也独立保存。
- 深色工作台、剪贴板粘贴、链接计数、任务反馈；`Ctrl+Enter` 开始下载。

**新下载需要网络与系统 Edge/Chrome；启动、已有素材合成和视频校验可以离线使用。**

## 快速运行

需要 Windows 64 位、Python 3.12+。本仓库提供源码，依赖首次安装需要网络。

```powershell
git clone https://github.com/carpentry-liu/douyin-downloader.git
cd douyin-downloader
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe scripts\portable_entry.py
```

1. 选择「下载作品」，粘贴抖音作品、小红书笔记或作者主页链接，也支持分享文案。
2. 选择保存位置，按需勾选生成完整播放版，点击「开始下载」。小红书也可点击「仅读取」。
3. 完成后打开保存目录；素材与校验信息一起保存。

源码运行默认保存到项目 `downloads`。免安装 EXE 默认保存到 EXE 旁的 `downloads`，也可以更改位置。程序使用独立的临时浏览器，不读取日常浏览器登录资料。

每条链接的全部内容放在自己的文件夹内，例如：

```text
downloads/
├── 2026-09-25_15-30-08_作者甲/
│   ├── 作品ID_作者甲.mp4
│   └── 作品ID_作者甲.json
└── 2026-09-25_15-31-20_作者乙/
    ├── 01.jpg
    ├── 01_实况.mp4
    ├── 原声.mp3
    ├── 作品信息.json
    ├── 作品ID_作者乙_完整播放版.mp4
    └── 作品ID_作者乙_完整播放版.json
```

时间戳使用本机当地时间，作者名取平台昵称并清理文件名非法字符；缺失时使用「未知作者」。批量链接分别保存；同一批文案重复出现的相同 URL 只处理一次。再次发起下载会重新获取并创建新目录，不再跳过历史作品。原有目录可继续用于离线合成。

## 小红书使用说明

- 单篇「仅读取」保存 `笔记正文.txt` 与 `笔记信息.json`；「开始下载」再保存静态图片或视频、封面。图文默认生成静音 MP4，每张 5 秒；暂不提取图文配乐或实况片段。
- 主页「仅读取」保存作者资料、`主页摘要.txt` 与 `笔记列表.csv`，不逐篇读取正文。「开始下载」按索引逐篇下载，并在作者目录下创建每篇笔记的独立目录。
- 主页默认最多 20 篇，可设 1–200，按页面加载顺序，可能含置顶。输出记录实际读取条数和范围，不代表作者全部历史；粉丝数原样保存，未返回的统计值保持缺失。
- 使用独立匿名浏览器。正常浏览器登录后可见，不代表匿名工具也可访问。遇到要求登录、验证或 `300012`（IP 风险）时停止并报告，不会把登录页当作空主页或下载成功。

**当前验证限制：** 生成式图片/视频归档和真实浏览器契约测试已覆盖下载链路；本次两个真实主页在当前网络均返回平台安全限制，尚未完成真实小红书媒体下载的端到端成功验收。请先以一条可匿名访问的笔记验证，再扩大主页数量。

## 离线工具

进入「本地工具」，选择包含 **作品信息.json 和完整原素材** 的目录，点击「生成播放版」。选择 MP4 可以执行完整解码校验。不要单独移动清单或修改原素材。

![本地工具](docs/assets/local-tools.png)

## 构建单文件 EXE

在已经安装项目依赖的 Windows 环境执行：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe scripts\build_portable.py
# 如果旧版 EXE 正在运行，可以另起成品名称
.venv\Scripts\python.exe scripts\build_portable.py --name DouyinLocal-v040
```

生成 `dist/DouyinLocal.exe`、`使用说明.txt`、哈希记录和第三方许可。EXE 自带 Python、Tk、Playwright 驱动和 FFmpeg，可以单独移动，不要求目标电脑安装 Python；首次启动需要数秒解包。联网解析仍需要系统 Edge/Chrome。

当前公开源码，不在 Releases 提供包含 FFmpeg 的整合二进制。自行构建可在本机使用；若对外再分发，需满足第三方组件的许可与对应源码要求，详见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 命令行

```powershell
# 普通视频、图文和实况；把占位文案换成实际分享内容
.venv\Scripts\python.exe scripts\portable_entry.py --download "你的抖音分享链接" --output downloads

# 仅保存原素材，不生成合成版
.venv\Scripts\python.exe scripts\portable_entry.py --download "你的抖音分享链接" --originals-only

# 小红书：仅读取资料和索引，或下载主页前 5 篇
.venv\Scripts\python.exe scripts\portable_entry.py --read "你的小红书主页链接" --profile-limit 5
.venv\Scripts\python.exe scripts\portable_entry.py --download "你的小红书主页链接" --profile-limit 5 --originals-only

# 本地处理
.venv\Scripts\python.exe scripts\portable_entry.py --compose "素材目录" --offline --output output
.venv\Scripts\python.exe scripts\portable_entry.py --verify "已有视频.mp4" --offline
```

窗口版 EXE 支持同样参数，添加 `--report report.json` 可保存结构化结果。旧 `download.cmd` 和 `python -m douyin_local` 保留，只处理普通视频。

## 验证

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts\portable_entry.py --self-test --report .local\selftest.json

# 构建后，在独立目录使用生成的测试素材验收成品
.venv\Scripts\python.exe scripts\verify_portable.py
# 可选：再用自己的真实链接联网验收
.venv\Scripts\python.exe scripts\verify_portable.py --online-url "你的抖音分享链接"

# 可选真实浏览器契约测试：拦截请求并使用生成页面，需要 Edge/Chrome
$env:RUN_BROWSER_TESTS='1'
.venv\Scripts\python.exe -m unittest discover -s tests -p test_xhs_browser.py -v
```

测试覆盖真实本地 HTTP 传输、解码、目标 ID 匹配、图文解析、实况顺序、离线合成、防覆盖和 GUI 任务状态。夹具自动生成，不需要私人下载文件。`--offline` 用于程序级离线验收：阻断 Python 外部连接及 HTTP 代理连接，允许本机 IPC，浏览器自检使用离线上下文；不修改系统网络配置。

## 当前边界

- 抖音支持单篇作品和多条分享链接；小红书增加有限篇数的作者主页下载。暂不支持抖音主页、直播、账号登录或验证码处理。
- 平台页面、内容权限和风控可能变化，不能保证所有链接均可匿名下载；失败会显示原因。
- 优先选择平台当前可用的 H.264 视频；图片保留平台返回的格式与尺寸，不承诺创作者上传源文件或 4K。
- 不去除画面内已有水印。请下载自己有权保存和使用的内容。
- Windows 为桌面支持目标；尚未验证其他系统的 GUI。下载中断后重新运行，目前不保留跨进程续传文件。

## 开源与贡献

自研代码采用 [MIT](LICENSE)，第三方组件保留各自许可。

- [架构与边界](docs/architecture.md)
- [贡献指南](CONTRIBUTING.md)
- [代码审查记录](docs/review.md)
- [验证记录](docs/validation.md)
- [v0.3.1 下载目录迭代](docs/features/F-0004-download-folders/04-测试.md)
- [v0.4.0 小红书迭代](docs/features/F-0005-xiaohongshu/04-测试.md)
- [问题反馈](https://github.com/carpentry-liu/douyin-downloader/issues)
