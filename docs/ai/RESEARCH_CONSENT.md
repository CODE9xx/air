# AI Research Consent — Code9 Analytics

## Что это

Workspace-уровневое согласие на использование **анонимизированных** паттернов из их данных в общем индустриальном датасете для улучшения бенчмарков и моделей Code9.

## Состояния

`ai_research_consent.status`:

| Значение | Когда |
|---|---|
| `not_asked` | дефолт после создания workspace |
| `accepted` | owner явно согласился |
| `revoked` | owner ранее согласился, потом отозвал |

## API

См. `api/CONTRACT.md` § 10:
- `GET /workspaces/:wsid/ai/consent` — текущий статус.
- `POST /workspaces/:wsid/ai/consent` — `{action: accept|revoke, terms_version}` (только owner).

## Эффекты

| status | Можно использовать в `ai_research_patterns` | Можно делать персональный AI-анализ |
|---|---|---|
| `not_asked` | НЕТ | ДА |
| `accepted` | ДА (после анонимизации, sample_size>=10) | ДА |
| `revoked` | НЕТ. Уже сохранённые ai_research_patterns не удаляются (они полностью анонимны и не привязаны к workspace), но **новых** записей не делаем. | ДА |

## UI flow (Frontend Wave 2)

1. После первого успешного AI-анализа в workspace — модалка:
   > «Помогите улучшать Code9. Мы используем только анонимные паттерны (нет имён, телефонов, конкретных сделок). Вы можете отозвать согласие в любой момент.»
2. Кнопки: `Согласен` / `Не сейчас`.
3. Решение сохраняется в `ai_research_consent`.
4. В Settings → Privacy всегда виден текущий статус и кнопка `Отозвать` / `Дать согласие`.

## terms_version

- Хранится строка вида `v1`, `v2`. При изменении условий исследования — bump версии.
- При accept — записываем `terms_version`, `accepted_at`, `accepted_by_user_id`.
- При новом `terms_version` — UI просит подтвердить заново.

## Юридическая привязка

- Тексты согласий (RU + EN) — `apps/web/messages/ru.json` / `en.json`, ключ `consent.research.terms`.
- Версия должна быть архивирована (хранение текста терминов на момент согласия — V1, в MVP только version-key).

## Audit

- Любое изменение `ai_research_consent` пишет row в `notifications` workspace'а:
  `kind` ∉ enum, поэтому в MVP — отдельная in-app запись (не email). В V1 — email-подтверждение.
- Plus: всё под общими user-action логами (если будем вводить).
