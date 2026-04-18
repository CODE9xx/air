# Backup & Restore — Code9 Analytics

## Обязательное правило

**Непроверенный backup считается отсутствующим.** Перед первым реальным клиентом — обязательный restore drill на staging-окружении.

## 1. Что бэкапим

| Данные                                  | Где                                       | Частота        | Критичность |
|-----------------------------------------|-------------------------------------------|----------------|-------------|
| PostgreSQL (main + все tenant schemas)  | Docker volume `postgres-prod-data`        | ежедневно 03:00 UTC | CRITICAL    |
| `.env.production`                        | `/opt/code9-analytics/.env.production`    | вручную в password manager | CRITICAL    |
| Caddy certificates                       | Docker volume `caddy-data`                | еженедельно    | MEDIUM      |
| Redis                                    | Volume `redis-prod-data` (appendonly yes) | не бэкапим     | LOW         |

Redis — **не бэкапим**: он хранит только эфемерные job-queues, rate-limit counters и опциональные кеши. Потеря допустима. При инциденте воркер просто переиграет неудачные jobs.

`.env.production` — никогда не пушим в git и не храним в бэкапах на сервере. Положи его в password manager (1Password / Bitwarden / Vault) сразу после генерации.

## 2. Backup: pg_dump

### Первичная подготовка (один раз на сервере)

```bash
sudo mkdir -p /var/backups/code9
sudo chown code9:code9 /var/backups/code9
sudo chmod 700 /var/backups/code9
```

Без этих прав `pg_dump.sh` упадёт при первом прогоне (либо не сможет писать, либо файл окажется доступен не тому пользователю).

### Ручной прогон
```bash
make prod-backup
# или
PROJECT_DIR=/opt/code9-analytics bash deploy/backup/pg_dump.sh
```

Результат:
- `/var/backups/code9/code9_YYYYMMDD_HHMMSSZ.sql.gz`
- формат: plain SQL + gzip -9, `--clean --if-exists`
- retention: 14 дней rolling (конфигурируется через `RETAIN_DAYS`)

### Cron (автоматический)

```bash
crontab -e
```

```cron
0 3 * * * PROJECT_DIR=/opt/code9-analytics bash /opt/code9-analytics/deploy/backup/pg_dump.sh >> /var/log/code9-backup.log 2>&1
```

Следи за логом: `tail -f /var/log/code9-backup.log`.

### logrotate (опционально, Sprint 2)

`/etc/logrotate.d/code9-backup`:
```
/var/log/code9-backup.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
}
```

## 3. Offsite storage (Gate B)

До Gate B backup лежит только на том же сервере — это **не надёжно**. Перед пилотом настрой отправку на внешнее хранилище.

### Вариант 1: rclone → S3-совместимое хранилище

```bash
sudo apt install rclone
rclone config   # настроить remote 'offsite' → Backblaze B2 / AWS S3 / Yandex Object Storage
```

Добавить в конец `pg_dump.sh` (TODO-блок уже есть):
```bash
rclone copy "$OUT_FILE" offsite:code9-backups/ || echo "[backup] WARN offsite upload failed"
```

Настрой lifecycle rule на bucket: удалять объекты старше 90 дней.

### Вариант 2: второй VPS

```bash
# на бэкап-сервере:
sudo adduser --disabled-password backup-receiver
# скопировать ssh-ключ с prod-сервера

# на prod-сервере (в pg_dump.sh):
rsync -avz "$OUT_FILE" backup-receiver@backup.example.com:/backups/code9/
```

### Шифрование (рекомендуется для обоих вариантов)

```bash
# перед upload
gpg --batch --yes --symmetric --cipher-algo AES256 \
    --passphrase-file ~/.gpg-backup-passphrase \
    "$OUT_FILE"
# uploads "$OUT_FILE.gpg"
```

## 4. Restore

**ОСТОРОЖНО**: restore.sh делает `--clean --if-exists` → DROPает таблицы в целевой БД.

### Scope restore.sh (Gate A / Sprint 0)

