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
