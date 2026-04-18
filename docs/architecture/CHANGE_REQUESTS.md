# Change Requests

Здесь фиксируются заявки агентов на изменение файлов/директорий **вне своей зоны владения** (см. `FILE_OWNERSHIP.md`).

## Как подать заявку

Добавь новый раздел в конец файла по шаблону:

```md
## CR-YYYYMMDD-NN — короткий заголовок

- **Автор (роль):** BE / FE / DW / CRM / QA / LEAD
- **Затронутые файлы:** список путей
- **Owner(ы) зоны:** кого надо согласовать
- **Причина:** что ломается без этого изменения
- **Предлагаемое изменение:** diff / описание
- **Риски:** breaking change? обратная совместимость?
- **Статус:** `proposed` | `approved` | `rejected` | `done`
- **Решение/комментарии:** (после ревью)
```

Пример номера: `CR-20260418-01`.

## Правила

1. Без approved CR менять чужие файлы запрещено.
2. Lead Architect аппрувит любую CR; owner зоны — только свою.
3. После `done` — CR остаётся в истории, не удаляется.

---

## CR-20260418-01 — BE: ORM-модели main-schema в совместной зоне

- **Автор (роль):** BE
- **Затронутые файлы:** `apps/api/app/db/models/__init__.py` (новый файл; раньше пуст / с stub'ом)
- **Owner(ы) зоны:** BE + DW (совместная зона)
- **Причина:** Wave 2 backend-роутерам нужны импортируемые SQLAlchemy-модели
  (`from app.db.models import User, Workspace, CrmConnection, ...`), иначе все
  endpoints не запускаются.
- **Предлагаемое изменение:** добавлены классы для всех таблиц main-schema из
  `docs/db/SCHEMA.md` §1 + дополнительно `AdminSession` и `AdminSupportSession`
  (упомянуты как "DW добавит в Wave 2" в `AUTH.md` и `ADMIN_SUPPORT_MODE.md`).
  Использован уже существующий `_helpers.py` (uuid_pk, now_default, enum_check)
  и `enums.py` без изменений. CHECK-констрейнты построены через `enum_check()`.
- **Особенности:**
  * поле `metadata` именовано как `metadata_json` в Python (т.к. это
    зарезервированное имя у SQLAlchemy DeclarativeBase), на уровне БД — `metadata`.
  * добавлено поле `crm_connections.name` (TEXT, nullable) для пользовательского
    переименования (используется PATCH /crm/connections/:id, см. бриф BE).
  * `deletion_requests.status` поддерживает значение `processing` (есть в
    enum, но отсутствует в SCHEMA.md CHECK — DW: уточнить или расширить CHECK).
- **Риски:** DW при генерации миграций должен использовать те же имена
  таблиц/полей. Если DW предпочитает `metadata` (raw) — переименовать
  Python-атрибут на уровне модели (mapped via `Column("metadata", ...)`) уже
  сделано, миграция — без изменений.
- **Статус:** `done`
- **Решение/комментарии:** Принято BE в Wave 2.

### Resolution (Lead, 2026-04-18)
- Status: CLOSED
- Notes: Изменение принято BE в Wave 2. DW должен подтвердить совместимость имён полей миграций.

## CR-20260418-02 — BE: добавление поля `crm_connections.name`

- **Автор (роль):** BE
- **Затронутые файлы:** `docs/db/SCHEMA.md` §1.6 (нужно добавить колонку);
  `apps/api/app/db/models/__init__.py` (уже добавлено в коде модели).
- **Owner(ы) зоны:** LEAD + DW
- **Причина:** PATCH `/crm/connections/:id` (бриф BE) переименовывает
  подключение — нужна колонка для отображаемого имени.
- **Предлагаемое изменение:** `name TEXT NULL`.
- **Риски:** низкие (новая nullable колонка).
- **Статус:** `done`

### Resolution (Lead, 2026-04-18)
- Status: CLOSED
- Notes: Nullable-колонка `name` добавлена в ORM модели BE. DW — включить в миграцию 0002.

---

## CR-20260418-03 — QA: fail-fast на дефолтные секреты в production

- **Автор (роль):** QA
- **Затронутые файлы:** `apps/api/app/core/settings.py`
- **Owner(ы) зоны:** BE
- **Причина:** `JWT_SECRET`, `ADMIN_JWT_SECRET`, `FERNET_KEY` имеют публичные дефолты. При деплое без перекрытия ENV — токены подписываются/шифруются публичным ключом. Обнаружено при Security Review Wave 3.
- **Предлагаемое изменение:** добавить `model_validator(mode="after")` в `Settings`.
- **Риски:** breaking change только в production — контейнер не стартует без правильных secrets. Это желаемое поведение.
- **Статус:** `done`
- **Решение/комментарии:** Реализован `check_prod_secrets` validator в Settings.

### Resolution (Lead, 2026-04-18)
- Status: CLOSED
- Notes: `@model_validator(mode="after")` добавлен в `apps/api/app/core/settings.py`. При APP_ENV=production с дефолтными JWT_SECRET/ADMIN_JWT_SECRET/FERNET_KEY — контейнер не стартует. Cross-zone approved by Lead (security-critical).

## CR-20260418-04 — QA: tenant-schema regex требует prefix `crm_`

- **Автор (роль):** QA
- **Затронутые файлы:** `scripts/migrations/apply_tenant_template.py:22`, `apps/worker/worker/lib/tenant.py:48`
- **Owner(ы) зоны:** DW
- **Причина:** текущий regex `^[a-z_][a-z0-9_]{0,62}$` допускает зарезервированные имена PostgreSQL (`public`, `pg_catalog`). DROP SCHEMA на такое имя катастрофичен. Обнаружено при Security Review Wave 3.
- **Предлагаемое изменение:** заменить regex в обоих файлах:
  ```python
  _SCHEMA_RE = re.compile(r"^crm_[a-z0-9][a-z0-9_]{1,59}$")
  ```
- **Риски:** низкие — все существующие tenant-схемы начинаются с `crm_` по генератору `generate_tenant_schema`.
- **Статус:** `done`

### Resolution (Lead, 2026-04-18)
- Status: CLOSED
- Notes: Regex обновлён в `scripts/migrations/apply_tenant_template.py` и `apps/worker/worker/lib/tenant.py`. Cross-zone approved by Lead (security-critical DDL injection prevention).

## CR-20260418-05 — QA: rolling refresh-token при /auth/refresh

- **Автор (роль):** QA
- **Затронутые файлы:** `apps/api/app/auth/router.py` (функция `refresh`)
- **Owner(ы) зоны:** BE
- **Причина:** `AUTH.md §3` описывает rolling refresh (ротация токена при каждом использовании). Текущая реализация не ротирует — скомпрометированный refresh действует 30 дней. Security finding P1-002.
- **Предлагаемое изменение:** в `refresh()` endpoint добавить генерацию нового `opaque`, обновить `row.refresh_token_hash`, выставить новый cookie через `Response` параметр.
- **Риски:** требует добавления `Response` в сигнатуру endpoint + обновления `RefreshResponse` или использования `Response` напрямую.
- **Статус:** `proposed`

### Resolution (Lead, 2026-04-18)
- Status: DEFERRED to V1
- Notes: Требует существенного рефакторинга auth/router.py (BE-зона). Риск для MVP-demo незначителен (refresh TTL 30 дней, нет production-трафика). Реализовать в V1 совместно с CSRF-токенами. Assignee: BE.

## CR-20260418-06 — QA: добавить FERNET_KEY и jwt_secret в worker SENSITIVE_KEYS

- **Автор (роль):** QA
- **Затронутые файлы:** `apps/worker/worker/lib/log_mask.py:13-25`
- **Owner(ы) зоны:** DW
- **Причина:** worker `SENSITIVE_KEYS` не содержит `fernet_key`, `jwt_secret`. При случайном логировании — утечка в stdout. Security finding P1-001.
- **Предлагаемое изменение:** добавить в `SENSITIVE_KEYS`:
  ```python
  "fernet_key",
  "jwt_secret",
  "admin_jwt_secret",
  ```
- **Риски:** нет.
- **Статус:** `done`

### Resolution (Lead, 2026-04-18)
- Status: CLOSED
- Notes: `fernet_key`, `jwt_secret`, `admin_jwt_secret` добавлены в SENSITIVE_KEYS в `apps/worker/worker/lib/log_mask.py`. Cross-zone minor security fix approved by Lead.

## CR-20260418-07 — QA: реализовать tenant-эндпоинты support mode

- **Автор (роль):** QA
- **Затронутые файлы:** `apps/api/app/admin/router.py`
- **Owner(ы) зоны:** BE
- **Причина:** AC-11 и `ADMIN_SUPPORT_MODE.md` требуют эндпоинтов `/admin/support-mode/session/:id/tenant/*`. Не реализованы в Wave 2. Заблокировано: `❌ FAIL` в AC_REPORT.
- **Предлагаемое изменение:** добавить роуты с dependency-проверкой `AdminSupportSession` и audit-logging каждого запроса.
- **Риски:** средние — требует доступа к tenant-схеме из main-schema контекста (SET search_path).
- **Статус:** `proposed`

### Resolution (Lead, 2026-04-18)
- Status: DEFERRED to V1
- Notes: Реализация требует серьёзной работы в BE-зоне (admin/router.py + tenant search_path + audit middleware). AC-11 остаётся FAIL для MVP-demo, но не блокирует демонстрацию основного сценария. Assignee: BE. Priority: P1 для V1.

## CR-20260418-08 — QA: создать packages/ai/anonymizer.py

- **Автор (роль):** QA
- **Затронутые файлы:** `packages/ai/anonymizer.py` (новый файл)
- **Owner(ы) зоны:** BE (AI-зона)
- **Причина:** P0-001 — модуль описан в `ANONYMIZER_RULES.md §5`, требуется для AC-10 (AI). Тесты `test_anonymizer.py` написаны, но все skip до появления модуля.
- **Предлагаемое изменение:** реализовать `anonymize(text) -> (str, PrivacyRisk)` и `build_research_pattern(...)` согласно документу.
- **Риски:** нет production-зависимостей от отсутствующего модуля (job делает mock).
- **Статус:** `done`

### Resolution (Lead, 2026-04-18)
- Status: CLOSED
- Notes: Создан `packages/ai/src/packages_ai/anonymizer.py` с функциями `anonymize()` и `build_research_pattern()`. Реализованы regex-паттерны для email, телефонов RU/EN, ИНН (с проверкой контрольной суммы), паспорта РФ, кредитных карт (Luhn), IP v4. Privacy risk: low/medium/high согласно ANONYMIZER_RULES.md. AC-10 разблокирован. P0-001 закрыт. Cross-zone approved by Lead (MVP-blocker).

---

## CR-20260418-09 — LEAD: рассинхрон пути RQ-job delete_connection_data

- **Автор (роль):** LEAD
- **Затронутые файлы:** `apps/worker/worker/jobs/retention.py`
- **Owner(ы) зоны:** DW
- **Причина:** BE enqueue строит путь `worker.jobs.retention.delete_connection_data`, но функция находится в `worker.jobs.delete`. При постановке job в Redis — RQ не сможет найти callable.
- **Предлагаемое изменение:** добавить re-export в `retention.py`:
  ```python
  from .delete import delete_connection_data as delete_connection_data
  ```
- **Риски:** нет — re-export без изменения логики.
- **Статус:** `done`

### Resolution (Lead, 2026-04-18)
- Status: CLOSED (LEAD-001)
- Notes: Добавлен re-export `delete_connection_data` в `apps/worker/worker/jobs/retention.py`. RQ теперь корректно разрешает путь `worker.jobs.retention.delete_connection_data`. Альтернативный fix — изменить маппинг в BE (CR требуется), но re-export чище для MVP.
