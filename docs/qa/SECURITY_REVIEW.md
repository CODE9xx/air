# Security Review — Code9 Analytics Wave 2

**Дата:** 2026-04-18  
**Ревьюер:** QA/Security Engineer (Wave 3)  
**Scope:** `apps/api/app/**`, `apps/worker/worker/**`, `scripts/**`

---

## 1. Token leakage / Log-masking

### 1.1 Worker — `apps/worker/worker/lib/log_mask.py`

**PASS.** `MaskedLogger` / `mask_bearer` корректно заменяет `Bearer <token>` → `Bearer ***`.  
`mask_dict` покрывает ключи: `access_token`, `refresh_token`, `authorization`, `code_verifier`,
`client_secret`, `password`, `password_hash`, `email_code_hash`, `refresh_token_hash`.

**Gap:** `FERNET_KEY` и `jwt_secret` — **отсутствуют** в `SENSITIVE_KEYS` воркера (только в API-варианте `log_mask.py`). Если они попадут в kwargs worker-логгера, утекут plaintext.  
→ Зафиксировано как **P1-001** в DEFECTS.md.

### 1.2 API — `apps/api/app/core/log_mask.py`

**PASS.** `MaskingFormatter` установлен на root-логгер в `main.py` через `install_log_masker()`.  
`SENSITIVE_KEY_PATTERN` покрывает `fernet_key`, `jwt_secret`, `refresh_token_hash`.  
`BEARER_PATTERN` — корректный regex.

**Gap:** `MaskingFormatter.format()` маскирует только `record.msg` и `record.args`. Если
сообщение пишется через `logger.exception("Unhandled exception: %s", exc)` и `exc` содержит
чувствительные данные в `__str__`, маскировка не применяется к вложенному трейсбеку.  
→ Принято к сведению, низкий риск в MVP.

### 1.3 Grep по `apps/api/app/**/*.py` — f-строки с токенами в логах

Результаты поиска по паттернам `access_token`, `refresh_token`, `Authorization:`:

| Файл | Строка | Контекст | Оценка |
|------|--------|---------|--------|
| `auth/router.py:218` | `access_token=access` | JSON-ответ клиенту (LoginResponse) | OK — это поле ответа, не лог |
| `auth/router.py:308` | `access_token=access` | RefreshResponse | OK |
| `admin/router.py:102` | `"access_token": access` | JSON-ответ admin login | OK |
| `db/models/__init__.py:91` | `refresh_token_hash` | ORM-колонка | OK |
| `core/log_mask.py:17` | Regex-паттерн | Сам маскировщик | OK |

**Вывод: прямых утечек токенов в f-строках логов не обнаружено.**

`email.py:16` — `logger.info("email_sent", extra={"to": to, "subject": subject})` — тема письма (`subject`) содержит описание действия, но не код. Сам **код** передаётся через `body` в `_emit` → `print(msg)`, что выводит код в stdout. Это задокументированное поведение для DEV-режима (`DEV_EMAIL_MODE=log`), не дефект MVP.

---

## 2. Password hashing

**PASS.**  
- `apps/api/app/core/security.py:21-25`: argon2id через `argon2-cffi`, параметры:
  - `time_cost=3` (iter=3) ✅
  - `memory_cost=64 * 1024` (64 MB) ✅
  - `parallelism=2` (par=2) ✅
- Соответствуют `docs/security/AUTH.md §1`.
- `verify_secret()` использует `PasswordHasher.verify()` библиотеки, не ручное сравнение `==`. Timing-safe. ✅
- `needs_rehash()` реализован для будущей автоматической ротации параметров. ✅

---

## 3. JWT

**PASS (с одним gap).**  
- Алгоритм: `HS256` ✅ (`settings.jwt_algorithm`)
- Access TTL: `900 секунд = 15 min` ✅ (`ACCESS_TOKEN_TTL_SECONDS`)
- Отдельный `ADMIN_JWT_SECRET` от `JWT_SECRET` ✅ (`create_access_token` выбирает secret по `scope`)
- `decode_token` проверяет `scope` в payload ✅
- Claims: `sub`, `scope`, `iat`, `exp`, `jti` ✅

**Gap (P2):** Refresh-токен не ротируется при `/auth/refresh`. При каждом вызове выдаётся новый access-токен, но cookie `code9_refresh` и хеш в БД остаются прежними до истечения TTL. `docs/security/AUTH.md §3` описывает "rolling refresh", однако реализация не делает ротацию. Риск: если refresh украдут, его можно использовать все 30 дней.  
→ Зафиксировано как **P1-002** в DEFECTS.md.

