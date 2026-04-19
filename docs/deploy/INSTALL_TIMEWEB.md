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
# Gate A: console (коды видны в логах api), Gate B: smtp — см. "Phase 1 — SMTP" ниже.
EMAIL_BACKEND=console
DEV_EMAIL_MODE=log
SMTP_HOST=
SMTP_PORT=587
SMTP_MODE=starttls
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=noreply@$DOMAIN_APP
SMTP_TIMEOUT_SECONDS=10

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

## 9a. Gate B Phase 1 — включение Timeweb SMTP

> Делается **после** Gate A (контейнеры healthy, `https://$DOMAIN_APP` открывается,
> регистрация + логин через console-коды в логах уже работают).
> Цель: заменить console-backend на реальную отправку через Timeweb SMTP, чтобы
> письма по сбросу пароля / подтверждению e-mail / подтверждению удаления
> подключения приходили на ящик пользователя.

### 9a.1. На стороне Timeweb — завести почтовый ящик

Выполняется вручную в панели Timeweb (агент не имеет туда доступа):

1. Панель Timeweb → **Почта** → выбрать домен `$DOMAIN_APP` → **Создать ящик**:
   - Имя: `noreply`
   - Пароль: сгенерируй (password manager).
2. Открой карточку ящика → вкладка **Настройки SMTP**. Запиши:
   - SMTP-host: обычно `smtp.timeweb.ru`
   - Порты: `465` (SSL) и `587` (STARTTLS).
3. Вкладка **DKIM** → скопируй DNS-запись и добавь её в DNS зоны `$DOMAIN_APP`:
   - `default._domainkey.$DOMAIN_APP TXT "v=DKIM1; k=rsa; p=..."`
4. Добавь SPF и DMARC в DNS зоны:
   - `@ TXT "v=spf1 include:_spf.timeweb.ru ~all"`
   - `_dmarc.$DOMAIN_APP TXT "v=DMARC1; p=quarantine; rua=mailto:postmaster@$DOMAIN_APP"`
5. Подожди 5–10 минут, проверь:
   ```bash
   dig +short TXT $DOMAIN_APP | grep spf
   dig +short TXT default._domainkey.$DOMAIN_APP
   dig +short TXT _dmarc.$DOMAIN_APP
   ```

### 9a.2. На VPS — обновить .env.production и перезапустить api/worker

```bash
cd /opt/code9-analytics

# Бэкап текущего .env
cp .env.production .env.production.$(date -u +%Y%m%dT%H%M%SZ).bak

# Открыть и заменить блок Email (см. .env.production.template, секция Gate B).
nano .env.production
```

Нужные значения:

```ini
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.timeweb.ru
SMTP_PORT=465
SMTP_MODE=ssl              # если 465. Для 587 → starttls
SMTP_USER=noreply@$DOMAIN_APP
SMTP_PASSWORD=<пароль_из_шага_9a.1>
SMTP_FROM=noreply@$DOMAIN_APP
SMTP_TIMEOUT_SECONDS=10
```

Перезапуск:

```bash
make prod-tw-down
make prod-tw-up
make prod-tw-ps           # api / worker / scheduler healthy
make prod-tw-logs api | tail -n 50 | grep -iE "smtp|email"   # не должно быть traceback'ов
```

**Fail-fast guard:** если `APP_ENV=production` + `EMAIL_BACKEND=smtp` + пустой
`SMTP_HOST` — api-контейнер не стартует (валидатор в `app.core.settings`).
Это дешёвая страховка от «забыл подставить» — не баг, а фича.

### 9a.3. Тестовая доставка

Цель: убедиться, что письмо реально приходит на внешний ящик.

