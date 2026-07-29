# -*- coding: utf-8 -*-
"""report_pipeline 共享类型。"""
from __future__ import annotations

from typing import Any, Callable

from trader_shared._logging import get_logger

_logger = get_logger(__name__)

MarkFn = Callable[[str], None]


def _noop_mark(_label: str) -> None:
    return None

