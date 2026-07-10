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
        assert "线段不足" not in line

    def test_theory_line_low_conf_annotation(self):
        """conf=low 时旁注段偏少，主名仍是趋势/盘整。"""
        line = format_chanlun_theory_line({
            "structure_type": "上涨趋势",
            "structure_confidence": "low",
            "trend_label": "拉升段",
            "buy_points": [],
            "sell_points": [],
            "divergence": {},
        })
        assert "上涨趋势(段偏少)" in line
        assert "线段不足" not in line

    def test_midline_structure_not_segment_insufficient(self):
        """周线中线结构主状态不应再是线段不足。"""
        w = _bars(60)
        r = chanlun_strategy_midline(w[-1]["close"], weekly_bars=w, daily_bars=[])
        chan = r["chanlun"]
        st = str(chan.get("structure_type") or "")
        assert not st.startswith("线段不足")
        if st:
            assert st in (
                "无结构", "盘整", "上涨趋势", "下跌趋势",
                "单边上涨", "单边下跌",
            ) or st == ""

    def test_daily_and_midline_timeframe_separated(self):
        """短线 daily 与中线 weekly 的 timeframe 字段分离。"""
        w, d = _bars(40), _bars(80)
        daily = chanlun_strategy(d[-1]["close"], d)
        mid = chanlun_strategy_midline(d[-1]["close"], weekly_bars=w, daily_bars=d)
        assert daily["chanlun"].get("timeframe") == "daily"
        assert mid["chanlun"].get("timeframe") == "weekly"