```bash
# 1. Зарегистрируй тестового пользователя с ящиком, к которому у тебя есть доступ:
curl -sS -X POST https://$DOMAIN_API/api/v1/auth/password-reset/request \
     -H "Content-Type: application/json" \
     -d '{"email":"kyzx@yandex.ru"}'
# → 204 (анти-энумерация, всегда 204)

# 2. Проверь логи:
make prod-tw-logs api | grep email_sent | tail -n 5
# → должна быть запись backend=smtp, subject=..., без кода в теле лога.

# 3. Открой входящие kyzx@yandex.ru — в папке "Входящие" или "Спам" должно
#    быть письмо "Code9: сброс пароля" с 6-значным кодом.
```

Если письмо в спаме — значит DKIM/SPF/DMARC ещё не пропагнулись. Подожди
15–30 минут, проверь `dig` ещё раз, повтори.

Если письмо не пришло вообще, смотри `email_send_failed` в логах. Типовые
причины (в логе `error_type`):

- `SMTPAuthenticationError` → пароль ящика неправильный.
- `SMTPConnectError` / `socket.timeout` → Timeweb режет outbound 465 с VPS
  (бывает при новом аккаунте — пиши в саппорт) или неправильный host/port.
- `SMTPSenderRefused` → `SMTP_FROM` не совпадает с `SMTP_USER` (Timeweb
  требует `From:` = аутентифицированный ящик).

### 9a.4. Acceptance для Gate B Phase 1

- [ ] `EMAIL_BACKEND=smtp`, `SMTP_HOST=smtp.timeweb.ru`, `SMTP_FROM=noreply@$DOMAIN_APP`.
- [ ] `make prod-tw-ps` — api / worker / scheduler healthy.
- [ ] `/auth/password-reset/request` → 204, в логах `email_sent backend=smtp`.
- [ ] Письмо пришло на тестовый внешний ящик (не спам).
- [ ] `docker compose logs api | grep -iE "SMTP_PASSWORD|pwd="` пусто
      (секрет не утёк в логи).

После выполнения — добавь строку в `docs/deploy/GATE_SIGNOFFS.md` → Gate B log
с датой и commit SHA. Phase 2 (amoCRM OAuth + pull) можно запускать только
после этой галочки.

---

## 9b. Gate B Phase 2A — регистрация amoCRM OAuth и включение real CRM

> Делается **после** §9a (SMTP работает, письма доставляются на внешний ящик).
> Цель: зарегистрировать OAuth-приложение в amoCRM, прописать `AMOCRM_CLIENT_ID`
> / `AMOCRM_CLIENT_SECRET` / `AMOCRM_REDIRECT_URI` в `.env.production`,
> переключить `MOCK_CRM_MODE=false` и проверить, что реальный клиент может
> подключить свой аккаунт amoCRM через UI.
>
> **ВАЖНО — backend-код Phase 2A.** OAuth-callback (обмен `code` → tokens,
> Fernet-шифрование, enqueue `bootstrap_tenant_schema` → `pull_amocrm_core`)
> уже описан в `apps/api/app/crm/oauth_router.py` и
> `apps/api/app/core/crypto.py`, но может быть ещё не задеплоен. Перед
> запуском §9b оператор **обязан** убедиться, что на VPS собран образ с
> этим кодом — см. §9b.4. Иначе `MOCK_CRM_MODE=false` приведёт к 501 на
> `/integrations/amocrm/oauth/start`.
>
> **Scope §9b — только amoCRM.** Kommo/Bitrix24 в backend пока обозначены
> только placeholder'ами (`app/db/models/enums.py` `Provider.KOMMO`, stub в
> `crm_connectors.factory`); для реальной интеграции нужен отдельный connector
> — Phase 2C/Sprint 4.

### 9b.1. Что даёт эта фаза клиенту

- Клиент жмёт **«Подключить amoCRM»** → amoCRM открывает страницу
  авторизации → клиент разрешает доступ → возврат на
  `https://$DOMAIN_APP/app/connections/<id>?flash=amocrm_connected`.
- Backend шифрует `access_token` / `refresh_token` (Fernet, `FERNET_KEY`) и
  кладёт в `crm_connections` — **plaintext токенов в БД нет**.
