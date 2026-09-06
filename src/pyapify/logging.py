"""Internal logging helpers for PyAPIfy.

All framework subsystems use the ``pyapify`` logger hierarchy.  The runtime
configures the file handler; modules only need to ask for their subsystem
logger and never configure global application logging themselves.
"""
from __future__ import annotations
import logging

ROOT_LOGGER = "pyapify"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the PyAPIfy logging namespace."""
    if not name:
        return logging.getLogger(ROOT_LOGGER)
    return logging.getLogger(f"{ROOT_LOGGER}.{name}")


def log_exception(logger: logging.Logger, message: str, *args) -> None:
    """Log an exception with its traceback using the PyAPIfy logger."""
    logger.exception(message, *args)
