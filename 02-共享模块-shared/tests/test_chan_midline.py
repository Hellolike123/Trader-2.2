"""中线缠论 vs 日线缠论双链路。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.chan_core import (  # noqa: E402
    chanlun_strategy,
    chanlun_strategy_midline,
    format_chanlun_theory_line,
)


def _bars(n: int, start: float = 100.0) -> list[dict]:
    out = []
    p = start
    for i in range(n):
        c = p * (1.012 if i % 3 else 0.988)
        out.append({
            "open": p,
            "high": max(p, c) * 1.015,
            "low": min(p, c) * 0.985,
            "close": c,
            "volume": 1000 + i * 10,
            "date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
        })
        p = c
    return out


class TestChanMidline:
    def test_prefers_weekly(self):
        w, d = _bars(40), _bars(80)
        r = chanlun_strategy_midline(w[-1]["close"], weekly_bars=w, daily_bars=d)
        assert r["chanlun"]["timeframe"] == "weekly"

    def test_daily_fallback(self):
        d = _bars(50)
        r = chanlun_strategy_midline(d[-1]["close"], weekly_bars=[], daily_bars=d)
        assert r["chanlun"]["timeframe"] == "daily_fallback"

    def test_insufficient(self):
        r = chanlun_strategy_midline(10.0, weekly_bars=[], daily_bars=_bars(5))
        assert r["chanlun"]["timeframe"] == "insufficient"

    def test_daily_strategy_tags_daily(self):
        d = _bars(50)
        r = chanlun_strategy(d[-1]["close"], d)
        assert r["chanlun"].get("timeframe") == "daily"

    def test_theory_line_format(self):
        w = _bars(40)
        r = chanlun_strategy_midline(w[-1]["close"], weekly_bars=w, daily_bars=[])
        line = format_chanlun_theory_line(r)
        assert "·" in line
        assert any(x in line for x in ("看涨", "看跌", "中性"))