- Сразу стартует `bootstrap_tenant_schema` → `pull_amocrm_core` (первичная
  выгрузка pipelines / stages / users / deals / contacts).

### 9b.2. Регистрация OAuth-приложения в amoCRM (оператор, 10 мин)

Делается человеком в панели **своего** amoCRM-аккаунта (`https://<твой>.amocrm.ru`):

1. **Настройки** → **Интеграции** → справа вверху **«Создать интеграцию»** → выбираем **«Внешняя интеграция»** (OAuth 2.0).
2. Заполняем карточку:
   - **Название**: `Code9 Analytics`
   - **Описание**: `AI-аналитика воронок продаж по данным amoCRM`
   - **Ссылка для перенаправления (redirect_uri)** — копируем **посимвольно**:

     ```
     https://api.aicode9.ru/api/v1/integrations/amocrm/oauth/callback
     ```

     (для другого домена — `https://$DOMAIN_API/api/v1/integrations/amocrm/oauth/callback`).
     Если в панели amoCRM будет другой URI — exchange_code вернёт
     `invalid_grant` и пользователь увидит flash `amocrm_invalid_grant` (см. §9b.6).

   - **Права доступа**: минимально — **«Сделки»**, **«Контакты»**, **«Компании»**,
     **«Пользователи»**, **«Задачи»** (для Phase 2A pull достаточно первых четырёх;
     задачи / беседы / письма — Phase 2B/2C).
   - **Согласие с политикой** → поставить галочку.

3. Сохранить → amoCRM открывает карточку интеграции с **«ID интеграции»**
   (`client_id`) и **«Секретный ключ»** (`client_secret`). **Секретный ключ
   видно ТОЛЬКО при первом показе** — скопируй в password manager
   немедленно. Если потерял — надо пересоздать интеграцию (amoCRM не даст
   посмотреть секрет повторно).

4. **НЕ коммить** эти значения в git. Сохрани локально:
   - `AMOCRM_CLIENT_ID` = ID интеграции
   - `AMOCRM_CLIENT_SECRET` = секретный ключ

### 9b.3. Обновить .env.production на VPS

Значения подставляет оператор вручную (агент **не должен** получать секрет
в своём промпте):

```bash
cd /opt/code9-analytics

# Бэкап текущего .env
cp .env.production .env.production.$(date -u +%Y%m%dT%H%M%SZ).bak

nano .env.production
```

Нужные правки (блок `# --- Real CRM OAuth`):

```ini
# Переключаем на реальные CRM:
MOCK_CRM_MODE=false

AMOCRM_CLIENT_ID=<ID интеграции из amoCRM>
AMOCRM_CLIENT_SECRET=<секретный ключ из amoCRM>
AMOCRM_REDIRECT_URI=https://api.aicode9.ru/api/v1/integrations/amocrm/oauth/callback
```

**Fail-fast guard** (`app/core/settings.py::check_prod_secrets`): если
`APP_ENV=production` + `MOCK_CRM_MODE=false`, но хотя бы один из
`AMOCRM_CLIENT_ID` / `AMOCRM_CLIENT_SECRET` / `AMOCRM_REDIRECT_URI` пустой —
api-контейнер **не стартует**. Дополнительно `AMOCRM_REDIRECT_URI` обязан
начинаться с `https://` (amoCRM не принимает http в prod).

```bash
# Проверка: в .env.production нет CHANGE_ME, AMOCRM_* заполнены, MOCK=false
grep -E '^(MOCK_CRM_MODE|AMOCRM_REDIRECT_URI)=' .env.production
grep -c '^AMOCRM_CLIENT_ID=.\+$' .env.production   # → 1
grep -c '^AMOCRM_CLIENT_SECRET=.\+$' .env.production   # → 1
```

### 9b.4. Пересобрать и перезапустить api / worker / scheduler

OAuth-callback, `crypto.py` и `pull_amocrm_core` живут в образах api и worker.
После `git pull` на VPS образы нужно **пересобрать** — runtime-env один, но
код вшит в слой образа:

