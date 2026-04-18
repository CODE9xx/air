# Production Checklist — Code9 Analytics

Gate-модель: **A → B → C**. Нельзя пропускать этап. Каждый gate имеет чёткие критерии; не отмечай пункт на веру — проверяй командой/наблюдением.

Источники истины: `docs/qa/AC_REPORT.md`, `docs/qa/DEFECTS.md`, `docs/architecture/WAVE4_REPORT.md`, `docs/architecture/CHANGE_REQUESTS.md`.

---

## Gate A — Staging / demo

Цель: можно показать продукт внутренне или команде инвестора. Реальных пользовательских CRM-данных ещё нет.

### Infrastructure
- [ ] Сервер с минимум 4 vCPU / 8 GB / 80 GB SSD.
- [ ] DNS A-записи для `app.` и `api.` указывают на сервер.
- [ ] ufw включён, разрешены только 22 / 80 / 443.
- [ ] SSH только по ключу, `PasswordAuthentication no` в `sshd_config`.
- [ ] Docker Engine + Compose plugin работают (`docker run hello-world`).

### Secrets & configuration
- [ ] `.env.production` существует, `chmod 600`, владелец не root.
- [ ] `APP_ENV=production` (иначе fail-fast валидатор не сработает).
- [ ] `JWT_SECRET`, `ADMIN_JWT_SECRET`, `FERNET_KEY` — **не** дефолтные / не `CHANGE_ME_*`.
- [ ] `POSTGRES_PASSWORD` — ≥ 32 символа, случайный.
- [ ] `ADMIN_BOOTSTRAP_PASSWORD` — сгенерирован и сохранён в password manager.
- [ ] `CORS_ORIGINS` / `ALLOWED_ORIGINS` содержат **только** prod-домены (никаких wildcard, никаких `http://localhost`).
- [ ] `MOCK_CRM_MODE=true` (в Gate A мы ещё на mock).

### HTTPS & headers
- [ ] `curl -I https://app.yourdomain.com` → 200/308, сертификат валиден.
- [ ] `curl -I https://api.yourdomain.com/api/v1/health` → 200, JSON `{"status":"ok"}`.
- [ ] Отправлены security headers: `Strict-Transport-Security`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`.
- [ ] HTTP запросы редиректят на HTTPS (`curl -I http://app.yourdomain.com` → 301/308 на https).

### Compose & services
- [ ] `make prod-config` выходит с кодом 0.
- [ ] `make prod-up` → все 7 контейнеров в статусе `Up`: caddy, web, api, worker, scheduler, postgres, redis.
  - Сервисы с healthcheck (caddy, web, api, postgres, redis) должны быть `Up (healthy)`.
  - `worker` и `scheduler` healthcheck в Sprint 0 не имеют — достаточно статуса `Up`; их работоспособность проверяется через `make prod-logs` и факт обработки jobs.
- [ ] `make prod-migrate` прошла без ошибок; `alembic heads` возвращает один head.
- [ ] `make prod-seed` прошёл один раз; админ-пароль сменён в UI.
- [ ] `make prod-smoke` возвращает OK.

### Network isolation
- [ ] `ss -tlnp` на сервере: `5432` и `6379` только на `127.0.0.1`.
- [ ] Снаружи (с другой машины) `nc -zv -w 5 <public-ip> 5432` → connection refused / timeout.
- [ ] Снаружи `nc -zv -w 5 <public-ip> 6379` → connection refused / timeout.
- [ ] Попытка подключиться psql с внешнего адреса — connection refused.

Почему `nc`, а не `curl`: `curl` пытается говорить HTTP, что не соответствует Postgres/Redis wire-protocol — ответ может ввести в заблуждение. `nc -z` проверяет именно TCP-досягаемость порта.

### Logs & secrets hygiene
- [ ] `docker compose logs api | grep -E "Bearer ey|refresh_token.{10}|FERNET|jwt_secret"` → **пусто**.
- [ ] `docker compose logs worker | grep -E "Bearer ey|refresh_token.{10}|FERNET"` → **пусто**.
- [ ] В Caddy access-логах пароли не появляются (нет пути `/auth/login` с query-параметрами).

