# Phase 2A Report — amoCRM OAuth + External Widget

**Дата:** 2026-04-21
**Роль:** Lead Engineer
**Область:** Phase 2A — реальный amoCRM OAuth flow, external-button виджет, первичный pull воронок/этапов/пользователей/контактов/сделок, UI-видимость подключений.
**Диапазон коммитов:** `e1e5948` (Gate A sign-off, 2026-04-18) → `268ab43` (Task #52.4, 2026-04-21).

---

## 1. Scope

Phase 2A закрывает путь «от кнопки в amoCRM → видимое в кабинете подключение с counts»:

1. Реальный OAuth обмен `authorization_code` на `access_token + refresh_token` для amoCRM (Phase 2A flow).
2. External-button integration widget: рендерим кнопку в amoCRM UI, из которой клиент переходит в наш кабинет и авторизует подключение.
3. Первичный pull справочников + 100 сделок после `amocrm_connected`.
4. UI-карточка подключения показывает `metadata.last_pull_counts` (воронки/этапы/менеджеры/контакты/сделки).
5. После refresh страницы `/app/connections` активное подключение остаётся видимым (Task #52.4).

Phase 2A **не** включает (перенесено в 2B): companies, emails, chats, calls privacy gate, token estimate, lost clients, AI chat, реальные платежи, owner console, billing, referrals, CSRF / rolling refresh / session table.

---

## 2. Созданные / изменённые файлы

**Итого:** 19 коммитов, 50 уникальных файлов (19 новых, 33 изменённых с пересечением).

### 2.1 Backend (apps/api)

| Файл | Действие | Описание |
|------|----------|----------|
| `apps/api/app/core/crypto.py` | Создан | Fernet-обёртка для шифрования amoCRM OAuth-токенов at rest |
| `apps/api/app/core/jobs.py` | Изменён | Enqueue payload через `kwargs=` (Task #52.3D) — RQ распаковывает в kwargs worker-функции |
| `apps/api/app/core/settings.py` | Изменён | Новые env: `AMOCRM_CLIENT_ID/SECRET`, `AMOCRM_EXTERNAL_*`, SMTP, `FERNET_KEY` guard |
| `apps/api/app/core/email.py` | Изменён | Phase 1 SMTP backend (STARTTLS/SSL) с safe fallback на console |
| `apps/api/app/crm/oauth_router.py` | Изменён | Реальный `exchange_code`, `_ui_redirect(flash=...)`, cap 100 сделок на первом pull |
| `apps/api/app/crm/external_router.py` | Создан | Webhook `/crm/external/amocrm/install` → 200 OK (не 204) |
| `apps/api/app/crm/router.py` | Изменён | `ws_crm_router` + `list_workspace_connections` (Task #52.4); `_serialize_conn` не меняем |
| `apps/api/app/main.py` | Изменён | `include_router(ws_crm_router, prefix=API_PREFIX)` |
| `apps/api/app/db/migrations/main/env.py` | Изменён | Alembic asyncpg ssl=require → psycopg2 sslmode=require |
| `apps/api/app/db/migrations/main/versions/0002_amocrm_external_button.py` | Создан | Поля external-button в `crm_connections` |
| `apps/api/app/db/migrations/main/versions/0003_pull_amocrm_job_kind.py` | Создан | CK-constraint: новый job_kind `pull_amocrm` (revid укорочен до VARCHAR(32)) |
| `apps/api/app/db/migrations/tenant/env.py` | Изменён | Тот же SSL-translate для tenant Alembic |
| `apps/api/app/db/models/enums.py` | Изменён | `JobKind.PULL_AMOCRM` |
| `apps/api/app/db/url_translate.py` | Создан | Общая функция asyncpg↔psycopg2 для Alembic |

### 2.2 Worker (apps/worker)

| Файл | Действие | Описание |
|------|----------|----------|
| `apps/worker/worker/jobs/crm.py` | Изменён | Per-connection OAuth creds для external_button (Task #52.3F) |
| `apps/worker/worker/jobs/crm_pull.py` | Создан | `pull_amocrm` job: воронки/этапы/пользователи/контакты/100 сделок; raw SQL UPDATE с real column `metadata` (Task #52.3G) |
| `apps/worker/worker/lib/amocrm_creds.py` | Создан | Резолвер OAuth creds: env → connection-specific secrets |
| `apps/worker/worker/lib/db.py` | Изменён | Использование `url_translate` при подключении к основной БД |
| `apps/worker/worker/lib/url_translate.py` | Создан | Та же функция, но в worker-пакете (decouple от apps/api, Task #52.3) |

### 2.3 Frontend (apps/web)

| Файл | Действие | Описание |
|------|----------|----------|
| `apps/web/app/[locale]/app/connections/page.tsx` | Изменён | Убран `ws-demo-1` fallback; 5-state render: `!ready` / `hasNoWorkspace` / fetching / empty-with-CTA / list (Task #52.4) |
| `apps/web/app/[locale]/app/connections/new/page.tsx` | Изменён | Рендер `AmoCrmExternalButton` как primary CTA |
| `apps/web/app/[locale]/app/connections/[id]/page.tsx` | Изменён | Detail page + reconnect flow |
| `apps/web/components/integrations/AmoCrmExternalButton.tsx` | Создан | Виджет с CODE9 branding (brief #52.2), manual `window.onload` после подгрузки скрипта |
| `apps/web/components/cabinet/ConnectionCard.tsx` | Изменён | Рендер `metadata.last_pull_counts` в формате `1/7/2/0/0` с `tabular-nums` + tooltip |
| `apps/web/public/amocrm-logo.png` | Создан | Asset для external-button виджета |
| `apps/web/app/icon.svg` | Создан | Code9 favicon (задача hygiene) |
| `apps/web/lib/env.ts` | Изменён | В prod-билде не тянем mock API |
| `apps/web/messages/ru.json` | Изменён | Ключи: `cabinet.connections.flash.*`, `noWorkspaceTitle`, `noWorkspaceBody`, `detail.pullCounts` |
| `apps/web/messages/en.json` | Изменён | Те же ключи en-версии (RU=351 / EN=351, zero divergence) |
| `packages/shared/typescript/index.ts` | Изменён | Тип `CrmConnection.metadata.last_pull_counts` |

### 2.4 Tests

| Файл | Действие | Описание |
|------|----------|----------|
| `tests/api/test_amocrm_external_button.py` | Создан | Webhook 200 OK + структура ответа |
| `tests/api/test_amocrm_worker_credentials.py` | Создан | Per-connection OAuth creds резолвер |
| `tests/api/test_apply_tenant_template_escape.py` | Создан | Escape `%` в DSN при `Config.set_main_option` (Task #52.3E) |
| `tests/api/test_crm_pull_metadata_sql_column.py` | Создан | Гуард: raw SQL UPDATE использует column name `metadata`, не `connection_metadata` (Task #52.3G) |
| `tests/api/test_job_kinds.py` | Создан | Check-constraint `pull_amocrm` в enum |
| `tests/api/test_jobs_enqueue.py` | Создан | Enqueue payload → kwargs распаковка (Task #52.3D) |
| `tests/api/test_url_translate.py` | Создан | asyncpg↔psycopg2 translation |
| `tests/api/test_workspace_scoped_crm_connections.py` | Создан | Роут `/workspaces/{ws}/crm/connections` существует, auth-first, `_serialize_conn` используется, `external_button` **не** фильтруется (Task #52.4) |

### 2.5 Infra / Deploy / Config

| Файл | Действие | Описание |
|------|----------|----------|
| `deploy/docker-compose.prod.timeweb.yml` | Изменён | Mount `apps/api:/apps/api:ro` в worker (Task #52.3); prod-build без mock API |
| `deploy/Caddyfile` | Изменён | Routing для external webhook path |
| `infra/docker/web.Dockerfile` | Изменён | Prod-билд без mock API + favicon |
| `docker-compose.yml` | Изменён | Dev PYTHONPATH: `packages/*/src` для api/worker |
| `scripts/migrations/apply_tenant_template.py` | Изменён | Regex `crm_` prefix + escape `%` в DSN (Task #52.3E); decouple от apps/api (Task #52.3) |
| `.env.example` | Изменён | Новые amoCRM / SMTP envs |
| `.env.production.template` | Изменён | Новые amoCRM / SMTP envs (prod-версия) |
| `docs/deploy/INSTALL_TIMEWEB.md` | Изменён | Gate B Phase 2A runbook для amoCRM OAuth |

---

## 3. Ключевые фиксы / интеграционные проблемы, найденные и закрытые

Phase 2A шёл с жёстким E2E-циклом «кнопка в amoCRM → UI в кабинете показывает counts». Каждая подзадача была real-world блокером:

| Task | Суть проблемы | Решение |
|------|---------------|---------|
| #52.3 | Worker импортировал `apps.api.*` → круговая зависимость | Mount `apps/api:ro` + extract `url_translate` в worker/lib |
| #52.3D | `enqueue(f, payload)` передавался позиционно → worker получал `args=(dict,)` вместо kwargs | Перешли на `enqueue(f, kwargs=payload)` |
| #52.3E | Alembic падал с `ValueError: unsupported format character` когда в password был `%` | Escape `%%` + scrub exception message, чтобы не утёк пароль |
| #52.3F | Worker тянул OAuth creds из env — для external_button mode creds per-connection | `amocrm_creds.py` резолвер: env → connection-specific `external_client_id/secret` |
| #52.3G | Raw SQL использовал ORM-атрибут `connection_metadata` → `UndefinedColumnError` | Реальное имя колонки — `metadata`; добавлен source-level guard-test |
| #52.4 | После refresh `/app/connections` подключение не отображалось — frontend дёргал несуществующий endpoint `/workspaces/{ws}/crm/connections` | Добавлен `ws_crm_router`; на frontend убран `ws-demo-1` fallback, добавлен 5-state render |

Дополнительно:
- **amoCRM webhook 204 vs 200** (commit `11fcfe3`): amoCRM считает 204 как ошибку и не устанавливает интеграцию — вернули 200 OK из `external_router.py`.
- **Alembic revision id > 32 символов** (commit `1f01950`): PG enforce; переименовали `0003_ck_job_kind_pull_amocrm_core.py` → `0003_pull_amocrm_job_kind.py`.
- **Mock API в prod-билде** (commit `9154ccd`): ключ `MOCK_CRM_MODE` попадал в production image — возможные утечки mock-данных. Отрезано в `apps/web/lib/env.ts` + `infra/docker/web.Dockerfile`.
- **amoCRM widget `window.onload`** (commit `bc46700`): amoCRM SDK ожидал `window.onload` до готовности DOM — руками дёрнули `onload` после загрузки скрипта.

---

## 4. Verification Results (по состоянию на 2026-04-21, HEAD=`268ab43`)

### 4.1 Backend / API

- `GET /api/v1/workspaces/{wsid}/crm/connections` без `Authorization` → **401** с unified error body (не 404).
- `GET /api/v1/workspaces/{wsid}/crm/connections` с валидным JWT + wsid `5cddd8c2-2bd5-47c2-8b43-0c29e9b00bf9` → **200**, 1 connection (`1ede9725-4b4e-4157-8a12-a8ac9c67f274`, `auth_mode=external_button`).
- В ответе присутствует `metadata.last_pull_counts = {pipelines: 1, stages: 7, users: 2, contacts: 0, deals: 0}` (первый pull; 0 контактов/сделок на demo-аккаунте это норма).
- В теле ответа **нет** `access_token` / `refresh_token` / `client_secret` / `password` (assert в тестах + in-container проверка).

### 4.2 Frontend

- Web-билд после Task #52.4: новый чанк `page-30ee5bfd19aa662c.js` содержит `noWorkspaceTitle`, `noWorkspaceBody`; строка `ws-demo-1` отсутствует в рантайм-коде (только в комментариях старых коммитов в git history).
- Сервер отдаёт i18n-ключи: «Нет подключений» (empty-with-CTA) и «Нет доступного проекта» (no-workspace) — оба встречаются в HTML на `/ru/app/connections`.
- RU=351 / EN=351 ключей, zero divergence.

### 4.3 Logs / hygiene

- За последние 10 минут (по состоянию на deploy): 0 ERROR в `api`, 0 ERROR в `web`, 0 ERROR в `worker`.
- `docker logs` не содержит `access_token` / `refresh_token` / `client_secret` (проверено grep'ом).

### 4.4 Blob integrity

Сверка blob SHA committed vs runtime на VPS:

| Файл | Статус |
|------|--------|
| `apps/api/app/crm/router.py` | match |
| `apps/api/app/main.py` | match |
| `apps/web/app/[locale]/app/connections/page.tsx` | match |
| `apps/web/components/cabinet/ConnectionCard.tsx` | match |
| `apps/web/messages/en.json` | match |
| `apps/web/messages/ru.json` | match |
| `tests/api/test_workspace_scoped_crm_connections.py` | **diff** (по дизайну — тесты не попадают в runtime image; VPS-копия — dev scratch) |

---

## 5. Commit log (Phase 2A)

```
268ab43 2026-04-21  fix(crm): show workspace-scoped amoCRM connections after refresh
6989121 2026-04-21  fix(worker): use real column name 'metadata' in raw SQL UPDATE (Task #52.3G)
95af08a 2026-04-21  fix(worker): load amoCRM OAuth creds per-connection for external_button (Task #52.3F)
124021c 2026-04-21  fix(migrations): escape % in DSN for Alembic + scrub ValueError (Task #52.3E)
2663075 2026-04-21  fix(api): enqueue payload via kwargs= so RQ unpacks to kwargs (Task #52.3D)
67dd75e 2026-04-21  fix(worker): decouple tenant bootstrap from apps/api import (Task #52.3)
1f01950 2026-04-20  fix(alembic): shorten revision id of 0003 pull_amocrm_job_kind (VARCHAR(32))
1aa0a42 2026-04-20  fix(crm): allow amoCRM pull job and normalize Postgres SSL for worker
4db973c 2026-04-20  feat(web): CODE9 Analytics branding for amoCRM widget
8851f9d 2026-04-20  feat(crm): cap first amoCRM pull at 100 deals for Phase 2A
11fcfe3 2026-04-20  fix(crm): return 200 OK from amoCRM external webhook (not 204)
bc46700 2026-04-20  fix(web): manually invoke window.onload after amoCRM widget script load
9154ccd 2026-04-20  fix(web): stop shipping mock API in prod build + add Code9 favicon
e2d6cfd 2026-04-19  feat(web): render amoCRM external integration widget
51e5fc1 2026-04-19  fix(crm): align amoCRM external button secrets URI naming
617ecca 2026-04-19  feat(crm): enable amoCRM OAuth Phase 2A flow
cb906ff 2026-04-18  docs(deploy): add Gate B Phase 2A runbook in INSTALL_TIMEWEB.md
3225c39 2026-04-18  feat(email): Phase 1 SMTP backend with STARTTLS/SSL + safe fallback
c902321 2026-04-18  fix(dev-compose): add packages/*/src to PYTHONPATH for api/worker
82ab473 2026-04-18  fix(alembic): translate asyncpg ssl=require to psycopg2 sslmode=require
```

---

## 6. Готовность / Gate B

**Вердикт: Phase 2A CLOSED. Gate B Sprint 1 — в работе (не в этом отчёте).**

### Что работает в production (aicode9.ru):

- amoCRM external-button виджет рендерится и запускает OAuth flow.
- `exchange_code` успешно обменивает `authorization_code` → `access_token + refresh_token`.
- Первичный pull заполняет `metadata.last_pull_counts`.
- UI показывает counts (формат `1/7/2/0/0`) в ConnectionCard.
- После refresh страницы подключение остаётся видимым.
- i18n полная (RU/EN), zero divergence.

### Что **не** в Phase 2A (перенесено в 2B):

См. `docs/product/BACKLOG_PHASE_2B.md` — 7 направлений.

### Открытые дефекты / технический долг:

| ID | Severity | Описание | План |
|----|----------|----------|------|
| P2-004 | P2 | Caddy healthcheck false-positive на VPS (alpine wget + `localhost` → `::1` → refused) | Proposed: заменить `localhost` на `127.0.0.1` в `deploy/docker-compose.prod.timeweb.yml`, отдельный 1-line commit |
| P2-005 | P2 | `deploy/Caddyfile.codenine.live` + `deploy/codenine_form_proxy.py` существуют на VPS, но не закоммичены | Proposed: отдельный commit `feat(deploy): add codenine.ru form-proxy for calculator lead capture` |
| P1-007 | P1 | CSRF / rolling refresh / session table — всё ещё open с Gate A | Gate B Sprint 1 |
| P1-008 | P1 | Offsite backup + restore drill | Gate B Sprint 2 |

---

## 7. Не в scope

- Phase 2B features (см. backlog).
- Gate C (реальные платежи, YooKassa/Stripe).
- Public launch / открытая регистрация.

---

## 8. Ссылки

- `docs/deploy/GATE_SIGNOFFS.md` — Gate A sign-off `0af4da1` 2026-04-18.
- `docs/deploy/INSTALL_TIMEWEB.md` — runbook amoCRM OAuth Phase 2A.
- `docs/architecture/CHANGE_REQUESTS.md` — общий CR-реестр.
- `docs/architecture/DECISIONS.md` — ADR-реестр.
- `docs/product/BACKLOG_PHASE_2B.md` — отложенные направления 2B.
