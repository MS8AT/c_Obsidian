# План открытия `https://obsidian.ms8at.by:18444`

**Исторический план от 03.11.2026.** Последующие исправления и датированная
проверка описаны в [RouterOS HTTPS](ROUTEROS_HTTPS_RU.md). Адреса и gateway ниже
не являются текущими defaults и не разрешают повторное применение.

Дата среза: 03.11.2026, Europe/Minsk. План не содержит паролей и не является
квитанцией RouterOS на применение.

## Целевой маршрут

```text
DNS obsidian.ms8at.by  -> 93.125.6.89 (A1)
DNS www.obsidian.ms8at.by -> CNAME obsidian.ms8at.by
Интернет TCP/18444
  -> RouterA / A1 / 1_A1
  -> QR gateway TLS virtual host (общее 80/443 не изменять)
  -> HTTP upstream 10.6.0.30:8080
  -> c_Obsidian production container
```

QR Station уже владеет TCP 80/443. Поэтому внешний 18444 должен завершаться
на существующем TLS-шлюзе QR Station, а новый c_Obsidian должен принимать
только внутренний HTTP на `10.6.0.30:8080`. Это сохраняет текущие 80/443 и
избегает отдельного неподтверждённого сертификата в новом контейнере.

## Этапы и критерии

### 0. Локальная проверка

- [x] `c_Obsidian` 0.2.0 отвечает локально на health.
- [x] 16 API/CLI тестов: 15 PASS, 1 SKIP из-за Windows symlink.
- [x] Container build и 17 HTTP smoke-checks прошли в изолированном Linux/amd64.
- [x] Пользовательский пароль не входит в образ, Git, логи или аргументы.

Критерий перехода: локальный `/api/health` = 200, login/session/CSRF,
create/read/image/logout проходят, образ имеет известный SHA-256.

### 1. Свежий RouterA preflight

Read-only через exact profile `mikrotik-88-1`:

- identity `RouterA`, RouterOS 7.20.6, x86_64;
- A1 `1_A1` и актуальный адрес;
- свободен ли `10.6.0.30` на `Dockers` по ARP/bridge/container inventory;
- установлен ли package `container`, свободно ли место;
- точные имена QR gateway container, veth, mounts и конфигурационного volume;
- какой процесс завершает TLS и где лежат virtual hosts/certificates;
- текущие NAT/filter правила 80/443/18443 и их immutable IDs.

Если любой target не подтверждён — остановиться, не использовать догадку.

### 2. Контейнер

Подготовить отдельные RouterOS объекты с ownership marker `AI_OBSIDIAN_...`:

- veth/interface для `10.6.0.30/24` на `Dockers`;
- отдельные mounts для `/vault`, `/state`, `/data`, `/config`;
- импорт проверенного linux/amd64 image tar;
- `OBSIDIAN_SHARED_GATEWAY=1`, `OBSIDIAN_DOMAIN=obsidian.ms8at.by`;
- `start-on-boot=yes`, logging без содержимого заметок и секретов;
- создать `Domiteli` только защищённым TTY prompt, сохранить PBKDF2-хеш.

Критерий: контейнер RUNNING; `http://10.6.0.30:8080/api/health` = 200;
login `Domiteli` и production API работают из LAN; текущие QR/WinBox/SSH не изменились.

### 3. Gateway и сертификат

После bounded inventory существующего QR gateway:

- добавить только `server_name obsidian.ms8at.by` и `www.obsidian.ms8at.by`;
- HTTP challenge/redirect и TLS virtual host на отдельном внутреннем listener;
- reverse proxy на `http://10.6.0.30:8080`;
- перед reload выполнить штатный config test;
- сертификат получить существующим способом шлюза; не копировать private key
  в Source, Git, image или RouterOS script.

Если gateway не поддерживает отдельный host/port без риска для QR Station,
остановиться и подготовить отдельный review вместо изменения общего шлюза.

### 4. RouterOS publication

После health контейнера и gateway:

- добавить A1 dst-nat TCP `18444` на gateway listener;
- добавить LAN hairpin/diagnostic path TCP `18444` на тот же gateway;
- добавить ровно один forward accept для `connection-nat-state=dstnat` и
  target, если текущий filter не пропускает поток;
- не менять правила QR Station 80/443 и 18443;
- сразу снять fresh readback, immutable ID и counters.

Не использовать numeric rule index. Для rollback сохранить exact immutable IDs
и preimage. После применения проверить management access и отсутствие duplicate
ownership comments.

### 5. DNS

- оставить `obsidian.ms8at.by A 93.125.6.89`;
- создать `www.obsidian.ms8at.by CNAME obsidian.ms8at.by`;
- проверить authoritative DNS и public resolver;
- не добавлять AAAA без рабочего IPv6 egress.

### 6. Проверка в порядке пользователя

1. `http://10.6.0.30:8080/api/health` из LAN.
2. `https://192.168.88.1:18444` из LAN; возможна проверка сертификата по имени.
3. `https://obsidian.ms8at.by:18444` из внешней сети A1.
4. `https://www.obsidian.ms8at.by:18444` после CNAME.
5. Login, RU/EN/中文, graph, image upload, note creation.
6. Counters NAT/filter, container restart, persistent account/vault.

## Текущий результат

На последнем read-only срезе:

- локальный health PASS;
- `192.168.88.1:18444` CLOSED;
- `93.125.6.89:18444` CLOSED;
- `10.6.0.30:8443` CLOSED;
- RouterA NAT `18444` ABSENT;
- `www.obsidian.ms8at.by` NXDOMAIN;
- QR Station 80/443 unchanged.

## Gate перед mutation

Пользовательский запрос и подтверждение плана получены. Для RouterOS Custom
mutation дополнительно требуется одноразовая plan-bound HMAC approval receipt
из защищённого внешнего approval-контура. Агент не создаёт и не изменяет
approval, HMAC key или receipt. До получения этой квитанции live mutation,
image import, container creation, NAT/filter и DNS write не выполняются.

## Rollback

Остановить только новый контейнер; удалить только `AI_OBSIDIAN_...` объекты,
точно связанные с этой публикацией; восстановить preimage gateway; вернуть DNS
preimage `www`; проверить QR Station 80/443, 18443, WinBox, SSH и существующие
контейнеры. Если live outcome UNKNOWN — не повторять применение до reconciliation.
