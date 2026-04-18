# Demo RunBook — Code9 Analytics MVP

**Версия:** Wave 4 (2026-04-18)  
**Аудитория:** команда на демо-сессии, sales-инженер, технический основатель  
**Окружение:** Docker Desktop / OrbStack, macOS / Linux

---

## Предусловия

- Docker Desktop или OrbStack установлен и запущен
- Порты 3000, 8000, 5432, 6379 свободны
- Git-репозиторий склонирован в локальную папку

---

## Шаг 1: Подготовка окружения

```bash
cd /Users/maci/Desktop/CODE9_ANALYTICS
cp .env.example .env
```

Файл `.env` содержит dev-секреты. **Не менять** для демо — всё настроено.

Проверка: `.env` должен существовать в корне.

---

## Шаг 2: Запуск стека

```bash
make up
```

**Ожидаемое поведение:**
- Docker скачивает образы (только первый раз, ~2-5 мин)
- Поднимаются 5 контейнеров: `code9-postgres`, `code9-redis`, `code9-api`, `code9-worker`, `code9-web`

**Проверка:**
```bash
make ps
# Ожидаем: все 5 сервисов в состоянии Up / healthy
docker compose logs api | tail -5
# Ожидаем: "Uvicorn running on http://0.0.0.0:8000"
```

**При ошибке:**
- `port already in use` → `lsof -i :8000` (или :3000, :5432) и остановить конфликтующий процесс
- `no such file or directory` → убедиться, что вы в корне репозитория

---

## Шаг 3: Применить миграции БД

```bash
make migrate
```

**Ожидаемое поведение:** Alembic применяет все main-schema миграции. Создаются таблицы `users`, `workspaces`, `crm_connections` и т.д.

**Проверка:**
```bash
make psql
# В psql:
\dt
# Ожидаем: список таблиц: users, workspaces, crm_connections, jobs, ...
\q
```

**При ошибке:**
- `relation already exists` → миграция уже была применена, ОК
- `connection refused` → postgres не готов, подождать 10 сек и повторить

---

## Шаг 4: Сидировать демо-данные

```bash
make seed
```

**Ожидаемое поведение:** Создаётся admin-пользователь (`admin@code9.local` / `admin-demo-password`) и демо-воркспейс.

**Проверка:**
```bash
docker compose logs api | grep -i "seed\|admin\|bootstrap"
# Ожидаем: "Admin created" или аналогичное
```

**При ошибке:**
- `duplicate key` → seed уже выполнялся, ОК — данные уже есть

---

## Шаг 5: Открыть UI

Открыть в браузере: **http://localhost:3000**

**Ожидаемое поведение:** Страница приветствия Code9 Analytics на русском языке.

**Проверка:** В правом верхнем углу — переключатель RU/EN.

---

## Шаг 6: Регистрация пользователя

1. Перейти на http://localhost:3000/register
2. Ввести email (например `demo@example.com`) и пароль (мин. 8 символов)
3. Нажать "Зарегистрироваться"

**Ожидаемое поведение:** Редирект на страницу подтверждения email.

**Проверка:** В логах api появится строка с кодом:
```bash
docker compose logs api | grep "EMAIL\|email_sent" | tail -3
# Ожидаем: EMAIL -> demo@example.com | Code: XXXXXX
```

---

## Шаг 7: Подтверждение email

1. Скопировать 6-значный код из логов (шаг 6)
2. Ввести код на странице верификации
3. Нажать "Подтвердить"

**Ожидаемое поведение:** Email подтверждён, редирект на страницу входа.

**При ошибке:**
- `code expired` → код TTL 15 мин. Запросить повторно кнопкой "Отправить снова"
- `too many attempts` → более 5 неверных попыток, запросить новый код

---

## Шаг 8: Вход в систему

1. Перейти на http://localhost:3000/login
2. Ввести email и пароль
3. Нажать "Войти"

**Ожидаемое поведение:** Успешный вход, редирект на dashboard. Cookie `code9_refresh` установлен (проверить в DevTools → Application → Cookies).

---

## Шаг 9: Подключение mock amoCRM

1. В сайдбаре выбрать "CRM Подключения"
2. Нажать "Подключить amoCRM"
3. В mock-режиме — кнопка создаёт подключение мгновенно

**Ожидаемое поведение:**
- `status: active` в UI за < 5 секунд
- Worker запускает job `bootstrap_tenant_schema`

**Проверка:**
```bash
docker compose logs worker | grep "bootstrap_tenant_schema" | tail -3
# Ожидаем: [job bootstrap_tenant_schema] completed
```

---

## Шаг 10: Запуск аудита и просмотр дашборда

1. В разделе CRM → нажать "Синхронизировать данные" → дождаться job `fetch_crm_data`
2. Нажать "Запустить аудит" → дождаться job `run_audit_report`
3. Открыть Dashboard → посмотреть агрегаты: воронка, активность менеджеров

**Проверка:**
```bash
docker compose logs worker | grep "run_audit_report\|fetch_crm_data" | tail -5
# Ожидаем: статус completed для обоих jobs
```

**Ожидаемое в UI:** Дашборд показывает данные из mock-фикстур (100 сделок, менеджеры, воронка).

---

## Шаг 11 (опционально): Admin Panel

1. Открыть http://localhost:8000/docs → Authorize с токеном admin
2. Или использовать: `POST /api/v1/admin/auth/login` с `{"email": "admin@code9.local", "password": "admin-demo-password"}`
3. `GET /api/v1/admin/workspaces` → список всех воркспейсов

**Примечание:** Tenant-эндпоинты support mode (`/admin/support-mode/session/:id/tenant/*`) отложены до V1 (AC-11 DEFERRED).

---

## Troubleshooting

| Симптом | Причина | Решение |
|---------|---------|---------|
| `make up` зависает | Docker тянет образы | Подождать 5 мин, проверить интернет |
| API не отвечает (http://localhost:8000) | api-контейнер не поднялся | `docker compose logs api` |
| Нет кода в логах | EMAIL_BACKEND=console не настроен | Проверить `.env`: `DEV_EMAIL_MODE=log` |
| Worker не обрабатывает jobs | Worker упал | `docker compose restart worker` |
| `migrate` падает с ошибкой | Postgres не готов | Подождать 10 сек, `make migrate` снова |
| Белый экран в браузере | web-контейнер не собрался | `docker compose logs web \| tail -20` |
| Ошибка 500 на login | settings misconfigured | `docker compose logs api \| grep ERROR` |

---

## Полный сброс (если что-то пошло не так)

```bash
make clean
make fresh
# Затем с шага 3
```

**ВНИМАНИЕ:** `make clean` удаляет все volumes, включая данные postgres. Все данные будут потеряны.

---

## Команда для быстрого старта (всё за одну команду)

```bash
cp .env.example .env && make demo
```

После завершения открыть http://localhost:3000 — переходите к шагу 6 (Регистрация).
