"""
Отправка писем.

В DEV — пишем в логи (`DEV_EMAIL_MODE=log`). В V1 — SMTP/transactional API.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("code9.email")


def _emit(to: str, subject: str, body: str) -> None:
    """Универсальная отправка. Сейчас — print + лог."""
    msg = f"EMAIL -> {to}: {subject}\n{body}"
    # Двойная сигнализация: print для docker logs, logger — для structured.
    print(msg)
    logger.info("email_sent", extra={"to": to, "subject": subject})


def send_verification_code(email: str, code: str, purpose: str) -> None:
    """
    Шлёт email с 6-значным кодом.

    purpose: 'email_verify' | 'password_reset' | 'connection_delete'.
    """
    subjects = {
        "email_verify": "Code9: подтверждение email",
        "password_reset": "Code9: сброс пароля",
        "connection_delete": "Code9: подтверждение удаления подключения",
    }
    subject = subjects.get(purpose, "Code9: подтверждение действия")
    body = (
        f"Ваш код подтверждения: {code}\n"
        f"Код действителен 10-15 минут.\n"
        f"Если вы не запрашивали это действие — проигнорируйте письмо.\n"
    )
    _emit(email, subject, body)


def send_notification(email: str, subject: str, body: str) -> None:
    """Произвольное уведомление (нотификации)."""
    _emit(email, subject, body)
