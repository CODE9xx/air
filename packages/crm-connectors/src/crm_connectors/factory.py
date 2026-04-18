"""
Фабрика коннекторов.

Используется и API, и worker'ом:

    from crm_connectors import get_connector, Provider

    connector = get_connector(Provider.AMOCRM)  # mock=True по умолчанию (MVP)

Флаг `mock` можно передать явно, либо фабрика сама прочитает `MOCK_CRM_MODE`
из окружения (через `apps.api.app.core.settings`, если доступно, иначе — из
`os.environ`). Любой `truthy` — включает mock.
"""

from __future__ import annotations

import os
from typing import Optional

from .amocrm import AmoCrmConnector
from .base import CRMConnector
from .bitrix24 import Bitrix24Connector
from .enums import Provider
from .kommo import KommoConnector
from .mock import MockCRMConnector


def _read_mock_mode_from_settings() -> Optional[bool]:
    """
    Пытается прочитать `MOCK_CRM_MODE` из `apps.api.app.core.settings`.
    Если settings ещё не существует (ранняя стадия разработки) — возвращает None.
    """
    try:
        from apps.api.app.core import settings as _settings  # type: ignore
    except Exception:
        return None
    # Ожидаемые варианты: `settings.MOCK_CRM_MODE` или `settings.settings.MOCK_CRM_MODE`.
    for attr in ("MOCK_CRM_MODE", "mock_crm_mode"):
        if hasattr(_settings, attr):
            return bool(getattr(_settings, attr))
        inner = getattr(_settings, "settings", None)
        if inner is not None and hasattr(inner, attr):
            return bool(getattr(inner, attr))
    return None


def _read_mock_mode_from_env() -> bool:
    """Парсит `MOCK_CRM_MODE` из окружения. По умолчанию — True (MVP)."""
    raw = os.environ.get("MOCK_CRM_MODE", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_mock_mode() -> bool:
    """Итоговое решение: mock-режим или нет."""
    from_settings = _read_mock_mode_from_settings()
    if from_settings is not None:
        return from_settings
    return _read_mock_mode_from_env()


def get_connector(provider: Provider, *, mock: Optional[bool] = None) -> CRMConnector:
    """
    Возвращает нужный коннектор.

    Args:
        provider: какой провайдер «эмулируется» (или используется реально).
        mock: если явно True — всегда MockCRMConnector. Если None — читает
            MOCK_CRM_MODE из settings/env. Если False — реальный коннектор.

    Raises:
        ValueError: если provider неизвестен.
    """
    effective_mock = mock if mock is not None else is_mock_mode()

    if effective_mock:
        # В моке provider сохраняем «как просили» — чтобы БД писала нужное значение.
        return MockCRMConnector(provider=provider)

    if provider == Provider.AMOCRM:
        return AmoCrmConnector()
    if provider == Provider.KOMMO:
        return KommoConnector()
    if provider == Provider.BITRIX24:
        return Bitrix24Connector()
    if provider == Provider.MOCK:
        # MOCK-провайдер без mock-режима — бессмысленно, но вернём Mock.
        return MockCRMConnector(provider=Provider.MOCK)

    raise ValueError(f"Unknown provider: {provider!r}")


__all__ = ["get_connector", "is_mock_mode"]
