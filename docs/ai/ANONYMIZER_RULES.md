# AI Anonymizer Rules — Code9 Analytics

Применяется перед сохранением паттернов в `ai_research_patterns` и (опционально) перед сохранением `ai_conversation_scores.raw_llm_output`, если `privacy_risk` высокий.

## 1. Блэклист (запрещено сохранять)

| Категория | Примеры | Что делаем |
|---|---|---|
| Имена | «Иван Иванов», «John Smith» | заменяем на `[NAME]` |
| Телефоны | `+7 999 ...`, `+1 (415) ...` | `[PHONE]` |
| Email | `a@b.com` | `[EMAIL]` |
| Названия компаний | «ООО Ромашка», «Acme Inc» | `[COMPANY]` |
| Внутренние ID сделок CRM | `deal_id`, `contact_id`, `external_id` | удаляем поле |
| URL'ы | `https://...` | `[URL]` |
| Сырые транскрипты | целые фразы из `calls.transcript_ref` или `messages.text` | **запрещено сохранять** |
| Сырые сообщения | `messages.text` | **запрещено** |
| Точные суммы | `123 456,78 RUB` | bucket: `<10k`, `10k-50k`, `50k-200k`, `200k-1M`, `1M+` |
| ИНН/паспорт/банк | любые номера документов | удаляем |

Реализация:
- regex-сет (телефоны, email, URL, валюта).
- NER (V1; в MVP — список словарных имён + capitalize-эвристика).
- Whitelist-fields подход: для `ai_research_patterns` мы заранее знаем, какие колонки разрешены — всё остальное **не пишется**.

## 2. Вайтлист (разрешено сохранять)

| Категория | Примеры |
|---|---|
| Отрасль (`industry`) | `b2b_saas`, `retail`, `realestate` |
| Тип возражения (`objection_type`) | `price`, `trust`, `timing`, `competitor`, `not_decision_maker` |
| Тип ответа (`response_type`) | `acknowledged`, `reframed`, `ignored`, `closed` |
| Канал (`channel`) | `call`, `chat`, `email` |
| Этап воронки (`stage_kind`) | `open`, `won`, `lost` |
| Bucket длительности | `0-30s`, `30-120s`, `2-5m`, `5-15m`, `15m+` |
| Bucket периода | `week`, `month`, `quarter` |
| Confidence модели | `0.00..1.00` |
| Sample size | int, **>= 10** |

## 3. Минимальный sample_size

- **10** записей минимум для сохранения паттерна в `ai_research_patterns`.
- Меньше — не сохраняем (риск re-identification).

## 4. Privacy risk

Анонимайзер возвращает оценку `privacy_risk ∈ {low, medium, high}`.

| Уровень | Решение |
|---|---|
| `low` | сохраняем спокойно |
| `medium` | сохраняем, но `raw_llm_output = NULL` в `ai_conversation_scores` |
| `high` | `should_store = false` — паттерн не пишем в `ai_research_patterns` вообще |

Триггеры high:
- меньше 3 уникальных аккаунтов в bucket (легко вычислить, кто это);
- остались токены, похожие на PII (regex поймал что-то нестандартное);
- редкий `industry` (например, `nuclear_energy_ru`) с малым sample.

## 5. Реализация (Wave 2, `packages/ai/anonymizer.py`)

```python
def anonymize(text: str) -> tuple[str, PrivacyRisk]: ...

def build_research_pattern(scores: list[ConversationScore], industry: str) -> ResearchPattern | None:
    """
    Возвращает None, если sample_size < 10 или privacy_risk == high.
    """
```

## 6. Тесты (QA Wave 2)

- Каждое regex-правило — таблично-параметризованный тест: вход → ожидаемый выход.
- Snapshot: «золотая» история для `anonymize` на корпусе из ~50 фрагментов.
- Property-based: что бы ни вернула LLM, после анонимизации не должно быть строк, матчащих PII-regex.

## 7. Что мы НЕ делаем

- Не пытаемся «расшифровать» обратно — anonymize однонаправлен.
- Не храним mapping «маска → оригинал» (нет ключа к re-identification).
- Не отправляем PII в LLM **без** анонимизации (анонимизация — ДО LLM-вызова, не после).
