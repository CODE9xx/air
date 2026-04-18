# INSTALL_TIMEWEB.md — Code9 Analytics на Timeweb

Runbook для развёртывания Gate A / Sprint 0 на инфраструктуре Timeweb Cloud:

- **VPS** (Ubuntu 22.04/24.04): web + API + worker + scheduler + Caddy + Redis в Docker Compose.
- **Managed Postgres** (отдельный кластер Timeweb): держит все данные, доступен с VPS по приватной сети.

Документ написан так, чтобы его мог **последовательно выполнить CLI-агент** (Claude Code) через ssh на VPS, и чтобы человек-оператор видел, где нужно его подтверждение.

> Если ты не используешь managed Postgres — читай `SERVER_SETUP.md` (Вариант A, всё в docker).

---

## 0. Предусловия (оператор-человек — сделай ДО запуска агента)

Перед тем как отдать runbook CLI-агенту:

### 0.1. Данные Timeweb

Заполни таблицу и держи её открытой рядом:

| Параметр | Значение (пример) | Где взять |
|----------|-------------------|-----------|
| VPS public IPv4 | `72.56.232.201` | Timeweb → VPS → твой сервер → Сеть |
| VPS root-доступ  | пароль / ssh-ключ | Timeweb → VPS → Доступы |
| Managed DB host (private) | `192.168.0.4`   | Timeweb → Кластеры БД → твой кластер → Доступы (приватный хост) |
| Managed DB port | `5432` | там же |
| Managed DB user | `gen_user` (или созданный тобой) | там же |
| Managed DB password | `<secret>` | при создании кластера; можно пересоздать |
| Managed DB name | `default_db` (или своя) | там же |
| VPS и managed DB в одной приватной сети | **да** | Timeweb → Cloud Networks / VPC |

Если VPS и managed DB **не в одной приватной сети** — приватный IP не будет доступен. Создай VPC и привяжи оба ресурса, либо используй публичный хост managed DB и обязательно `sslmode=require`.

### 0.2. DNS

Два A-record'а должны указывать на VPS public IP **до запуска** compose — Caddy не получит Let's Encrypt-сертификат иначе:

- `app.yourdomain.com`  → `72.56.232.201`
- `api.yourdomain.com`  → `72.56.232.201`

Проверь локально:
```bash
dig +short app.yourdomain.com
dig +short api.yourdomain.com
```
Оба должны вернуть IP VPS. Если пусто — подожди пропагации (до часа), потом продолжай.

### 0.3. Генерация секретов (ЛОКАЛЬНО у тебя, не на VPS)

Никогда не отправляй эти команды агенту — он запишет их в чат. Сгенерируй локально и храни в password manager:

```bash
# JWT_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# ADMIN_JWT_SECRET (должен отличаться от JWT_SECRET)
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# FERNET_KEY (шифрует OAuth-токены CRM)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ADMIN_BOOTSTRAP_PASSWORD (одноразовый, сменишь в UI)
python3 -c "import secrets; print(secrets.token_urlsafe(16))"
```

Пароль managed DB берёшь из Timeweb — генерировать не нужно.

### 0.4. Репозиторий

Убедись, что у VPS есть доступ к git-репозиторию (https с токеном или ssh-deploy key). Запомни URL — `https://github.com/ORG/code9-analytics.git` или подобный.

### 0.5. Роль CLI-агента

Агент делает всё, что **не требует человеческого решения**:
OS-пакеты, firewall, docker, клонирование, compose-операции, проверки.

Агент **НЕ должен**:
- Придумывать пароли/секреты (тебе их даёт человек).
- Пушить `.env.production` в git.
- Запускать destructive-команды без явного флага `CONFIRM=YES`.
- Менять DNS, выпускать реальные сертификаты вручную (Caddy сам).
- Снимать бэкап PROD-БД в небезопасное место.

Если на шаге что-то идёт не так — агент **останавливается** и возвращает человеку лог ошибки.

---

## 1. Переменные runbook'а

Перед стартом оператор отдаёт агенту блок переменных:

