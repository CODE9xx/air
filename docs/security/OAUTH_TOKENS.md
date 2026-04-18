# OAuth Tokens — Code9 Analytics

## Правила

1. Токены CRM-провайдеров (`access_token`, `refresh_token`) шифруются **Fernet** при записи в БД.
2. Ключ — только в env (`FERNET_KEY`). Никогда не в коде, не в Dockerfile, не в git.
3. Ротация ключей — **V1** (нужно держать два ключа при миграции: decrypt-with-old → encrypt-with-new).

## Шифрование

```python
from cryptography.fernet import Fernet

fernet = Fernet(os.environ["FERNET_KEY"])
ct = fernet.encrypt(token.encode("utf-8"))   # bytes, складываем в BYTEA
# ...
token = fernet.decrypt(ct).decode("utf-8")
```

- Поля в `crm_connections`: `access_token_encrypted BYTEA`, `refresh_token_encrypted BYTEA`.
- Доступ к расшифровке — только из worker-job'ов (`refresh_token`, `fetch_crm_data`, `delete_connection_data`). API request cycle расшифровку **не** делает.

## Token refresh

- `refresh_token` выполняется **только** как RQ job в очереди `crm`.
- Триггеры: scheduled (за 15 мин до `token_expires_at`) + on-demand при 401 в коннекторе.
- Если refresh вернул 401 / `invalid_grant` / `invalid_token`:
  - `crm_connections.status = 'lost_token'`;
  - `last_error` заполняется;
  - создаётся `notifications.kind = 'connection_lost_token'`;
  - **никакие новые платные (AI, export) jobs не запускаются** (API проверяет статус до enqueue).
- Пользователь видит кнопку «Переподключить» → `POST /crm/connections/:id/reconnect` → новый OAuth-flow.

## API responses

- `GET /crm/connections/:id` и `GET /workspaces/:wsid/crm/connections` возвращают:
  - `external_account_id` (можно)
  - `external_domain` (можно)
  - `status` (можно)
  - `token_expires_at` (можно — для UI «токен протухнет через N дней»)
  - **НЕ возвращают** ни access, ни refresh, ни их длину, ни hash.
- Никаких debug-endpoint'ов, дающих токен наружу. Даже `support-mode` не раскрывает токен админу.

## Логирование

- Перед отправкой в `structlog`/print — прогон строк через маскировку:
  - любое значение, попадающее в context под ключами `access_token`, `refresh_token`, `authorization`, `code_verifier`, `client_secret` → `***`;
  - дополнительно — regex `Bearer\s+[A-Za-z0-9._-]+` → `Bearer ***`.
- Маскировщик живёт в `apps/api/app/core/logging.py` (Wave 2, Backend).

## Хранение в Redis

- В Redis можно класть **только** временные OAuth state (csrf state param), PKCE verifier — НО **не** сами токены.
- TTL: ≤10 минут.

## Удаление токенов

- При `crm_connections.status = 'lost_token'` — старые токены остаются зашифрованными в БД (могут понадобиться для диагностики; ротация через 30 дней).
- При `status = 'deleted'` — `access_token_encrypted = NULL`, `refresh_token_encrypted = NULL` в той же транзакции, что и `DROP SCHEMA`.

## Тест-режим (MOCK_CRM_MODE)

- В mock — токены фиктивные, но проходят через тот же Fernet-шифр (чтобы отладить путь целиком).
- `MockCRMConnector.refresh_token()` никогда не возвращает 401 — проверяется в unit-тесте QA.
