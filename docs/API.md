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
Only PNG/JPEG/GIF/WebP signatures are accepted. SVG/HTML are unsupported by the image API. Prism HTML has its separate API below.
API writes are serialized with scans within the server. No deletion, shell execution, arbitrary filesystem reads or outbound fetch API.

Graph fields use stable English identifiers. `level` and `reason` follow
[POLICY.md](POLICY.md). `role_clues` explain the four-quadrant classification.
`warnings` must be checked: a partial scan is not evidence of an empty vault.

## API действий с данными, сборка 0.3.2-prism-api

Local bearer API и production session API используют общую реализацию.
GET /api/capabilities перечисляет операции и ограничения; GET /api/views —
виды карт и параметры проекций. Методы ниже включены в OpenAPI.

| Действие | Метод |
|---|---|
| Список и поиск заметок | GET /api/notes?q=... |
| Текст и версия заметки | GET /api/note?path=... |
| Создание заметки | POST /api/notes |
| Редактирование заметки | PUT /api/notes/update |
| Загрузка изображения | POST /api/images |
| Просмотр изображения | GET /api/image?path=... |
| Версия изображения | GET /api/image/info?path=... |
| Замена изображения | PUT /api/images/update |
| Карта, поиск, группировка, срез времени | GET /api/graph?view=...&q=...&group=...&until=...&language=... |
| Текущий HTML, размер и SHA-256 | GET /api/prism/prototype |
| Неизменяемый исходный HTML | GET /api/prism/prototype?original=1 |
| Импорт или правка HTML | PUT /api/prism/prototype |
| Возврат рабочего HTML к авторскому | POST /api/prism/reset |
| Изолированный предпросмотр текущего HTML | GET /prism |

PUT редактора заметки возвращает 201 для совместимости со старым local API;
новые PUT изображения и HTML возвращают 200. В production все POST/PUT
требуют cookie и X-CSRF-Token; local требует bearer. Readonly запрещает
запись. Host/Origin проверяются. API не повышает write-права и не выполняет
shell, модели, системные команды, смену mount или чтение произвольных путей.

Сначала GET содержимого и sha256, затем expected_sha256 вместе с изменением.
Устаревшая версия даёт 409 revision_conflict без перезаписи; занятый lock —
409 write_conflict. Перед повтором перечитать состояние. Для HTML версия
обязательна; для заметок и изображений опциональна ради совместимости.
Встроенный редактор заметки всегда передаёт прочитанный SHA-256.

```json
{"content":"<!doctype html><html><body>Новая версия</body></html>","expected_sha256":"<sha256 из GET>"}
```

Импорт передаёт содержимое файла, а не серверный путь. HTML ограничен 2 МиБ.
Рабочие версии хранятся content-addressed в /state/prism, переключение версии
атомарно. Исходный встроенный HTML не изменяется. Local serve хранит состояние
временно; для сохранения между запусками передать serve --state <отдельный
каталог состояния>. Токены в этом каталоге не сохраняются.

Предпросмотр /prism имеет sandbox без allow-same-origin и сетевых запросов;
правка HTML не ослабляет CSP основного приложения. Production требует входа;
loopback тоже требует bearer либо отдельную HttpOnly cookie с Path=/prism.
Она выдаётся после авторизованного GET /api/prism/prototype, не даёт доступа
к другим API и меняется после перезапуска сервера. Токен в URL не передаётся.

Импорт папки и «Добавить пример» используют POST /api/notes и POST /api/images
для каждого файла. ИИ может выполнить тот же путь без файлового диалога.
Общего batch и серверного обхода произвольных каталогов нет. Закрытие/отмена
диалогов, выбор файла и таймер воспроизведения — локальные действия интерфейса;
их данные читаются и меняются через перечисленные API.

Кнопки внутри HTML reference относятся только к авторской демонстрации.
Native раздел «Призма» имеет отдельный движок, проекты и API ниже.
HTML не преобразуется автоматически в вычислительную модель кейса.

## Native Призма: отдельные проекты в ветке 0.3

| Действие | Метод |
|---|---|
| Список проектов | GET /api/prism/v1/cases |
| Новый проект / Сохранить как | POST /api/prism/v1/cases |
| Прочитать модель | GET /api/prism/v1/cases/{case_id} |
| Править условия, правила и сценарии | PUT /api/prism/v1/cases/{case_id} |
| Пересчитать | POST /api/prism/v1/cases/{case_id}/evaluate |
| Сравнить взгляды/сценарии | POST /api/prism/v1/cases/{case_id}/compare |
| Альтернативная модель | POST /api/prism/v1/cases/{case_id}/challenge |
| История проекта | GET /api/prism/v1/cases/{case_id}/history |
| Прочитать снимок версии | GET /api/prism/v1/cases/{case_id}/snapshot?revision=... |
| Зафиксировать снимок | POST /api/prism/v1/cases/{case_id}/snapshot |
| Экспорт проекта | GET /api/prism/v1/cases/{case_id}/export |
| Проверить импорт | POST /api/prism/v1/import/validate |
| Создать проект из экспорта | POST /api/prism/v1/import/commit |

POST create принимает title, question, domain/context, nodes, assertions,
rules, scenarios, models и source_refs. Новый id генерируется сервером,
начальная revision=1. «Сохранить как» создаёт независимый case id.
PUT принимает model и expected_revision: устаревшая версия даёт 409.

Пример создания отдельного проекта:

```json
{"title":"Проект А","question":"Можно ли восстановить связи?","domain":"vault-maintenance"}
```

Папки native проектов: Prism/Data/<case_id>/model.json, events.jsonl,
snapshots; читаемый протокол — Prism/Cases/<case_id>.md. Они хранятся в
пользовательском vault, а не внутри образа приложения. Оригинальный vault
нельзя подменять демохранилищем при обновлении контейнера.

GET snapshot является чистым чтением: не добавляет событий и снимков.
Создание snapshot — отдельный POST с write-правами и CSRF. Evaluate/compare
и import/validate доступны в readonly, но production POST требует CSRF.

Импорт: validate возвращает package_sha256, затем commit принимает package
и expected_package_sha256. Существующий case id не перезаписывается.
Экспорт сохраняет model, protocol, hashes и сведения о внешних источниках;
self_contained/external_dependencies показывают ограничения автономности.
Импорт создаёт новую локальную revision=1; полная история прежнего хранилища
не воссоздаётся из одного экспорта.

Визуальные фильтры PROCESS/USER/ARCH/AI не меняют факты. Сценарные изменения
сохраняются в scenarios как допущения; правка базы требует отдельного режима.
Сервер выполняет ограниченный DSL prism_core, а не JS из загруженного HTML.
Model inference и выдача полномочий на внешние действия не входят в API.
