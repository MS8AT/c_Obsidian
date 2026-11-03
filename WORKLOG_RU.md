# c_Obsidian · журнал

## 03.11.2026 · версия 0.2.0, проверки и подготовка RouterA

Поручение: проверить весь API/CLI, сделать план и чеклист, опубликовать на
GitHub, подготовить контейнер RouterA, внешний доступ через A1 по домену
obsidian.ms8at.by и пользователя Domiteli. Пароль из поручения не копировался
в код, Git, документы или image.

Реализованы production WSGI, защищённые server-side sessions, отзыв при logout,
CSRF, rate limit, PBKDF2-хеширование и protected-prompt provisioning. Добавлены
Dockerfile, Compose, Caddy standalone/shared, CI и полный HTTP smoke.

Windows: 16 тестов, 15 PASS и 1 SKIP (создание symlink недоступно).
Первый прогон выявил незакрытые соединения SQLite при очистке тестового
окружения; добавлено явное закрытие соединений, повторный полный прогон PASS.

Live read-only через exact Find/Preview/штатный адаптер подтвердил RouterA
7.20.6 x86_64, активный A1 93.125.6.89 и A1Route. NAT80/443 на A1 уже принадлежит
QR Station 10.6.0.20. DNS A нового имени не обнаружен. Ничего на RouterOS,
шлюзе QR, в DNS, accounts или контейнерах не изменялось.

Продолжение и фактический статус: [план/чеклист](docs/PLAN_CHECKLIST_RU.md).
Перед router mutation нужны недостающий bounded gateway inventory, точный план
с preimage/verify/rollback и операторская approval-квитанция штатного адаптера.
Source/local test, GitHub CI, container build, live deploy и operator acceptance
фиксируются отдельно. Время/адреса здесь — срез, не постоянные настройки.

## 03.11.2026 · повторная проверка внешнего порта

Пользователь сообщил, что порт открыт, и подтвердил точный план публикации.
Свежий read-only readback показал обратное: NAT `18444` отсутствует, TCP
`93.125.6.89:18444`, `192.168.88.1:18444` и `10.6.0.30:8443` закрыты.
`obsidian.ms8at.by` имеет A `93.125.6.89`; `www.obsidian.ms8at.by` — NXDOMAIN.
QR Station на 80/443 не изменён. Контейнер на RouterA не запущен.

Операторское подтверждение есть, но штатный RouterOS skill требует
одноразовую plan-bound HMAC approval receipt для Custom mutation; агент её не
создаёт. Поэтому после подтверждения не выполнялись ни NAT, ни импорт image,
ни DNS/gateway mutation. Следующий владелец: операторский approval-процесс и
назначенный интегратор RouterA. Evidence: `evidence/live-port-check-20261103.json`.
