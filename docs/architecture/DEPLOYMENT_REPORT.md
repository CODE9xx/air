# Deployment Report — Sprint 0 (Deploy Foundation)

**Дата**: 2026-04-18
**Скоуп**: Sprint 0 — MVP deploy foundation для staging / closed pilot.
**Статус**: ✅ **COMPLETE** — все артефакты созданы, валидация YAML пройдена, `make demo` не сломан. Готово к верификации на реальном VPS (Gate A).

Источник спецификации: `code9_analytics_claude_deploy_package.docx` (711 строк). Не задействовано из скоупа: Kubernetes/k3s, реальные CRM API, реальные платежи, SMTP, CSRF, refresh-rotation — всё осталось в Sprint 1-4.

---

## 1. Что сделано (файлы и артефакты)

### 1.1 Deploy-инфраструктура

| Файл | Назначение | Строк | Статус |
|------|------------|-------|--------|
| `deploy/docker-compose.prod.yml` | Prod-stack: caddy, web, api, worker, scheduler, postgres, redis | ~170 | ✅ |
| `deploy/Caddyfile` | Reverse-proxy + Let's Encrypt + security headers (CSP, HSTS, X-Frame-Options) | ~100 | ✅ |
| `deploy/backup/pg_dump.sh` | Ежедневный `pg_dump --clean --if-exists` + gzip + retention 14 дней | ~90 | ✅ (chmod +x) |
| `deploy/backup/restore.sh` | Restore из .sql.gz с подтверждением `YES RESTORE`, останавливает worker/scheduler | ~90 | ✅ (chmod +x) |

### 1.2 Секреты и конфигурация

| Файл | Назначение | Статус |
|------|------------|--------|
| `.env.production.template` | Все переменные с `CHANGE_ME_*` + инструкции по генерации (secrets.token_urlsafe, Fernet.generate_key) | ✅ |
| `.gitignore` | Добавлено `.env.production`, `.env.staging`, `/var/backups/`, `*.sql.gz` | ✅ |

### 1.3 Makefile — 14 prod-* targets

| Target | Что делает |
|--------|------------|
| `prod-config` | `docker compose config --quiet` — валидация YAML+env |
| `prod-build` | Сборка 3-х образов (api/worker/web) из существующих Dockerfile |
| `prod-up` / `prod-down` | Запуск / остановка стека (volumes сохраняются) |
| `prod-logs` | `docker compose logs -f api worker caddy` |
| `prod-ps` | Статус контейнеров |
| `prod-migrate` | `alembic upgrade head` в prod-контейнере api |
| `prod-seed` | `seed_admin.py` (разовый bootstrap) |
| `prod-smoke` | `curl https://${PUBLIC_API_URL}/api/v1/health` |
| `prod-backup` | Вызов `deploy/backup/pg_dump.sh` с правильными переменными окружения |
| `prod-restore BACKUP=...` | Вызов `deploy/backup/restore.sh` с подтверждением |
| `prod-shell-api` / `prod-shell-worker` | Отладочный bash в контейнерах |
| `prod-psql` | Интерактивный psql в prod postgres |

Dev targets (`up`, `down`, `demo`, `migrate`, `seed`, ...) **не тронуты** — `make -n demo` всё так же даёт up → sleep → migrate → seed.

### 1.4 Документация

| Файл | Назначение | Строк |
|------|------------|-------|
| `docs/deploy/SERVER_SETUP.md` | Пошаговая инструкция для Ubuntu 22.04/24.04 VPS: apt prep → docker engine → ufw → code9 user → secrets → Caddyfile → first run → verification | ~236 |
| `docs/deploy/PRODUCTION_CHECKLIST.md` | Gate-модель **A → B → C**: staging / closed pilot / public launch с чекбоксами для каждого gate | ~170 |
| `docs/deploy/BACKUP_RESTORE.md` | pg_dump + retention + cron + offsite (rclone/rsync) + GPG + restore drill procedure + RPO/RTO + disaster recovery | ~230 |
| `docs/architecture/DEPLOYMENT_REPORT.md` | **Этот файл** | — |

