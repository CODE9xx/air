# File Ownership — Code9 Analytics

Цель: каждый файл в monorepo имеет **одного ответственного агента** (роль). Остальные могут читать, но правят только через **CHANGE_REQUESTS**.

## Роли

| Ключ | Роль | Основная зона |
|---|---|---|
| `LEAD` | Lead Architect | infra, docker, docs, корневые конфиги |
| `BE` | Backend Engineer | `apps/api/` |
| `FE` | Frontend Engineer | `apps/web/` |
| `DW` | DB & Worker Engineer | `apps/worker/`, миграции, tenant-schema, seed |
| `CRM` | CRM Integration Engineer | `packages/crm-connectors/` |
| `QA` | QA Engineer | `tests/`, `docs/qa/` |

## Карта владения

| Путь | Owner | Могут читать | Менять только через PR/CR |
|---|---|---|---|
| `/README.md` | LEAD | все | — |
| `/docker-compose.yml` | LEAD | все | — |
| `/.env.example` | LEAD | все | — |
| `/.gitignore`, `/.editorconfig`, `/.dockerignore`, `/Makefile` | LEAD | все | — |
| `infra/**` | LEAD | все | — |
| `docs/architecture/**` | LEAD | все | — |
| `docs/product/**` | LEAD | все | — |
| `docs/security/**` | LEAD | все | BE (по согласованию) |
| `docs/api/CONTRACT.md` | LEAD + BE (совместно) | все | меняется парой LEAD+BE через CR |
| `docs/db/SCHEMA.md` | LEAD + DW | все | LEAD+DW через CR |
| `docs/db/MIGRATION_STRATEGY.md` | DW | все | — |
| `docs/ai/**` | LEAD | все | — |
| `docs/claude/AGENT_BRIEFS.md` | LEAD | все | — |
| `docs/PLAN_APPROVAL.md` | LEAD | все | — |
| `docs/qa/**` | QA | все | — |
| `docs/README.md` | LEAD | все | — |
| `apps/api/app/main.py` | BE | все | — |
| `apps/api/app/auth/**` | BE | все | — |
| `apps/api/app/users/**` | BE | все | — |
| `apps/api/app/workspaces/**` | BE | все | — |
| `apps/api/app/crm/**` | BE | все | CRM Integration (контракт коннекторов — через CR) |
| `apps/api/app/dashboards/**` | BE | все | — |
| `apps/api/app/billing/**` | BE | все | — |
| `apps/api/app/jobs/**` | BE | все | DW (имена очередей/job-функций — через CR) |
| `apps/api/app/ai/**` | BE | все | — |
| `apps/api/app/admin/**` | BE | все | — |
| `apps/api/app/db/models/**` | BE + DW | все | парой BE+DW через CR |
| `apps/api/app/db/migrations/**` | DW | все | — |
| `apps/api/pyproject.toml` | BE | все | — |
| `apps/web/**` | FE | все | — |
| `apps/worker/**` | DW | все | — |
| `packages/shared/**` | BE + FE (парно) | все | парой BE+FE через CR |
| `packages/crm-connectors/**` | CRM | все | — |
| `packages/ai/**` | BE | все | — |
| `scripts/seed/**` | DW | все | — |
| `scripts/migrations/**` | DW | все | — |
| `tests/**` | QA | все | — |

## Протокол изменения чужой зоны

1. Агент пишет заявку в `docs/architecture/CHANGE_REQUESTS.md` по шаблону (см. файл).
2. Owner и Lead Architect одобряют (комментарии в CR).
3. Только после OK — меняется файл.

В срочных случаях Lead Architect может внести правку в любой файл, но с пометкой в `DECISIONS.md` или `CHANGE_REQUESTS.md`.

## Запрещённые пересечения

- BE НЕ трогает `apps/web/**` и `packages/crm-connectors/**`.
- FE НЕ трогает `apps/api/**`, `apps/worker/**`, `packages/crm-connectors/**`, `docs/db/**`, `docs/security/**`.
- DW НЕ трогает `apps/web/**`, `packages/crm-connectors/**` (кроме контракта через CR).
- CRM НЕ трогает `apps/api/**` и `apps/web/**` напрямую (только через `packages/crm-connectors/` + CR на контракт).
- QA не правит production-код (только `tests/`, `docs/qa/`).