```bash
cd /opt/code9-analytics
git pull --ff-only

# Sanity-check: файлы на месте (если нет — код Phase 2A ещё не смержен в твою ветку):
test -f apps/api/app/crm/oauth_router.py && echo "oauth_router: ok"
test -f apps/api/app/core/crypto.py      && echo "crypto:       ok"
test -f apps/worker/worker/jobs/crm_pull.py && echo "crm_pull:    ok"

# Пересборка (≈3–8 мин):
docker compose -f deploy/docker-compose.prod.timeweb.yml build api worker scheduler

# Перезапуск ТОЛЬКО api/worker/scheduler (caddy/web/redis не трогаем — без downtime для SPA):
docker compose -f deploy/docker-compose.prod.timeweb.yml up -d --force-recreate api worker scheduler

# Убедиться, что api прошёл prod-валидатор:
docker compose -f deploy/docker-compose.prod.timeweb.yml ps
docker compose -f deploy/docker-compose.prod.timeweb.yml logs api --since=2m | grep -Ei 'error|traceback|fail-fast' || echo "✓ нет ошибок старта"
```

**abort**:
- Если в логах api при старте — `ValueError: MOCK_CRM_MODE=false, но не заполнены: AMOCRM_...` → вернись в §9b.3, проверь `.env.production`.
- Если импорт `app.core.crypto` / `crm_connectors.amocrm` падает → Phase 2A backend ещё не смержен в твою ветку → откати `MOCK_CRM_MODE=true` в `.env.production`, перезапусти api.

### 9b.5. UI-проверка: подключение реального amoCRM

Из браузера под живым пользователем:

1. `https://$DOMAIN_APP/ru/app/connections/new` → кнопка «Подключить amoCRM».
   - **Если UI ещё вызывает `POST /crm/connections/mock-amocrm` напрямую**
     (старый mock-flow, apps/web/app/[locale]/app/connections/new/page.tsx) —
     это значит Phase 2B UI change не докатился. Открой `/app/connections/new`
     в DevTools → Network и проверь, какой endpoint дёргает кнопка:
     - Ожидаемо: `GET /api/v1/integrations/amocrm/oauth/start?workspace_id=...`
       → возвращает JSON `{"mock": false, "authorize_url": "https://www.amocrm.com/oauth?...", "connection_id": "...", "state": "..."}`.
     - Фронт должен сделать `window.location.assign(authorize_url)`.
   - Как быстрый обходной путь можно вручную дёрнуть `start` из DevTools:
     `fetch('/api/v1/integrations/amocrm/oauth/start?workspace_id=<uuid>', {credentials: 'include'}).then(r=>r.json()).then(console.log)`
     — взять `authorize_url` и перейти по нему.
2. amoCRM показывает экран авторизации: «Разрешить Code9 Analytics доступ к вашему аккаунту».
   - **«Разрешить»** → редирект на callback → BE выполняет exchange_code +
     fetch_account + Fernet-encrypt + enqueue jobs → редирект на
     `https://$DOMAIN_APP/app/connections/<id>?flash=amocrm_connected`.
   - **«Отмена»** → redirect на callback с `error=access_denied` →
     редирект на `/app/connections?flash=amocrm_cancelled`.
3. На странице `/app/connections/<id>` статус подключения должен стать
   **`active`**, появиться `external_account_id`, `external_domain`
   (`<subdomain>.amocrm.ru`).
4. Через 1–2 минуты в workspace появятся pipelines / stages / users
   (первая страница `pull_amocrm_core`). Полный дамп зависит от объёма
   аккаунта — сотни тысяч сделок могут тянуться часами (пагинация по 250).

### 9b.6. Безопасные команды для логов / диагностики

Все три команды исключают токены и пароли из вывода:

```bash
# 1) OAuth start/callback работают, без secrets:
docker compose -f deploy/docker-compose.prod.timeweb.yml logs api --since=15m \
  | grep -E 'amocrm_oauth_(started|completed|user_declined|state_miss|no_subdomain)|amocrm_(exchange|fetch_account|token_encrypt)_' \
  | head -n 20

# 2) Sanity: секретов НЕТ в логах (должно быть пусто):
docker compose -f deploy/docker-compose.prod.timeweb.yml logs api --since=15m \
  | grep -iE 'client_secret|access_token|refresh_token|Bearer [A-Za-z0-9]|AMOCRM_CLIENT_SECRET|FERNET_KEY'

# 3) Worker — bootstrap + первый pull прошли:
docker compose -f deploy/docker-compose.prod.timeweb.yml logs worker --since=15m \
  | grep -E 'bootstrap_tenant_schema|pull_amocrm_core' | head -n 30
```

Каждое подключение в Redis оставляет ключ `oauth_state:amocrm:<random>` с
TTL 600s — сразу удаляется после успешного callback'а (защита от replay).
Проверить «висящие» state'ы:

```bash
docker compose -f deploy/docker-compose.prod.timeweb.yml exec redis \
  redis-cli --scan --pattern 'oauth_state:amocrm:*' | head
```

Ожидаемо: ничего (или 1-2 свежих, если сейчас идёт OAuth). Если висит сотня —
state тикнулись, но ни один callback не отработал → проблема на redirect_uri
/ firewall / DNS `api.aicode9.ru`.

### 9b.7. Troubleshooting типовых ошибок

Флеши в URL приходят на `/app/connections[/<id>]?flash=<код>`:

| Flash                         | Причина                                                                                       | Что делать                                                                                                                                             |
|-------------------------------|-----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| `amocrm_cancelled`            | Пользователь нажал «Отмена» в amoCRM.                                                        | Норма. Просто просим попробовать ещё раз.                                                                                                              |
| `amocrm_bad_referer`          | amoCRM вернул callback без query-параметра `referer`, поэтому нельзя определить subdomain.    | Редкий случай: amoCRM-портал сменил поведение. Смотри `amocrm_oauth_no_subdomain` в логах; при повторении — заводим issue, даём workaround в UI.       |
| `amocrm_invalid_grant`        | amoCRM отклонил authorization_code (`400 hint=invalid_grant`). Обычно — mismatch redirect_uri. | 1) Проверь `AMOCRM_REDIRECT_URI` в `.env.production` **посимвольно** == редиректу в панели amoCRM. 2) code живёт ~20 сек — не ретраить старый callback. |
| `amocrm_exchange_failed`      | Сеть / 5xx / таймаут при обмене code → token.                                                  | `docker compose logs api --since=5m \| grep amocrm_exchange_failed` — смотри `error_type`. 5xx amoCRM — ждём; таймаут — проверь outbound TCP.          |
| `amocrm_connected`            | Успех. Подключение active.                                                                    | —                                                                                                                                                      |
| `mock_oauth_ok`               | `MOCK_CRM_MODE=true` всё ещё активен.                                                         | Если ожидался real OAuth — вернись в §9b.3 и смени `MOCK_CRM_MODE`.                                                                                    |
| `amocrm_credentials_missing`  | `AMOCRM_AUTH_MODE=external_button`: amoCRM не прислала webhook с credentials за `AMOCRM_EXTERNAL_WAIT_SECONDS`. | 1) Проверь, что webhook доставляется: `docker compose logs api --since=5m \| grep amocrm_external_credentials`. 2) Проверь, что `AMOCRM_SECRETS_URI` (или legacy `AMOCRM_EXTERNAL_WEBHOOK_URL`) посимвольно совпадает с Secrets URI в панели amoCRM. 3) Увеличь `AMOCRM_EXTERNAL_WAIT_SECONDS` если сеть медленная. Попроси пользователя начать заново. |

Ошибки HTTP на стороне BE:

| Ответ `/oauth/start` | Причина                                                                                  | Что делать                                                                                       |
|----------------------|------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| 501 `configuration_error` + `amocrm_connector_import_failed` | PYTHONPATH не содержит `/packages/crm-connectors/src`. | Проверь `deploy/docker-compose.prod.timeweb.yml` → api/worker service → `PYTHONPATH`. Должно быть `/app:/app/scripts:/packages/ai/src:/packages/crm-connectors/src`. Пересобери. |
| 501 `configuration_error` + `AMOCRM_CLIENT_ID не задан` | `.env.production` не подмонтирован / `AMOCRM_CLIENT_ID` пустой. | §9b.3, затем `up -d --force-recreate api`. |
| 403 `forbidden`      | Пользователь не owner/admin workspace.                                                    | Пригласи его с ролью owner/admin или используй другого.                                          |
| 404 `not_found`      | `workspace_id` не принадлежит пользователю / workspace удалён.                            | Проверь UUID в URL start-запроса.                                                               |

Ошибка `/oauth/callback`:

| Ответ | Причина | Что делать |
|-------|---------|------------|
| 400 `invalid_state` | state истёк (TTL 10 мин), подменён, или уже использован (replay). | Попроси пользователя начать заново. Если повторяется систематически — проверь clock drift на VPS (`timedatectl`) и Redis (`docker compose exec redis redis-cli time`). |
| 500 + `amocrm_token_encrypt_failed` в логах | `FERNET_KEY` отсутствует / битый / поменялся между deploy'ами. | `grep FERNET_KEY .env.production` → 44-байтный base64. Если ключ был изменён после первых подключений — старые зашифрованные токены потеряны, надо переподключать. |

### 9b.8. Безопасность (операционные правила для Gate B Phase 2A)

- `AMOCRM_CLIENT_SECRET` виден в `.env.production` (mode 600) и только там.
  **Не** пишем его в issue-трекер, чаты, git, Sentry.
- `access_token` / `refresh_token` хранятся в
  `crm_connections.access_token_encrypted` / `refresh_token_encrypted` как
  Fernet-ciphertext. Plaintext не кладём ни в БД, ни в `metadata_json`,
  ни в `payload` jobs.
- amoCRM ротирует `refresh_token` на каждом `refresh` — worker должен
  сохранять **новый** refresh, а не переиспользовать старый
  (`_token_pair_from_response` уже делает правильно). Если увидишь, что
  через 24 часа все подключения внезапно ушли в `lost_token` — первым делом
  проверь, что `refresh` job в worker'е пишет новый refresh в БД.
- Любое попадание `access_token` / `refresh_token` / `client_secret` в
  stdout / stderr / Sentry — **incident**, повод для ротации client_secret
  в amoCRM (создать новую интеграцию, обновить `.env.production`, убить
  старую в amoCRM).

### 9b.9. Acceptance для Gate B Phase 2A

- [ ] В amoCRM создана интеграция «Code9 Analytics», redirect_uri посимвольно совпадает с `AMOCRM_REDIRECT_URI`.
- [ ] `.env.production` на VPS содержит `MOCK_CRM_MODE=false`, заполненные `AMOCRM_CLIENT_ID`, `AMOCRM_CLIENT_SECRET`, `AMOCRM_REDIRECT_URI`. Mode 600, не в git.
- [ ] `docker compose -f deploy/docker-compose.prod.timeweb.yml ps` — api/worker/scheduler healthy после пересборки.
- [ ] Реальное подключение прошло: flash `amocrm_connected`, `crm_connections.status=active`, `external_account_id` / `external_domain` заполнены.
- [ ] В логах api есть `amocrm_oauth_started` + `amocrm_oauth_completed`; нет `client_secret` / `access_token` / `Bearer <...>`.
- [ ] Worker стартанул `bootstrap_tenant_schema` → `pull_amocrm_core`, оба перешли в `finished` без `InvalidGrant` / `TokenExpired`.
- [ ] `/app/connections/<id>` в UI показывает pipelines / stages / users клиента.