### Functional smoke (ручной)
- [ ] Регистрация → код приходит в `docker compose logs api` (SMTP позже).
- [ ] Verify email → login → dashboard открывается.
- [ ] Create workspace → connect mock-amoCRM → audit запускается → результаты появляются.
- [ ] Admin login → базовая admin-страница открывается (список workspace / пользователей).
- [ ] Logout → refresh-cookie удалён; повторный запрос с прежним access падает 401.

> **Scope Gate A**: полноценный admin support-mode (`start_support_session` с reason / TTL / запись в `admin_audit_logs` внутри транзакции) — это CR-07, реализуется в Sprint 1 и проверяется на Gate B. На Gate A достаточно, что админ логинится и видит базовую admin-страницу.

### Backup
- [ ] `make prod-backup` создаёт .sql.gz в `/var/backups/code9/`.
- [ ] cron-задание добавлено в crontab пользователя `code9`.
- [ ] Лог в `/var/log/code9-backup.log` доступен и ротируется (logrotate в Sprint 2).

### Documentation
- [ ] `docs/deploy/SERVER_SETUP.md` прочитан и пройден оператором.
- [ ] `docs/demo/RUN_BOOK.md` актуален для текущей версии.
- [ ] Контакт owner'а записан в `README.md`.

**Gate A пройден** → можно показывать staging-URL команде, партнёрам, инвесторам. **Нельзя** принимать реальные клиентские CRM-данные.

---

## Gate B — Closed pilot (ограниченный круг клиентов)

