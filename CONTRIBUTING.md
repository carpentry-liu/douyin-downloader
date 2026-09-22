# 参与开发

欢迎提交 issue 和 pull request。复现时附操作系统、Python/程序版本、步骤和已去除私人信息的错误描述。不要上传 Cookie、登录资料、签名媒体直链或无权公开的素材。

## 开发环境

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe scripts\portable_entry.py
```

`src/douyin_local/desktop.py` 负责主线程事件与任务控制，`desktop_view.py` 负责布局。`posts.py` 适配平台数据，`albums.py` 保存原素材，`compose.py` 仅使用本地文件。新增功能应放在对应层。

## 提交前验证

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m pip check
git diff --check
```

界面改动需真实窗口截图，检查主按钮、较小窗口、任务成功与失败。解析变更需用自己可访问的公开作品验证，不能用文件存在或 HTTP 200 代替解码成功。测试夹具由 FFmpeg 生成，不依赖特定账号和真实媒体。

PR 写清触发条件、改动后的行为与实际验证结果，使用 Conventional Commits。GitHub CI 仅运行测试，不默认构建或发布第三方整合二进制。

## 许可证

自研代码为 MIT；贡献内容采用同一许可证。第三方库保持各自许可，详见 THIRD_PARTY.md。
