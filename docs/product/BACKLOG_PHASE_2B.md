# Phase 2B Backlog — отложенные направления

**Дата:** 2026-04-21
**Статус:** draft
**Предыдущая фаза:** Phase 2A закрыт коммитом `268ab43` (см. `docs/architecture/PHASE_2A_REPORT.md`).
**Владелец скоупа:** Lead Engineer + Product.

---

## Зачем этот документ

После закрытия Phase 2A у нас остался набор направлений, которые либо **сознательно отложены** (потому что в 2A был жёсткий фокус «от кнопки amoCRM до counts в UI»), либо **обнаружены** в процессе 2A и не вписались в scope. Этот файл — single source of truth для Phase 2B planning.

**Правила:**
- Каждый item имеет: scope, why-deferred, AC (acceptance criteria), зависимости, приблизительный weight (S/M/L).
- Порядок в документе ≠ приоритет. Приоритизация — отдельно, после Gate B Sprint 1.
- Item нельзя закрывать без явного cross-reference из commit message (`feat: ... (closes BACKLOG_PHASE_2B#N)`).

---

## B2B-1. Companies

**Scope.** Вторая сущность в CRM-модели (после deals/contacts) — компания/юрлицо. В amoCRM это `companies`; в нашей текущей модели — нет.

**Why deferred.** В Phase 2A фокус был на demo-кейс «воронка + сделки + менеджеры + контакты». Companies — отдельная таблица в tenant schema, отдельный pull, отдельный UI-вью. Не блокирует аудит базового уровня.

**AC:**
- В `packages/crm-connectors/amocrm.py` добавлен `fetch_companies` (paginated, cap 100 на первом pull).
- В tenant schema — таблица `companies` (id, crm_id, name, created_at, updated_at, responsible_user_id, custom_fields JSONB).
- В `metadata.last_pull_counts.companies` — счётчик.
- UI ConnectionCard показывает `companies` в строке counts.
- Dashboard `/app/dashboards/overview` — блок «компании» (total, new за период).

**Зависимости:** — (самостоятельное направление).

**Weight:** M.

---

## B2B-2. Emails

**Scope.** Переписка с контактами/сделками через CRM email-модуль (в amoCRM это `notes` с `note_type='email_message_*'` + dedicated email-endpoints).

**Why deferred.** Emails — самый тяжёлый источник трафика в API amoCRM, частый кандидат на rate-limit. В 2A этот риск не брали. Также для аудита нужно решить privacy-gate (см. B2B-4).

**AC:**
- В `packages/crm-connectors/amocrm.py` добавлен `fetch_emails` (paginated, last_modified cursor).
- В tenant schema — таблица `emails` (id, crm_id, thread_id, from, to, subject, body_text, body_html, entity_type, entity_id, created_at).
- Privacy-gate (см. B2B-4) применяется до сохранения body.
- AI-анализ (B2B-7) умеет читать email-треды.

**Зависимости:** B2B-4 (privacy gate), B2B-5 (token estimate для AI).

**Weight:** L.

---

## B2B-3. Chats

**Scope.** Мессенджер-диалоги, привязанные к сделкам/контактам (WhatsApp/Telegram/другие каналы, которые в amoCRM проходят как chat-notes).

**Why deferred.** Те же причины что и для emails — объём + privacy. Плюс разнородность форматов (текст / media / voice-сообщения).

**AC:**
- В `packages/crm-connectors/amocrm.py` добавлен `fetch_chats` (incremental, channel-aware).
- В tenant schema — таблица `chats` (id, crm_id, channel, from, to, text, media_ref, entity_id, created_at).
- Media (audio/images) — только ссылки, не контент (privacy).
- Privacy-gate применяется до сохранения текста.
- AI-анализ умеет читать chat-треды.

**Зависимости:** B2B-4 (privacy gate), B2B-5 (token estimate).

**Weight:** L.

---

## B2B-4. Calls privacy gate

**Scope.** Формальный механизм согласия/исключения для звонков и чувствительной переписки перед их анализом/хранением.

**Why deferred.** В 2A calls не тянули в принципе. Перед тем как тянуть — нужно решить:
1. Даёт ли пользователь **явное согласие** на хранение body разговоров.
2. На **каких ролях** (владелец / РОП / менеджер) включать по умолчанию.
3. Какая **retention** для записей (audio — не храним, расшифровка — опционально).
4. Как **анонимизировать** PII в теле сообщения до отправки в LLM.

