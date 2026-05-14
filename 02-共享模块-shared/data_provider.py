"""Unified DataProvider interface — thin re-export layer.

All real implementation lives in trader_shared/data_provider.py.
This file exists for backward compatibility only.
"""
from trader_shared.data_provider import *  # noqa: F401,F403
from trader_shared.data_provider import (
    Security,
    get_provider,
    set_provider,
)
