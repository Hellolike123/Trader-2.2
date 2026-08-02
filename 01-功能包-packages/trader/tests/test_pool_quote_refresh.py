"""池价刷新走 provider / get_quotes — handoff A2/A3 无网测。

法源：docs/plans/pool-quote-provider-handoff.md
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARED = ROOT.parents[1] / "02-共享模块-shared"
for p in (str(SCRIPTS), str(SHARED)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pool_cmds.plan_view import _refresh_pool_prices  # noqa: E402


def test_refresh_writes_fields_and_skips_failures():
    """A2: 成功票写 current/change_pct/price_fetched_at；失败票保留旧价。"""
    items = [
        {"name": "票A", "current": 1.0, "change_pct": 0.0},
        {"name": "票B", "current": 2.0, "change_pct": -1.0},
        {"name": "票C", "current": 3.0, "change_pct": 0.5},
    ]
    pool = {"items": items}

    def fake_quotes(targets):
        assert list(targets) == ["票A", "票B", "票C"]
        return {
            "票A": {"current_price": 11.56, "current_change_pct": 1.23},
            "票B": {},  # 失败
            "票C": {"current_price": 0, "current_change_pct": 9.9},  # 无效价
        }

    with patch("pool_cmds.plan_view.save_pool") as mock_save:
        out = _refresh_pool_prices(items, pool, quote_fn=fake_quotes)

    assert out[0]["current"] == 11.56
    assert out[0]["change_pct"] == 1.23
    assert out[0]["price_fetched_at"]
    assert out[1]["current"] == 2.0
    assert out[1]["change_pct"] == -1.0
    assert "price_fetched_at" not in out[1]
    assert out[2]["current"] == 3.0
    assert "price_fetched_at" not in out[2]
    mock_save.assert_called_once_with(pool)


def test_refresh_no_save_when_all_fail():
    items = [{"name": "票X", "current": 9.0, "change_pct": 0.0}]
    pool = {"items": items}

    with patch("pool_cmds.plan_view.save_pool") as mock_save:
        _refresh_pool_prices(items, pool, quote_fn=lambda _t: {"票X": {}})

    assert items[0]["current"] == 9.0
    mock_save.assert_not_called()


def test_refresh_default_path_calls_get_quotes_once():
    """A3: 默认路径一次批量 get_quotes，多码并行入口。"""
    items = [
        {"name": "甲", "current": 1.0, "change_pct": 0.0},
        {"name": "乙", "current": 2.0, "change_pct": 0.0},
    ]
    pool = {"items": items}
    calls: list[list[str]] = []

    def fake_get_quotes(targets, **_kwargs):
        calls.append(list(targets))
        return {
            "甲": {"current_price": 10.0, "current_change_pct": 0.5},
            "乙": {"current_price": 20.0, "current_change_pct": -0.5},
        }

    with patch("trader_shared.data_access.get_quotes", side_effect=fake_get_quotes) as mock_gq:
        with patch("pool_cmds.plan_view.save_pool"):
            _refresh_pool_prices(items, pool)

    assert mock_gq.call_count == 1
    assert calls == [["甲", "乙"]]
    assert items[0]["current"] == 10.0
    assert items[1]["current"] == 20.0


def test_get_quotes_uses_bounded_thread_pool():
    """A3: get_quotes 经 ThreadPoolExecutor 并行拉取。"""
    from trader_shared import data_access as da

    mock_p = MagicMock()
    sec = MagicMock()
    mock_p.resolve_security.return_value = sec
    mock_p.fetch_quote.side_effect = lambda _sec: {
        "current_price": 10.0,
        "current_change_pct": 1.0,
    }

    real_executor = da.ThreadPoolExecutor
    constructed: list[int] = []

    class TrackingExecutor(real_executor):
        def __init__(self, *args, **kwargs):
            mw = kwargs.get("max_workers")
            if mw is None and args:
                mw = args[0]
            constructed.append(int(mw or 0))
            super().__init__(*args, **kwargs)

    with patch.object(da, "get_provider", return_value=mock_p):
        with patch.object(da, "ThreadPoolExecutor", TrackingExecutor):
            out = da.get_quotes(["a", "b", "c"], max_workers=4)

    assert set(out) == {"a", "b", "c"}
    assert all(out[k].get("current_price") == 10.0 for k in out)
    assert constructed == [3]  # min(4, 8, len=3) → 3
    assert mock_p.fetch_quote.call_count == 3


def test_watch_uses_get_quote_not_light_data():
    """A1/M3: watch 现价段走 data_access.get_quote。"""
    src = (SCRIPTS / "pool_cmds" / "watch.py").read_text(encoding="utf-8")
    assert "from trader_shared.data_access import get_quote" in src
    assert "from trader_shared.light_data import" not in src
    assert "HttpClient()" not in src


def test_plan_view_refresh_has_no_light_data_direct():
    """A1: _refresh_pool_prices 路径无 light_data.fetch_quote / HttpClient 直调。"""
    src = (SCRIPTS / "pool_cmds" / "plan_view.py").read_text(encoding="utf-8")
    assert "from trader_shared.light_data import fetch_quote" not in src
    assert "HttpClient()" not in src
    assert "get_quotes" in src