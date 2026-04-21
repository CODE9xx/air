"""
Контрактные тесты ``scripts.migrations.apply_tenant_template._escape_pct_for_configparser``.

Bug E (Task #52.3E, обнаружен 2026-04-21 в live-recovery после фикса Bug D)
-----------------------------------------------------------------------
Alembic ``Config.set_main_option`` делегирует в stdlib ``ConfigParser`` с
``BasicInterpolation``. URL-encoded символы в DB-пароле (``%40`` = ``@``,
``%7C`` = ``|``, ``%3E`` = ``>``, ``%23`` = ``#``, ``%3B`` = ``;``) парсятся
как префикс подстановки — raise::

    ValueError: invalid interpolation syntax in '<FULL DSN>' at position N

Сообщение исключения содержит **полный DSN** — утекает в worker stderr,
docker-логи, RQ ``exc_info`` в Redis. Фикс: ``url.replace("%", "%%")`` перед
``set_main_option`` (ConfigParser разэкранирует обратно на ``get``).

БЕЗОПАСНОСТЬ ТЕСТА: используются ТОЛЬКО синтетические DSN. ``DATABASE_URL``
НЕ читается, реальные credentials не попадают в логи тестраннера.

Тесты:
  1. Round-trip: set(escape(dsn)) → get() == dsn для характерных паттернов.
  2. Control: DSN без '%' проходит как есть.
  3. Regression guard: НЕэкранированный DSN действительно триггерит Bug E
     (нужен, чтобы мы увидели, если ConfigParser когда-нибудь перестанет
     падать — и фикс сам по себе устарел).
  4. Scrubber: ``apply_tenant_template`` перехватывает ``ValueError`` от
     ``set_main_option`` и переписывает на RuntimeError без DSN в тексте.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from alembic.config import Config

from scripts.migrations.apply_tenant_template import (
    _escape_pct_for_configparser,
    apply_tenant_template,
)


# Синтетические DSN — НЕ реальные credentials. Намеренно включены
# характерные паттерны URL-encoded паролей из managed-Postgres.
_SYNTHETIC_DSNS = [
    # Множественные URL-encoded spec-chars (@ | > # ;) — главный кейс Bug E.
    "postgresql+psycopg2://u:p%40%7C%3E%23%3Bx@h:5432/d?sslmode=require",
    # Одиночный %.
    "postgresql+psycopg2://u:p%xyz@h:5432/d",
    # Escaped percent literal (%25 = '%').
    "postgresql+psycopg2://u:a%25b@h:5432/d",
    # % в host (unusual, но валидный ConfigParser-кейс).
    "postgresql+psycopg2://u:p@h%2Einternal:5432/d",
    # % в query string.
    "postgresql+psycopg2://u:p@h:5432/d?options=%2Dc%20timezone%3DUTC",
    # Control: DSN без '%' — escape должен быть no-op.
    "postgresql+psycopg2://u:plain@h:5432/d",
    # Control: пустой пароль.
    "postgresql+psycopg2://u:@h:5432/d",
]


@pytest.mark.parametrize("dsn", _SYNTHETIC_DSNS)
def test_escape_roundtrip_through_configparser(dsn: str) -> None:
    """set(escape(dsn)) → get() должен вернуть исходный dsn."""
    cfg = Config()
    escaped = _escape_pct_for_configparser(dsn)
    # НЕ должен падать.
    cfg.set_main_option("sqlalchemy.url", escaped)
    resolved = cfg.get_main_option("sqlalchemy.url")
    assert resolved == dsn, (
        f"ConfigParser round-trip сломан: input={dsn!r} → "
        f"escaped={escaped!r} → get()={resolved!r}"
    )


def test_escape_is_noop_for_dsn_without_percent() -> None:
    """DSN без '%' не изменяется."""
    dsn = "postgresql+psycopg2://user:password@host:5432/db"
    assert _escape_pct_for_configparser(dsn) == dsn


def test_escape_doubles_every_percent() -> None:
    """Контракт: каждый '%' превращается в '%%' (один проход)."""
    assert _escape_pct_for_configparser("a%b%c") == "a%%b%%c"
    assert _escape_pct_for_configparser("%%") == "%%%%"
    assert _escape_pct_for_configparser("") == ""


def test_bug_e_still_reproduces_without_escape() -> None:
    """Regression guard: без escape ConfigParser должен падать на % в DSN.

    Если этот тест когда-нибудь PASS-нёт без escape — значит ConfigParser
    изменил поведение и ``_escape_pct_for_configparser`` можно упростить.
    """
    cfg = Config()
    raw = "postgresql+psycopg2://u:p%40x@h:5432/d"
    with pytest.raises(ValueError, match="interpolation"):
        cfg.set_main_option("sqlalchemy.url", raw)


class _FakeCfg:
    """Минимальный стаб Alembic Config — имитирует ValueError на set_main_option
    с DSN в тексте (как это делает реальный ConfigParser.before_set)."""

    cmd_opts = None

    def __init__(self, *_args, **_kwargs) -> None:
        self.attributes: dict = {}

    def set_main_option(self, _key: str, value: str) -> None:
        # Точный формат, который производит stdlib ConfigParser при '%' в value.
        raise ValueError(f"invalid interpolation syntax in {value!r} at position 31")


def test_apply_tenant_template_scrubs_configparser_value_error() -> None:
    """Defence-in-depth: если escape не сработает, ``apply_tenant_template``
    ловит ``ValueError`` и переписывает на ``RuntimeError`` без DSN в тексте.

    Имитируем: escape возвращает DSN как есть (симуляция регресса) →
    ``set_main_option`` бросает ``ValueError`` с DSN в сообщении →
    ``apply_tenant_template`` ловит и переписывает на безопасный RuntimeError.

    Тест полностью герметичен: Config подменён, ensure_schema замокан,
    реальная БД и alembic.ini не используются.
    """
    synthetic_dsn = "postgresql+psycopg2://u:SECRET%40LEAK@h:5432/d"

    with patch(
        "scripts.migrations.apply_tenant_template.ensure_schema",
        return_value=None,
    ), patch(
        "scripts.migrations.apply_tenant_template._sync_url",
        return_value=synthetic_dsn,
    ), patch(
        "scripts.migrations.apply_tenant_template._escape_pct_for_configparser",
        side_effect=lambda url: url,  # регресс: escape выключен
    ), patch(
        "scripts.migrations.apply_tenant_template.Config",
        _FakeCfg,
    ):
        with pytest.raises(RuntimeError) as exc_info:
            apply_tenant_template("crm_synthetic_test")

    err_text = str(exc_info.value)
    # Главное требование: DSN/пароль НЕ должны появиться в новом сообщении.
    assert "SECRET" not in err_text, (
        f"Bug E leak regression: scrubber пропустил пароль: {err_text!r}"
    )
    assert "%40LEAK" not in err_text
    assert synthetic_dsn not in err_text
    # ``raise ... from None`` подавляет оригинал.
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    # Новое сообщение осмысленное.
    assert "Bug E" in err_text or "ConfigParser" in err_text