```bash
# --- задаёт оператор ---
export DOMAIN_APP="app.yourdomain.com"
export DOMAIN_API="api.yourdomain.com"
export ACME_EMAIL="admin@yourdomain.com"
export REPO_URL="https://github.com/ORG/code9-analytics.git"
export REPO_BRANCH="main"

# Timeweb managed DB
export TW_DB_HOST="192.168.0.4"
export TW_DB_PORT="5432"
export TW_DB_USER="gen_user"
export TW_DB_NAME="default_db"
export TW_DB_PASSWORD="<передан оператором, не логируй>"
export TW_DB_SSLMODE="require"

# Секреты приложения (сгенерированы оператором локально)
export JWT_SECRET="<64-byte token>"
export ADMIN_JWT_SECRET="<64-byte token, отличный от JWT_SECRET>"
export FERNET_KEY="<44-char Fernet key>"
export ADMIN_BOOTSTRAP_EMAIL="admin@yourdomain.com"
export ADMIN_BOOTSTRAP_PASSWORD="<strong pw>"

# VPS
export VPS_IP="72.56.232.201"
export APP_USER="code9"
export PROJECT_DIR="/opt/code9-analytics"
```

Агент **не печатает** значения этих переменных в ответах — только их имена.

---

## 2. Phase 1 — OS prep, Docker, firewall

Выполняется под `root` (SSH).

### 2.1. Обновление и базовые пакеты

```bash
apt update && apt upgrade -y
apt install -y git curl make htop ufw ca-certificates gnupg lsb-release dnsutils netcat-openbsd
```

**verify**:
```bash
git --version && docker --version 2>/dev/null || true
```

### 2.2. Docker Engine + Compose plugin

```bash
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

**verify**:
```bash
docker run --rm hello-world
docker compose version
```

Ожидание: `Hello from Docker!` + `Docker Compose version v2.x`.

**abort condition**: если `hello-world` падает — агент останавливается, сообщает оператору, что `dockerd` не поднимается.

### 2.3. Создание application-user

```bash
id "$APP_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$APP_USER"
usermod -aG sudo,docker "$APP_USER"
mkdir -p "/home/$APP_USER/.ssh"
# Если агент заходит по root-ключу, он же нужен $APP_USER для следующих шагов:
if [[ -f /root/.ssh/authorized_keys ]]; then
    cp /root/.ssh/authorized_keys "/home/$APP_USER/.ssh/authorized_keys"
fi
chown -R "$APP_USER:$APP_USER" "/home/$APP_USER/.ssh"
chmod 700 "/home/$APP_USER/.ssh"
chmod 600 "/home/$APP_USER/.ssh/authorized_keys" 2>/dev/null || true
```

### 2.4. Firewall (ufw)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
yes | ufw enable
ufw status verbose
```

**verify**: в `ufw status` видны `22/tcp`, `80/tcp`, `443/tcp`, `443/udp`. Больше ничего входящего.

### 2.5. /var/backups/code9

```bash
mkdir -p /var/backups/code9
chown "$APP_USER:$APP_USER" /var/backups/code9
chmod 700 /var/backups/code9
touch /var/log/code9-backup.log
chown "$APP_USER:$APP_USER" /var/log/code9-backup.log
chmod 600 /var/log/code9-backup.log
```

**Checkpoint Phase 1**: переключись на `$APP_USER` для всех следующих шагов (`su - $APP_USER` или новая ssh-сессия). Последующие команды — не от root.

---

## 3. Phase 2 — код и секреты

### 3.1. Клонирование

```bash
sudo mkdir -p "$PROJECT_DIR"
sudo chown "$APP_USER:$APP_USER" "$PROJECT_DIR"
cd /opt
git clone --branch "$REPO_BRANCH" "$REPO_URL" code9-analytics
cd "$PROJECT_DIR"
```

**verify**:
```bash
test -f deploy/docker-compose.prod.timeweb.yml \
  && test -f deploy/Caddyfile \
  && test -f .env.production.template \
  && echo "✓ репозиторий на месте"
```

**abort**: если какого-то файла нет — ветка/репозиторий не тот, агент сообщает оператору.

### 3.2. `.env.production`

Создаём из шаблона и подставляем значения. В `.env.production.template` есть два блока БД — используем **Вариант B (Timeweb managed)**. Агент пишет финальный файл атомарно:

