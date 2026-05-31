"""Centralized logging configuration for trader_shared modules.

Usage:
    from trader_shared._logging import get_logger
    logger = get_logger(__name__)
    logger.warning("Something went wrong: %s", exc)
"""
from __future__ import annotations

import logging
import os
import sys

_LOG_LEVEL = os.environ.get("TRADER_LOG_LEVEL", "WARNING").upper()
_LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root() -> None:
    """Configure root logger once."""
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger("trader")
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT))
        root.addHandler(handler)
    root.setLevel(getattr(logging, _LOG_LEVEL, logging.WARNING))


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the 'trader' namespace.

    Args:
        name: Module name (typically __name__).

    Returns:
        Configured Logger instance.
    """
    _configure_root()
    # Strip prefix to keep logger names short
    if name.startswith("trader_shared."):
        name = name[len("trader_shared."):]
    elif name.startswith("trader_shared"):
        name = name[len("trader_shared"):]
    return logging.getLogger(f"trader.{name}")
