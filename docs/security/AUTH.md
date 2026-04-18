# Authentication — Code9 Analytics

## Summary

- Пароли: **argon2id** (par=2, mem=64MB, iter=3) через `argon2-cffi`.
- Access JWT: HS256, **TTL 15 min**, подпись `JWT_SECRET`.
- Refresh: **opaque random token**, **30 дней**, хранится как argon2-hash в `user_sessions`.
- Email-код: 6-значный numeric, TTL 15 min, ≤5 попыток, argon2-hash в БД.
- Rate limiting: FastAPI dependency + Redis (sliding window).
- Admin — отдельный JWT (`ADMIN_JWT_SECRET`), отдельная таблица `admin_users`, scope=`admin`.

## 1. Хранение паролей

```
argon2id(password, parallelism=2, memory_cost=64*1024 KiB, iterations=3)
```
- Хэш в `users.password_hash`.
- Миграция алгоритма (если в будущем сменим параметры) — автоматический rehash при следующем успешном login.

## 2. JWT (access)

- Алгоритм: HS256.
- Секрет: `JWT_SECRET` (user-scope), `ADMIN_JWT_SECRET` (admin-scope).
- TTL: 15 минут.
- Claims:
  ```json
  {
    "sub": "<user_id>",
    "scope": "user",
    "iat": 1713400000,
    "exp": 1713400900,
    "jti": "<uuid>"
  }
  ```
- НЕ храним в JWT email/имя — только id + scope.
- Frontend держит access в памяти, refresh — в httpOnly cookie.

## 3. Refresh-токены

- Генерация: `secrets.token_urlsafe(48)` → 64+ символа.
- В БД: `user_sessions.refresh_token_hash` = argon2id от токена.
- TTL: 30 дней (колонка `expires_at`).
- Cookie: `code9_refresh`, `HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`.
- На `/auth/refresh`: читаем cookie → находим session по argon2 verify (по user_id из JWT?... нет; см. ниже) → выдаём новый access и новый refresh (rolling).
  - **Реализация:** cookie содержит `<session_id>.<opaque>`. По `session_id` находим row, затем `argon2.verify(row.refresh_token_hash, opaque)`.
- `revoked_at != NULL` или `expires_at < now()` → unauthorized.

### Таблица `user_sessions`

См. `db/SCHEMA.md` § 1.2. Поля: `id, user_id, refresh_token_hash, user_agent, ip, expires_at, revoked_at, created_at`. **Добавляется в alembic миграции Backend/DW Engineer в Wave 2.**

## 4. Email-коды

- Формат: 6 цифр (000000-999999), генерация `secrets.choice(range(0,10))` для каждой цифры.
- Хэш: argon2id → `email_verification_codes.code_hash`.
- TTL: 15 минут для verify/reset, 10 минут для `connection_delete` (deletion flow использует `deletion_requests`, см. отдельный doc).
- Попытки: `attempts <= 5`, при превышении — row переходит в состояние «потреблён неудачно», надо просить новый.
- Purpose enum: `email_verify`, `password_reset`, `connection_delete`.

## 5. Rate limits

Реализуется через FastAPI dependency + Redis (sliding window, `INCR + PEXPIRE` или атомарный lua-скрипт).

| Endpoint | Лимит | Ключ |
|---|---|---|
| `POST /auth/login` | 5/min | IP |
| `POST /auth/login` | 10/min | нормализованный email |
| `POST /auth/register` | 3/min | IP |
| `POST /auth/password-reset/request` | 3/10min | email |
| `POST /auth/verify-email/confirm` | 10/hour | user_id |
| `POST /auth/verify-email/request` | 3/10min | user_id |
| `POST /admin/auth/login` | 5/min | IP |

При превышении — 429 `rate_limited` с заголовком `Retry-After`.

## 6. 2FA

- Поля `two_factor_enabled`, `two_factor_secret_encrypted` есть в `users`.
- Логика 2FA реализуется в **V1** (не MVP).
- Секрет будет зашифрован Fernet (тем же `FERNET_KEY`, что и OAuth-токены).

## 7. Session invalidation

| Событие | Действие |
|---|---|
| `POST /auth/logout` | помечаем текущий `user_sessions.revoked_at = NOW()` |
| Смена пароля | `UPDATE user_sessions SET revoked_at=NOW() WHERE user_id=? AND revoked_at IS NULL` |
| Подозрительная активность (admin action) | тот же массовый revoke |

Access JWT НЕ умеет быть «revoked» явно (stateless). Но TTL — 15 минут, после чего клиент обязан обновиться, и на refresh — проверка session status.

## 8. CSRF / CORS

- API — только JSON (нет form posts), `Content-Type: application/json`. Это уже снижает CSRF-риск.
- Refresh cookie — `SameSite=Lax`, `HttpOnly`, `Secure`.
- `/auth/refresh` ожидает cookie + опционально CSRF-header `X-Code9-CSRF` (в V1, опционально).
- CORS: `allow_origins` — только из env `ALLOWED_ORIGINS`.
- `allow_credentials=true` (нужно для cookie).

## 9. Логи

- Никогда не логируем: password, password_hash, access_token, refresh_token, email-код.
- Логируем user_id, client_ip, user_agent, endpoint, rate-limit bucket.
- При 401/403 — логируем причину (`invalid_password`, `email_not_verified`, `session_revoked`), но не сам введённый пароль.

## 10. Admin auth

- Таблица `admin_users`, отдельно от `users`.
- JWT secret `ADMIN_JWT_SECRET`, scope=`admin`.
- Endpoint: `/admin/auth/login`. Rate-limit: 5/min per IP.
- Admin session (refresh): аналогично user, но cookie `code9_admin_refresh`, отдельная таблица `admin_sessions` **(добавить в DW миграции Wave 2)**.
- Все admin-действия идут через middleware, проверяющий `scope=admin` + пишущий `admin_audit_logs` в той же транзакции.
