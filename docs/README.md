# Code9 Analytics — Документация

Навигация по документам. Каждая секция имеет конкретного owner'а (см. `architecture/FILE_OWNERSHIP.md`).

## Product
- [`product/VISION.md`](product/VISION.md) — зачем продукт, для кого, ключевые сценарии.

## Architecture
- [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) — высокоуровневая архитектура: сервисы, потоки данных, multi-tenant.
- [`architecture/TECH_STACK.md`](architecture/TECH_STACK.md) — технологии и обоснование.
- [`architecture/DECISIONS.md`](architecture/DECISIONS.md) — ADR-лог.
- [`architecture/FILE_OWNERSHIP.md`](architecture/FILE_OWNERSHIP.md) — карта владения файлами между ролями.
- [`architecture/CHANGE_REQUESTS.md`](architecture/CHANGE_REQUESTS.md) — заявки на изменение чужих зон.

## DB
- [`db/SCHEMA.md`](db/SCHEMA.md) — полная схема main + tenant template.
- [`db/MIGRATION_STRATEGY.md`](db/MIGRATION_STRATEGY.md) — alembic + multi-schema стратегия.

## API
- [`api/CONTRACT.md`](api/CONTRACT.md) — все endpoints MVP.

## Security
- [`security/AUTH.md`](security/AUTH.md) — пароли, JWT, refresh, 2FA.
- [`security/OAUTH_TOKENS.md`](security/OAUTH_TOKENS.md) — хранение токенов CRM.
- [`security/DELETION_FLOW.md`](security/DELETION_FLOW.md) — flow удаления подключения.
- [`security/ADMIN_SUPPORT_MODE.md`](security/ADMIN_SUPPORT_MODE.md) — админ + support-mode.
- [`security/RETENTION_POLICY.md`](security/RETENTION_POLICY.md) — retention days + jobs.

## AI
- [`ai/RESEARCH_CONSENT.md`](ai/RESEARCH_CONSENT.md) — согласие на анонимизированное исследование.
- [`ai/ANONYMIZER_RULES.md`](ai/ANONYMIZER_RULES.md) — блэк/вайт-листы, правила.

## QA
- [`qa/ACCEPTANCE_CRITERIA.md`](qa/ACCEPTANCE_CRITERIA.md) — критерии приёмки MVP.
- [`qa/MANUAL_TEST_CHECKLIST.md`](qa/MANUAL_TEST_CHECKLIST.md) — чек-лист ручного прохождения.

## Claude / Sub-agents
- [`claude/AGENT_BRIEFS.md`](claude/AGENT_BRIEFS.md) — брифы для 5 ролей Wave 2.

## Approval
- [`PLAN_APPROVAL.md`](PLAN_APPROVAL.md) — пакет решений, требующих одобрения владельца.