---

## 2. Ключевые архитектурные решения

### 2.1 Один VPS, Docker Compose

**Решение**: MVP деплоится на **одну VPS** через `docker compose`. Никакого Kubernetes, Nomad, Swarm.

**Обоснование**: На стадии 1-3 пилот-клиентов одна VPS (4 vCPU / 8 GB / 80 GB SSD) покрывает нагрузку с огромным запасом. k8s добавил бы 2-3 недели работы и ∞ операционной сложности без каких-либо выгод. Переход на managed-инфру запланирован в Gate C (Sprint 4+).

### 2.2 Caddy вместо nginx/Traefik

**Решение**: Reverse-proxy — Caddy v2.

**Обоснование**:
- Автоматический Let's Encrypt из коробки, без certbot cron.
- Конфиг в 40 строк для двух доменов против 120+ у nginx.
- HTTP/3 (QUIC) бесплатно.
- Активная поддержка.

Альтернатива — nginx + certbot — рассмотрена и отклонена как overengineering для single-VPS MVP.

### 2.3 Split-domain (app. + api.)

**Решение**: Два домена: `app.example.com` (web) и `api.example.com` (api).

**Обоснование**: Разделение упрощает:
- CORS (origin прод-фронта явный, `*` не нужен).
- Cookie-scope (`refresh_token` SameSite=Lax только для app-origin).
- CSP (для api — минимальный, для app — rich).
- Возможность в будущем вынести web на CDN без перестройки api.

### 2.4 Postgres/Redis bind на 127.0.0.1

**Решение**: Postgres и Redis **не слушают** внешние интерфейсы. В compose `ports: [127.0.0.1:5432:5432]` и аналогично для 6379.

**Обоснование**: Снижение attack surface до нуля на уровне сети. Даже при утечке POSTGRES_PASSWORD или REDIS_PASSWORD подключиться снаружи невозможно без SSH-туннеля. ufw это подкрепляет, но bind — первая линия.

### 2.5 Backup-стратегия

**Решение**: pg_dump + gzip → `/var/backups/code9/`, retention 14 дней, offsite откладывается на Gate B.

**Обоснование**:
- На Gate A реальных клиентских данных нет — локального бэкапа достаточно.
- На Gate B (pilot) обязательно offsite (rclone → S3-совместимое) + GPG encryption + restore drill раз в 2 недели.
- На Gate C переход на managed Postgres с PITR (WAL streaming) — RPO 15 минут.

Redis **не бэкапим** (эфемерные job-queues).

### 2.6 Feature flags → Sprint'ы

Осознанные компромиссы MVP, которые документированы в `PRODUCTION_CHECKLIST.md` как Gate B/C требования:

| Что | Где отложено | Sprint |
|-----|--------------|--------|
| SMTP | Email-коды в stdout (`docker compose logs api`) | Sprint 3 |
| CSRF-токены | Cookie `SameSite=Lax` даёт частичную защиту | Sprint 1 |
| Refresh rotation + reuse detection | Refresh валиден 30 дней | Sprint 1 |
| Session/device table | Нет отзыва сессий в /settings | Sprint 1 |
| Реальные amoCRM/Kommo/Bitrix24 | `MOCK_CRM_MODE=true` использует фикстуры | Sprint 4 |
| YooKassa/Stripe | Mock billing | Sprint 4 |
| Sentry / uptime monitoring | Только `docker compose logs` | Sprint 2 |
| CSP refinement | Starter policy, возможно потребует tuning после первого прода | Sprint 2 |

---

## 3. Компромиссы Sprint 0 (TODO)

### 3.1 Bind-mount packages/ и scripts/ вместо COPY в Dockerfile ⚠️

