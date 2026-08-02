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
    format_chanlun_short_light,
    format_chanlun_theory_line,
)
from trader_shared import chan_core  # noqa: E402
from trader_shared.config import CHANLUN_MIN_BARS  # noqa: E402


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

    def test_cd1a_daily_insufficient_is_explicit_in_analysis_and_display(self):
        """C-D1a：日线不足须 fail closed，不能显示成正常中性无买卖点。"""
        d = _bars(CHANLUN_MIN_BARS - 1)
        r = chanlun_strategy(d[-1]["close"], d)
        chan = r["chanlun"]

        assert chan["timeframe"] == "insufficient"
        assert chan["data_ok"] is False
        assert chan["data_bars_daily"] == CHANLUN_MIN_BARS - 1
        assert "日线不足" in chan["data_note"]

        line = format_chanlun_short_light(r)
        assert "日线不足" in line
        assert "暂无买卖点 · 中性" not in line

    def test_cd1b_empty_daily_bars_reports_fetch_failure_honestly(self):
        """C-D1b：空 bars 明示日线为空，不能伪装成正常结构。"""
        r = chanlun_strategy(10.0, [])
        chan = r["chanlun"]

        assert chan["timeframe"] == "insufficient"
        assert chan["data_ok"] is False
        assert chan["data_bars_daily"] == 0
        assert "日线数据为空" in chan["data_note"]
        assert "数据为空" in format_chanlun_short_light(r)

    def test_cd1b_analysis_failure_is_not_rendered_as_neutral(self, monkeypatch):
        """C-D1b：分析异常须保留失败原因，不得降成“暂无买卖点”。"""
        def _fail(*args, **kwargs):
            raise RuntimeError("夹具损坏")

        monkeypatch.setattr(chan_core, "chanlun_analysis", _fail)
        daily = _bars(CHANLUN_MIN_BARS)
        r = chanlun_strategy(daily[-1]["close"], daily)
        chan = r["chanlun"]

        assert chan["timeframe"] == "insufficient"
        assert chan["data_ok"] is False
        assert "分析失败" in chan["data_note"]
        assert "夹具损坏" in chan["data_note"]
        assert "暂无买卖点" not in format_chanlun_short_light(r)

    def test_cd1c_data_counts_and_adjust_mode_are_auditable(self):
        """C-D1c：透出日周根数；复权不一致时不得假称 qfq 已统一。"""
        daily = [{**bar, "adjust": "qfq"} for bar in _bars(50)]
        weekly_qfq = [{**bar, "adjust": "qfq"} for bar in _bars(30)]
        same = chanlun_strategy_midline(
            daily[-1]["close"], weekly_bars=weekly_qfq, daily_bars=daily
        )["chanlun"]

        assert same["data_bars_daily"] == 50
        assert same["data_bars_weekly"] == 30
        assert same["adjust_mode"] == "qfq"
        assert same["data_ok"] is True

        weekly_raw = [{**bar, "adjust": "none"} for bar in _bars(30)]
        mixed = chanlun_strategy_midline(
            daily[-1]["close"], weekly_bars=weekly_raw, daily_bars=daily
        )["chanlun"]
        assert mixed["adjust_mode"] == "mixed"

    def test_theory_line_format(self):
        w = _bars(40)
        r = chanlun_strategy_midline(w[-1]["close"], weekly_bars=w, daily_bars=[])
        line = format_chanlun_theory_line(r)
        assert "·" in line
        assert any(x in line for x in ("看涨", "看跌", "中性", "先观望"))
        assert "线段不足" not in line
        assert "无法判断" not in line

    def test_theory_line_low_conf_annotation(self):
        """conf=low 时旁注段偏少，主名仍是趋势/盘整。"""
        # 笔级够、段未齐时不应显示「笔数不足」/「线段不足」
        from trader_shared.conclusion_block import _build_wave_label
        wave = _build_wave_label({
            "chanlun": {
                "segments": [],
                "strokes": [{"direction": "up"}, {"direction": "down"}, {"direction": "up"}],
                "trend_label": "拉升段",
                "structure_type": "上涨趋势",
                "buy_points": [],
                "sell_points": [],
                "divergence": {},
            }
        }, 10.0)
        assert "笔数不足" not in wave
        assert "线段不足" not in wave
        assert "拉升" in wave or "上涨" in wave

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

    def test_wave_label_never_says_segment_insufficient(self):
        """有笔但段未齐：用结构/待确认 + 线段未成型，禁止「线段不足」。"""
        from trader_shared.conclusion_block import _build_wave_label

        # 有结构、无 trend_label → 应出结构主名，不吓人
        wave_struct = _build_wave_label({
            "chanlun": {
                "segments": [],
                "strokes": [{"direction": "up"}, {"direction": "down"}, {"direction": "up"}],
                "trend_label": "",
                "structure_type": "盘整",
                "buy_points": [],
                "sell_points": [],
                "divergence": {},
            }
        }, 10.0)
        assert wave_struct == "盘整 · 线段未成型"
        assert "线段不足" not in wave_struct

        # 无结构、trend 不可用 → 先观望（可执行），禁止「无法判断/线段不足」
        wave_thin = _build_wave_label({
            "chanlun": {
                "segments": [],
                "strokes": [{"direction": "up"}, {"direction": "down"}, {"direction": "up"}],
                "trend_label": "数据不足",
                "structure_type": "无结构",
                "buy_points": [],
                "sell_points": [],
                "divergence": {},
            }
        }, 10.0)
        assert wave_thin == "中枢未成型 · 先观望"
        assert "线段不足" not in wave_thin
        assert "无法判断" not in wave_thin

        # 笔不足 → 先观望，不写无法判断
        wave_no_stroke = _build_wave_label({
            "chanlun": {
                "segments": [],
                "strokes": [{"direction": "up"}],
                "trend_label": "",
                "structure_type": "",
                "buy_points": [],
                "sell_points": [],
                "divergence": {},
            }
        }, 10.0)
        assert wave_no_stroke == "笔数不足 · 先观望"
        assert "无法判断" not in wave_no_stroke

        # 历史缓存 structure_type=线段不足* → 不当主名，改中枢未成型·先观望
        wave_legacy = _build_wave_label({
            "chanlun": {
                "segments": [{"direction": "up"}],
                "strokes": [{"direction": "up"}, {"direction": "down"}, {"direction": "up"}],
                "trend_label": "",
                "structure_type": "线段不足5/11",
                "buy_points": [],
                "sell_points": [],
                "divergence": {},
            }
        }, 10.0)
        assert "线段不足" not in wave_legacy
        assert "先观望" in wave_legacy
        assert "无法判断" not in wave_legacy

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
