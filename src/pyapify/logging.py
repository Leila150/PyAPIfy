"""Internal logging helpers for PyAPIfy.

PyAPIfy owns its logger namespace while still using Python's standard
``logging`` package. Framework modules can log without configuring global
logging, and applications/plugins can use the exported helpers directly.
"""
from __future__ import annotations
import logging
from typing import Any

ROOT_LOGGER = "pyapify"
LOGGER_NAME = ROOT_LOGGER

DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL


def get_logger(component: str | None = None) -> logging.Logger:
    """Return a logger under the PyAPIfy logging namespace."""
    if not component:
        return logging.getLogger(ROOT_LOGGER)
    return logging.getLogger(f"{ROOT_LOGGER}.{component}")


def configure_logger(logger: logging.Logger, level: int = logging.DEBUG) -> logging.Logger:
    """Configure a logger for direct use without adding duplicate handlers.

    Runtime file handlers remain the responsibility of ``PyAPIfyRuntime``.
    This helper is intentionally conservative: it only sets the level and
    prevents messages from being duplicated by ancestor handlers when a
    caller explicitly configures a child logger.
    """
    logger.setLevel(level)
    return logger


def log(
    level: str | int,
    message: str,
    *args: Any,
    component: str | None = None,
    **kwargs: Any,
) -> None:
    """Log a message through a PyAPIfy logger.

    ``level`` may be a standard logging integer or a case-insensitive name
    such as ``"info"`` or ``"error"``.
    """
    logger = get_logger(component)
    if isinstance(level, str):
        numeric = getattr(logging, level.upper(), None)
        if not isinstance(numeric, int):
            raise ValueError(f"Unknown log level: {level}")
        level = numeric
    logger.log(level, message, *args, **kwargs)


def log_exception(logger: logging.Logger, message: str, *args: Any) -> None:
    """Log an exception with its traceback using the PyAPIfy logger."""
    logger.exception(message, *args)


__all__ = [
    "ROOT_LOGGER", "LOGGER_NAME", "DEBUG", "INFO", "WARNING", "ERROR",
    "CRITICAL", "get_logger", "configure_logger", "log", "log_exception",
]
