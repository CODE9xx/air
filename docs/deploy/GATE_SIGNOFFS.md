# Gate Sign-offs — Code9 Analytics

Этот файл фиксирует формальное подписание каждого перехода Gate A → B → C.
Owner подписывает после того, как **все** пункты соответствующего раздела
`docs/deploy/PRODUCTION_CHECKLIST.md` зелёные и лично проверены.

**Правила**:
- Подписание до прохождения чеклиста = нарушение процесса.
- Sign-off делается на конкретной commit SHA.
- Запись добавляется append-only — старые записи не редактируются.
- Если после gate-перехода обнаружен блокер — открывается новая запись "rollback"
  с указанием причины; следующий sign-off — с новой SHA.

---

## Gate A — Staging / Demo

**Цель**: staging-сервер с demo-данными, без реальных клиентских CRM.

**Критерии** (краткая выдержка из PRODUCTION_CHECKLIST.md Gate A):
1. Compose валиден, все 7 контейнеров Up; сервисы с healthcheck (caddy/web/api/postgres/redis) — Up (healthy); worker/scheduler — просто Up.
2. HTTPS валиден для app. и api.; security headers присутствуют.
3. Postgres/Redis bind только на 127.0.0.1; снаружи `nc -zv <ip> 5432|6379` → refused/timeout.
4. Логи api/worker не содержат raw-токенов / FERNET_KEY / Bearer.
5. Функциональный smoke: регистрация → verify → login → workspace → mock-amoCRM → audit → dashboard → базовый admin login.
6. Backup: `make prod-backup` создаёт `code9_*.sql.gz` + `code9_globals_*.sql.gz`; cron настроен.
7. Полноценный admin support-mode (start с reason → `admin_audit_logs`) — **Gate B (CR-07, Sprint 1)**, на Gate A не требуется.

### Signoff log

| Дата (UTC)  | Версия (commit SHA) | Оператор | Домен              | Результат | Комментарий                |
|-------------|---------------------|----------|--------------------|-----------|----------------------------|
| YYYY-MM-DD  | `abc1234…`          | —        | app.example.com    | —         | Первый staging deploy      |
| 2026-04-18  | `0af4da1`           | CODE9    | aicode9.ru         | PASS      | Timeweb VPS 72.56.232.201 + managed Postgres (VPC 192.168.0.4); 6/6 контейнеров healthy; Let's Encrypt выдан для aicode9.ru + api.aicode9.ru; миграции/seed прошли; бэкап + cron 03:15 UTC; 8000/3000/6379 недоступны снаружи. |

<!-- Пример заполнения:
| 2026-04-20  | `a1b2c3d4`          | CODE9    | staging.code9.io   | PASS      | make prod-* всё зелёное    |
-->

---

## Gate B — Closed Pilot (1-3 клиента с реальным amoCRM)

**Цель**: ограниченный круг клиентов подключает реальные CRM; owner ведёт onboarding вручную.

**Предусловия**: все пункты Gate A зелёные + Sprint 1 (CSRF, rolling refresh, sessions) + Sprint 2 (monitoring, offsite backup, restore drill).

**Критерии** (выдержка из PRODUCTION_CHECKLIST.md Gate B):
1. CSRF double-submit / `X-CSRF-Token` заголовок на state-changing endpoints.
2. Rolling refresh + reuse detection (CR-05).
3. Session / device table + UI отзыва.
4. SMTP настроен (DKIM/SPF/DMARC); email-verification на внешний ящик.
5. Sentry / GlitchTip подключены; uptime-чек с алертом.
6. Restore drill пройден на staging; RPO/RTO зафиксированы.
7. Offsite backup + шифрование at rest (GPG или storage-level).
8. Anonymizer golden-corpus тесты зелёные.

### Signoff log

| Дата (UTC)  | Версия (commit SHA) | Оператор | Клиенты         | Результат | Комментарий                |
|-------------|---------------------|----------|-----------------|-----------|----------------------------|
| YYYY-MM-DD  | `abc1234…`          | —        | —               | —         | Ещё не пройден             |

---

## Gate C — Public Launch / Real Payments

**Цель**: открытая регистрация, реальные платежи через YooKassa / Stripe.

**Предусловия**: Gate A + B + Sprint 3 (email, ToS/Privacy) + Sprint 4 (real CRM APIs, billing, webhook signature verification).

**Критерии** (выдержка из PRODUCTION_CHECKLIST.md Gate C):
1. YooKassa / Stripe sandbox: полный flow от deposit до webhook прошёл.
2. HMAC webhook verification + idempotency по `event_id`.
3. Real amoCRM `exchange_code` + `refresh` + `invalid_grant` → `lost_token`.
4. Tenant isolation regression test.
5. Terms of Service + Privacy Policy подписаны юристом.
6. Incident response runbook с playbook'ами.
7. Secrets rotation procedures документированы и проверены.
8. Postgres на managed instance или с репликацией.

### Signoff log

| Дата (UTC)  | Версия (commit SHA) | Оператор | Платёжные шлюзы          | Результат | Комментарий                |
|-------------|---------------------|----------|--------------------------|-----------|----------------------------|
| YYYY-MM-DD  | `abc1234…`          | —        | YooKassa / Stripe        | —         | Ещё не пройден             |

---

## Rollback log

Если после sign-off обнаружен критический блокер (data loss, security breach,
недоступность > SLA) — фиксируем откат, чтобы следующий gate потребовал
повторного прохождения чеклиста с новой SHA.

| Дата       | С какого gate откат | Причина                              | Действие                      |
|------------|---------------------|--------------------------------------|-------------------------------|
| YYYY-MM-DD | —                   | —                                    | —                             |

---

## Как подписать gate (процедура для оператора)

1. Пройти все пункты соответствующего раздела `PRODUCTION_CHECKLIST.md`. Поставить "[x]" в каждом.
2. Получить SHA последнего коммита: `git rev-parse --short HEAD`.
3. Добавить строку в **signoff log** соответствующего раздела этого файла.
4. Закоммитить изменение отдельным коммитом: `git commit -m "ops: gate A sign-off for <domain>"`.
5. Пушнуть и сообщить команде.
6. Если что-то пошло не так после sign-off — добавить в **Rollback log** и открыть issue с причиной.
