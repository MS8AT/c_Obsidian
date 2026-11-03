# Контейнер и внешний HTTPS

Версия 0.2.0: локальный режим остаётся без зависимостей. Для контейнера
добавлены Gunicorn 26.2.0 и Caddy 2 из официальных образов. Все процессы web
после инициализации томов работают под отдельным UID 10001.

## Устройство контейнера

- Приложение: Gunicorn, только `127.0.0.1:8765` внутри контейнера.
- Caddy standalone: 8080/8443 с ACME и HTTPS для выбранного домена.
- Caddy shared gateway: только внутренний HTTP8080; TLS завершает существующий
  шлюз. Включение: `OBSIDIAN_SHARED_GATEWAY=1`.
- `/vault`: заметки, пользовательские изображения; первоначально демохранилище.
- `/state`: accounts.json с PBKDF2-SHA256-хешем и БД отзываемых сессий.
- `/data`, `/config`: persistent storage Caddy. В shared-режиме ACME принадлежит
  внешнему шлюзу, его сертификаты в этот контейнер не копируются.

Учётные записи, БД сессий, ключи, пароли и реальные заметки не входят в образ
или Git. Изолированные тестовые реквизиты CI не подходят для живого сервиса.

## Первый запуск Docker на отдельном сервере

```sh
docker compose build
docker compose run --rm --entrypoint python obsidian /app/auth_store.py --state /state --username ExampleUser
docker compose up -d
```

Вторая команда открывает защищённый prompt, не принимает пароль в аргументах.
Файл учётной записи создаётся эксклюзивно: повторный запуск не меняет пароль
и не перезаписывает данные. Сервер без учётной записи завершается до открытия
web-портов. Выход из web-интерфейса отзывает сессию в БД, включая после restart.

## RouterA

Нельзя исполнять compose на RouterOS: нужен container image tar для linux/amd64,
отдельный veth и mounts. Готовый tar и SHA-256 публикуются как artifact workflow.
Это отдельный image build, не доказательство установки на устройстве.

Текущий вариант для RouterA — shared gateway из
[плана и чеклиста](PLAN_CHECKLIST_RU.md). QR Station уже принимает A1:80/443.
Пробрасывать эти порты повторно на другой IP нельзя. Примеры новых virtual
hosts в `deploy/qr-gateway-*.conf` — кандидаты: пути сертификатов и challenge
root должны быть проверены на действующем gateway до применения.

Официальные источники: [RouterOS Container](https://manual.mikrotik.com/docs/containers/),
[Caddy reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy),
[Caddy internal ports](https://caddyserver.com/docs/caddyfile/options#https-port),
[Gunicorn](https://pypi.org/project/gunicorn/).

## Production API

`POST /api/login` принимает JSON `{username,password}` и устанавливает
HttpOnly/Secure/SameSite=Lax cookie. `GET /api/session` после входа возвращает
CSRF-токен. Все POST изменения требуют `X-CSRF-Token`. `POST /api/logout`
отзывает текущую сессию. Локальный CLI/serve продолжает использовать свой
ключ текущего запуска и не создаёт production-аккаунтов.

Документ OpenAPI содержит обе схемы: bearer для local serve и session cookie
для production. В production никакие заметки, изображения и JavaScript
интерфейса не доступны до входа; публичны только health и страница входа.