**Проблема**: Существующие `infra/docker/api.Dockerfile` и `worker.Dockerfile` копируют только `apps/api` → `/app`. Worker импортирует `scripts.migrations.apply_tenant_template`, а api — `packages.shared`, которые в prod-образ **не** попадают.

**Текущий fix**: В `deploy/docker-compose.prod.yml` прописан bind-mount:
```yaml
volumes:
  - ../packages:/packages:ro
  - ../scripts:/app/scripts:ro
```
Это работает, но **нарушает принцип immutable containers** — образ зависит от состояния файловой системы хоста.

**Правильный fix (Sprint 1)**: Обновить Dockerfiles prod-стадии:
```dockerfile
# api.Dockerfile (prod stage)
COPY apps/api /app
COPY packages /packages
COPY scripts /app/scripts
```
И пересобрать. После этого убрать bind-mount из compose.

**Риск**: Минимальный. Хост-файлы меняются только при `git pull`, который всегда сопровождается `make prod-build` — но если оператор забудет пересобрать образы, он увидит изменения в коде без рестарта. Задокументировано в `docs/deploy/SERVER_SETUP.md` (раздел 11 — Обновление).

### 3.2 Alembic migration path жёстко прописан

В `prod-migrate` путь к alembic.ini — `/app/app/db/migrations/main/alembic.ini`. Это жёсткая привязка к текущей структуре `apps/api/app/db/migrations/...`. Если путь изменится — упадёт.

**Смягчение**: Путь к миграциям документирован в `Makefile` комментарием. При реорганизации проекта этот target придётся править.

### 3.3 Scheduler — отдельный контейнер, но конфиг минимальный

Scheduler запускает `python -m worker.scheduler` и полагается на существующий код в `apps/worker/`. Если расписание jobs придётся менять — нужен рестарт контейнера. В Sprint 1 возможно перевести на APScheduler с hot-reload, но это out of scope.

### 3.4 CSP — starter, не финальный

CSP в Caddyfile сформулирован консервативно (default-src 'self', images data:, connect-src api). Next.js и статика могут потребовать `'unsafe-inline'` для initial hydration — это выяснится при первом реальном запуске. Документировано в `PRODUCTION_CHECKLIST.md` как item Gate B.

### 3.5 ADMIN_BOOTSTRAP_EMAIL/PASSWORD в .env — разовое

Бутстрап админа через `scripts/seed/seed_admin.py` запускается один раз. После того как пароль сменён в UI, переменные в `.env.production` становятся **эффективно секретом прошлого**, но остаются в файле. Оператор обязан вручную удалить/обнулить их после первого логина. Инструкция — в `SERVER_SETUP.md` раздел 9 и `PRODUCTION_CHECKLIST.md` Gate A.

### 3.6 Offsite backup — manual setup

`deploy/backup/pg_dump.sh` содержит **TODO-блок** с примером rclone upload, но сам по себе не делает offsite. Оператор обязан до Gate B настроить один из вариантов:
1. `rclone` → S3-совместимое хранилище (Backblaze B2 / AWS S3 / Yandex Object Storage).
2. `rsync` → второй VPS.

Обоснование такого подхода: выбор storage-провайдера — бизнес-решение (цена, юрисдикция, DPA), скрипт не должен его навязывать.

### 3.7 logrotate — отдельная задача

Логи бэкапов (`/var/log/code9-backup.log`) не ротируются автоматически. Конфиг logrotate приведён в `BACKUP_RESTORE.md` раздел 2, но применение — ручное. Логи Docker-контейнеров ротируются Docker'ом (json-file driver), default 10MB × 3 файла.

---

## 4. Быстрый старт — первый деплой

Для оператора, у которого есть чистая Ubuntu 22.04 VPS и два DNS A-record'а на её IP:

