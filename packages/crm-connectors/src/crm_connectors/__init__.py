"""
Code9 Analytics — CRM connectors package.

Публичный API:

    from crm_connectors import (
        get_connector, is_mock_mode,
        Provider, ConnectionStatus,
        CRMConnector, MockCRMConnector, AmoCrmConnector,
        KommoConnector, Bitrix24Connector,
        TokenPair,
        RawDeal, RawContact, RawCompany, RawPipeline, RawStage,
        RawUser, RawCall, RawMessage, RawTask, RawNote,
        CRMConnectorError, TokenExpired, InvalidGrant,
        RateLimited, ProviderError,
    )
"""

from .amocrm import AmoCrmConnector
from .base import (
    CRMConnector,
    RawCall,
    RawCompany,
    RawContact,
    RawDeal,
    RawMessage,
    RawNote,
    RawPipeline,
    RawStage,
    RawTask,
    RawUser,
    TokenPair,
)
from .bitrix24 import Bitrix24Connector
from .enums import ConnectionStatus, Provider
from .exceptions import (
    CRMConnectorError,
    InvalidGrant,
    NotImplementedInMVP,
    ProviderError,
    RateLimited,
    TokenExpired,
)
from .factory import get_connector, is_mock_mode
from .kommo import KommoConnector
from .mock import MockCRMConnector

__version__ = "0.1.0"

__all__ = [
    # factory
    "get_connector",
    "is_mock_mode",
    # enums
    "Provider",
    "ConnectionStatus",
    # protocol + impls
    "CRMConnector",
    "MockCRMConnector",
    "AmoCrmConnector",
    "KommoConnector",
    "Bitrix24Connector",
    # tokens
    "TokenPair",
    # raw dataclasses
    "RawDeal",
    "RawContact",
    "RawCompany",
    "RawPipeline",
    "RawStage",
    "RawUser",
    "RawCall",
    "RawMessage",
    "RawTask",
    "RawNote",
    # exceptions
    "CRMConnectorError",
    "TokenExpired",
    "InvalidGrant",
    "RateLimited",
    "ProviderError",
    "NotImplementedInMVP",
    # aliases (исторические/альтернативные имена)
    "AmoCRMConnector",
]


# --- Backwards-compatible aliases --------------------------------------------
# Часть потребителей (и тесты QA) могут ожидать имя `AmoCRMConnector`
# (CamelCase по модулю). Даём алиас, не меняя каноническое имя класса.
AmoCRMConnector = AmoCrmConnector
