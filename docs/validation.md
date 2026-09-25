# v0.3 验证记录

本页保留 v0.3.0 历史证据。最新目录归档迭代见 [v0.3.1 验证](features/F-0004-download-folders/04-测试.md)。

日期：2026-09-22。环境：Windows x64、Python 3.12.3、系统 Edge；依赖版本见 pyproject.toml / requirements-build.txt。

## 自动测试与构建

| 实际命令（项目根） | 结果 |
|---|---|
| `.venv\Scripts\python.exe -m unittest discover -s tests -v` | 28 项通过，2.469 秒；包含真实 HTTP、FFmpeg、Tk 主线程与工作线程测试 |
| `.venv\Scripts\python.exe -m pip check` | No broken requirements found |
| `git diff --check` | 无空白错误 |
| `.venv\Scripts\python.exe scripts\build_portable.py` | 成功生成 v0.3.0 单文件 EXE，94,263,979 字节 |
| `.venv\Scripts\python.exe scripts\verify_portable.py` | 实际 EXE 的 4 组离线验收通过，退出码 0 |

预期失败的 GUI 测试会记录 `Desktop operation failed: DownloadError`；测试随后确认错误状态与控件恢复，该行不是未处理异常。

本机构建 EXE 的 SHA-256：`a25aaaec77b73231bc61ed88f811ed5889b3f5cbd1c8d8f5339094fae6ab13ec`。该值识别本次本地成品，不承诺其他机器构建得到相同二进制。

## 隔离成品验收

验收脚本为每次运行新建独立目录，把最终 EXE 复制进带中文的路径；清除 Python、虚拟环境、FFmpeg 和 Playwright 驱动路径环境变量，子进程 PATH 仅保留 Windows 系统路径。动态生成两张 160×120 图片、0.4 秒实况片段、2 秒音轨，未使用私人媒体夹具。

1. `--self-test`：确认 frozen=True，实际 Tk 界面可创建，内嵌 FFmpeg 完整解码，浏览器离线上下文可用。
2. `--compose <生成素材目录> --offline`：生成 2 秒 H.264/AAC 播放版，保留原素材。
3. `--verify <播放版> --offline`：完整解码及哈希检查成功。
4. `--download <合成占位链接> --offline`：预期退出码 1，明确拒绝联网下载。

## 在线结果与限制

另执行 `scripts\verify_portable.py --online-url "<用户提供的普通视频短链> <用户提供的图文短链>"`，未把真实链接和媒体上传到仓库。

- 普通视频成功：1080×1920，10.45 秒，H.264/AAC，完整解码通过。
- 图文失败：浏览器解析未能完成；随后源码入口单独重试，仍未取得作品数据。尚不能确定是平台响应、内容状态还是解析兼容性，未将该项记为通过。
- 因此这次混合在线验收退出码为 1。图文解析和本地合成的生成式测试通过，不等于该真实图文样本端到端通过。

## 实际窗口检查

运行最终 `dist/DouyinLocal.exe`，检查默认 1180×790 客户区（截图 1182×822）和 1920×1032 最大化窗口。下载页和本地工具页的主要操作完整可见，导航正常；空素材目录点击合成会在任务区显示明确错误。

- [默认下载页截图](assets/workspace.png)
- [默认本地工具页截图](assets/local-tools.png)

这是原生 Tk 应用，没有浏览器前端控制台。实际窗口未出现 Tk 回调错误提示，自动测试覆盖任务成功、失败与控件恢复。最小尺寸和其他 Windows DPI 尚未完成单独视觉验收；窗口检查后收到用户 Esc 中止，已停止进一步桌面操作。移动端不在支持范围。

## 代码审查

按 OCR 规则人工审查并修复问题，详见 [review.md](review.md)。独立 LLM 服务未配置，不能称为独立模型自动审查通过。
