"""
Логгер worker'а с автоматическим маскированием секретов.

Это тонкая обёртка над ``structlog``, которая:
- ставит обработчик-маскировщик (см. ``log_mask.mask_dict``);
- пропускает Bearer-заголовки через ``log_mask.mask_bearer``.

Использование:

    from worker.lib.logger import get_logger
    log = get_logger(__name__)
    log.info("refresh_token ok", connection_id=cid)

В MVP используется простой fallback (print), если structlog не сконфигурирован.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

from worker.lib.log_mask import mask_bearer, mask_dict

_LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()

_LOGGERS: dict[str, "MaskedLogger"] = {}


class MaskedLogger:
    """Упрощённая обёртка вокруг stdlib logging с маскировкой kwargs/messages."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(levelname)-5s [%(name)s] %(message)s",
                )
            )
            self._logger.addHandler(handler)
            self._logger.setLevel(_LOG_LEVEL)
            self._logger.propagate = False

    def _fmt(self, msg: str, kwargs: dict[str, Any]) -> str:
        if not kwargs:
            return mask_bearer(msg)
        masked = mask_dict(kwargs)
        pairs = " ".join(f"{k}={v!r}" for k, v in masked.items())
        return f"{mask_bearer(msg)} {pairs}"

    def debug(self, msg: str, **kw: Any) -> None:
        self._logger.debug(self._fmt(msg, kw))

    def info(self, msg: str, **kw: Any) -> None:
        self._logger.info(self._fmt(msg, kw))

    def warning(self, msg: str, **kw: Any) -> None:
        self._logger.warning(self._fmt(msg, kw))

    def error(self, msg: str, **kw: Any) -> None:
        self._logger.error(self._fmt(msg, kw))


def get_logger(name: str = "worker") -> MaskedLogger:
    """Синглтон логгера по имени."""
    if name not in _LOGGERS:
        _LOGGERS[name] = MaskedLogger(name)
    return _LOGGERS[name]


__all__ = ["MaskedLogger", "get_logger"]