**AC:**
- Schema: `workspaces.privacy_config JSONB` с полями `calls_enabled`, `emails_enabled`, `chats_enabled`, `ai_anonymize_level` (off/emails-phones/all).
- UI: `/app/settings/privacy` с понятным копирайтингом на RU/EN.
- Backend: перед pull'ом calls/emails/chats проверяется `privacy_config.<kind>_enabled`; если `false` — pull пропускается (+ лог).
- Анонимайзер (`packages/ai/anonymizer.py`) применяется до отправки в LLM.
- Тесты: интеграционный тест что `calls_enabled=false` → 0 записей в tenant.calls после pull.

**Зависимости:** — (блокер для B2B-2, B2B-3, calls-pull).

**Weight:** M.

---

## B2B-5. Token estimate

**Scope.** Перед запуском AI-job на больших объёмах (тред из 500 писем) — оценивать стоимость в токенах и показывать pre-approval UI.

**Why deferred.** В 2A AI не запускали на реальных данных. Первый real-run без estimate = риск неожиданного счёта.

**AC:**
- Функция `estimate_tokens(texts: list[str], model: str) -> {input, output_est, cost_usd}`.
- UI: перед «Запустить AI-анализ» — modal с estimate + подтверждение.
- Backend: job отказывается стартовать, если estimate > `workspace.ai_budget_remaining`.
- Ledger: `ai_spend` списания с workspace billing balance.

**Зависимости:** — (блокер для запуска AI в проде).

**Weight:** S.

---

## B2B-6. Lost clients

**Scope.** Отдельный отчёт «потерянные клиенты» — сделки, которые были в работе, но закрылись как lost, с группировкой по причинам и по менеджерам.

**Why deferred.** В 2A был базовый audit-отчёт без этой агрегации. Добавить в 2B как отдельный view, а не мешать в общий dashboard.

**AC:**
- SQL-вью `lost_deals_view` в tenant schema (fields: deal_id, reason, manager_id, lost_at, days_in_pipeline).
- Endpoint `GET /api/v1/workspaces/{ws}/reports/lost-clients?from=…&to=…`.
- UI `/app/reports/lost-clients` — таблица + bar-chart по reason, stacked по manager.
- Экспорт CSV.

**Зависимости:** — (работает на уже существующих deals, нужны lost-reasons в custom_fields).

**Weight:** S.

---

## B2B-7. AI chat

**Scope.** Conversational UI внутри кабинета: пользователь задаёт вопрос «сколько у меня брошенных сделок в Q3?» — получает ответ через LLM, который генерирует SQL → выполняет в tenant schema → пересказывает.

**Why deferred.** Это самый амбициозный item — требует готового token estimate (B2B-5), готовых данных (companies/emails/chats если вопрос их касается), privacy gate (B2B-4). Плюс отдельный security review (SQL injection через LLM — реальная угроза).

**AC:**
- Endpoint `POST /api/v1/workspaces/{ws}/ai/chat` (streaming).
- Sandboxed SQL runner: только `SELECT`, только tenant schema, timeout 5s, row limit 10k.
- UI: drawer/panel в кабинете с историей чата (in-memory per session, не храним).
- PII в запросе/ответе → анонимайзер.
- Токены списываются с ledger через B2B-5.
- Security review passed (пропущен без review — запрещено к запуску).

**Зависимости:** B2B-4, B2B-5, B2B-1/2/3 (для полезных ответов).

**Weight:** L+ (требует security review).

---

## Cross-cutting / инфраструктурные items (не из списка, но блокируют некоторые B2B-*)

Эти пункты переносятся из Gate A technical debt, они **не** являются Phase 2B feature work, но могут блокировать отдельные B2B-items:

- **Rolling refresh + session table** (P1-002, P1-005, P1-006 из Wave 4). Нужен перед public launch (Gate C). Для closed pilot (Gate B) — желателен. Не блокирует B2B-1..7 напрямую.
- **CSRF double-submit** (P1-006). Аналогично.
- **Offsite backup + restore drill** (P1-008 из Phase 2A report). Блокер Gate B.
- **Sentry / uptime** (из Gate B criteria). Желательно до первых real-pilot клиентов.

Их планирование — вне scope этого документа; см. `docs/deploy/PRODUCTION_CHECKLIST.md` Gate B.

---

## История документа

| Дата | Изменение |
|------|-----------|
| 2026-04-21 | Создан. 7 items из директивы пользователя + cross-cutting раздел. |
