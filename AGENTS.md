# 抖音本地下载器

- 项目 Git 根为本目录；若上层有工作区规范，继续遵循其规则。
- `src/douyin_local/` 保存本地 CLI、解析和下载逻辑；上游库通过依赖安装，不复制第三方快照到源码。
- `downloads/` 保存用户视频和下载记录，`.local/` 保存诊断与浏览器数据；均不得提交。
- 不输出或提交 Cookie、浏览器存储、含临时签名的媒体直链。
- 权威设计：DESIGN.md 和 docs/architecture.md；当前下载目录改动记录在 F-0004，界面与公开记录在 F-0003。
- `posts/albums/service` 处理在线素材，`compose` 仅处理本地文件，`desktop` 不承载媒体逻辑。`scripts/build_portable.py` 生成忽略的 dist 成品，不能打包 downloads、.local、Cookie 和浏览器资料。
- 必跑：`.venv\Scripts\python.exe -m unittest discover -s tests -v`。
- 解析或下载变更另需运行 README 的真实链接命令，记录成功与失败及环境；不能把 HTTP 200 或文件存在当成有效视频。
- 打包变更需用最终 EXE 在隔离目录运行自检、本地合成和真实下载；GUI 需真实窗口截图。禁止把源码通过当作成品通过。
- 公开分支只包含源码、生成式测试、构建入口和公开文档，不纳入历史私人验收记录或原始下载素材。公开发布前检查完整待推送树。
