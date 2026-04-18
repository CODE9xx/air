# packages/crm-connectors

Адаптеры для CRM-провайдеров: **amoCRM**, **Kommo**, **Bitrix24** + **Mock**.
Единый интерфейс (`CRMConnector`) позволяет API / worker'у не знать, с каким
именно CRM-поставщиком работает система.

- **Owner:** CRM Integration Engineer.
- **Python:** >= 3.11.
- **Deps:** `httpx`, `pydantic`, `python-dateutil`.

## Установка

В monorepo подключается как path-dependency. Локально для разработки:

```bash
pip install -e packages/crm-connectors
```

## Быстрый старт

```python
from crm_connectors import get_connector, Provider

# В MVP MOCK_CRM_MODE=true → вернётся MockCRMConnector.
connector = get_connector(Provider.AMOCRM)

# Mock OAuth (вернёт http://localhost:3000/app/connections/mock-callback?...)
url = connector.oauth_authorize_url(state="csrf-xyz", redirect_uri="http://localhost:8000/api/v1/crm/oauth/amocrm/callback")

# exchange_code вернёт TokenPair с access/refresh и expires_at = now+30d.
tokens = connector.exchange_code(code="mock-code", redirect_uri="http://localhost:8000/...")

# Счётчики для pre-sync preview
summary = connector.audit(tokens.access_token)

# Выгрузка (limit поддержан — раздуваем фикстуры до нужного объёма).
deals = list(connector.fetch_deals(tokens.access_token, limit=100))
# len(deals) == 100
```

## Когда вернётся реальный коннектор

`factory.get_connector` читает флаг:

1. Если параметр `mock=True|False` передан явно — используется он.
2. Иначе — пробует `apps.api.app.core.settings.MOCK_CRM_MODE`.
3. Иначе — `MOCK_CRM_MODE` из `os.environ` (по умолчанию `true`).

Чтобы явно запросить реальный `AmoCrmConnector`:

```python
connector = get_connector(Provider.AMOCRM, mock=False)
# → AmoCrmConnector; однако большинство методов raise NotImplementedError
#   до V1 (см. docs/product/ROADMAP.md).
```

## Публичный API

```python
from crm_connectors import (
    # factory
    get_connector, is_mock_mode,
    # enums (синхронизированы с docs/db/SCHEMA.md)
    Provider, ConnectionStatus,
    # Protocol + impls
    CRMConnector, MockCRMConnector, AmoCrmConnector,
    KommoConnector, Bitrix24Connector,
    # dataclasses
    TokenPair,
    RawDeal, RawContact, RawCompany, RawPipeline, RawStage,
    RawUser, RawCall, RawMessage, RawTask, RawNote,
    # exceptions
    CRMConnectorError, TokenExpired, InvalidGrant,
    RateLimited, ProviderError,
)
```

## Контракт `CRMConnector`

```python
class CRMConnector(Protocol):
    provider: Provider

    # OAuth
    def oauth_authorize_url(self, state: str, redirect_uri: str) -> str: ...
    def exchange_code(self, code: str, redirect_uri: str) -> TokenPair: ...
    def refresh(self, refresh_token: str) -> TokenPair: ...

    # Метаданные аккаунта и pre-sync audit
    def fetch_account(self, access_token: str) -> dict: ...
    def audit(self, access_token: str) -> dict: ...

    # Fetchers
    def fetch_deals(self, access_token, since=None, limit=None) -> Iterable[RawDeal]: ...
    def fetch_contacts(self, access_token, since=None, limit=None) -> Iterable[RawContact]: ...
    def fetch_companies(self, access_token, since=None, limit=None) -> Iterable[RawCompany]: ...
    def fetch_pipelines(self, access_token) -> Iterable[RawPipeline]: ...
    def fetch_stages(self, access_token) -> Iterable[RawStage]: ...
    def fetch_users(self, access_token) -> Iterable[RawUser]: ...
    def fetch_calls(self, access_token, since=None, limit=None) -> Iterable[RawCall]: ...
    def fetch_messages(self, access_token, since=None, limit=None) -> Iterable[RawMessage]: ...
    def fetch_tasks(self, access_token, since=None, limit=None) -> Iterable[RawTask]: ...
    def fetch_notes(self, access_token, since=None, limit=None) -> Iterable[RawNote]: ...
```

Все `Raw*` — immutable `@dataclass(frozen=True)`, содержат минимально нужные
структурированные поля + `raw_payload: dict` с оригинальным ответом провайдера.
Нормализация в колонки (`tenant.deals`, `tenant.contacts`, ...) — ответственность
worker'а (`normalize_tenant_data`).

## Исключения

| Класс | Когда | Реакция worker'а |
|---|---|---|
| `TokenExpired` | 401 на API | Триггер job `refresh_token` |
| `InvalidGrant` | 400 invalid_grant | `crm_connections.status = 'lost_token'` + notification |
| `RateLimited` | 429 | Повтор через `retry_after_seconds` |
| `ProviderError` | 5xx / unexpected | Retry с экспоненциальной backoff |

## MockCRMConnector — как это устроено

Фикстуры — в `src/crm_connectors/fixtures/`:

| Файл | Размер |
|---|---|
| `amo_audit_summary.json` | 1 объект (deals_total=12450, ...) |
| `amo_pipelines.json` | 4 воронки × 5-7 этапов |
| `amo_users.json` | 12 пользователей (11 активных) |
| `amo_companies.json` | 5 компаний |
| `amo_contacts.json` | 22 контакта |
| `amo_deals.json` | 22 сделки (открытые / выигранные / проигранные) |
| `amo_calls.json` | 12 звонков |
| `amo_messages.json` | 31 сообщение (whatsapp/telegram/site/email) |
| `amo_tasks.json` | 12 задач |
| `amo_notes.json` | 10 заметок |

Если `fetch_*(limit=N)` просит больше, чем есть в фикстуре — Mock «раздувает»
выборку повторами, суффиксуя `crm_id` (`10001-r1`, `10001-r2`, ...), чтобы
соблюсти `UNIQUE(external_id)` в tenant-схеме.

`since` фильтрация — по соответствующему полю (`created_at`/`sent_at`).

## Как добавить нового провайдера

1. Создать `src/crm_connectors/<provider>.py` — класс-коннектор, реализующий
   `CRMConnector`. Для заглушек — использовать паттерн из `kommo.py`.
2. Добавить значение в `enums.Provider` (+ обновить CHECK в `docs/db/SCHEMA.md`
   через CR к LEAD+DW).
3. Расширить `factory.get_connector` веткой `if provider == Provider.<NEW>`.
4. Добавить фикстуры `<new>_*.json` (опционально: Mock может использовать
   общие amo-фикстуры как есть, если структура совместима).

## Границы ответственности

- **Этот пакет** — только контракт коннектора + реализации.
- **Шифрование токенов** (Fernet) — `apps/worker/worker/lib/crypto.py` (DW).
- **Роуты OAuth / state / 302** — `apps/api/app/crm/` (BE).
- **Enqueue job'ов** (`fetch_crm_data`, `refresh_token`) — API+worker (BE+DW).
- Изменения контракта — через `docs/architecture/CHANGE_REQUESTS.md`.