Скрипт восстанавливает **только основной дамп БД** (`code9_<stamp>.sql.gz`). Globals-дамп (`code9_globals_<stamp>.sql.gz`) он **не применяет**. Для двух out-of-the-box сценариев этого достаточно:

- **Restore drill на том же кластере** — роль `POSTGRES_USER` уже существует, main-dump без `--create/--globals`, просто перезаливает схему.
- **In-place recovery на работающем prod-сервере** — то же самое: кластер уже проинициализирован через `.env.production`, globals уже есть.

**Не-scope** (требует ручных шагов — см. §8 "Disaster recovery"): полный перенос на **чистую новую VPS**. Там сначала надо восстановить globals (роли/tablespaces), а только потом main dump. Это TODO Sprint 2 — добавить флаг `--with-globals=<path>` в restore.sh.

### Процедура восстановления (реальный инцидент)

```bash
ssh code9@server
cd /opt/code9-analytics

# 1. Снять свежий backup на всякий случай
make prod-backup

# 2. Выбрать бэкап для восстановления
ls -lah /var/backups/code9/
export RESTORE_FROM=/var/backups/code9/code9_20260415_030000Z.sql.gz

# 3. Запустить restore (скрипт попросит YES RESTORE)
make prod-restore BACKUP=$RESTORE_FROM

# 4. Проверить, что приложение работает
make prod-smoke
make prod-logs  # убедиться что worker поднялся
```

Скрипт автоматически останавливает worker/scheduler на время restore, потом стартует обратно.

### Procedure: Restore drill (обязательно до Gate B)

Цель drill — убедиться, что бэкап реально разворачивается и приложение остаётся рабочим. Делай минимум раз в 2 недели.

```bash
# на staging-сервере (отдельная VPS или тот же, но другой compose project):

# 1. Скопировать свежий backup с prod
scp code9@prod:/var/backups/code9/code9_YYYYMMDD_HHMMSSZ.sql.gz /tmp/

# 2. Поднять чистый compose
cd /opt/code9-staging
make prod-up
sleep 30

# 3. Прогнать миграции (создаёт схему, в которую будем заливать дамп)
# Восстановление из --clean --if-exists dump сам сбросит таблицы
make prod-migrate

# 4. Сам restore
make prod-restore BACKUP=/tmp/code9_YYYYMMDD_HHMMSSZ.sql.gz

# 5. Smoke
make prod-smoke

# 6. Ручные проверки:
#    - войти как admin
#    - увидеть demo-workspace
#    - запустить audit-job → увидеть результаты
#    - отметить в логах отсутствие raw-токенов

# 7. Записать результат в docs/deploy/BACKUP_RESTORE.md (секция "Drill log")
```

### RPO / RTO

| Метрика | Цель MVP (Gate A) | Цель Pilot (Gate B) | Цель Production (Gate C) |
|---------|-------------------|---------------------|--------------------------|
| RPO (recovery point, сколько данных потеряем)  | 24 часа | 24 часа | 15 минут (WAL streaming) |
| RTO (recovery time, за сколько поднимем)       | 4 часа  | 2 часа  | 30 минут |
| Restore drill cadence                            | quarterly | bi-weekly | monthly + после каждой крупной миграции |

## 5. Миграции и rollback

Alembic миграции **не имеют автоматического rollback** в prod — это принципиально. Политика:

1. Миграция тестируется на staging перед prod.
2. Перед прогоном — свежий backup.
3. Если миграция упала — сначала попытка `alembic downgrade -1`, если невозможно → restore из backup.
4. Destructive миграции (DROP COLUMN, DROP TABLE) — только в отдельном PR с ревью архитектора.
5. Добавление `NOT NULL` к существующей колонке — через two-phase: сначала добавить nullable + backfill, потом NOT NULL.

## 6. Drill log

Заполняется после каждого drill.

| Дата       | Версия backup | RTO (мин) | Кто тестировал | Проблемы / fix |
|------------|---------------|-----------|----------------|----------------|
| 2026-XX-XX | code9_YYYYMMDD | —          | —              | первый drill до pilot |

## 7. Secrets rotation (Sprint 2+)

### FERNET_KEY rotation (если key скомпрометирован)

