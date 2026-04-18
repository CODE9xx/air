"""
Отправка писем.

Поддерживаем два backend'а через ``EMAIL_BACKEND``:

* ``console``  — пишем в stdout + structured log. Подходит для dev/демо,
  а также как fallback, если SMTP-доступ ещё не настроен.
* ``smtp``     — реальная отправка через stdlib ``smtplib`` (STARTTLS / SSL /
  plain). В проде рекомендуем ``SMTP_MODE=starttls`` (587) или ``ssl`` (465).

Дизайн-принципы:

* Call sites остаются синхронными — ``send_verification_code`` / ``send_notification``
  импортируются из auth/crm-роутеров как обычные функции. SMTPBackend блокирует
  I/O, но это тонкая операция (1 письмо = 1 запрос на код / сброс пароля),
  и в MVP мы не вынесли её в RQ-очередь. TODO: если времена отправки
  начнут заметно бить по p95, перевести backend на worker job.
* **Никогда** не печатаем код подтверждения в ``logger.info`` — только subject +
  backend. Код viден лишь в stdout console-backend'а (dev), и никогда
  не попадает в prod-логи.
* **Никогда** не логируем SMTP_PASSWORD / SMTP_USER в тексте исключений —
  ловим SMTP-ошибку и эмитим безопасный ``email_send_failed`` без секретов.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Optional

from app.core.settings import get_settings

logger = logging.getLogger("code9.email")


# ---------------------------------------------------------------------------
#  Шаблоны
# ---------------------------------------------------------------------------
#
# Phase 1 — inline dict'ы. Если шаблоны начнут разрастаться (HTML, локализация),
# вынесем в ``apps/api/templates/emails/*.txt`` + jinja2. Для Gate B простой
# текст гарантированно доходит и не блокируется спам-фильтрами.

_VERIFICATION_SUBJECTS: dict[str, str] = {
    "email_verify":       "Code9: подтверждение e-mail",
    "password_reset":     "Code9: сброс пароля",
    "connection_delete":  "Code9: подтверждение удаления подключения",
    "invite":             "Code9: приглашение в workspace",
}

_VERIFICATION_BODIES: dict[str, str] = {
    "email_verify": (
        "Здравствуйте!\n\n"
        "Ваш код подтверждения e-mail: {code}\n\n"
        "Код действителен 15 минут.\n"
        "Если вы не запрашивали регистрацию в Code9, просто проигнорируйте письмо.\n\n"
        "— Code9 Analytics"
    ),
    "password_reset": (
        "Здравствуйте!\n\n"
        "Вы запросили сброс пароля в Code9 Analytics.\n"
        "Ваш код: {code}\n\n"
        "Код действителен 15 минут. Если вы не запрашивали сброс — игнорируйте "
        "это письмо, ваш текущий пароль остаётся в силе.\n\n"
        "— Code9 Analytics"
    ),
    "connection_delete": (
        "Здравствуйте!\n\n"
        "Вы запросили удаление CRM-подключения в Code9 Analytics.\n"
        "Ваш код подтверждения: {code}\n\n"
        "Код действителен 15 минут. Если вы не запрашивали это действие — "
        "срочно зайдите в аккаунт и смените пароль.\n\n"
        "— Code9 Analytics"
    ),
    "invite": (
        "Здравствуйте!\n\n"
        "Вас пригласили в workspace Code9 Analytics.\n"
        "Код для завершения регистрации: {code}\n\n"
        "Код действителен 15 минут.\n\n"
        "— Code9 Analytics"
    ),
}

_DEFAULT_SUBJECT = "Code9: подтверждение действия"
_DEFAULT_BODY = (
    "Ваш код подтверждения: {code}\n"
    "Код действителен 15 минут.\n"
    "Если вы не запрашивали действие — проигнорируйте письмо.\n"
    "— Code9 Analytics"
)


def _render_verification(code: str, purpose: str) -> tuple[str, str]:
    subject = _VERIFICATION_SUBJECTS.get(purpose, _DEFAULT_SUBJECT)
    body = _VERIFICATION_BODIES.get(purpose, _DEFAULT_BODY).format(code=code)
    return subject, body


# ---------------------------------------------------------------------------
#  Backends
# ---------------------------------------------------------------------------

class EmailBackend(ABC):
    """Общий интерфейс отправки писем."""

    name: str = "abstract"

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None:
        """Отправить письмо синхронно.

        В случае неуспеха backend должен либо сам подавить исключение
        (и залогировать), либо дать понятное безопасное исключение —
        никаких SMTP-credentials в traceback.
        """
        raise NotImplementedError


class ConsoleBackend(EmailBackend):
    """Dev-backend: print в stdout + structured log.

    ВНИМАНИЕ: тело письма (в т.ч. код подтверждения) уходит в stdout.
    В prod использовать только при ``MOCK_CRM_MODE=true`` или как
    явный сознательный выбор оператора — не дефолт.
    """

    name = "console"

    def send(self, to: str, subject: str, body: str) -> None:
        msg = f"EMAIL -> {to}: {subject}\n{body}"
        # stdout — чтобы видно было в `docker compose logs api`.
        print(msg)
        # Structured log — только факт отправки, без тела и кода.
        logger.info("email_sent", extra={"to": to, "subject": subject, "backend": self.name})


class SMTPBackend(EmailBackend):
    """Prod-backend: отправка через stdlib smtplib (sync, короткая сессия)."""

    name = "smtp"

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        sender: str,
        mode: str = "starttls",
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender
        self.mode = (mode or "starttls").lower()
        self.timeout = timeout

    def _build_message(self, to: str, subject: str, body: str) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body, charset="utf-8")
        # RFC-заголовки, помогающие deliverability.
        msg["Auto-Submitted"] = "auto-generated"
        msg["X-Mailer"] = "code9-analytics"
        return msg

    def _open_client(self) -> smtplib.SMTP | smtplib.SMTP_SSL:
        if self.mode == "ssl":
            # Порт 465, TLS сразу.
            context = ssl.create_default_context()
            return smtplib.SMTP_SSL(
                host=self.host,
                port=self.port,
                timeout=self.timeout,
                context=context,
            )
        # plain + опциональный STARTTLS.
        client = smtplib.SMTP(host=self.host, port=self.port, timeout=self.timeout)
        if self.mode == "starttls":
            context = ssl.create_default_context()
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        # mode=="none" → без шифрования (dev/internal relay).
        return client

    def send(self, to: str, subject: str, body: str) -> None:
        msg = self._build_message(to, subject, body)
        try:
            with self._open_client() as client:
                if self.user and self.password:
                    client.login(self.user, self.password)
                client.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            # Маскируем — никогда не кладём SMTP_PASSWORD/USER в traceback.
            logger.error(
                "email_send_failed",
                extra={
                    "to": to,
                    "subject": subject,
                    "backend": self.name,
                    "error_type": type(exc).__name__,
                    "smtp_host": self.host,
                    "smtp_port": self.port,
                    # Никаких self.user/self.password в логах.
                },
            )
            # Наверх летит generic RuntimeError — чтобы случайно не
            # показать SMTP-сообщение в http-response.
            raise RuntimeError("email_send_failed") from None

        logger.info(
            "email_sent",
            extra={"to": to, "subject": subject, "backend": self.name},
        )


# ---------------------------------------------------------------------------
#  Factory (lazy singleton)
# ---------------------------------------------------------------------------

_backend_singleton: Optional[EmailBackend] = None


def _build_backend() -> EmailBackend:
    s = get_settings()
    kind = (s.email_backend or "console").strip().lower()

    if kind == "smtp":
        if not s.smtp_host:
            # Не даём тихо падать: если админ сказал smtp, но не заполнил host,
            # в prod это поймает validator, в dev — логируем и fallback на console.
            logger.warning(
                "email_backend_smtp_missing_host_fallback_console",
                extra={"smtp_host": s.smtp_host},
            )
            return ConsoleBackend()
        return SMTPBackend(
            host=s.smtp_host,
            port=s.smtp_port,
            user=s.smtp_user,
            password=s.smtp_password,
            sender=s.smtp_from,
            mode=s.smtp_mode,
            timeout=float(s.smtp_timeout_seconds),
        )
    # default / explicit console
    return ConsoleBackend()


def get_backend() -> EmailBackend:
    """Кэшированный backend. Инициализируется при первой отправке."""
    global _backend_singleton
    if _backend_singleton is None:
        _backend_singleton = _build_backend()
    return _backend_singleton


def reset_backend() -> None:
    """Для тестов: сбросить singleton, чтобы перечитать env."""
    global _backend_singleton
    _backend_singleton = None


# ---------------------------------------------------------------------------
#  Public API (сохраняем подпись прежних функций)
# ---------------------------------------------------------------------------

def send_verification_code(email: str, code: str, purpose: str) -> None:
    """
    Шлёт e-mail с кодом (6-значным в Code9).

    ``purpose``: 'email_verify' | 'password_reset' | 'connection_delete' | 'invite'.
    """
    subject, body = _render_verification(code, purpose)
    _send(email, subject, body, purpose=purpose)


def send_notification(email: str, subject: str, body: str) -> None:
    """Произвольное уведомление (нотификации из админки/биллинга)."""
    _send(email, subject, body, purpose="notification")


def _send(email: str, subject: str, body: str, *, purpose: str) -> None:
    backend = get_backend()
    try:
        backend.send(email, subject, body)
    except Exception:
        # Логирование уже сделано backend'ом. Наверх пробрасываем generic —
        # роутеры решают, как реагировать (для password-reset — тихо глотать:
        # анти-энумерация важнее, чем фидбек юзеру).
        logger.warning(
            "email_dispatch_failed",
            extra={"to": email, "subject": subject, "purpose": purpose,
                   "backend": backend.name},
        )
        # На данном этапе НЕ ре-райзим: верхние эндпоинты уже закоммитили
        # EmailVerificationCode, и мы не хотим отдавать 500 в user flow.
        # Оператор увидит email_send_failed в логах → починит SMTP.
        return
