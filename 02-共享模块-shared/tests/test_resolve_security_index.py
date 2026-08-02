"""C-D1d：指数名不得解析成个股（上证指数≠平安银行）。"""
from __future__ import annotations

from trader_shared.cache_utils import daily_bars_cache_target
from trader_shared.light_data import resolve_security
from trader_shared.market_types import Security


def test_shanghai_composite_not_pingan():
    sec = resolve_security("上证指数")
    assert sec.code == "000001"
    assert sec.market == "SH", f"上证指数须 SH，实际 {sec.market}（SZ 会落到平安银行）"
    assert sec.qq_symbol == "sh000001"


def test_kcb50_maps_to_index_000688():
    sec = resolve_security("科创50")
    assert sec.code == "000688"
    assert sec.market == "SH"
    assert sec.qq_symbol == "sh000688"


def test_index_and_stock_same_code_cache_keys_differ():
    sh = daily_bars_cache_target("000001", provider="tencent", adjust="qfq", market="SH")
    sz = daily_bars_cache_target("000001", provider="tencent", adjust="qfq", market="SZ")
    assert sh != sz
    assert Security(code="000001", market="SH").qq_symbol == "sh000001"
    assert Security(code="000001", market="SZ").qq_symbol == "sz000001"
