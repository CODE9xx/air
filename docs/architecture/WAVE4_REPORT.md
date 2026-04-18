# Wave 4 Report — Lead Architect

**Дата:** 2026-04-18  
**Роль:** Lead Architect  
**Область:** Integration Sweep + CR Closure + MVP Demo Readiness

---

## 1. Созданные / изменённые файлы

| Файл | Действие | Описание |
|------|----------|----------|
| `docker-compose.yml` | Изменён | CR-01: монтирование `./scripts:/app/scripts:ro` + `PYTHONPATH` для api и worker |
| `apps/api/app/core/settings.py` | Изменён | CR-03: fail-fast `@model_validator` для prod-секретов |
| `apps/worker/worker/lib/tenant.py` | Изменён | CR-04: regex `^crm_[a-z0-9][a-z0-9_]{1,59}$` |
| `scripts/migrations/apply_tenant_template.py` | Изменён | CR-04: аналогичный regex |
| `apps/worker/worker/lib/log_mask.py` | Изменён | CR-06: добавлены `fernet_key`, `jwt_secret`, `admin_jwt_secret` в SENSITIVE_KEYS |
| `apps/worker/worker/jobs/retention.py` | Изменён | LEAD-001: re-export `delete_connection_data` для корректного RQ-пути |
| `packages/ai/src/packages_ai/anonymizer.py` | Создан | CR-08: MVP-анонимайзер PII (email, phones, INN, passport, card, IP) |
| `packages/ai/src/packages_ai/__init__.py` | Изменён | CR-08: экспорт `anonymize`, `build_research_pattern` |
| `.env.example` | Изменён | 3.1: добавлены POSTGRES_DSN, NEXT_PUBLIC_DEFAULT_LOCALE, EMAIL_BACKEND, DEBUG |
| `Makefile` | Изменён | 3.2: добавлены `migrate`, `seed`, `test`, `lint`, `demo` |
| `README.md` | Переписан | 3.3: финальный README с архитектурой, quick start, demo scenario, known gaps |
| `docs/demo/RUN_BOOK.md` | Создан | 3.4: пошаговый runbook для демо-сессии |
| `docs/architecture/DECISIONS.md` | Изменён | 3.5: добавлены ADR-011, ADR-012, ADR-013 (Wave 4) |
| `docs/architecture/CHANGE_REQUESTS.md` | Изменён | Resolution для CR-01..CR-08 + новый CR-09 (LEAD-001) |
| `docs/architecture/WAVE4_REPORT.md` | Создан | Этот файл |

**Итого:** 15 файлов изменено/создано.

---

## 2. Закрытые CR

| CR | Статус | Решение |
|----|--------|---------|
| CR-01 | **CLOSED** | `./scripts` монтируется в api и worker + `PYTHONPATH=/app:/app/scripts` |
| CR-02 | **CLOSED** | Nullable-колонка `name` принята BE, DW включит в миграцию |
| CR-03 | **CLOSED** | `@model_validator(mode="after")` в `Settings` — fail-fast при prod-секретах |
| CR-04 | **CLOSED** | Regex `^crm_[a-z0-9][a-z0-9_]{1,59}$` в двух файлах |
| CR-05 | **DEFERRED to V1** | Требует серьёзного рефакторинга BE auth/router.py. Assignee: BE |
| CR-06 | **CLOSED** | `fernet_key`, `jwt_secret`, `admin_jwt_secret` в worker SENSITIVE_KEYS |
| CR-07 | **DEFERRED to V1** | Tenant support-mode endpoints — сложная BE-задача, не блокирует demo |
| CR-08 | **CLOSED** | `packages/ai/src/packages_ai/anonymizer.py` создан — P0-001 закрыт |
| CR-09 | **CLOSED** | LEAD-001: re-export delete_connection_data в retention.py |

**Закрыто CR:** 6 из 8 (+ CR-09 новый/закрытый).

---

## 3. Integration Smoke Check — результаты

### 3.1 Очереди RQ
**Статус: PASS** — имена очередей в BE (`apps/api/app/core/jobs.py: JOB_KIND_TO_QUEUE`) и в worker (`apps/worker/worker/lib/queues.py: JOB_TO_QUEUE`) совпадают для всех ключевых jobs.

