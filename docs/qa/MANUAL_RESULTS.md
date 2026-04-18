# Manual Test Results — Code9 Analytics MVP

**Дата:** 2026-04-18  
**Метод:** Статический анализ кода + проверка реализации. Динамические тесты отмечены как [нужна среда].

---

### Section 0. Предусловия

- [x] 0.1 `.env.example` существует, содержит все ключи (FERNET_KEY, JWT_SECRET, ADMIN_JWT_SECRET)
- [x] 0.2 `docker-compose.yml` описывает 5 сервисов (api, worker, web, postgres, redis)
- [ ] 0.3 `docker compose up --build` без ошибок — [нужна среда]
- [ ] 0.4 `docker compose ps` — все 5 `healthy` — [нужна среда]

---

### Section 1. Smoke

- [x] 1.1 `GET /` → `{"service":"code9-api",...}` (реализовано в `main.py`)
- [x] 1.2 `GET /health` → 200 `{status:ok}` (реализовано)
- [ ] 1.3 `GET http://localhost:3000/health` → 200 [нужна среда]
- [ ] 1.4 `GET http://localhost:3000` → HTML [нужна среда]

---

### Section 2. Регистрация и email-verify

- [x] 2.1 `POST /auth/register` → 201, workspace создан (проверено в `test_auth.py::test_register`)
- [x] 2.2 В логах api строка `EMAIL -> ...` (реализовано через `email.py:print`)
- [x] 2.3 `POST /auth/verify-email` с кодом → `email_verified=true` (проверено в `test_auth.py::test_verify_email`)
- [ ] 2.4 Регистрация через UI `/register` — [нужна среда]

---

### Section 3. Login / logout

- [x] 3.1 Login без verify → 403 `email_not_verified` (реализовано в `auth/router.py:195-199`)
- [x] 3.2 Login с verify → 200 + cookie `code9_refresh` (проверено в `test_auth.py::test_login`)
- [ ] 3.3 Cookie httpOnly, secure в DevTools — [нужна среда]
- [x] 3.4 `POST /auth/refresh` с cookie → новый access (реализовано в `auth/router.py:261-308`)
- [x] 3.5 Logout → `revoked_at` в БД (реализовано в `auth/router.py:232-256`)
- [ ] 3.6 Cookie удалён после logout в браузере — [нужна среда]

---

### Section 4. Password reset

- [x] 4.1 `POST /auth/password-reset/request` → email-код (реализовано в `auth/router.py:436-460`)
- [x] 4.2 `POST /auth/password-reset/confirm` с кодом + новым паролем → OK (проверено в `test_auth.py`)
- [x] 4.3 Все предыдущие refresh-сессии revoked после смены пароля (реализовано в `auth/router.py:517-528`)
- [ ] 4.4 Login со старым паролем не работает после reset — [нужна среда]

---

### Section 5. Workspace

- [x] 5.1 Workspace создаётся автоматически при регистрации (реализовано в `auth/router.py:116-138`)
- [ ] 5.2 `POST /workspaces/:wsid/members/invite` с role=analyst → pending member — [нужна среда]
- [ ] 5.3 Второй user видит workspace после accept — [нужна среда]

---

### Section 6. CRM connection (mock)

- [x] 6.1 `POST /crm/connections/mock-amocrm` → status=active в ответе, enqueue job (реализовано в `crm/router.py:134-183`)
- [ ] 6.2 UI показывает status=active за <5s — [нужна среда]
- [ ] 6.3 Postgres: `SELECT tenant_schema` — `crm_amo_xxxxxxxx` — [нужна среда]
- [x] 6.4 `GET /crm/connections` — нет token-полей в ответе (проверено в `_serialize_conn`)

---

### Section 7. Sync

- [x] 7.1 `POST /crm/connections/:id/sync` → job_id (реализовано)
- [ ] 7.2 `select count(*) from crm_amo_xxxxxxxx.raw_deals` → ≥10 за ≤30s — [нужна среда]
- [ ] 7.3 Worker-лог «[job fetch_crm_data] completed» — [нужна среда]
- [ ] 7.4 Notification `sync_complete` в UI — [нужна среда]

