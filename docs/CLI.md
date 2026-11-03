# CLI · Командная строка · 命令行

Запускать только локальную копию Python-файлов. Run the local module copy.
请运行本地模块副本。`--vault`, `--lang` и `--created-property` стоят **до** команды.

```powershell
# RU / EN / 简体中文
py -3 -B obsidian.py --lang ru --help
py -3 -B obsidian.py --lang en status
py -3 -B obsidian.py --lang zh scan

# Новое хранилище / New vault / 新建知识库
py -3 -B obsidian.py --vault "C:\MyNotes" init

# Статус / Status / 状态
py -3 -B obsidian.py --vault "C:\MyNotes" status

# Граф JSON / Graph JSON / 图谱 JSON
py -3 -B obsidian.py --vault "C:\MyNotes" scan

# Читать / Read / 读取
py -3 -B obsidian.py --vault "C:\MyNotes" read "Home.md"

# Создать из UTF-8 Markdown / Create from UTF-8 / 从 UTF-8 文件创建
py -3 -B obsidian.py --vault "C:\MyNotes" create "Inbox/Идея.md" --content-file "C:\Drafts\idea.md"

# Импорт фото / Import image / 导入图片
py -3 -B obsidian.py --vault "C:\MyNotes" photo "C:\Pictures\photo.jpg" --path "assets/photo.jpg"

# Чтение HTTP / Read-only HTTP / HTTP 只读
py -3 -B obsidian.py --vault "C:\MyNotes" serve --open

# Создание через HTTP / Allow creation / 允许创建
py -3 -B obsidian.py --vault "C:\MyNotes" --lang ru serve --write --open --port 8765

# Другое свойство даты / Custom date property / 自定义日期属性
py -3 -B obsidian.py --vault "C:\MyNotes" --created-property date_created scan
```

По умолчанию: `demo-vault` рядом с программой, язык `ru`, порт `8765`.
Имена команд и ключей API стабильны и не переводятся. Статус возвращает
локализованную метку; GUI переведён полностью. Системные сообщения argparse
могут оставаться на английском.

Default: adjacent demo vault, Russian labels, port 8765. Command and JSON names
are stable machine identifiers. Argparse system diagnostics may remain English.

默认使用程序旁的演示知识库、俄语标签和端口 8765。命令和 JSON 字段名保持稳定，
argparse 的系统诊断可能仍为英语。

Exit codes: `0` success; `2` invalid argument, file error or vault error.
Only `serve` is long running. `Ctrl+C` stops it. No scheduler is installed.
