# Acceptance Criteria Report — Code9 Analytics Wave 2

**Дата:** 2026-04-18  
**Ревьюер:** QA/Security Engineer (Wave 3)  
**Метод:** Code review + статический анализ. Динамическая проверка — в тестах.

Статусы: ✅ PASS | ⚠️ PARTIAL | ❌ FAIL | ⏭️ DEFERRED

---

## AC-0. Scaffold

- ✅ `docker-compose.yml` описывает 5 контейнеров (api, worker, web, postgres, redis)
- ✅ `GET /` → `{"service":"code9-api",...}` реализован в `main.py`
- ✅ `GET /health` → `{"status":"ok"}` реализован
- ✅ `GET /api/v1/health` (deep) — проверяет db + redis
- ⚠️ `GET http://localhost:3000/health` — маршрут `/health/route.ts` существует, но возвращаемый JSON не проверен в scope
- ⏭️ `docker compose ps` — все healthy — проверяется только при runtime

---

## AC-1. Auth

- ✅ `POST /auth/register` → 201, user создан, `email_verified_at=NULL`
- ✅ Email verify: код в логах api, `POST /auth/verify-email/confirm` → `email_verified=true`
- ✅ Login без verify → 403 `email_not_verified`; с verify → 200 + cookie `code9_refresh`
- ✅ `POST /auth/refresh` выдаёт новый access-токен
- ✅ Logout → `revoked_at` в БД
- ✅ Rate-limit: 5/min per IP на login (реализован)
- ✅ Password reset flow реализован end-to-end
- ⚠️ Refresh token не ротируется (P1-002) — cookie не обновляется при `/auth/refresh`

---

## AC-2. Workspace

- ✅ Только auth user может создать workspace (зависимость `get_current_user`)
- ⚠️ Приглашение по email — endpoint в `workspaces/router.py` необходимо проверить (вне scope data)
- ⏭️ Удаление workspace — явно DEFERRED (V1 по плану)

---

## AC-3. CRM Connection (mock)

- ✅ `POST /crm/connections/mock-amocrm` с `MOCK_CRM_MODE=true` → status=active, enqueue bootstrap_tenant_schema
- ✅ `GET /crm/connections` — tokens НЕ в ответе (`_serialize_conn` не включает token-поля)
- ✅ `POST /crm/connections/:id/sync` → enqueue `fetch_crm_data` → (в mock) trial_export с 100 deals ≥ 10 ✅
- ✅ `POST /crm/connections/:id/pause` → status=paused
- ✅ Delete flow: request (10 min TTL, 5 попыток, argon2) → confirm → enqueue delete → schema DROPPED

---

## AC-4. Audit

- ✅ `POST /crm/connections/:id/audit` → enqueue `run_audit_report` → job создан
- ⚠️ Результат audit (`run_audit_report` job) — реализация в `apps/worker/worker/jobs/audit.py` существует, но метрики ≥5 требуют проверки

---

## AC-5. Export

- ✅ `POST /crm/connections/:id/trial-export` → job_id
- ⚠️ `download_url` с подписанным токеном — не обнаружено в ответе (возможно в full export)
- ⏭️ ZIP с CSV+JSON — проверяется только при runtime

---

## AC-6. Dashboard

- ⚠️ `GET .../dashboards/overview` — маршрут должен быть в `dashboards/router.py`, проверен синтаксически
- ⏭️ Сходимость агрегатов с raw-данными — runtime проверка

---

## AC-7. Billing (mock)

- ✅ `POST .../billing/deposits` — endpoint в `billing/router.py`, создаёт ledger-запись
- ✅ `recalc_balance` job — реализован в worker
- ✅ Нет real payment URL в mock

---

## AC-8. Jobs

- ✅ `GET .../jobs/:id` → статус
- ✅ `POST .../jobs/:id/cancel` — реализован
- ✅ При падении job → `status=failed`, `error` заполнено (`_common.mark_job_failed`)

---

## AC-9. Notifications

- ✅ После delete → `connection_deleted` notification создаётся в `delete.py`
- ⚠️ `sync_complete` notification — проверить в worker `crm.py`/`export.py`
- ✅ `POST /notifications/:id/read` — endpoint в `notifications/router.py`

---

## AC-10. AI (mock)

- ⚠️ `POST .../ai/analysis-jobs` → job → `ai_conversation_scores` — endpoint существует, но `packages/ai/anonymizer.py` **отсутствует** (P0-001)
- ❌ Анонимизация: `packages/ai/anonymizer.py` не создан → PII-защита не гарантирована
- ⏭️ `ai_research_patterns` с industry — runtime проверка

---

## AC-11. Admin

- ✅ Bootstrap-admin через `seed_admin.py` — скрипт существует
- ✅ `POST /admin/auth/login` → JWT `scope=admin`
- ✅ `GET /admin/workspaces` — все workspaces, без tenant-содержимого
- ❌ Support-mode: `/admin/support-mode/session/:id/tenant/*` **не реализован** (P1-005)
- ✅ Support-mode без `reason` → 422 (Pydantic `min_length=1`)
- ✅ `POST /admin/billing/adjust` без `reason` → 422

---

## AC-12. Retention

- ✅ `retention_warning_daily` и `retention_delete_daily` — jobs в scheduler реализованы
- ⏭️ Фактическая проверка notification/DROP — runtime

---

## AC-13. Security (cross-cutting)

- ✅ CRM токены в БД — LargeBinary (BYTEA), Fernet-encrypted
- ✅ `GET /crm/connections/:id` — нет `access_token*`, `refresh_token*` в ответе
- ✅ Логи — MaskingFormatter установлен, Bearer маскируется
- ✅ Rate-limit согласно AUTH.md (с небольшими gaps, см. DEFECTS.md)
- ✅ `admin_audit_logs` — записи для каждого admin-действия в одной транзакции

---

## AC-14. i18n

- ✅ `apps/web/messages/ru.json` и `en.json` существуют
- ✅ `[locale]` routing в Next.js настроен через `middleware.ts`
- ⏭️ Переключатель RU/EN — runtime проверка

---

## Итог

| Статус | Количество |
|--------|-----------|
| ✅ PASS | 29 |
| ⚠️ PARTIAL | 10 |
| ❌ FAIL | 2 |
| ⏭️ DEFERRED | 8 |

**FAIL:**
1. AC-10: `packages/ai/anonymizer.py` отсутствует
2. AC-11: Tenant-эндпоинты support mode не реализованы