```bash
cat > "$PROJECT_DIR/.env.production" <<EOF
# --- Окружение ---
APP_ENV=production
DEBUG=false
LOG_LEVEL=info

# --- Публичные URLы ---
PUBLIC_APP_URL=https://$DOMAIN_APP
PUBLIC_API_URL=https://$DOMAIN_API
BASE_URL=https://$DOMAIN_API

# --- Timeweb managed Postgres ---
POSTGRES_HOST=$TW_DB_HOST
POSTGRES_PORT=$TW_DB_PORT
POSTGRES_USER=$TW_DB_USER
POSTGRES_PASSWORD=$TW_DB_PASSWORD
POSTGRES_DB=$TW_DB_NAME
POSTGRES_DSN=postgresql://$TW_DB_USER:$TW_DB_PASSWORD@$TW_DB_HOST:$TW_DB_PORT/$TW_DB_NAME?sslmode=$TW_DB_SSLMODE
DATABASE_URL=postgresql+asyncpg://$TW_DB_USER:$TW_DB_PASSWORD@$TW_DB_HOST:$TW_DB_PORT/$TW_DB_NAME?ssl=$TW_DB_SSLMODE

# --- Redis (в compose) ---
REDIS_URL=redis://redis:6379/0

# --- Security ---
JWT_SECRET=$JWT_SECRET
ADMIN_JWT_SECRET=$ADMIN_JWT_SECRET
FERNET_KEY=$FERNET_KEY

# --- CORS ---
ALLOWED_ORIGINS=https://$DOMAIN_APP
CORS_ORIGINS=https://$DOMAIN_APP

# --- CRM / Email / Mock ---
MOCK_CRM_MODE=true
EMAIL_BACKEND=console
DEV_EMAIL_MODE=log
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@$DOMAIN_APP

# --- Admin bootstrap ---
ADMIN_BOOTSTRAP_EMAIL=$ADMIN_BOOTSTRAP_EMAIL
ADMIN_BOOTSTRAP_PASSWORD=$ADMIN_BOOTSTRAP_PASSWORD

# --- Frontend build-time ---
NEXT_PUBLIC_API_URL=https://$DOMAIN_API/api/v1
NEXT_PUBLIC_APP_URL=https://$DOMAIN_APP
NEXT_PUBLIC_DEFAULT_LOCALE=ru

# --- Placeholders для Sprint 4 ---
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
YOOKASSA_WEBHOOK_SECRET=
STRIPE_PUBLIC_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
AMOCRM_CLIENT_ID=
AMOCRM_CLIENT_SECRET=
AMOCRM_REDIRECT_URI=https://$DOMAIN_API/api/v1/crm/oauth/amocrm/callback

# --- Backup ---
BACKUP_DIR=/var/backups/code9
RETAIN_DAYS=14
EOF

chmod 600 "$PROJECT_DIR/.env.production"
ls -la "$PROJECT_DIR/.env.production"
```

**verify**:
```bash
# Ни одного CHANGE_ME не должно остаться:
grep -n "CHANGE_ME" "$PROJECT_DIR/.env.production" && echo "❌ остались CHANGE_ME" || echo "✓ секреты подставлены"
# APP_ENV точно production:
grep "^APP_ENV=" "$PROJECT_DIR/.env.production"
```

**abort**: если есть `CHANGE_ME` — агент останавливается и просит оператора поправить переменные.

### 3.3. Caddyfile

Заменяем `example.com` на реальные домены **во ВСЕХ** местах, включая CSP:

```bash
cd "$PROJECT_DIR"
sed -i \
    -e "s|app\.example\.com|$DOMAIN_APP|g" \
    -e "s|api\.example\.com|$DOMAIN_API|g" \
    -e "s|admin@example\.com|$ACME_EMAIL|g" \
    deploy/Caddyfile
```

**verify**: не должно остаться ни одного `example.com` (иначе CSP сломает фронт):

```bash
grep -n "example\.com" deploy/Caddyfile && echo "❌ остались example.com — CSP не пропустит API" || echo "✓ Caddyfile готов"
```

**abort**: если что-то осталось — агент показывает найденные строки и останавливается.

---

## 4. Phase 3 — связность с managed Postgres

**До** `compose up` проверяем, что VPS видит managed DB. Это **критический чекпоинт** — если здесь фэйл, поднимать compose бессмысленно.

### 4.1. TCP-доступ

```bash
cd "$PROJECT_DIR"
# Считываем POSTGRES_HOST/PORT из .env.production:
set -a; . ./.env.production; set +a
nc -zv -w 5 "$POSTGRES_HOST" "$POSTGRES_PORT"
```

Ожидание: `Connection to 192.168.0.4 5432 port [tcp/*] succeeded!`

**abort conditions**:
- `Connection refused` / `timeout` → VPS не в одной VPC с кластером БД. Оператор должен привязать оба ресурса к одной private network в Timeweb.
- `Name or service not known` → `POSTGRES_HOST` — это hostname, а не IP, и DNS не резолвит. Используй private IP из панели Timeweb.

