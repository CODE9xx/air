"""
Контрактные тесты ``worker.lib.amocrm_creds.load_amocrm_oauth_credentials``.

Task #52.3F (Bug F, обнаружен 2026-04-21 в live-recovery после фиксов D/E)
-----------------------------------------------------------------------
``pull_amocrm_core`` / ``refresh_token`` исторически читали OAuth
client_id / client_secret из env ``AMOCRM_CLIENT_ID`` / ``AMOCRM_CLIENT_SECRET``
независимо от ``crm_connections.amocrm_auth_mode``. Для режима
``external_button`` (#44.6) это неверно: у каждого подключения свои
credentials, приходящие вебхуком и зашифрованные Fernet'ом в
``amocrm_client_secret_encrypted``. Глобальные env для external_button
пусты — worker падал с ``RuntimeError: AMOCRM_CLIENT_ID / AMOCRM_CLIENT_SECRET
не заданы``.

Fix: helper ``load_amocrm_oauth_credentials(conn_row, connection_id=...)``
резолвит credentials по ``conn_row['amocrm_auth_mode']``:

  * ``external_button``  — строго per-installation из БД. Без fallback
    на env (иначе утечка глобальных creds в чужой аккаунт).
  * ``static_client`` / None / ``''`` — env (legacy / pre-#44.6).

БЕЗОПАСНОСТЬ ТЕСТА: синтетические plaintext secrets, шифруем локально
Fernet'ом с тестовым FERNET_KEY из ``tests/conftest.py``. Реальные токены
1ede9725 НЕ используются. Логи проверяем на отсутствие plaintext.

Тесты (6):
  1. external_button + per-install creds → возвращает (client_id, decrypted).
  2. external_button + пустые поля → ``AmoCredentialsMissingError``, БЕЗ
     fallback на env (даже если env установлены).
  3. static_client + env установлены → возвращает env.
  4. NULL/empty auth_mode (legacy pre-#44.6 connection) → fallback на env.
  5. external_button + битые encrypted bytes → ``AmoCredentialsDecryptError``,
     plaintext и Fernet-traceback НЕ утекают в exc.
  6. static_client + env пусты → ``RuntimeError`` без env-значений в сообщении.

Плюс log-hygiene guard: во всех ветках helper НЕ логирует plaintext
client_secret (caplog-captured records scanned).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# sys.path: worker package живёт в ``apps/worker/`` — не входит в PYTHONPATH
# api-контейнера по умолчанию. Добавляем его локально, чтобы тест был
# самодостаточен и запускался как через ``docker compose exec api pytest``,
# так и локально (pytest из корня репо).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_SRC = _REPO_ROOT / "apps" / "worker"
if _WORKER_SRC.is_dir() and str(_WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(_WORKER_SRC))

# Импорт после sys.path hack.
from worker.lib.amocrm_creds import (  # noqa: E402
    AmoCredentialsDecryptError,
    AmoCredentialsMissingError,
    load_amocrm_oauth_credentials,
)
from worker.lib.crypto import encrypt_token  # noqa: E402


# Помечаем все тесты — helper синхронный, async-фикстуры не нужны.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# Синтетические значения — НЕ реальные credentials.
_SYNTHETIC_EB_CLIENT_ID = "eb-client-id-synthetic-44-6"
_SYNTHETIC_EB_SECRET_PLAINTEXT = "eb-client-secret-PLAINTEXT-synthetic"
_SYNTHETIC_STATIC_ID = "static-client-id-synthetic"
_SYNTHETIC_STATIC_SECRET = "static-client-secret-synthetic"
_SYNTHETIC_CONN_ID = "00000000-0000-0000-0000-0000000000aa"


# ---------------------------------------------------------------------------
# 1. external_button happy path
# ---------------------------------------------------------------------------


def test_external_button_uses_per_connection_credentials(monkeypatch, caplog):
    """
    Режим external_button: helper дешифрует Fernet и возвращает
    per-installation (client_id, client_secret). Env не читается.
    """
    # Ставим env, чтобы убедиться, что helper их ИГНОРИРУЕТ.
    monkeypatch.setenv("AMOCRM_CLIENT_ID", "env-should-NOT-be-used")
    monkeypatch.setenv("AMOCRM_CLIENT_SECRET", "env-should-NOT-be-used-secret")

    encrypted = encrypt_token(_SYNTHETIC_EB_SECRET_PLAINTEXT)
    conn_row = {
        "amocrm_auth_mode": "external_button",
        "amocrm_client_id": _SYNTHETIC_EB_CLIENT_ID,
        "amocrm_client_secret_encrypted": encrypted,
    }

    with caplog.at_level(logging.DEBUG, logger="code9.worker.amocrm_creds"):
        client_id, client_secret = load_amocrm_oauth_credentials(
            conn_row, connection_id=_SYNTHETIC_CONN_ID
        )

    assert client_id == _SYNTHETIC_EB_CLIENT_ID
    assert client_secret == _SYNTHETIC_EB_SECRET_PLAINTEXT

    # Log-hygiene: plaintext secret НЕ должен попасть в логи helper'а.
    full_log = "\n".join(r.getMessage() for r in caplog.records)
    assert _SYNTHETIC_EB_SECRET_PLAINTEXT not in full_log, (
        "BUG: plaintext client_secret утёк в лог helper'а"
    )


# ---------------------------------------------------------------------------
# 2. external_button missing per-install creds — no env fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_field",
    [
        "amocrm_client_id",
        "amocrm_client_secret_encrypted",
        "both",
    ],
)
def test_external_button_never_falls_back_to_env_when_creds_missing(
    monkeypatch, missing_field
):
    """
    external_button + пустые client_id / encrypted secret → raise
    ``AmoCredentialsMissingError``. Ни в коем случае не fallback на env,
    даже если ``AMOCRM_CLIENT_ID/SECRET`` установлены — иначе глобальный
    secret мог бы случайно уехать в чужой аккаунт amoCRM.
    """
    monkeypatch.setenv("AMOCRM_CLIENT_ID", "should-not-be-read")
    monkeypatch.setenv("AMOCRM_CLIENT_SECRET", "should-not-be-read-secret")

    encrypted = encrypt_token(_SYNTHETIC_EB_SECRET_PLAINTEXT)
    conn_row = {
        "amocrm_auth_mode": "external_button",
        "amocrm_client_id": (
            None if missing_field in ("amocrm_client_id", "both")
            else _SYNTHETIC_EB_CLIENT_ID
        ),
        "amocrm_client_secret_encrypted": (
            None if missing_field in ("amocrm_client_secret_encrypted", "both")
            else encrypted
        ),
    }

    with pytest.raises(AmoCredentialsMissingError) as exc_info:
        load_amocrm_oauth_credentials(
            conn_row, connection_id=_SYNTHETIC_CONN_ID
        )

    err_text = str(exc_info.value)
    # connection_id — ок; env-значения и plaintext secret — нет.
    assert _SYNTHETIC_CONN_ID in err_text
    assert "should-not-be-read" not in err_text
    assert _SYNTHETIC_EB_SECRET_PLAINTEXT not in err_text


# ---------------------------------------------------------------------------
# 3. static_client — env
# ---------------------------------------------------------------------------


def test_static_client_uses_env_credentials(monkeypatch):
    """
    static_client + env заполнены → helper возвращает env-значения.
    """
    monkeypatch.setenv("AMOCRM_CLIENT_ID", _SYNTHETIC_STATIC_ID)
    monkeypatch.setenv("AMOCRM_CLIENT_SECRET", _SYNTHETIC_STATIC_SECRET)

    conn_row = {
        "amocrm_auth_mode": "static_client",
        # Даже если per-install поля заполнены — в static_client
        # они игнорируются (мы не смешиваем режимы).
        "amocrm_client_id": "ignored-per-install-id",
        "amocrm_client_secret_encrypted": b"ignored-bytes",
    }

    client_id, client_secret = load_amocrm_oauth_credentials(
        conn_row, connection_id=_SYNTHETIC_CONN_ID
    )
    assert client_id == _SYNTHETIC_STATIC_ID
    assert client_secret == _SYNTHETIC_STATIC_SECRET


# ---------------------------------------------------------------------------
# 4. NULL auth_mode (legacy pre-#44.6) — env fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("null_like", [None, "", "   "])
def test_null_or_empty_auth_mode_fallback_to_env(monkeypatch, null_like):
    """
    Pre-#44.6 connections: ``amocrm_auth_mode`` = NULL / пустая строка /
    whitespace → обрабатываются как ``static_client``, env читается.
    Это backward-compat для уже существующих подключений до рефактора
    #44.6 (они не имеют per-install creds).
    """
    monkeypatch.setenv("AMOCRM_CLIENT_ID", _SYNTHETIC_STATIC_ID)
    monkeypatch.setenv("AMOCRM_CLIENT_SECRET", _SYNTHETIC_STATIC_SECRET)

    conn_row = {
        "amocrm_auth_mode": null_like,
        "amocrm_client_id": None,
        "amocrm_client_secret_encrypted": None,
    }
    client_id, client_secret = load_amocrm_oauth_credentials(
        conn_row, connection_id=_SYNTHETIC_CONN_ID
    )
    assert client_id == _SYNTHETIC_STATIC_ID
    assert client_secret == _SYNTHETIC_STATIC_SECRET


# ---------------------------------------------------------------------------
# 5. external_button decrypt failure — safe error
# ---------------------------------------------------------------------------


def test_external_button_decrypt_failure_raises_safe_error(monkeypatch):
    """
    external_button + битые encrypted bytes (не Fernet-ciphertext):
    helper бросает ``AmoCredentialsDecryptError``. Сообщение НЕ содержит
    plaintext, оригинальный traceback подавлен ``from None`` — чтобы
    Fernet-внутренности (теоретически несущие части токена) не утекли
    в worker stderr / RQ ``exc_info``.
    """
    conn_row = {
        "amocrm_auth_mode": "external_button",
        "amocrm_client_id": _SYNTHETIC_EB_CLIENT_ID,
        # Мусор — Fernet.decrypt бросит InvalidToken.
        "amocrm_client_secret_encrypted": b"not-a-valid-fernet-ciphertext-xyz",
    }

    with pytest.raises(AmoCredentialsDecryptError) as exc_info:
        load_amocrm_oauth_credentials(
            conn_row, connection_id=_SYNTHETIC_CONN_ID
        )

    err_text = str(exc_info.value)
    assert _SYNTHETIC_CONN_ID in err_text
    # Никаких Fernet-внутренностей или raw ciphertext в сообщении.
    assert "InvalidToken" not in err_text
    assert "not-a-valid" not in err_text
    # ``raise ... from None`` подавляет __cause__.
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True


# ---------------------------------------------------------------------------
# 6. static_client with empty env — safe RuntimeError
# ---------------------------------------------------------------------------


def test_static_client_missing_env_raises_safe_runtime_error(monkeypatch):
    """
    static_client + env ``AMOCRM_CLIENT_ID/SECRET`` пусты → ``RuntimeError``.
    Сообщение НЕ должно содержать значений env (даже пустых cues).
    """
    monkeypatch.delenv("AMOCRM_CLIENT_ID", raising=False)
    monkeypatch.delenv("AMOCRM_CLIENT_SECRET", raising=False)

    conn_row = {
        "amocrm_auth_mode": "static_client",
        "amocrm_client_id": None,
        "amocrm_client_secret_encrypted": None,
    }

    with pytest.raises(RuntimeError) as exc_info:
        load_amocrm_oauth_credentials(
            conn_row, connection_id=_SYNTHETIC_CONN_ID
        )

    err_text = str(exc_info.value)
    assert _SYNTHETIC_CONN_ID in err_text
    # Не должно быть ``AmoCredentialsMissingError`` — это другой режим.
    assert not isinstance(exc_info.value, AmoCredentialsMissingError)
    assert not isinstance(exc_info.value, AmoCredentialsDecryptError)
