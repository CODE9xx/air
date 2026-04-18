"""
Исключения, используемые коннекторами.

Иерархия:
    CRMConnectorError
    ├── TokenExpired      — access_token просрочен, нужен refresh
    ├── InvalidGrant      — refresh_token невалиден (требуется reconnect)
    ├── RateLimited       — провайдер вернул 429
    └── ProviderError     — любая прочая ошибка провайдера (5xx / необычные 4xx)
"""

from __future__ import annotations

from typing import Any


class CRMConnectorError(Exception):
    """Базовый класс всех ошибок коннекторов."""

    def __init__(self, message: str, *, provider: str | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.provider = provider
        # payload НЕ должен логироваться автоматически — может содержать токены.
        self.payload = payload


class TokenExpired(CRMConnectorError):
    """Access token просрочен. Worker должен вызвать `refresh`."""


class InvalidGrant(CRMConnectorError):
    """
    Refresh-токен невалиден (отозван / истёк / аккаунт отключён).
    API должен перевести подключение в статус `lost_token` и уведомить пользователя.
    """


class RateLimited(CRMConnectorError):
    """Провайдер вернул 429. `retry_after_seconds` — когда можно повторить."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        retry_after_seconds: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message, provider=provider, payload=payload)
        self.retry_after_seconds = retry_after_seconds


class ProviderError(CRMConnectorError):
    """Обобщённая ошибка провайдера (5xx / неожиданный ответ)."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message, provider=provider, payload=payload)
        self.status_code = status_code


class NotImplementedInMVP(CRMConnectorError):
    """
    Метод реального коннектора не реализован в MVP (V1+).
    Используется как обёртка над `NotImplementedError` для случаев, когда
    BE/worker хочет отличать «фича-flag отключена» от «незаконченный код».
    В текущем skeleton большинство методов реальных коннекторов всё ещё
    raise NotImplementedError — это намеренно: исключение обнажает баг
    конфигурации (mock=False в MVP), а не «штатное» поведение.
    """


__all__ = [
    "CRMConnectorError",
    "TokenExpired",
    "InvalidGrant",
    "RateLimited",
    "ProviderError",
    "NotImplementedInMVP",
]