- Refresh хранится в `user_sessions.refresh_token_hash` как argon2id-хеш, не plaintext ✅
- При logout → `revoked_at` выставляется в БД ✅
- При password-reset → ВСЕ сессии revoke ✅

---

## 4. OAuth tokens at rest

**PASS.**  
- `apps/worker/worker/lib/crypto.py`: Fernet из `cryptography`, ключ из `os.getenv("FERNET_KEY")` ✅
- Если `FERNET_KEY` не задан → `FernetKeyMissingError` (runtime fail-fast) ✅
- `apps/api/app/db/models/__init__.py:189-190`: `access_token_encrypted = Column(LargeBinary)`, `refresh_token_encrypted = Column(LargeBinary)` — BYTEA ✅
- `_serialize_conn()` в `crm/router.py` — не включает token-поля в ответ ✅
- Расшифровка (`decrypt_token`) — только в `worker/jobs/crm.py`, не в API ✅

**Gap (P2):** `settings.py:52` содержит **захардкоженный дефолтный** `FERNET_KEY`:  
```
default="V2fZ7eYm_Qc_f0p-Jb5HcH8XxJz0Aq7W1GH8wKmYP_M="
```
Если разработчик забудет перекрыть его в .env — dev и prod будут использовать один публичный ключ.  
→ Зафиксировано как **P1-003** в DEFECTS.md.

---

## 5. Tenant isolation

**MOSTLY PASS.**

- `apps/worker/worker/jobs/export.py:101`: `SET LOCAL search_path = {q_schema}, public`  
  Используется `f'"{schema}"'` — это корректное SQL-quoting identifier'а.  
  **Однако**: `SET LOCAL search_path` — **не транзакционный** для DDL, а здесь используется для SELECT/INSERT в рамках транзакции. В PostgreSQL `SET LOCAL` откатывается вместе с транзакцией — это корректно ✅

- Валидация имени схемы: `_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")` в `apply_tenant_template.py:22`.  
  **Gap:** Regex не начинается с `crm_` — документация (`docs/security/DELETION_FLOW.md`) гарантирует prefix `crm_`, но валидатор его не проверяет. Теоретически можно создать схему `public` или `pg_catalog` если передать невалидный tenant_schema напрямую в БД.  
  → Зафиксировано как **P1-004** в DEFECTS.md.

- DROP SCHEMA: `conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))` — identifier в двойных кавычках ✅. Имя предварительно провалидировано через `_validate_schema_name` ✅

---

## 6. Deletion flow

**PASS.**  
- `deletion_requests.expires_at = NOW() + 10 minutes` ✅ (`crm/router.py:285`)
- `max_attempts = 5` ✅ (ORM default `server_default="5"`)
- `email_code_hash = argon2id(code)` ✅ (`hash_secret(code)`)
- После подтверждения → enqueue `delete_connection_data` → `DROP SCHEMA CASCADE` → `status='deleted'`, токены=NULL ✅
- Попытка `delete/request` на уже `deleted/deleting` → HTTP 409 ✅
- `resume_connection` проверяет только `status == "paused"`, но не блокирует `deleted`. **Проверка:**  
  `pause_connection` блокирует `deleted/deleting` → 409 ✅  
  `resume_connection` принимает только `paused`, иначе 409 ✅ — реактивация deleted невозможна на API-уровне.

---

## 7. Admin support mode

**MOSTLY PASS.**

- Отдельная таблица `admin_users` ✅, отдельный `ADMIN_JWT_SECRET` ✅
- Support mode: обязательный `reason: str = Field(min_length=1)` ✅ — пустая строка → 422
- TTL 60 min: `expires_at = _now() + timedelta(minutes=60)` ✅
- `admin_audit_logs` пишется в одной транзакции через `await session.flush()` + одиночный `commit` ✅

**Gap (P1):** `GET /admin/support-mode/current` возвращает `reason` admin-сессии без дополнительной проверки — **это ожидаемо** по документу. OK.

**Gap (P1):** Эндпоинты `/admin/support-mode/session/:id/tenant/*` для чтения tenant-данных **отсутствуют** в реализации (`admin/router.py`). `docs/security/ADMIN_SUPPORT_MODE.md §Доступ к tenant-данным` описывает их, но router их не содержит.  
→ Зафиксировано как **P1-005** в DEFECTS.md.

**Gap (P2):** `admin_logout` не делает `revoked_at` для admin_sessions — нет revoke refresh токена.  
→ **P2-001** в DEFECTS.md.