---

### Section 8. Audit

- [x] 8.1 `POST /crm/connections/:id/audit` → job_id (реализовано)
- [ ] 8.2 Отчёт с ≥5 метриками за ≤15s — [нужна среда]

---

### Section 9. Export

- [x] 9.1 `POST /crm/connections/:id/trial-export` → job_id (реализовано)
- [ ] 9.2 Status `succeeded` за ≤60s — [нужна среда]
- [ ] 9.3 `download_url` скачивается, ZIP корректный — [нужна среда]

---

### Section 10. Dashboards

- [ ] 10.1 `/dashboards/overview` → funnel, managers_activity — [нужна среда]
- [ ] 10.2 Числа сходятся с SELECT count — [нужна среда]

---

### Section 11. Billing (mock)

- [ ] 11.1 `POST /billing/deposits` → ledger row — [нужна среда]
- [ ] 11.2 `balance_cents` пересчитывается — [нужна среда]

---

### Section 12. AI

- [ ] 12.1 `POST /ai/consent {action:accept}` → status=accepted — [нужна среда]
- [ ] 12.2 `POST /ai/analysis-jobs` → `ai_conversation_scores` — [нужна среда; **blocker** P0-001 anonymizer missing]
- [ ] 12.3 После N≥10 scoring → `ai_research_patterns` — [нужна среда]
- [ ] 12.4 `ai_conversation_scores.raw_llm_output` без PII — [нужна среда]

---

### Section 13. Admin

- [x] 13.1 `POST /admin/auth/login` с bootstrap email/password → JWT scope=admin (реализовано в `admin/router.py`)
- [x] 13.2 `GET /admin/workspaces` → список (реализовано)
- [x] 13.3 Support-mode start без `reason` → 422 (Pydantic min_length=1)
- [x] 13.4 Support-mode start с `reason` → `support_session_id` (реализовано)
- [ ] 13.5 Доступ к `/admin/support-mode/session/:id/tenant/deals` — **❌ НЕ РЕАЛИЗОВАН** (P1-005)
- [ ] 13.6 `admin_audit_logs` строка при каждом tenant-запросе — [нужна среда; нет endpoint'ов]
- [ ] 13.7 После 60 мин → 403 — [нужна среда]

---

### Section 14. Delete connection

- [x] 14.1 `POST /crm/connections/:id/delete/request` → deletion_request, код в логе (реализовано)
- [x] 14.2 5 неверных попыток → `status=cancelled`, `too_many_attempts` (проверено в `test_workspace.py`)
- [ ] 14.3 Правильный код → status=deleted, schema DROPPED за ≤30s — [нужна среда]
- [ ] 14.4 `\dn` — старой schema нет — [нужна среда]
- [ ] 14.5 `access_token_encrypted` = NULL — [нужна среда]
- [x] 14.6 `billing_ledger` записи остались (не удаляются по FK design)

---

### Section 15. Retention

- [ ] 15.1 `retention_delete_daily` вручную → connections >90 дней удалены — [нужна среда]

---

### Section 16. Security sanity

- [x] 16.1 Grep по логам: нет `Bearer [A-Za-z0-9]{20,}` — MaskingFormatter установлен в `main.py` (статически подтверждено)
- [x] 16.2 Grep: нет `"access_token":"[^\*]` — `_serialize_conn` не возвращает токены
- [x] 16.3 `*_token_encrypted` — LargeBinary (BYTEA), не Text — подтверждено в ORM-моделях

---

### Section 17. i18n

- [x] 17.1 `messages/ru.json` и `messages/en.json` существуют
- [ ] 17.2 Переключатель RU/EN в UI — [нужна среда]
- [ ] 17.3 Нет хардкод-строк вне `messages/*.json` — [grep по apps/web вне scope QA]
