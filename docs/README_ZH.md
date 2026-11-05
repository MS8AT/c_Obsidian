# 快速开始 · 简体中文

c_Obsidian 0.2.1 是独立的本地 Obsidian Markdown 知识库辅助工具，提供 CLI、
本机 HTTP API、四种可解释的地图和图片库。它不会安装或修改 Obsidian 或
Maps of the Ideaverse 插件。

[在 MikroTik 上更改用户名和密码](ACCOUNTS_ZH.md)。容器 HTTPS 配置请参阅
[RouterOS 部署说明（俄文）](ROUTEROS_HTTPS_RU.md)和[部署指南（俄文）](DEPLOYMENT_RU.md)。

使用 Python 3.10 或更高版本，在**本地**模块文件夹中运行，无需第三方依赖：

```powershell
py -3 -B obsidian.py --lang zh serve --write --open
```

演示知识库包含 47 篇虚构笔记和三张原创插图。顶部固定栏中的 **RU · EN · 中文**
按钮可切换整个菜单、地图名称、表单、提示及消息的语言。浏览器会记住所选语言。
笔记原文保留不变，不会自动翻译。

- **思想生长**：按日期或文件夹展示五个层级。
- **星空**：根据链接距离，将笔记聚集到最近的已选枢纽。
- **引力**：用同心圆展示五个层级。
- **思维角色**：根据标题、地图类型和任务划分四种角色。
- **图片**：展示嵌入笔记中的本地 PNG、JPEG、GIF 和 WebP 图片。

点击节点可查看其层级原因、出链、反向链接和原文。点击“+ 新建笔记”，输入
`Inbox/新想法.md` 等路径和 Markdown 内容。已有文件不会被覆盖。
点击“+ 图片”将文件添加到 `assets/`，然后把显示的 `![[assets/photo.jpg]]`
嵌入文本写入一篇新笔记，刷新后即可在图片库中查看。

打开自己的知识库：

```powershell
py -3 -B obsidian.py --vault "C:\MyNotes" --lang zh serve --write --open
```

省略 `--write` 可启用 HTTP 只读模式。在服务器终端按 `Ctrl+C` 停止。
CLI 的 `create` 和 `photo` 命令是明确的新增文件操作。扫描不修改笔记；
API 不支持替换或删除已有文件。

服务器仅监听 `127.0.0.1`，使用每次运行独立的访问密钥，并检查 Host 和 Origin。
不调用云服务或 AI，不请求 CDN 或外部图片。未使用 `--open` 时，终端会显示带有
会话密钥的启动链接，请勿公开。网络共享中的代码应先复制到本地并核对 SHA-256。

这是首个版本，使用自己的[透明分级规则](POLICY.md)，与 Ideaverse 的算法不同。
暂不支持 3D 或 Bases。时间线仅按创建日期显示笔记，使用**当前链接**，不重建
过去的链接变化。日期来自简单的 `created` 属性或文件名，不使用文件系统时间。
只支持顶层标量 frontmatter 和部分 Markdown 链接语法。每次扫描都会读取并
计算所有笔记的哈希，然后复用未变化文件的解析缓存。限制为 20,000 篇笔记、
每篇 2 MiB、每张图片 12 MiB；尚未测试大型知识库。受保护目录、隐藏目录和
符号链接或目录联接不会被扫描。

[CLI 参考](CLI.md) · [API 参考](API.md) · [OpenAPI](../openapi.json)

地图灵感来自 [Nick Milo 的 Maps of the Ideaverse](https://github.com/nickmilo/ideaverse-maps)。
未复制上游代码或截图，演示插图为原创素材。此工具的 CLI 与
[Obsidian 官方 CLI](https://help.obsidian.md/cli) 相互独立。

感谢每一位用户、贡献者和项目的朋友，感谢有你们！
谢谢大家提供想法、反馈、翻译、测试与支持。