### 4.2. Auth + version через psql

Без compose (compose ещё не поднят). Используем одноразовый контейнер:

```bash
docker run --rm --network host \
  -e PGPASSWORD="$POSTGRES_PASSWORD" postgres:18-alpine \
  psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
       -c "select version();"
```

Ожидание: одна строка `PostgreSQL 15.x/16.x/17.x/18.x on x86_64...`.

**abort**:
- `FATAL: password authentication failed` → пароль неверный (или `gen_user` удалили). Оператор перегенерирует в панели.
- `FATAL: no pg_hba.conf entry for host` → VPS-ip не добавлен в белый список доступа managed DB. Оператор идёт в Timeweb → кластер → Доступы → добавить VPS.
- `FATAL: SSL is required` → добавь `?sslmode=require` (или поправь `TW_DB_SSLMODE=require`).

### 4.3. Права на схему `public` и CREATE EXTENSION

Проверь, может ли `gen_user` создавать расширения и схемы (нужно для multi-tenant — каждый tenant в своей схеме):

```bash
docker run --rm --network host \
  -e PGPASSWORD="$POSTGRES_PASSWORD" postgres:18-alpine \
  psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
SELECT current_user, session_user;
SELECT has_database_privilege(current_user, current_database(), 'CREATE') AS can_create_schema;
SELECT has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_in_public;
SQL
```

Ожидание: обе `can_create_*` = `t`.

**abort**: если `can_create_schema = f` → Timeweb выдал read-only пользователя, либо БД создана через шаблон с ограничениями. Оператор создаёт нового пользователя с правами в панели Timeweb.

### 4.4. Extensions (одноразово)

```bash
make prod-tw-db-extensions
```

Ожидание (три `CREATE EXTENSION`):
```
CREATE EXTENSION
CREATE EXTENSION
CREATE EXTENSION
✓ extensions установлены
```

**abort**:
- `permission denied to create extension "pgcrypto"` → у `gen_user` нет прав на CREATE EXTENSION. Варианты:
  - Timeweb: большинство extensions разрешено по умолчанию; если нет — тикет в support.
  - Альтернатива: выполнить от имени системного суперюзера через панель Timeweb (query-editor).

---

## 5. Phase 4 — compose up

### 5.1. Валидация

```bash
cd "$PROJECT_DIR"
make prod-tw-config
```

Ожидание: `✓ docker-compose.prod.timeweb.yml валиден`.

### 5.2. Build (5–15 минут на слабой VPS)

```bash
make prod-tw-build
```

Логи длинные. Агент стримит их, но в финальный отчёт кладёт только последние 30 строк + статус `exit 0`.

### 5.3. Up

```bash
make prod-tw-up
sleep 30
make prod-tw-ps
```

Ожидание — 6 контейнеров:
- `code9-prod-caddy`   → Up (healthy)
- `code9-prod-web`     → Up (healthy)
- `code9-prod-api`     → Up (healthy)
- `code9-prod-worker`  → Up
- `code9-prod-scheduler` → Up
- `code9-prod-redis`   → Up (healthy)

Статусы `worker`/`scheduler` без `(healthy)` — это ожидаемо для Sprint 0 (healthcheck не определён).

**abort**:
- `code9-prod-api` → restarting/unhealthy → открываем `make prod-tw-logs` и ищем `fail-fast` сообщения (обычно — `JWT_SECRET=CHANGE_ME` или `.env.production` не смонтировался).
- `code9-prod-web` → unhealthy в течение > 2 минут → fetch на 127.0.0.1:3000 не отвечает, обычно порт/билд сломан.
- `caddy` → ошибка обращается к ACME → проверь, что DNS уже указывает на VPS public IP (см. Phase 0.2).

### 5.4. Миграции

```bash
make prod-tw-migrate
```

Ожидание: alembic пишет `Running upgrade ... -> ..., create_* tables`, в конце — нет ошибок. `INFO` строки про revisions и таблицы допустимы.

**abort**: если падает на `permission denied for schema public` — возвращаемся в Phase 4.3 и выясняем права.

### 5.5. Seed admin

```bash
make prod-tw-seed
```

Ожидание: `Admin user created: <email>` или `Admin already exists` (если повторно). **Сразу после первого логина меняй пароль в UI.**

---

## 6. Phase 5 — smoke

### 6.1. HTTP health

```bash
make prod-tw-smoke
# или напрямую:
curl -fsS https://$DOMAIN_API/api/v1/health
```

