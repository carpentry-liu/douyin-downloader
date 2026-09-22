# 第三方依赖

本项目自行实现输入、抖音响应适配和输出记录，第三方源码不复制到 `src/`。安装版本固定在 pyproject.toml 和 requirements.txt，依赖保留在忽略的 `.venv`。

| 依赖 | 固定版本 | 上游与许可证 | 用途与部署影响 |
|---|---|---|---|
| yt-dlp | 2026.8.19 | https://github.com/yt-dlp/yt-dlp ，Unlicense | 直接解析候选及实际 HTTP 下载、重试、格式选择 |
| Playwright | 1.62.0 | https://github.com/microsoft/playwright-python ，Apache-2.0 | 通过独立浏览器加载抖音公开详情页；优先使用本机 Edge/Chrome，否则安装 Chromium |
| imageio-ffmpeg | 0.6.0 | https://github.com/imageio/imageio-ffmpeg ，BSD-2-Clause（Python 包） | 提供 FFmpeg 路径和视频元信息读取 |
| FFmpeg | wheel 内 7.1 Windows essentials | https://ffmpeg.org/legal.html ，本机二进制构建包含 `--enable-gpl --enable-version3` | 对视频完整解码；二进制许可证独立于 imageio-ffmpeg，打包分发时须另行保留对应许可及源码义务 |
| PyInstaller | 6.22.0（仅构建） | https://github.com/pyinstaller/pyinstaller ，GPL-2.0-or-later + bootloader exception | 生成 Windows 单文件，内嵌 Python/Tk 与依赖；不要求目标机器安装 Python |

本次额外构建本机使用的 `dist/DouyinLocal.exe`，包含 Python 3.12.3、Tcl/Tk、Playwright Node 驱动、yt-dlp 和 FFmpeg，不包含浏览器。构建脚本收集已安装依赖许可至 EXE 内 `licenses/` 及 `dist/third-party-licenses/`；Playwright 驱动及其 ThirdPartyNotices 随包保留。

FFmpeg 来自未修改的 imageio-ffmpeg 0.6.0 Windows wheel。上游维护入口为 https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0 ，FFmpeg 源码 https://github.com/FFmpeg/FFmpeg/tree/n7.1 。此处只为用户本机打包，不发布公共安装包；若后续对外再分发，应一起提供对应 FFmpeg 构建及全部库的完整源码、构建说明和许可，单给上游链接不能代替这些材料。
