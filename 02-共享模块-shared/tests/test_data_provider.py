"""Tests for the akshare data provider backend (P0 #2 fix).

The `_akshare_to_bar` and `_akshare_fetch_quote` helpers were calling
`to_float(...)` as a bare function name, but the module never imported
`to_float` at top level. When TRADER_DATA_PROVIDER=akshare was set, calling
any akshare method immediately raised `NameError: name 'to_float' is not
defined`.

This test verifies the top-level import is now present.
"""
from __future__ import annotations

import importlib
import sys


def test_akshare_to_float_imported() -> None:
    """`from trader_shared.light_data import to_float` must exist in data_provider module."""
    import trader_shared.data_provider as dp
    importlib.reload(dp)
    assert hasattr(dp, "to_float"), "data_provider module must expose to_float at top level"
    # to_float should be the same callable as light_data.to_float
    from trader_shared.light_data import to_float as light_to_float
    assert dp.to_float is light_to_float


def test_akshare_class_method_uses_top_level_to_float() -> None:
    """UnifiedProvider.to_float (instance method) should still be wired to light_data.to_float."""
    from trader_shared.data_provider import UnifiedProvider
    from trader_shared.light_data import to_float as light_to_float

    provider = UnifiedProvider(backend="akshare")
    # Call the instance method
    assert provider.to_float("3.14") == 3.14
    assert provider.to_float(None) is None
    assert provider.to_float("--") is None