Ожидание: `200 OK` и JSON `{"status":"ok",...}`.

### 6.2. Frontend живой

```bash
curl -I https://$DOMAIN_APP
```

Ожидание: `HTTP/2 200` или `HTTP/2 3xx` (редирект на /ru). Любой `5xx` — фэйл.

### 6.3. Защита портов снаружи (с ДРУГОЙ машины, не с VPS)

Оператор делает это локально:

```bash
# Redis изнутри compose слушает 127.0.0.1:6379 — НЕ должен быть доступен снаружи:
nc -zv -w 5 $VPS_IP 6379   # ожидается: Connection refused / timeout

# Managed DB должна быть доступна ТОЛЬКО из VPS private-сети, не с public IP:
nc -zv -w 5 $VPS_IP 5432   # ожидается: Connection refused / timeout
```

Если порты 5432 / 6379 открыты снаружи — firewall настроен неправильно. Stop, исправляй ufw.

### 6.4. Секретов нет в логах

```bash
cd "$PROJECT_DIR"
docker compose -f deploy/docker-compose.prod.timeweb.yml logs api --since=10m \
  | grep -Ei "bearer|secret|fernet|jwt_secret|password=|PGPASSWORD" | head
```

Ожидание: **пусто**. Если находит — фэйл (SEC-03 из Gate A critical list).

### 6.5. Ручные проверки (оператор, UI)

Из браузера, от имени живого пользователя:

1. Регистрация → в `make prod-tw-logs | grep api` приходит e-mail-код (SMTP в Sprint 3 не настроен).
2. Логин → cookie `refresh_token` с `HttpOnly; Secure; SameSite=Lax` (DevTools → Application).
3. Создать workspace → подключить mock-amoCRM → запустить audit → увидеть dashboard.
4. Админ-логин (`$ADMIN_BOOTSTRAP_EMAIL`) → открывается базовая admin-страница.

Полноценный tenant support-mode (start-with-reason → `admin_audit_logs`) — Gate B / CR-07.

---

## 7. Phase 6 — backup

### 7.1. Одноразовый ручной прогон

```bash
make prod-tw-backup
ls -lah /var/backups/code9/
```

Ожидание: `code9_YYYYMMDD_HHMMSSZ.sql.gz` + `code9_globals_YYYYMMDD_HHMMSSZ.sql.gz`. Размер main-дампа — от десятков КБ (пустая БД Sprint 0).

**note про globals на managed Postgres**: `pg_dumpall --globals-only` может вернуть неполный дамп (у `gen_user` нет прав superuser на `pg_authid`). Это **норма** — для restore drill на этом же managed-кластере globals не нужны (роли уже живут в кластере). Для миграции на другого провайдера нужно будет экспортировать роли отдельно (Sprint 2, см. `BACKUP_RESTORE.md §Secrets rotation`).

### 7.2. Cron

```bash
crontab -e
# Добавь строку:
0 3 * * * PROJECT_DIR=/opt/code9-analytics bash /opt/code9-analytics/deploy/backup/pg_dump_managed.sh >> /var/log/code9-backup.log 2>&1
```

Из агента это делается через:

```bash
CRON_LINE="0 3 * * * PROJECT_DIR=$PROJECT_DIR bash $PROJECT_DIR/deploy/backup/pg_dump_managed.sh >> /var/log/code9-backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v "pg_dump_managed\.sh"; echo "$CRON_LINE" ) | crontab -
crontab -l
```

---

## 8. Phase 7 — restore drill (обязательно до Gate B, можно отложить для Gate A)

Лёгкий вариант — на **staging-БД** (если есть отдельная managed-БД под staging) или временно на `default_db_restore_drill`, создав её в панели Timeweb.

```bash
# 1. Поднять stash БД (в панели Timeweb: создать новую managed БД)
# 2. В .env.production временно поменять POSTGRES_DB на stash:
#    NB: или сделать копию .env.production как .env.restore-drill и использовать её
# 3. Прогнать restore:
BACKUP=$(ls -t /var/backups/code9/code9_*.sql.gz | head -n1)
make prod-tw-restore BACKUP=$BACKUP
# ответить YES RESTORE
# 4. make prod-tw-smoke
# 5. Записать результат в docs/deploy/BACKUP_RESTORE.md §Drill log
# 6. В панели Timeweb удалить stash БД
# 7. Вернуть оригинальный POSTGRES_DB в .env.production
```

