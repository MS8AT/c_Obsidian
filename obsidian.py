"""c_Obsidian CLI and authenticated loopback HTTP API. Python 3.10+."""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from obsidian_core import LANGUAGES, MAX_IMAGE, VERSION, Vault, VaultError

HERE = Path(__file__).resolve().parent
MESSAGES = {
    "ru": {"vault": "Хранилище", "ready": "Готово", "error": "Ошибка", "help": "Локальное хранилище Obsidian: API, CLI, карты и изображения"},
    "en": {"vault": "Vault", "ready": "Ready", "error": "Error", "help": "Local Obsidian vault: API, CLI, maps and images"},
    "zh": {"vault": "知识库", "ready": "就绪", "error": "错误", "help": "本地 Obsidian 知识库：API、CLI、地图和图片"},
}


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, vault, port=0, writable=False, language="ru"):
        self.vault, self.writable, self.language = vault, writable, language
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        super().__init__(("127.0.0.1", port), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    server: Server

    def log_message(self, *_):
        pass  # Never put note contents, paths or authorization in access logs.

    def reply(self, status, value, mime="application/json; charset=utf-8"):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8") if not isinstance(value, bytes) else value
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def guard(self, api=True):
        if self.headers.get("Host") != urlsplit(self.server.origin).netloc:
            self.reply(403, {"error": "invalid_host"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            self.reply(403, {"error": "invalid_origin"})
            return False
        supplied = self.headers.get("Authorization", "")
        if api and not secrets.compare_digest(supplied.encode('utf-8'), ("Bearer " + self.server.token).encode('utf-8')):
            self.reply(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        parsed = urlsplit(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if not self.guard(api=path.startswith("/api/") and path != "/api/health"):
            return
        try:
            with self.server.lock:
                if path == "/api/health":
                    self.reply(200, {"ok": True, "version": VERSION, "auth": "token"})
                elif path == "/api/status":
                    self.reply(200, {"version": VERSION, "language": self.server.language, "languages": list(LANGUAGES), "writable": self.server.writable, "vault": self.server.vault.root.name})
                elif path == "/api/openapi":
                    self.reply(200, json.loads((HERE / "openapi.json").read_text(encoding='utf-8')))
                elif path == "/api/graph":
                    self.reply(200, self.server.vault.graph())
                elif path == "/api/note":
                    self.reply(200, self.server.vault.read(query.get("path", [""])[0]))
                elif path == "/api/image":
                    raw, mime = self.server.vault.image(query.get("path", [""])[0])
                    self.reply(200, raw, mime)
                elif path in {"/", "/index.html", "/app.js", "/style.css"}:
                    name = "index.html" if path == "/" else path[1:]
                    mime = {"index.html": "text/html", "app.js": "application/javascript", "style.css": "text/css"}[name]
                    self.reply(200, (HERE / "web" / name).read_bytes(), mime + "; charset=utf-8")
                else:
                    self.reply(404, {"error": "not_found"})
        except VaultError as exc:
            self.reply(400, {"error": str(exc)})
        except (OSError, UnicodeError):
            self.reply(500, {"error": "file_error"})

    def do_POST(self):
        if not self.guard():
            return
        if not self.server.writable:
            self.reply(403, {"error": "read_only"})
            return
        try:
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                raise VaultError("json_required")
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_IMAGE * 2:
                raise VaultError("invalid_size")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise VaultError("invalid_body")
            with self.server.lock:
                if self.path == "/api/notes":
                    result = self.server.vault.create(data["path"], data["content"])
                elif self.path == "/api/images":
                    result = self.server.vault.add_image(data["path"], base64.b64decode(data["base64"], validate=True))
                else:
                    self.reply(404, {"error": "not_found"})
                    return
            self.reply(201, result)
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            self.reply(400, {"error": str(exc) if isinstance(exc, VaultError) else "invalid_body"})
        except OSError:
            self.reply(500, {"error": "file_error"})


def parser(language="ru"):
    p = argparse.ArgumentParser(description=MESSAGES[language]["help"])
    p.add_argument("--lang", choices=LANGUAGES, default=language, help="ru | en | zh")
    p.add_argument("--vault", type=Path, default=HERE / "demo-vault", help="Markdown vault folder")
    p.add_argument("--created-property", default="created")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Status / Статус / 状态")
    commands.add_parser("scan", help="Graph JSON / Граф JSON / 图谱 JSON")
    commands.add_parser("init", help="Create an empty vault / Создать хранилище / 创建知识库")
    read = commands.add_parser("read", help="Read note / Читать заметку / 读取笔记")
    read.add_argument("path")
    create = commands.add_parser("create", help="Create note / Создать заметку / 创建笔记")
    create.add_argument("path")
    create.add_argument("--content-file", type=Path, required=True, help="UTF-8 Markdown file")
    photo = commands.add_parser("photo", help="Import image / Добавить изображение / 导入图片")
    photo.add_argument("source", type=Path)
    photo.add_argument("--path", required=True, help="Destination inside vault")
    serve = commands.add_parser("serve", help="Open interface / Открыть интерфейс / 打开界面")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--write", action="store_true", help="Enable creation / Разрешить создание / 允许创建")
    serve.add_argument("--open", action="store_true", help="Open browser / Открыть браузер / 打开浏览器")
    return p


def main():
    language = "ru"
    if "--lang" in sys.argv:
        try:
            value = sys.argv[sys.argv.index("--lang") + 1]
            if value in LANGUAGES:
                language = value
        except IndexError:
            pass
    args = parser(language).parse_args()
    try:
        if args.command == "init":
            args.vault.mkdir(parents=True, exist_ok=True)
            vault = Vault(args.vault)
            result = vault.create("Home.md", "---\ntype: home\ncreated: " + __import__("datetime").date.today().isoformat() + "\n---\n# Home / Главная / 首页\n\n[[Inbox/First note]]\n")
        else:
            vault = Vault(args.vault, args.created_property)
            if args.command == "serve":
                with Server(vault, args.port, args.write, args.lang) as server:
                    # Token stays in the fragment, is removed by the UI, and is never logged.
                    url = server.origin + "/#" + server.token
                    if args.open:
                        webbrowser.open(url)
                        print(MESSAGES[args.lang]["ready"] + ": " + server.origin)
                    else:
                        print(url, flush=True)  # For deliberate manual use; do not publish this URL.
                    try:
                        server.serve_forever()
                    except KeyboardInterrupt:
                        pass
                return 0
            if args.command == "scan":
                result = vault.graph()
            elif args.command == "read":
                result = vault.read(args.path)
            elif args.command == "create":
                if args.content_file.stat().st_size > 2 * 1024 * 1024:
                    raise VaultError("note_too_large")
                result = vault.create(args.path, args.content_file.read_text(encoding="utf-8-sig"))
            elif args.command == "photo":
                if args.source.stat().st_size > MAX_IMAGE:
                    raise VaultError("image_too_large")
                result = vault.add_image(args.path, args.source.read_bytes())
            else:
                result = {"version": VERSION, "vault": vault.root.name, "languages": list(LANGUAGES), "label": MESSAGES[args.lang]["vault"], "summary": vault.graph()["summary"]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (VaultError, OSError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc), "label": MESSAGES[args.lang]["error"]}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