1. Сгенерировать новый ключ `FERNET_KEY_NEW`.
2. Добавить в `.env.production` как `FERNET_KEY_NEW`.
3. Выкатить миграционный job (будет разработан в Sprint 2), который:
   - читает все `access_token_enc`/`refresh_token_enc` из `crm_connections`,
   - расшифровывает старым ключом,
   - шифрует новым и обновляет в той же транзакции.
4. После прохода перевести `FERNET_KEY=$FERNET_KEY_NEW` и удалить `FERNET_KEY_NEW`.
5. Рестарт api + worker.

### JWT_SECRET rotation

Сброс всех активных сессий.
1. Сгенерировать новый `JWT_SECRET`.
2. Рестарт api: все access/refresh становятся невалидными, пользователи форсно логинятся заново.
3. Соответственно — делать в низкий-трафик окно и оповестить пользователей.

### ADMIN_JWT_SECRET rotation

Аналогично JWT_SECRET, но только админы получат 401 и должны перелогиниться.

### POSTGRES_PASSWORD rotation

Делать через:
1. Создать нового пользователя с новым паролем, дать права.
2. Обновить `DATABASE_URL` в `.env.production` на нового.
3. Рестарт api/worker/scheduler.
4. После успешного старта — удалить старого пользователя.

## 8. Disaster recovery (полный crash сервера)

**Важно про globals**: на чистой новой VPS кластер Postgres инициализируется из `.env.production` (POSTGRES_USER/PASSWORD/DB через `docker-entrypoint-initdb.d`) → у тебя будет правильная роль и БД, но **остальные объекты уровня кластера** (дополнительные роли, tablespaces, настройки `ALTER SYSTEM`, привилегии между ролями) придут только из `code9_globals_<stamp>.sql.gz`. Применять globals нужно **до** main dump, иначе restore main'а может упасть на GRANT к несуществующей роли или сослаться на отсутствующий tablespace.

**restore.sh в текущей версии (Gate A / Sprint 0) globals не применяет** — см. §4 "Scope". Для full DR на чистой VPS используй ручную последовательность ниже. TODO Sprint 2 — добавить `make prod-restore-full BACKUP=<main> GLOBALS=<globals>`.

```bash
# 1. Новый VPS по SERVER_SETUP.md шаги 1-5 (OS, docker, ufw, code9-user, clone, /var/backups/code9).
# 2. Восстановить .env.production из password manager → chmod 600.
# 3. Скачать ПАРНЫЕ свежие backup'ы:
rclone copy offsite:code9-backups/code9_<stamp>.sql.gz          /var/backups/code9/
rclone copy offsite:code9-backups/code9_globals_<stamp>.sql.gz  /var/backups/code9/

# 4. Поднять только postgres (без api/worker/scheduler), чтобы накатить globals в спокойствии:
cd /opt/code9-analytics
make prod-build
docker compose -f deploy/docker-compose.prod.yml --env-file .env.production up -d postgres
sleep 15

# 5. Применить globals — ТОЛЬКО ЭТИМ ШАГОМ, через psql -U postgres, database=postgres.
#    Пароль для суперюзера — тот же POSTGRES_PASSWORD из .env.production (alpine-image default).
gunzip -c /var/backups/code9/code9_globals_<stamp>.sql.gz \
  | docker compose -f deploy/docker-compose.prod.yml exec -T postgres \
      psql --username="$POSTGRES_USER" --dbname=postgres --set ON_ERROR_STOP=on

# 6. Поднять остальной стек:
make prod-up
sleep 30
make prod-ps                                # 7 контейнеров Up / 5 healthy

# 7. Восстановить main dump поверх инициализированной БД:
make prod-restore BACKUP=/var/backups/code9/code9_<stamp>.sql.gz

# 8. Обновить DNS A-записи на новый IP (app./api.).
# 9. make prod-smoke + функциональная проверка.
# 10. Записать инцидент в docs/deploy/GATE_SIGNOFFS.md (rollback log) с причиной и SHA.
```

Цель — уложиться в RTO для текущего gate (Gate A: 4 часа, Gate B: 2 часа, Gate C: 30 минут).
