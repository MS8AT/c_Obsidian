# 在 MikroTik 上更改用户名和密码

[Русский](ACCOUNTS_RU.md) · [English](ACCOUNTS_EN.md) · [简体中文](ACCOUNTS_ZH.md)

## 容器中的 c_Obsidian 账户

`--action` 命令需要 **0.2.1**。发布源代码不会自动升级现有的 0.2.0 容器。
请先单独安排升级到经过验证的镜像，并保留 `/state` 和 `/vault`。
这里管理的是网站账户，不是 RouterOS 管理员账户。

在 WinBox 终端中查看容器名称，然后进入其 shell：

```routeros
/container print
/container shell <container-name> user=app
```

将 `<container-name>` 替换为实际的 c_Obsidian 容器名称。以下命令在
**容器内部**的 `/app $` 提示符下运行：

```sh
cd /app
# 更改现有用户的密码：
python /app/auth_store.py --state /state --username ExistingUser --action password --lang en
# 同时更改用户名并设置新密码：
python /app/auth_store.py --state /state --username ExistingUser --action rename --new-username NewUser --lang en
```

请替换示例用户名。用户名长度为 3–64 个字符，只允许 `A–Z`、`a–z`、
`0–9`、`.`、`_`、`-`；密码长度为 8–256 个字符。新密码需要输入两次，
输入内容不会显示。两次输入不一致时，不会修改任何数据。
使用 `--lang ru|en|zh` 选择提示语言；如果 RouterOS 终端无法显示中文或俄文，
请使用 `en`。若终端不支持隐藏输入，工具会停止。

**首次创建账户**使用 `--action create`（默认操作），它不会覆盖已有的
accounts.json。更改密码或用户名会保留其他用户，以原子方式替换密码哈希文件，
并使旧会话失效。之后请使用新用户名和密码重新登录，无需重启容器。
不要在命令参数、聊天或报告中填写密码。工具不保存明文密码，请自行将其
保存在密码管理器中。

如果存在 `.accounts-update.lock`，之前的操作可能尚未结束。请先检查进程
和操作状态，不要直接删除锁文件。

## RouterOS / WinBox 用户

这是独立的账户。在 WinBox 中打开 **System → Users**，选中正确的用户。
修改 **Name** 字段可更改登录名。要更改密码，请使用该用户设置中的
**Password / Change Password**，并输入两次新密码；按钮名称因 WinBox
版本而异。保存后使用新凭据重新连接。仅更改密码时，不要修改 Group/Policies。

更改 RouterOS 账户不会更改 c_Obsidian 登录信息，反之亦然。

## 谢谢你们

感谢每一位用户、贡献者和项目的朋友，感谢有你们！
谢谢大家提供想法、反馈、翻译、测试与支持。