Цель: 1-3 реальных клиента с реальными amoCRM-данными, но через контролируемый onboarding (ручной ввод owner'ом в admin).

**Все пункты Gate A уже зелёные.** Плюс:

### Security hardening (Sprint 1)
- [ ] **CSRF-токены** включены для всех state-changing endpoints (`POST/PUT/PATCH/DELETE`). Для SPA — double-submit cookie или `X-CSRF-Token` header. См. P1-006 в DEFECTS.
- [ ] **Rolling refresh**: каждый `/auth/refresh` возвращает новый refresh + инвалидирует старый. Реализован **reuse detection** (попытка использовать старый refresh → invalidate всего семейства → принудительный logout). См. CR-05.
- [ ] **Session/device table**: пользователь видит список активных сессий в /settings и может их отозвать.
- [ ] **Admin/support audit**: каждая запись в `admin_audit_logs` имеет `reason`, `ttl_expired_at`, `tenant_id`, `actor_id`. По-прежнему в той же транзакции с действием. См. CR-07.
- [ ] **Tenant support-mode endpoints**: admin может открыть support-сессию с read-only доступом к tenant-данным; TTL 60 мин; всё в audit. См. AC-11 / CR-07.

### Email & onboarding (Sprint 3)
- [ ] **SMTP** настроен (SendGrid / Postmark / Amazon SES / свой). DKIM/SPF/DMARC прописаны в DNS.
- [ ] Email-verification доставляется на внешний ящик (gmail, proton, corporate).
- [ ] Password reset работает.
- [ ] Resend rate-limit включён.
- [ ] Terms of Service + Privacy Policy страницы добавлены (в `apps/web/app/[locale]/legal/`).

### Monitoring & error tracking
- [ ] **Error tracking** подключён: Sentry / GlitchTip / self-hosted. Api + worker + web шлют события.
- [ ] **Basic monitoring**: Uptime-чек на `app.` и `api.` (Uptime Kuma / Better Uptime). Алерт на email/telegram.
- [ ] **Disk / CPU / RAM** мониторятся (netdata / node_exporter + grafana-cloud или Uptime Kuma metrics).
- [ ] Порядок инцидента описан: кого будить, как откатываться (Sprint 0: минимальный runbook).

### Data safety (Sprint 2)
- [ ] **Restore drill пройден** на staging: взят backup, развёрнут в чистой БД, smoke-test зелёный.
- [ ] RPO / RTO зафиксированы в `docs/deploy/BACKUP_RESTORE.md`.
- [ ] Backup-retention минимум 7 daily + 4 weekly.
- [ ] Backup-файлы шифруются at rest (storage-level или GPG) — особенно если offsite.
- [ ] Offsite storage настроен (S3-совместимый bucket / второй VPS).
- [ ] Миграции имеют **rollback-policy** (downgrade-скрипты в Alembic или документированная процедура восстановления из дампа).

### Privacy
- [ ] `packages/ai/src/packages_ai/anonymizer.py` golden-corpus тесты зелёные.
- [ ] `ai_research_consent` workspace-scoped, отзыв работает.
- [ ] Логи обработки PII (что попало в `ai_research_patterns`) доступны owner'у по запросу.

### Performance
- [ ] Load-test с 10 concurrent users: p95 latency `/auth/login` < 500ms, `/dashboards/overview` < 1s.
- [ ] Worker обрабатывает ≥ 50 audit-job/минуту без накопления очереди.
- [ ] Redis memory usage < 50% от лимита.

**Gate B пройден** → можно запускать 1-3 клиентов с реальными CRM-данными.

---

## Gate C — Public launch / real payments

**Gate A + B уже зелёные.** Плюс:

### Payments
- [ ] YooKassa sandbox: полный flow от deposit до webhook прошёл с реальной sandbox-транзакцией.
- [ ] Stripe test mode: то же самое.
- [ ] Webhook signature verification (HMAC SHA-256) реализован и покрыт тестами — подделанный webhook отклоняется.
- [ ] Idempotency: повторный webhook с тем же `event_id` не создаёт дубликат в `billing_ledger`.
- [ ] Retries / backoff на webhook failures.
- [ ] Business-verification для YooKassa / Stripe пройдена (ИП/ООО + договор).

### Real CRM API
- [ ] amoCRM `exchange_code` реализован и покрыт integration-тестом против sandbox.
- [ ] amoCRM `refresh` реализован; при `invalid_grant` connection переходит в `lost_token` и пишется notification.
- [ ] CRM tokens хранятся Fernet-encrypted; ни один endpoint API не возвращает raw-token.
- [ ] CRM rate-limit handling: exponential backoff, jitter, alert на деградацию.
- [ ] Tenant isolation покрыта регрессионным тестом (пользователь A не видит данные tenant B).
- [ ] CRM sync logs tenant-scoped, хранятся ≥30 дней.

### Legal & compliance
- [ ] Terms of Service подписан юристом.
- [ ] Privacy Policy описывает сбор/хранение/передачу данных; в том числе GDPR / 152-ФЗ для российских клиентов.
- [ ] Cookie consent banner (для EU-пользователей).
- [ ] DPA (Data Processing Agreement) шаблон доступен для enterprise-клиентов.
- [ ] Точка контакта для data-subject-requests (Article 15-22 GDPR).

### Operational readiness
- [ ] Incident response runbook с playbook'ами для: down API, compromised secrets, data breach, billing-inconsistency.
- [ ] Staging окружение зеркалит production (миграции → staging → prod).
- [ ] CI/CD: build + test + deploy автоматически при merge в main.
- [ ] Secrets rotation procedure документирована (FERNET_KEY rotation, JWT rotation).
- [ ] On-call расписание (если команда > 1 человека).

### Scale readiness
- [ ] Postgres переведён на managed instance (RDS / Cloud SQL / Yandex Managed Postgres) ИЛИ настроена репликация master-replica.
- [ ] Redis переведён на managed ИЛИ persistence проверена после reboot.
- [ ] Docker image размеры < 800 MB (api), < 600 MB (worker), < 400 MB (web).
- [ ] CDN перед `app.` (Cloudflare / Bunny) для статических ассетов.

**Gate C пройден** → можно открывать публичную регистрацию и принимать платежи.

---

## Правила работы с gate'ами

- Не пропускай пункт "потому что мелочь" — мелочи бьют в prod.
- Фэйл на любом пункте → back to backlog, не в prod.
- Owner подписывает checklist перед каждым gate-переходом (digital signature в `docs/deploy/GATE_SIGNOFFS.md`, если нужно).
- После major-релиза — прогнать Gate A полностью ещё раз (smoke-регрессия).
