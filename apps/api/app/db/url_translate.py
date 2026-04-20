"""
DSN helpers: конвертация SQLAlchemy asyncpg-URL → sync (psycopg2) URL.

Используется везде, где нужен sync-контекст Postgres-подключения:

* ``apps/api/app/db/migrations/main/env.py``    — alembic (main schema);
* ``apps/api/app/db/migrations/tenant/env.py``  — alembic (tenant template);
* ``scripts/migrations/apply_tenant_template.py`` — DDL+alembic при
  bootstrap'е tenant-схемы;
* ``apps/worker/worker/lib/url_translate.py``   — MIRROR этого модуля
  (worker-образ не копирует ``apps/api`` в build-context, так что общий
  импорт невозможен; оба файла обязаны меняться в одном коммите).

Зачем транслировать query-параметры
-----------------------------------
``asyncpg`` использует libpq-совместимый **однобуквенный** алиас::

    postgresql+asyncpg://user:pass@host/db?ssl=require

``psycopg2`` (тот же libpq внизу) ждёт **полное имя**::

    postgresql+psycopg2://user:pass@host/db?sslmode=require

При замене только драйвера psycopg2 получит ``ssl=...`` и упадёт
``psycopg2.ProgrammingError: invalid dsn: invalid connection option "ssl"``.
Поэтому при смене схемы мы также транслируем параметр.

Маппинг ssl → sslmode
---------------------
``true`` / ``require`` / ``1``               → ``require``
``false`` / ``disable`` / ``0`` / пустая     → ``disable``
``prefer`` / ``allow`` / ``verify-ca`` /
    ``verify-full``                          → то же имя
любое другое                                 → ``require`` (безопасный
    дефолт для managed-Postgres с TLS-only политикой, напр. Timeweb)

Tie-break: ``sslmode`` выигрывает у ``ssl``
-------------------------------------------
Если в URL присутствуют **оба** параметра (``?ssl=...&sslmode=...``),
то трансляция пропускает входящий ``sslmode`` как есть и удаляет
``ssl``. Явное значение перевешивает вывод из короткой формы.

Безопасность
------------
Функция НЕ логирует DSN, пароль или другие поля URL. Вся трансляция —
чистая манипуляция со строкой. Исключения поднимаются без содержимого
исходного URL (см. callers — они тоже не должны печатать DSN).
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = ["asyncpg_to_psycopg2"]


# Значения, интерпретируемые как truthy для `ssl`.
_SSL_TRUTHY = frozenset({"true", "require", "1"})
# Значения, интерпретируемые как «TLS отключён».
_SSL_FALSY = frozenset({"false", "disable", "0", ""})
# Значения, которые libpq понимает как есть и мы пропускаем без изменений
# (только переименовываем ключ ssl → sslmode).
_SSL_LIBPQ_PASSTHROUGH = frozenset({"prefer", "allow", "verify-ca", "verify-full"})


def asyncpg_to_psycopg2(url: str) -> str:
    """
    Конвертирует asyncpg-URL в psycopg2-URL.

    Схема/драйвер::

        postgresql+asyncpg://…   → postgresql+psycopg2://…
        postgres+asyncpg://…     → postgresql+psycopg2://…

    Если URL уже psycopg2 / без драйвера — схема не трогается.

    Query-параметры::

        ssl=…   → sslmode=… (см. маппинг в модульном docstring)

    Другие параметры (``application_name``, ``connect_timeout``,
    ``options``, ``target_session_attrs`` и т.д.) передаются без изменений.

    :param url: исходный URL из ``DATABASE_URL``
    :return: URL, безопасный для ``sqlalchemy.create_engine(...)``
             с psycopg2-драйвером
    """
    # 1. Схема/драйвер.
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql+psycopg2://" + url[len("postgresql+asyncpg://"):]
    elif url.startswith("postgres+asyncpg://"):
        url = "postgresql+psycopg2://" + url[len("postgres+asyncpg://"):]

    # 2. Query-params.
    parts = urlsplit(url)
    if not parts.query:
        return url

    qs = parse_qsl(parts.query, keep_blank_values=True)

    # Определяем, есть ли уже `sslmode` явно: он — победитель при
    # одновременном присутствии `ssl` (tie-break, задокументирован выше).
    explicit_sslmode_present = any(k == "sslmode" for k, _ in qs)

    translated: list[tuple[str, str]] = []
    for key, value in qs:
        if key == "ssl":
            if explicit_sslmode_present:
                # Есть явный sslmode → игнорируем ssl (drop).
                continue
            low = value.strip().lower()
            if low in _SSL_TRUTHY:
                translated.append(("sslmode", "require"))
            elif low in _SSL_FALSY:
                translated.append(("sslmode", "disable"))
            elif low in _SSL_LIBPQ_PASSTHROUGH:
                translated.append(("sslmode", low))
            else:
                # Неизвестное значение — безопасный дефолт для managed-hosts.
                translated.append(("sslmode", "require"))
        else:
            translated.append((key, value))

    new_query = urlencode(translated, doseq=False)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
