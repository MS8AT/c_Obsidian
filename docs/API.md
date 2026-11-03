# Local HTTP API · Локальный API · 本地接口

Base URL: `http://127.0.0.1:8765`, or the port passed to `serve --port`.
Schema: [OpenAPI 3.1](../openapi.json), also `GET /api/openapi` after authentication.
Start: `py -3 -B obsidian.py --vault "C:\MyNotes" serve --write`.

The printed launch URL ends in `#<session-token>`. Extract that token manually
in your own client; send `Authorization: Bearer <session-token>`. It expires on
server restart. Never save it in source, reports or a shared configuration.
`--open` delivers the token to the browser automatically without printing it.

Ключ текущего запуска передаётся в заголовке `Authorization`, не в query string.
Сохранять его в общих файлах не нужно. Веб-интерфейс получает ключ из фрагмента
ссылки и сразу убирает фрагмент из адреса. Все пути — относительно хранилища,
с `/` вместо `\`. Ответы JSON и заметки используют UTF-8.

会话密钥通过 `Authorization` 请求头发送，重启服务器后失效。请勿保存到共享文件。
路径相对于知识库，使用 `/` 分隔；JSON 和笔记使用 UTF-8。

| Method | Endpoint | Result |
|---|---|---|
| GET | `/api/health` | Public minimal health, version; no vault data |
| GET | `/api/status` | Version, vault display name, languages, write mode |
| GET | `/api/openapi` | OpenAPI document |
| GET | `/api/graph` | Notes, resolved edges, summary, rules, warnings |
| GET | `/api/note?path=Home.md` | `{path, content}` |
| GET | `/api/image?path=assets/photo.jpg` | Raw image bytes and correct MIME |
| POST | `/api/notes` | Create a new note; requires `serve --write` |
| POST | `/api/images` | Add a new image; requires `serve --write` |

Create note, `Content-Type: application/json`:

```json
{"path":"Inbox/Идея.md","content":"---\ncreated: 2026-11-03\n---\n# Идея\n\n[[Home]]"}
```

Import image:

```json
{"path":"assets/photo.png","base64":"<base64-encoded PNG bytes>"}
```

`POST /api/images` returns `path`, `embed` and `sha256`; it does not edit a note.
Insert the returned embed in a newly created note to show it in the gallery.
Existing destination paths return `already_exists`, with no overwrite.

Minimal Python client, entering the transient token interactively:

```python
import getpass, json
from urllib.request import Request, urlopen

token = getpass.getpass('Session token: ')
request = Request('http://127.0.0.1:8765/api/graph',
                  headers={'Authorization': 'Bearer ' + token})
with urlopen(request, timeout=30) as response:
    result = json.load(response)
print(result['summary'])
```

Responses: `200` read success; `201` created; `400` invalid path, payload,
existing file or missing note/image; `401` missing/wrong token; `403` read-only,
wrong Host or cross-origin request; `404` unknown route; `500` filesystem error.
Errors are `{ "error": "stable_machine_code" }`; the UI translates known codes.
No CORS permission is emitted. Bind address is fixed to `127.0.0.1`; expose
neither this development server nor its token to the LAN or internet.

Limits: 2 MiB UTF-8 per note; 12 MiB per image; JSON body at most 24 MiB.
Only PNG/JPEG/GIF/WebP signatures are accepted. SVG/HTML are unsupported.
API writes are serialized with scans within the server. No file replacement,
deletion, shell execution, arbitrary filesystem reads or outbound fetch API.

Graph fields use stable English identifiers. `level` and `reason` follow
[POLICY.md](POLICY.md). `role_clues` explain the four-quadrant classification.
`warnings` must be checked: a partial scan is not evidence of an empty vault.