### 3.2 Job-функции
**Статус: PASS с одним фиксом** — 
- Все основные функции (`bootstrap_tenant_schema`, `fetch_crm_data`, `run_audit_report`, `recalc_balance`, `analyze_conversation`, `extract_patterns`) присутствуют в `worker/jobs/*.py`.
- LEAD-001 (P0): `delete_connection_data` находилась в `delete.py`, но BE enqueue строил путь `worker.jobs.retention.delete_connection_data`. **Исправлено** — добавлен re-export.

### 3.3 FE → BE Endpoints
**Статус: PASS** — все ключевые endpoints совпадают:

| FE вызов | BE endpoint | Статус |
|----------|-------------|--------|
| `POST /auth/register` | `auth/router.py:89` | OK |
| `POST /auth/login` | `auth/router.py:164` | OK |
| `POST /auth/logout` | `auth/router.py:232` | OK |
| `POST /auth/refresh` | `auth/router.py:261` | OK |
| `GET /auth/me` | `auth/router.py:573` | OK |
| `POST /auth/verify-email/confirm` | `auth/router.py:338` | OK |
| `POST /auth/password-reset/request` | `auth/router.py:436` | OK |
| `POST /admin/auth/login` | `admin/router.py:65` | OK |
| `POST /admin/auth/logout` | `admin/router.py:112` | OK |
| `GET /dashboards/overview` | `dashboards/router.py:279` | OK |
| `POST /admin/support-mode/start` | `admin/router.py:554` | OK |

### 3.4 packages/crm-connectors
Пакет монтируется как `./packages:/packages` в обоих контейнерах (api, worker). CR-01 добавил также `./scripts`. Зависимость `code9-crm-connectors` в `pyproject.toml` api устанавливается из `/packages/crm-connectors`.

---

## 4. Открытые дефекты (переносятся в V1)

| ID | Severity | Описание | Assignee |
|----|----------|----------|----------|
| P1-002 | P1 | Refresh token не ротируется (rolling refresh) | BE |
| P1-005 | P1 | Tenant-эндпоинты support mode не реализованы (AC-11 FAIL) | BE |
| P1-006 | P1 | CSRF-токены отсутствуют | BE + LEAD |
| P1-001 | P1 | Worker log_mask FERNET_KEY/jwt_secret — **CLOSED Wave 4** | Done |
| P1-003 | P1 | Hardcoded FERNET_KEY default — **CLOSED Wave 4** | Done |
| P1-004 | P1 | Tenant regex без crm_ prefix — **CLOSED Wave 4** | Done |
| P2-001 | P2 | Admin logout не revoke refresh-сессию | BE |
| P2-002 | P2 | Нет Redis rate-limit на delete/confirm | BE |
| P2-003 | P2 | Tumbling window вместо sliding window | BE |

**AC FAIL (MVP):**
- AC-11: Tenant-эндпоинты support mode → V1

---

## 5. Команда для MVP Demo

```bash
cd /Users/maci/Desktop/CODE9_ANALYTICS
cp .env.example .env
make demo
# → откройте http://localhost:3000
```

Полная последовательность:
1. `cp .env.example .env`
2. `make up` — поднять все 5 контейнеров
3. `sleep 10` — дождаться healthcheck
4. `make migrate` — применить alembic main-schema миграции
5. `make seed` — создать admin + demo workspace
6. Открыть http://localhost:3000 — зарегистрироваться → подтвердить email (код в `docker compose logs api`) → войти → подключить mock amoCRM → запустить audit → смотреть dashboard

---

## 6. Готовность к Demo

**Вердикт: YES-WITH-CAVEATS**

**Что работает:**
- Полный auth flow (register → verify → login → refresh → logout)
- Mock CRM connection + tenant schema bootstrap
- Sync / Export / Audit jobs через worker
- Dashboard агрегаты
- Admin panel (list workspaces, support-mode start/end)
- Billing mock
- AI anonymizer (P0-001 закрыт)
- Fail-fast секреты для production
- Tenant DDL protection (regex с crm_ prefix)

**Caveats (не блокируют демо):**
1. **AC-11 FAIL**: `/admin/support-mode/session/:id/tenant/*` не реализованы — demo не включает эту часть сценария
2. **Refresh rotation**: не реализован, но для 30-минутного демо не критично
3. **CSRF**: отсутствует, но SameSite=Lax + JSON body снижают риск в dev

**Demo не сломается если:** запускать по RUN_BOOK.md, использовать MOCK_CRM_MODE=true, не пытаться демонстрировать support-mode tenant-данные.
