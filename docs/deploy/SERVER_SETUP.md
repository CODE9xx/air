# Server Setup — Code9 Analytics (staging / closed pilot)

Инструкция для деплоя MVP на одну VPS (Ubuntu 22.04/24.04) через Docker Compose + Caddy HTTPS. Рассчитано на single-operator staging — не production с реальными платежами. Прохождение Gate A/B/C — см. `PRODUCTION_CHECKLIST.md`.

## Выбор топологии

Поддерживаются две:

- **Вариант A — всё в docker на одной VPS** (этот документ). Postgres/Redis/api/worker/scheduler/web/caddy запускаются compose'ом из `deploy/docker-compose.prod.yml`. Минимум внешних зависимостей, но бэкапы и масштабирование БД на тебе.
- **Вариант B — VPS + managed Postgres** (Timeweb Cloud, Yandex Managed DB, Supabase, Neon и т.п.). VPS держит только web/api/worker/scheduler/caddy/redis, БД — внешний managed-кластер через приватный IP. Compose: `deploy/docker-compose.prod.timeweb.yml`. Инструкция: **`docs/deploy/INSTALL_TIMEWEB.md`**.

Если у тебя Timeweb VPS + Timeweb managed Postgres — читай `INSTALL_TIMEWEB.md` и возвращайся сюда только за ссылками на общие разделы (firewall, Caddyfile, backup/restore drill). Дальше по этому документу — только Вариант A.

## 1. Требования к серверу

| Размер          | vCPU | RAM  | SSD   | Назначение                           |
|-----------------|------|------|-------|--------------------------------------|
| Минимум         | 2    | 4 GB | 40 GB | Только demo, 1-2 тестовых workspace  |
| Рекомендовано   | 4    | 8 GB | 80 GB | Закрытый пилот, ≤10 workspace        |
| С запасом       | 8    | 16 GB | 160 GB | Перед открытым бетой, managed Postgres отдельно |

ОС: Ubuntu 22.04 LTS или 24.04 LTS. Debian 12 тоже подходит. Остальные — адаптировать apt-команды.

Домены: два A-записи на IP сервера:
- `app.example.com` → frontend (Next.js)
- `api.example.com` → FastAPI

Один домен с `/api` подпутем тоже возможен, но split упрощает CORS, cookies и security headers — предпочтительнее.

## 2. Подготовка ОС

```bash
# --- подключение как root или sudo-пользователь ---
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl make htop ufw ca-certificates gnupg lsb-release

# --- создать отдельного пользователя для приложения (не root) ---
sudo adduser --disabled-password --gecos "" code9
sudo usermod -aG sudo code9
sudo mkdir -p /home/code9/.ssh
sudo cp ~/.ssh/authorized_keys /home/code9/.ssh/authorized_keys
sudo chown -R code9:code9 /home/code9/.ssh
sudo chmod 700 /home/code9/.ssh
sudo chmod 600 /home/code9/.ssh/authorized_keys
```

Дальнейшие команды выполнять из-под `code9`.

## 3. Docker Engine + Compose plugin

По официальной инструкции Docker для Ubuntu:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker code9
# Перелогиниться, чтобы применилось членство в docker-group
exit
# ssh code9@server
```

Проверка:
```bash
docker run --rm hello-world
docker compose version
```

## 4. Firewall (ufw)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp         # HTTP → Caddy автоматический редирект на HTTPS
sudo ufw allow 443/tcp        # HTTPS
sudo ufw allow 443/udp        # HTTP/3 (QUIC)
sudo ufw enable
sudo ufw status verbose
```

Postgres (`5432`) и Redis (`6379`) в compose bind на `127.0.0.1` — снаружи недоступны. Проверь после запуска:
```bash
# локально: должно быть только 127.0.0.1
ss -tlnp | grep -E "5432|6379"

# снаружи (с ДРУГОЙ машины, не с сервера):
# TCP-порт проверяем через nc, а не curl — curl ждёт HTTP и даст ложное OK/FAIL.
nc -zv -w 5 <public-ip> 5432   # ожидается: Connection refused / timeout
nc -zv -w 5 <public-ip> 6379   # ожидается: Connection refused / timeout
```

## 5. Клонирование проекта

```bash
sudo mkdir -p /opt/code9-analytics
sudo chown code9:code9 /opt/code9-analytics
cd /opt
git clone <repo-url> code9-analytics
cd code9-analytics
```

## 6. Секреты и .env.production

```bash
cp .env.production.template .env.production
chmod 600 .env.production
```

Сгенерируй секреты локально и вставь:

```bash
# JWT_SECRET и ADMIN_JWT_SECRET (разные!)
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# FERNET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# ADMIN_BOOTSTRAP_PASSWORD (минимум 16 символов, сменить после первого логина)
python3 -c "import secrets; print(secrets.token_urlsafe(16))"
```

Открой `nano .env.production` и заполни:
- `PUBLIC_APP_URL=https://app.yourdomain.com`
- `PUBLIC_API_URL=https://api.yourdomain.com`
- `ALLOWED_ORIGINS=https://app.yourdomain.com`
- `CORS_ORIGINS=https://app.yourdomain.com`
- `NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1`
- `NEXT_PUBLIC_APP_URL=https://app.yourdomain.com`
- все `CHANGE_ME_*`

Проверь что `APP_ENV=production` — без этого fail-fast валидатор не сработает, а продовая гигиена не гарантируется.

## 7. Caddyfile

```bash
nano deploy/Caddyfile
```

Замени ВСЕ вхождения доменов-примеров на реальные:
1. `app.example.com` → твой frontend-домен (site-блок).
2. `api.example.com` → твой API-домен (site-блок **и внутри CSP** — см. ниже).
3. `admin@example.com` → email для Let's Encrypt (ACME contact).

