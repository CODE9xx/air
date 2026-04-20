"""
Unit-тесты для ``app.db.url_translate.asyncpg_to_psycopg2``.

Проверяем:
* смену драйвера ``postgresql+asyncpg`` → ``postgresql+psycopg2``
  (и альтернативный вход ``postgres+asyncpg``);
* маппинг ``ssl=...`` → ``sslmode=...``:
    - require/true/1  → require
    - disable/false/0/empty → disable
    - prefer/allow/verify-ca/verify-full → то же имя
    - любое другое значение → require (безопасный дефолт для managed-Postgres);
* tie-break: если явно задан ``sslmode``, он побеждает и ``ssl`` отбрасывается;
* сохранение прочих query-параметров (порядок + значение);
* иммутабельность входа — функция не мутирует переданную строку;
* безопасность: в тестах нет реальных секретов (только ``u:p`` плейсхолдеры).

Тесты чисто строковые — без подключения к Postgres.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from app.db.url_translate import asyncpg_to_psycopg2


# ---------- Driver swap ----------


def test_driver_swap_asyncpg_to_psycopg2():
    out = asyncpg_to_psycopg2("postgresql+asyncpg://u:p@host:5432/db")
    assert out == "postgresql+psycopg2://u:p@host:5432/db"


def test_driver_swap_postgres_alias():
    # Альтернативный вход `postgres+asyncpg://` тоже поддерживается.
    out = asyncpg_to_psycopg2("postgres+asyncpg://u:p@host:5432/db")
    assert out == "postgresql+psycopg2://u:p@host:5432/db"


def test_driver_already_psycopg2_untouched():
    url = "postgresql+psycopg2://u:p@host:5432/db"
    assert asyncpg_to_psycopg2(url) == url


def test_driver_bare_postgresql_untouched():
    # Без указанного драйвера — схему не трогаем (SQLAlchemy сам подберёт).
    url = "postgresql://u:p@host:5432/db"
    assert asyncpg_to_psycopg2(url) == url


# ---------- ssl → sslmode mapping ----------


@pytest.mark.parametrize("ssl_value", ["require", "true", "1", "REQUIRE", "True", "TRUE"])
def test_ssl_truthy_maps_to_require(ssl_value):
    out = asyncpg_to_psycopg2(f"postgresql+asyncpg://u:p@host/db?ssl={ssl_value}")
    q = parse_qs(urlsplit(out).query)
    assert q == {"sslmode": ["require"]}


@pytest.mark.parametrize("ssl_value", ["disable", "false", "0", "DISABLE", "False", "FALSE"])
def test_ssl_falsy_maps_to_disable(ssl_value):
    out = asyncpg_to_psycopg2(f"postgresql+asyncpg://u:p@host/db?ssl={ssl_value}")
    q = parse_qs(urlsplit(out).query)
    assert q == {"sslmode": ["disable"]}


@pytest.mark.parametrize("ssl_value", ["prefer", "allow", "verify-ca", "verify-full"])
def test_ssl_libpq_passthrough_names(ssl_value):
    out = asyncpg_to_psycopg2(f"postgresql+asyncpg://u:p@host/db?ssl={ssl_value}")
    q = parse_qs(urlsplit(out).query)
    assert q == {"sslmode": [ssl_value]}


def test_ssl_empty_value_maps_to_disable():
    # Пустое значение ssl= трактуем как «явно выключено» —
    # ровно так же, как `disable`.
    out = asyncpg_to_psycopg2("postgresql+asyncpg://u:p@host/db?ssl=")
    q = parse_qs(urlsplit(out).query, keep_blank_values=True)
    assert q == {"sslmode": ["disable"]}


def test_ssl_unknown_value_defaults_to_require():
    # Для неизвестных значений безопасный дефолт — require
    # (managed-Postgres с TLS-only политикой, напр. Timeweb).
    out = asyncpg_to_psycopg2("postgresql+asyncpg://u:p@host/db?ssl=foobar")
    q = parse_qs(urlsplit(out).query)
    assert q == {"sslmode": ["require"]}


# ---------- Tie-break: explicit sslmode wins ----------


def test_tie_break_sslmode_wins_over_ssl():
    # ?ssl=disable&sslmode=require → sslmode=require (явное побеждает)
    out = asyncpg_to_psycopg2(
        "postgresql+asyncpg://u:p@host/db?ssl=disable&sslmode=require"
    )
    q = parse_qs(urlsplit(out).query)
    # ssl-ключ должен исчезнуть, остаётся только sslmode.
    assert q == {"sslmode": ["require"]}


def test_tie_break_sslmode_wins_reverse_order():
    # Порядок ключей в URL не важен для tie-break.
    out = asyncpg_to_psycopg2(
        "postgresql+asyncpg://u:p@host/db?sslmode=disable&ssl=require"
    )
    q = parse_qs(urlsplit(out).query)
    assert q == {"sslmode": ["disable"]}


# ---------- Other query params preserved ----------


def test_other_params_passthrough():
    out = asyncpg_to_psycopg2(
        "postgresql+asyncpg://u:p@host/db"
        "?ssl=require&application_name=worker&connect_timeout=5"
    )
    q = parse_qs(urlsplit(out).query)
    assert q["sslmode"] == ["require"]
    assert q["application_name"] == ["worker"]
    assert q["connect_timeout"] == ["5"]


def test_no_query_no_ssl_translation():
    # Без query-строки функция лишь меняет драйвер.
    out = asyncpg_to_psycopg2("postgresql+asyncpg://u:p@host/db")
    assert out == "postgresql+psycopg2://u:p@host/db"
    assert "?" not in out


# ---------- Full round-trip на «боевом» DSN-шаблоне ----------


def test_timeweb_shaped_dsn_round_trip():
    # Шаблон DSN managed Postgres (Timeweb): TLS-only, asyncpg-driver,
    # `ssl=require`. После трансляции — валидный psycopg2 URL.
    src = (
        "postgresql+asyncpg://code9:PLACEHOLDER@managed.example.ru:6432/"
        "code9?ssl=require&application_name=code9-worker"
    )
    out = asyncpg_to_psycopg2(src)
    parts = urlsplit(out)
    assert parts.scheme == "postgresql+psycopg2"
    assert parts.netloc == "code9:PLACEHOLDER@managed.example.ru:6432"
    assert parts.path == "/code9"
    q = parse_qs(parts.query)
    assert q == {
        "sslmode": ["require"],
        "application_name": ["code9-worker"],
    }


# ---------- Immutability ----------


def test_input_string_not_mutated():
    src = "postgresql+asyncpg://u:p@host/db?ssl=require"
    copy = src
    _ = asyncpg_to_psycopg2(src)
    assert src == copy  # Python-строки immutable, но assert фиксирует контракт.