После выполнения — добавь строку в `docs/deploy/GATE_SIGNOFFS.md` → Gate B
log (колонка «Клиенты» — кто первый прошёл real OAuth, в скобках subdomain
amoCRM). Phase 2B (chats, tasks, calls, companies, retention) можно
запускать только после этой галочки.

### 9b.10. Альтернативный режим: `AMOCRM_AUTH_MODE=external_button` (#44.6)

Начиная с задачи #44.6 backend поддерживает **два режима** получения
`client_id` / `client_secret` amoCRM:

| Режим             | Когда использовать                                                                                                 | `AMOCRM_CLIENT_ID/SECRET`      | Secrets URI                                                      |
|-------------------|--------------------------------------------------------------------------------------------------------------------|--------------------------------|------------------------------------------------------------------|
| `static_client`   | Классика OAuth 2.0: одна зарегистрированная интеграция → все клиенты используют одну пару credentials (§9b.2–9b.9). | **обязательны в `.env`**       | не используется                                                 |
| `external_button` | Маркетплейс amoCRM: amoCRM сама создаёт интеграцию в момент установки и шлёт per-install credentials на наш backend. | **пустые** (игнорируются)      | `AMOCRM_SECRETS_URI` обязателен (в панели amoCRM ↔ backend). Legacy alias `AMOCRM_EXTERNAL_WEBHOOK_URL` поддерживается, но не рекомендуется. |

**Когда это нужно.** Если в маркетплейсе amoCRM предполагается, что клиенты
ставят интеграцию **кнопкой «Установить»** из каталога (и каждая установка =
новая интеграция с своим `client_id`/`client_secret`), режим
`static_client` не подходит — нужен `external_button`.

**Как включить.**

1. В панели разработчика amoCRM для своей интеграции укажи **Secrets URI**
   (amoCRM data-secrets_uri):

    ```
    https://api.aicode9.ru/api/v1/integrations/amocrm/external/secrets
    ```

    (он же `AMOCRM_SECRETS_URI` в `.env.production`). Этот URL ДОЛЖЕН
    совпадать посимвольно. `redirect_uri` остаётся прежним:
    `https://api.aicode9.ru/api/v1/integrations/amocrm/oauth/callback`.

    Backend также слушает legacy alias
    `https://api.aicode9.ru/api/v1/integrations/amocrm/external/credentials`
    — тот же handler, тот же контракт. Для новых интеграций используй
    primary путь `/external/secrets`.

2. Обнови `.env.production`:

    ```ini
    MOCK_CRM_MODE=false
    AMOCRM_AUTH_MODE=external_button

    # static-поля для external_button НЕ нужны — оставь пустыми
    AMOCRM_CLIENT_ID=
    AMOCRM_CLIENT_SECRET=

    AMOCRM_REDIRECT_URI=https://api.aicode9.ru/api/v1/integrations/amocrm/oauth/callback
    AMOCRM_SECRETS_URI=https://api.aicode9.ru/api/v1/integrations/amocrm/external/secrets
    # Deprecated legacy alias. Оставляй пустым, если задан AMOCRM_SECRETS_URI.
    AMOCRM_EXTERNAL_WEBHOOK_URL=
    AMOCRM_EXTERNAL_WAIT_SECONDS=5.0
    ```

    Fail-fast валидатор в `APP_ENV=production` проверит, что для
    `external_button` заполнены `AMOCRM_SECRETS_URI` (или legacy
    `AMOCRM_EXTERNAL_WEBHOOK_URL`) и `AMOCRM_REDIRECT_URI` (оба
    должны быть `https://`).

3. Пересобери api/worker/scheduler:

    ```bash
    make prod-tw-build
    make prod-tw-up
    ```