Для Gate A достаточно подтвердить, что `make prod-tw-backup` работает. Drill — до Gate B.

---

## 9. Phase 8 — финализация и sign-off

### 9.1. Заполни GATE_SIGNOFFS.md

Открой `docs/deploy/GATE_SIGNOFFS.md`, впиши первую строку в Gate A log:

- дата
- версия (commit SHA): `git rev-parse --short HEAD`
- имя оператора
- результаты проверок Phase 5.1–5.5 (галочки или `FAIL`)

### 9.2. Отчёт оператору

Финальный отчёт от агента (не больше 30 строк):

```
✓ Phase 1: OS + docker + ufw + backup dir
✓ Phase 2: repo cloned at /opt/code9-analytics, .env.production written (600), Caddyfile patched
✓ Phase 3: DB reachable, extensions installed
✓ Phase 4: 6 containers up (caddy, web, api, worker, scheduler, redis)
✓ Phase 4: alembic migrate OK, admin seeded
✓ Phase 5: health 200, frontend 200, no secrets in logs
✓ Phase 6: backup manual OK (<file list>), cron set
— Phase 7: restore drill отложен до Gate B
```

Плюс: ссылки на UI (`https://$DOMAIN_APP`, `https://$DOMAIN_API/api/v1/health`) и напоминание оператору сменить `ADMIN_BOOTSTRAP_PASSWORD` после первого входа.

---

## 10. Troubleshooting (быстрые ответы, если что-то идёт не так)

| Симптом | Причина / первое действие |
|---------|---------------------------|
| `docker run hello-world` падает | dockerd не запущен. `systemctl status docker` + `journalctl -u docker --no-pager` |
| `nc` на private IP timeout | VPS и managed DB в разных private-сетях. Timeweb → VPC. |
| psql: `no pg_hba.conf entry for host` | VPS IP не whitelist'ится в Timeweb → кластер → Доступы → Добавить IP |
| psql: `SSL is required` | Добавить `?sslmode=require` в DSN + `?ssl=require` в asyncpg URL |
| `make prod-tw-up` и api в restart loop | `make prod-tw-logs api` → ищешь `fail-fast`, обычно `.env.production` не смонтировался или остались `CHANGE_ME_*` |
| 502 от `https://api.DOMAIN` | api-контейнер упал; `make prod-tw-logs` + `docker compose -f deploy/docker-compose.prod.timeweb.yml ps` |
| Caddy cert: `obtaining certificate: timeout` | DNS ещё не указывает на VPS. `dig +short $DOMAIN_APP` должен вернуть `$VPS_IP`. ufw 80/443 открыты. |
| `alembic upgrade head` падает на schema | Проверь права в Phase 4.3. Возможно `gen_user` не owner `default_db`. |
| Frontend 200 + `connect-src` violation в консоли | В `Caddyfile` не заменён `api.example.com` внутри CSP. `grep example\.com deploy/Caddyfile`. |
| Worker не берёт jobs | `make prod-tw-logs worker` → нет `Starting worker...` → Redis недоступен. `docker compose -f deploy/docker-compose.prod.timeweb.yml exec redis redis-cli ping`. |

---

## 11. Что НЕ делать в рамках этого runbook'а

- **CRM intergation, YooKassa/Stripe, SMTP** — Sprint 3/4, отложено.
- **CSRF-tokens, rolling refresh, session table** — Sprint 1.
- **Offsite backup (rclone + S3), GPG-шифрование, logrotate** — Sprint 2.
- **Изменение схемы managed DB из панели Timeweb** — всё через alembic-миграции.
- **Хранение `.env.production` в git** — он в `.gitignore`. Оператор хранит его **только** в password manager.

---

## 12. Референсы

- `deploy/docker-compose.prod.timeweb.yml` — compose-файл для этой топологии.
- `deploy/Caddyfile` — общий (domain-replacement делается sed'ом в 3.3).
- `deploy/backup/pg_dump_managed.sh` / `restore_managed.sh` — backup/restore для managed БД.
- `.env.production.template` — вариант B (managed Postgres).
- `Makefile` — цели `prod-tw-*`.
- `docs/deploy/SERVER_SETUP.md` — альтернативный вариант A (postgres в docker).
- `docs/deploy/BACKUP_RESTORE.md` — drill / rotation / disaster recovery.
- `docs/deploy/PRODUCTION_CHECKLIST.md` — Gate A / B / C acceptance.
- `docs/deploy/GATE_SIGNOFFS.md` — журнал sign-off'ов.