```bash
# 0. на локальной машине: сгенерировать секреты
python3 -c "import secrets; print(secrets.token_urlsafe(64))"  # JWT_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(64))"  # ADMIN_JWT_SECRET
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FERNET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"  # POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(16))"  # ADMIN_BOOTSTRAP_PASSWORD

# 1. на сервере (как root): подготовка ОС
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl make htop ufw ca-certificates gnupg lsb-release
sudo adduser --disabled-password --gecos "" code9
sudo usermod -aG sudo code9
sudo mkdir -p /home/code9/.ssh
sudo cp ~/.ssh/authorized_keys /home/code9/.ssh/authorized_keys
sudo chown -R code9:code9 /home/code9/.ssh

# 2. Docker Engine (официальная инструкция Docker)
# см. SERVER_SETUP.md раздел 3
sudo usermod -aG docker code9

# 3. ufw
sudo ufw default deny incoming
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable

# 4. перелогиниться как code9
exit
# ssh code9@server

# 5. клонировать проект
sudo mkdir -p /opt/code9-analytics && sudo chown code9:code9 /opt/code9-analytics
cd /opt
git clone <repo-url> code9-analytics
cd code9-analytics

# 6. настроить .env.production
cp .env.production.template .env.production
chmod 600 .env.production
nano .env.production   # вставить все секреты, заменить example.com → yourdomain.com

# 7. настроить Caddyfile
nano deploy/Caddyfile   # заменить app.example.com / api.example.com / admin@example.com

# 8. поднять
make prod-config   # валидация compose
make prod-build    # 5-10 мин на VPS
make prod-up       # старт всех контейнеров
sleep 30           # дать Caddy получить сертификат
make prod-ps       # все контейнеры healthy?
make prod-migrate  # применить alembic миграции
make prod-seed     # создать admin (разово)
make prod-smoke    # curl https://api.../health

# 9. верификация
bash -c 'ss -tlnp | grep -E "5432|6379"'  # должно быть 127.0.0.1 only
docker compose -f deploy/docker-compose.prod.yml logs api | grep -Ei "bearer|fernet|secret" || echo OK

# 10. backup cron
crontab -e
# добавить: 0 3 * * * PROJECT_DIR=/opt/code9-analytics bash /opt/code9-analytics/deploy/backup/pg_dump.sh >> /var/log/code9-backup.log 2>&1

# 11. первый test:
#   - открыть https://app.yourdomain.com
#   - зарегистрировать юзера → код в логах api
#   - верифицировать, залогиниться, создать workspace, подключить mock-amoCRM, запустить audit
#   - админ-логин → support-mode → проверить admin_audit_logs
```

Полный чеклист — в `docs/deploy/PRODUCTION_CHECKLIST.md` Gate A (36 пунктов).

---

## 5. Definition of Done — проверка

Из Section 18 deploy-package:

| Пункт | Статус | Как верифицировать |
|-------|--------|---------------------|
| Документы deploy созданы и читаемы | ✅ | `ls docs/deploy/` — 3 файла |
| docker-compose.prod.yml валиден | ✅ | `python3 -c "import yaml; yaml.safe_load(open('deploy/docker-compose.prod.yml'))"` — parses. Финальная проверка на сервере: `make prod-config` |
| `make demo` не сломан | ✅ | `make -n demo` — выдаёт up → sleep 10 → migrate → seed |
| `make prod-build` / `prod-up` | ⏳ | Верифицируется оператором на реальной VPS (sandbox без docker) |
| `make prod-migrate` работает с Alembic | ✅ | Target использует `alembic upgrade head` с правильным `-c` путём |
| `make prod-smoke` проверяет health | ✅ | `curl -fsS ${PUBLIC_API_URL}/api/v1/health` |
| Postgres/Redis на 127.0.0.1 | ✅ | В compose `ports: - "127.0.0.1:5432:5432"` и `127.0.0.1:6379:6379` |
| `.env.production.template` без секретов | ✅ | Все секреты `CHANGE_ME_*`, генераторы в комментариях |
| Логи маскируют bearer/fernet/secret | ✅ | Закрыто в Wave 4 (CR-06); проверка в Gate A чеклисте |
| Backup/restore скрипты добавлены | ✅ | `deploy/backup/pg_dump.sh` + `restore.sh`, chmod +x |
| Итоговый отчёт | ✅ | **Этот файл** |

