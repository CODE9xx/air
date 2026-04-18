# Manual Test Checklist — Code9 Analytics MVP

Чек-лист для ручного прохождения перед релизом MVP-1. Идём по порядку.

## 0. Предусловия

- [ ] `.env` скопирован из `.env.example`, `FERNET_KEY` сгенерирован, `JWT_SECRET` и `ADMIN_JWT_SECRET` заполнены.
- [ ] `docker compose up --build` выполнено без ошибок.
- [ ] `docker compose ps` — все 5 сервисов `healthy` / `running`.

## 1. Smoke

- [ ] `curl http://localhost:8000/` → 200.
- [ ] `curl http://localhost:8000/health` → 200 `{status:ok}`.
- [ ] `curl http://localhost:3000/health` → 200.
- [ ] `curl http://localhost:3000` → HTML с «Code9 Analytics — coming soon».

## 2. Регистрация и email-verify

- [ ] Регистрация нового user через UI `/register`.
- [ ] В логах api появилась строка `[DEV EMAIL] code=XXXXXX purpose=email_verify`.
- [ ] Ввод кода → `email_verified=true` в БД (`select email_verified_at from users;`).

## 3. Login / logout

- [ ] Login без verify → ошибка.
- [ ] Login с verify → редирект на `/dashboard`.
- [ ] В DevTools cookie `code9_refresh` — httpOnly, secure.
- [ ] Refresh по истечении access → новый access (DevTools Network).
- [ ] Logout → cookie удалён, в БД session.revoked_at != NULL.

## 4. Password reset

- [ ] `/forgot-password` → email-код в логе.
- [ ] Ввод кода + новый пароль → login со старым паролем не работает.
- [ ] Все предыдущие refresh-токены user'а revoked.

## 5. Workspace

- [ ] Создать workspace `Acme` со slug `acme`.
- [ ] Invite user `b@example.com` с role=`analyst` → появился pending member.
- [ ] Логин второго user → видит workspace `Acme` после accept.

## 6. CRM connection (mock)

- [ ] `POST /workspaces/:wsid/crm/connections` с `provider=amocrm`.
- [ ] UI показывает status=active за <5s.
- [ ] В Postgres: `SELECT tenant_schema FROM crm_connections` → `crm_amo_xxxxxxxx`.
- [ ] `\dn` в psql → появилась новая schema.
- [ ] `GET /workspaces/:wsid/crm/connections` — **нет** полей с `token`.

## 7. Sync

- [ ] `POST /crm/connections/:id/sync` → job_id.
- [ ] Через ≤30s: `select count(*) from crm_amo_xxxxxxxx.raw_deals` → ≥ 10.
- [ ] В worker-логах — «[job fetch_crm_data] completed».
- [ ] Notification `sync_complete` появилась в UI.

## 8. Audit

- [ ] `POST /workspaces/:wsid/audit/reports` → job_id.
- [ ] `GET /workspaces/:wsid/audit/reports/:id` — минимум 5 метрик.

## 9. Export

- [ ] `POST /workspaces/:wsid/export/jobs` с `entities=[deals,contacts,tasks]`.
- [ ] Status `succeeded` за ≤60s.
- [ ] `download_url` скачивается, внутри ZIP — CSV + JSON.

## 10. Dashboards

- [ ] `/dashboards/overview` показывает funnel, managers_activity.
- [ ] Числа сходятся с `SELECT count(*)` по deals в tenant.

## 11. Billing (mock)

- [ ] `POST /workspaces/:wsid/billing/deposits` `{amount_cents:100000}` → ledger row.
- [ ] `balance_cents` пересчитывается (`recalc_balance` job).
- [ ] Webhook-endpoint возвращает 200 на mock-payload.

## 12. AI

- [ ] `POST /workspaces/:wsid/ai/consent {action:accept}` → status=accepted.
- [ ] `POST /workspaces/:wsid/ai/analysis-jobs` с `input_ref={call_id:<valid>}` → job → `ai_conversation_scores` row.
- [ ] После N≥10 скорингов → `ai_research_patterns` содержит запись с industry workspace'а.
- [ ] `POST /workspaces/:wsid/ai/consent {action:revoke}` → новые scoring'и НЕ пишут в research_patterns.
- [ ] В `ai_conversation_scores.raw_llm_output` — нет PII (регулярками).

## 13. Admin

- [ ] `/admin/login` с `ADMIN_BOOTSTRAP_EMAIL / _PASSWORD` → успех.
- [ ] `/admin/workspaces` — виден список.
- [ ] Support-mode start без `reason` → 400.
- [ ] Support-mode start с `reason` → доступ к `/admin/support-mode/session/:id/tenant/deals`.
- [ ] Каждый tenant-запрос → строка в `admin_audit_logs` с `action=support_mode_read_tenant`, `metadata.session_id`, `metadata.reason`.
- [ ] После 60 мин — session истекает, следующий запрос → 403.

## 14. Delete connection

- [ ] `POST /crm/connections/:id/delete/request` → код в логе.
- [ ] 4 неверных ввода кода → пятый — тоже неверный → row `status=cancelled`, ошибка `too_many_attempts`.
- [ ] Новый request → новый код → правильный ввод → через ≤30s `crm_connections.status=deleted`, tenant schema DROPPED.
- [ ] `\dn` в psql — старой schema нет.
- [ ] `SELECT access_token_encrypted FROM crm_connections WHERE id=...` → NULL.
- [ ] `billing_ledger` записи по этому workspace — остались.

## 15. Retention (dev-run)

- [ ] Вручную запустить `retention_delete_daily` через `make worker-shell`.
- [ ] Connections с `deleted_at < NOW() - interval '90 days'` — фактически удалены (tenant dropped).

## 16. Security sanity

- [ ] Grep по логам api за 10 минут работы — нет совпадений с regex `[Bb]earer [A-Za-z0-9]{20,}`.
- [ ] Grep — нет строк вида `"access_token":"[^\*]`.
- [ ] `psql` → все поля `*_token_encrypted` — `bytea`, не `text`.

## 17. i18n

- [ ] Переключатель RU↔EN на `/` меняет все видимые тексты.
- [ ] В UI нет хардкод-строк на русском/английском в компонентах (grep по `apps/web` на кириллицу/латиницу должен давать только `messages/*.json`).