**Важно про CSP**: в site-блоке для `app.` есть директива `Content-Security-Policy` со строкой `connect-src 'self' https://api.example.com`. Это разрешение, куда fetch/XHR может ходить из браузера — **если не заменить `api.example.com` на реальный API-домен, браузер заблокирует все запросы от фронтенда к API (CSP violation)**. Проверь grep'ом, что ни одного `example.com` не осталось:

```bash
grep -n "example\.com" deploy/Caddyfile    # должно быть пусто
```

DNS должен быть прописан ДО первого запуска, иначе Caddy не получит Let's Encrypt-сертификат.

Для теста перед реальным DNS можно раскомментировать `acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` в глобальном блоке — Let's Encrypt staging выпускает самоподписанные сертификаты без rate-limit, но браузер будет ругаться.

## 8. Первый запуск

```bash
# проверить валидность compose
make prod-config

# собрать образы (5-10 мин на слабой VPS)
make prod-build

# запустить
make prod-up

# подождать 30 сек, пока Postgres поднимется и Caddy получит сертификат
make prod-ps

# применить миграции (main schema)
make prod-migrate

# создать админа (ОДНОРАЗОВО)
make prod-seed

# проверить health
curl -I https://api.yourdomain.com/api/v1/health
# или
make prod-smoke DOMAIN=https://api.yourdomain.com
```

## 9. Верификация после запуска

Пройди чек-лист из `PRODUCTION_CHECKLIST.md` — Gate A.

Минимум, который обязательно должен быть зелёным:
- `curl -I https://app.yourdomain.com` → 200
- `curl -I https://api.yourdomain.com/api/v1/health` → 200
- Postgres/Redis не торчат наружу (`ss -tlnp` показывает только 127.0.0.1)
- `docker compose -f deploy/docker-compose.prod.yml logs api | grep -Ei "bearer|secret|fernet|jwt_secret"` → **пусто**
- Зарегистрировать пользователя в UI → email-код приходит в `docker compose logs api` (SMTP в Sprint 3)
- Залогиниться → cookie `refresh_token` с `HttpOnly; Secure; SameSite=Lax`
- Создать workspace → подключить mock-amoCRM → запустить audit → увидеть dashboard
- Зайти в admin panel как `admin@yourdomain.com` → увидеть список workspace / базовую страницу (Gate A)

Полный admin support-mode (start с reason → запись в `admin_audit_logs`) — часть Gate B (CR-07, Sprint 1). Для Gate A достаточно, что админ логинится и видит базовую admin-страницу.

Если хоть один пункт фэйлит — открывай `docs/qa/DEFECTS.md` и фиксируй.

## 10. Backup

Сначала создай директорию под бэкапы с правильными правами:
```bash
sudo mkdir -p /var/backups/code9
sudo chown code9:code9 /var/backups/code9
sudo chmod 700 /var/backups/code9
```

Настрой cron у пользователя `code9`:
```bash
crontab -e
# Добавить:
0 3 * * * PROJECT_DIR=/opt/code9-analytics bash /opt/code9-analytics/deploy/backup/pg_dump.sh >> /var/log/code9-backup.log 2>&1
```

Права на /var/log:
```bash
sudo touch /var/log/code9-backup.log
sudo chown code9:code9 /var/log/code9-backup.log
sudo chmod 600 /var/log/code9-backup.log
```

И обязательно — **restore drill** до первого клиента. Инструкция в `BACKUP_RESTORE.md`.

## 11. Обновление

```bash
cd /opt/code9-analytics
git pull
make prod-build
make prod-up           # Compose пересоздаст только изменённые контейнеры
make prod-migrate       # если миграции
```

Перед каждым deploy — снятый свежий backup: `make prod-backup`.

## 12. Известные ограничения MVP

- SMTP не настроен (Sprint 3) — email-коды только в логах API.
- CSRF-tokens не реализованы (Sprint 1). Cookie `SameSite=Lax` даёт частичную защиту, но не 100%.
- Refresh token rotation не реализован (Sprint 1). Украденный refresh действителен 30 дней.
- Реальные amoCRM/Kommo/Bitrix24 API не подключены (Sprint 4). `MOCK_CRM_MODE=true` использует фикстуры.
- Платежи mock (Sprint 4).

См. `docs/qa/DEFECTS.md` и `docs/architecture/WAVE4_REPORT.md` для полного списка deferred items.

## 13. Troubleshooting

| Симптом                                     | Причина / fix                                                                                     |
|---------------------------------------------|--------------------------------------------------------------------------------------------------|
| Caddy: `obtaining certificate: timeout`     | DNS не прописан или ufw блокирует 80. Проверь `dig app.yourdomain.com` и `sudo ufw status`.       |
| `make prod-up` падает на api                | Fail-fast валидатор: одно из JWT_SECRET/ADMIN_JWT_SECRET/FERNET_KEY равно CHANGE_ME. Посмотри `make prod-logs`. |
| `alembic upgrade head` падает               | `.env.production` не содержит DATABASE_URL или Postgres ещё не поднялся. Подожди 30 сек + `make prod-ps`. |
| 502 от api.yourdomain.com                   | Api-контейнер упал. `make prod-logs` + `make prod-shell-api`.                                     |
| worker не берёт jobs                         | Redis не доступен или wrong queue names. `make prod-logs | grep worker`.                          |
| Нельзя войти в admin panel                   | `make prod-seed` не выполнялся или пароль другой. Проверь `.env.production → ADMIN_BOOTSTRAP_*`. |