---

## 8. Rate limiting

**MOSTLY PASS.**

| Endpoint | Реализовано | Лимит | Ключ | Статус |
|---|---|---|---|---|
| `POST /auth/login` | ✅ | 5/min IP | IP | PASS |
| `POST /auth/login` | ✅ | 10/min email | email | PASS |
| `POST /auth/register` | ✅ | 3/min | IP | PASS |
| `POST /admin/auth/login` | ✅ | 5/min | IP | PASS |
| `POST /auth/verify-email/confirm` | ✅ | 10/hour | user_id | PASS |
| `POST /auth/verify-email/request` | ✅ | 3/10min | user_id | PASS |
| `POST /auth/password-reset/request` | ✅ | 3/10min | email | PASS |

**Gap:** `/crm/connections/:id/delete/confirm` — отдельного Redis-ключевого rate-limit нет (защита через `max_attempts` в БД, что достаточно, но не идеально для distributed атак).  
Документ `AUTH.md` упоминает `deletion-confirm 5/10min` как отдельный rate-limit.  
→ **P2-002** в DEFECTS.md.

**Техническое замечание:** реализован tumbling window (bucket = `int(time.time() // window_seconds)`), а не sliding window. Это означает, что атакующий может сделать 2×limit запросов на границе окна. В docs написано "sliding window", реализован — tumbling.  
→ **P2-003** в DEFECTS.md.

---

## 9. CSRF / CORS

**PARTIAL PASS.**

- CORS: `allow_origins=settings.allowed_origins_list` — whitelist из env ✅
- `allow_credentials=True` ✅
- `allow_methods=["*"]` — широко, но стандартно для API ✅
- Cookie: `SameSite=Lax`, `HttpOnly=True`, `Secure=True` (только в prod) ✅

**Gap (P1):** `secure=settings.is_production` — в `development` режиме cookie устанавливается **без Secure флага**. При работе через HTTP в dev это приемлемо, но если разработчик откроет dev API по HTTPS — cookie всё равно пойдёт. Для тестовой среды — не блокер.

**Gap (P1-CSRF):** Нет CSRF-токена на state-changing endpoints. `AUTH.md §8` упоминает `X-Code9-CSRF` как V1-опциональный. Реально не реализован.  
Защита через `SameSite=Lax` частична: Lax не блокирует cross-site навигацию через GET, но блокирует для POST через form. Так как API использует JSON body (не form), риск снижен.  
→ **P1-006** в DEFECTS.md.

---

## 10. SQL injection / DDL injection

**PASS.**

- Все запросы в API через SQLAlchemy ORM с параметрами ✅
- Worker использует `text(...)` с `{"param": value}` placeholders ✅
- DDL (CREATE/DROP SCHEMA): имя в двойных кавычках `f'"{schema}"'` после валидации regex ✅
- `_validate_schema_name()` вызывается до любых DDL-операций в `apply_tenant_template.py` и `worker/lib/tenant.py` ✅
- `SET LOCAL search_path = {q_schema}, public` — `q_schema = f'"{schema}"'` — корректно экранирует ✅

**Gap (P2):** `CAST(:cid AS UUID)` в worker jobs — правильный паттерн, но можно использовать SQLAlchemy UUID type напрямую. Не является дырой, принято к сведению.

---

## Итоговая таблица security findings

| # | Область | Severity | Описание | Статус |
|---|---------|----------|---------|--------|
| S-1 | Log masking | P1 | Worker `log_mask.py` не маскирует `FERNET_KEY`, `jwt_secret` в SENSITIVE_KEYS | OPEN |
| S-2 | JWT/Refresh | P1 | Refresh token не ротируется при `/auth/refresh` (нет rolling) | OPEN |
| S-3 | Fernet key | P1 | Хардкоженный дефолтный FERNET_KEY в settings.py | OPEN |
| S-4 | Tenant DDL | P1 | Regex валидации не требует prefix `crm_` | OPEN |
| S-5 | Admin support | P1 | Tenant-эндпоинты для support mode не реализованы | OPEN |
| S-6 | CSRF | P1 | CSRF-защита отсутствует на mutating endpoints | OPEN |
| S-7 | Cookie | P2 | `secure=False` в non-prod режиме | ACCEPTED |
| S-8 | Rate limit | P2 | Tumbling window вместо sliding window | OPEN |
| S-9 | Rate limit | P2 | Нет Redis rate-limit на `delete/confirm` | OPEN |
| S-10 | Admin logout | P2 | Admin logout не revoke refresh-сессию | OPEN |