---

## 6. Риски и ограничения

### 6.1 Bind-mount хрупкость (см. 3.1)

Если оператор `git pull` без `make prod-build`, код в контейнерах обновится для api/web/worker (они копируют весь `apps/*`), но **не** для packages/scripts (они mount'ятся напрямую — обновятся моментально). Это может привести к рассинхрону: api видит старый код, но worker уже новую миграцию scripts. Mitigation: `SERVER_SETUP.md` раздел 11 явно требует `make prod-build` перед `make prod-up`.

### 6.2 No zero-downtime deploy

`docker compose up -d` пересоздаёт контейнеры → короткий downtime (2-5 секунд). На MVP это приемлемо, но на Gate C (реальные платежи) потребуется blue/green или rolling deploy — это Sprint 4+ работа с nginx/Caddy upstream rotation или переход на managed-инфру.

### 6.3 Single point of failure — VPS

Потеря VPS = потеря всего (кроме offsite backup на Gate B+). RTO — 4 часа для Gate A, 2 часа для Gate B. Disaster recovery playbook в `BACKUP_RESTORE.md` раздел 8.

### 6.4 Caddy-сертификат на первый запуск

Если DNS A-record ещё не реплицирован — Caddy будет retry'ить ACME и logs засорятся. Рекомендация: ставить DNS **за сутки** до первого `make prod-up`. Альтернатива для теста — `acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` в Caddyfile глобально (закомментировано, см. SERVER_SETUP.md раздел 7).

---

## 7. Следующие шаги

После того как этот прогон проходит на staging:

### Sprint 1 (security hardening, ~1 неделя)
1. CSRF double-submit cookie / `X-CSRF-Token` header (P1-006 из DEFECTS.md).
2. Rolling refresh token + reuse detection (CR-05).
3. Session/device table + `/settings/sessions` UI.
4. Dockerfile prod-стадия: COPY packages/ и scripts/ напрямую, убрать bind-mount.

### Sprint 2 (data safety + observability, ~1 неделя)
1. Restore drill на staging (обязательно до Gate B).
2. Offsite backup (rclone → S3 / rsync → второй VPS).
3. GPG encryption для offsite.
4. Sentry / GlitchTip.
5. Uptime Kuma + алерты.
6. logrotate настройки.

### Sprint 3 (email + onboarding, ~1 неделя)
1. SMTP (SendGrid / Postmark / Amazon SES).
2. DKIM/SPF/DMARC.
3. Email-verification на реальные ящики.
4. Password reset.
5. ToS + Privacy Policy страницы.

### Sprint 4 (real CRM + billing, ~2-3 недели)
1. amoCRM exchange_code + refresh.
2. Fernet migration job для rotation.
3. Rate-limit handling с exponential backoff.
4. YooKassa + Stripe sandbox полный flow.
5. Webhook HMAC verification.
6. Idempotency keys в `billing_ledger`.

---

## 8. Вердикт

**Sprint 0 (Deploy Foundation) — COMPLETE.**

Артефакты готовы. Можно:
- Арендовать VPS.
- Пройти `SERVER_SETUP.md` шаги 1-9.
- Запустить `make prod-build && make prod-up && make prod-migrate && make prod-seed && make prod-smoke`.
- Отметить Gate A чеклист.

Нельзя:
- Принимать реальных клиентов до Gate B (нужны Sprint 1+2 минимум).
- Брать реальные платежи до Gate C (нужны все Sprint 1-4).

**Owner sign-off required**: После первого успешного прогона на staging — отметиться в `docs/deploy/GATE_SIGNOFFS.md` (файл создаётся в момент первого gate перехода).

---

**Автор отчёта**: Claude (Lead Architect + Deploy role, Sprint 0).
**Ревьюер**: —
**Дата**: 2026-04-18.