4. Проверь button-config:

    ```bash
    curl -s "https://api.aicode9.ru/api/v1/integrations/amocrm/oauth/button-config" | jq .
    # {
    #   "mock": false,
    #   "auth_mode": "external_button",
    #   "redirect_uri": "https://api.aicode9.ru/api/v1/integrations/amocrm/oauth/callback",
    #   "secrets_uri": "https://api.aicode9.ru/api/v1/integrations/amocrm/external/secrets",
    #   "webhook_url": "https://api.aicode9.ru/api/v1/integrations/amocrm/external/secrets",
    #   "wait_seconds": 5.0,
    #   "button": { "name": null, "description": null, "logo": null, "scopes": null, "title": null }
    # }
    ```
    `secrets_uri` — primary. `webhook_url` дублирует его для legacy-фронтов.

**Как это работает под капотом.**

1. Клиент жмёт «Подключить amoCRM» → `GET /integrations/amocrm/oauth/start`
   создаёт pending `CrmConnection`, сохраняет `state` в Redis
   (`oauth_state:amocrm:<state>`, TTL 600s), возвращает
   `{auth_mode: "external_button", connection_id, state, redirect_uri}`.
   `authorize_url=null` — фронт **не редиректит** на amoCRM, а показывает
   клиенту инструкцию «Установите из маркетплейса».

2. Клиент жмёт «Установить» в маркетплейсе amoCRM → amoCRM создаёт
   интеграцию и **синхронно** шлёт `POST /integrations/amocrm/external/secrets`
   (primary; legacy alias `/external/credentials` тоже принимается)
   с `{state, client_id, client_secret, integration_id, account_id, account_subdomain}`.

3. Наш backend:
   - валидирует `state` в Redis (иначе 400 `invalid_state`);
   - проверяет, что пара `state` раньше не обрабатывалась (replay-guard
     через ключ `oauth_pair:amocrm:<state>`, TTL 600s; второй POST → 409);
   - шифрует `client_secret` Fernet-ом и пишет в `crm_connections.amocrm_client_secret_encrypted`;
   - возвращает `204 No Content`.

4. amoCRM редиректит пользователя на наш `redirect_uri` (тот же
   `/integrations/amocrm/oauth/callback?code=...&state=...&referer=...`).

5. Callback видит `auth_mode=external_button` в state-payload → ждёт
   credentials до `AMOCRM_EXTERNAL_WAIT_SECONDS` (polling 0.5s). Если
   webhook уже приехал — дешифрует `client_secret` и обменивает `code` на
   токены тем же `AmoCrmConnector`. Если за таймаут credentials не
   приехали — connection переводится в `failed`, пользователь попадает на
   `/app/connections?flash=amocrm_credentials_missing` (см. §9b.7).

**Замечания по безопасности.**

- `client_secret` **никогда** не пишется в БД plaintext'ом — только через `Fernet(FERNET_KEY).encrypt`.
- `log_mask.py` маскирует `client_secret`, `access_token`, `refresh_token`
  в логах автоматически. Перед прод-запуском проверь:
  `docker compose -f deploy/docker-compose.prod.timeweb.yml logs api --since=5m | grep -iE 'client_secret|Bearer '` — не должно быть значений.
- Webhook'а защищён `state`-парой — amoCRM не может «подсунуть» чужой
  connection без валидного `state` из Redis.
- Включить `external_button` можно только на `https://` webhook (валидатор
  Settings).

**Обратная совместимость.** `AMOCRM_AUTH_MODE=static_client` (default)
работает как раньше — существующие деплои **не меняют ничего**.

### 9b.11. Kommo / Bitrix24 — когда

В backend сейчас только enum `Provider.KOMMO` и stub factory; реальный
connector (`crm_connectors.kommo`, OAuth endpoints, pull jobs) — Phase 2C.
До мерджа соответствующего кода попытка выставить
`provider=kommo` в коде приведёт к `NotImplementedError` в factory.
Этот runbook обновится при запуске Kommo — пока не подключаем.

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

- **CRM integration (real amoCRM/Kommo), YooKassa/Stripe** — Gate B Phase 2 / Sprint 4, отложено.
- **SMTP** — включается в Gate B Phase 1, см. §9a. В Gate A живёт console-backend.
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
