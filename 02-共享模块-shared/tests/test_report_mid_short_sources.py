"""报告中线/短线字段源隔离（R3–R5 + E2 周/日价交叉 mock）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.conclusion_block import build_conclusion_block  # noqa: E402
from trader_shared.key_prices import build_key_prices  # noqa: E402
from trader_shared.mid_key_prices import build_mid_key_prices  # noqa: E402
from trader_shared.mistery_gate import compute_mistery_gate  # noqa: E402
from trader_shared.report_core import render_short_midline  # noqa: E402
from trader_shared.schema.v1 import validate_trader  # noqa: E402


def _weekly_bars(n: int = 40, base: float = 50.0) -> list[dict]:
    out = []
    p = base
    for i in range(n):
        if i % 7 == 3:
            c = p * 0.96
        elif i % 5 == 0:
            c = p * 1.03
        else:
            c = p * (1.005 if i % 2 == 0 else 0.998)
        out.append({
            "date": f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
            "open": c,
            "high": c * 1.02,
            "low": c * 0.98,
            "close": c,
            "volume": 1000 + i,
        })
        p = c
    return out


# 周线结构：life=48.0（刻意与日线 mid_support=40.0 不同）
_CHAN_MID = {
    "chanlun": {
        "structure_type": "盘整",
        "structure_confidence": "low",
        "trend_label": "下跌",
        "divergence": {},
        "timeframe": "weekly",
        "strokes": [
            {"direction": "up", "end_price": 55.0},
            {"direction": "down", "end_price": 48.0},
            {"direction": "up", "end_price": 62.0},
            {"direction": "down", "end_price": 52.5},
        ],
        "segments": [
            {"direction": "up", "high": 55.0, "low": 40.0},
            {"direction": "down", "high": 55.0, "low": 48.0},
            {"direction": "up", "high": 62.0, "low": 48.0},
        ],
        "zones": [
            {"valid": True, "zh_bottom": 51.0, "zh_top": 58.0, "zh_center": 54.5},
        ],
    }
}

# 日线 key_levels：mid_support=40.0 与周 life=48 故意相反
_DAILY_KL = {
    "short_support": 44.0,
    "mid_support": 40.0,
    "long_support": 35.0,
    "short_resist": 49.5,
    "mid_resist": 51.0,
    "long_resist": 55.0,
}


def _report() -> dict:
    kp = build_key_prices(
        current=48.5,
        support=45.0,
        stop=44.0,
        confirm=49.0,
        resistance=50.0,
        ma20=46.0,
        low_zone_lower=44.9,
        low_zone_upper=45.2,
        key_levels=_DAILY_KL,
    )
    # 中线：周引擎；即使传入日线 key_levels 也必须被忽略
    mk = build_mid_key_prices(
        current=48.5,
        weekly_bars=_weekly_bars(40),
        chanlun_midline=_CHAN_MID,
        key_levels=_DAILY_KL,
        ma20=46.0,
        stop=44.0,
    )
    gate = compute_mistery_gate({
        "major_stage": "蓄势偏强",
        "short_term_momentum": "震荡",
        "scene": "冲高减仓",
        "theory_status": "冲高减仓",
        "regime": "偏弱",
        "current": 48.5,
        "support": 45.0,
        "stop": 44.0,
        "confirm": 49.0,
        "buy_ref": kp["buy_ref"],
        "risk": kp["risk"],
        "reward_near": kp["reward_near"],
        "min_rr": 1.0,
        "turnover_rate": 4.0,
        "volume_ratio": 1.2,
        "change_pct": 2.0,
    })
    chan_mid = _CHAN_MID
    wyck_mid = {
        "spring_signal": False,
        "sos_signal": False,
        "upthrust_signal": False,
        "bc_signal": False,
        "sow_signal": False,
        "wyckoff_summary": "WEEK_ONLY_WYCK",
        "phase": "none",
    }
    conclusion = build_conclusion_block(
        major_stage="蓄势偏强",
        short_term_momentum="震荡",
        scene="冲高减仓",
        theory_status="冲高减仓",
        regime="偏弱",
        mistery_gate=gate,
        key_prices=kp,
        fusion={
            "action": "减仓",
            "weighted_score": -0.15,
            "signals_detail": {
                "chan": {"direction": -1, "reason": "DAY_ONLY_顶背驰"},
                "momentum": {"direction": 0, "reason": "DAY_ONLY_震荡"},
                "wyckoff": {"direction": -1, "reason": "DAY_ONLY_无"},
            },
        },
        has_position=False,
        chanlun_midline=chan_mid,
        wyckoff_midline=wyck_mid,
    )
    return {
        "name": "华工科技",
        "symbol": "000988.SZ",
        "current": 48.5,
        "change_pct": 2.0,
        "major_stage": "蓄势偏强",
        "short_term_momentum": "震荡",
        "market_env": {"level": "偏弱"},
        "ma_raw": {"ma5": 47.0, "ma20": 46.0, "ma250": 40.0},
        "support": 45.0,
        "stop": 44.0,
        "confirm": 49.0,
        "resistance": 50.0,
        "key_prices": kp,
        "mid_key_prices": mk,
        "mistery_gate": gate,
        "conclusion": conclusion,
        "daily_ruling": conclusion["daily_ruling"],
        "chanlun_midline": chan_mid,
        "wyckoff_midline": wyck_mid,
        "wyckoff": {"wyckoff_summary": "DAY_ONLY_WYCK"},
        "fusion": {
            "action": "减仓",
            "weighted_score": -0.15,
            "signals_detail": {
                "chan": {"direction": -1, "reason": "DAY_ONLY_顶背驰"},
                "momentum": {"direction": 0, "reason": "DAY_ONLY_震荡"},
                "wyckoff": {"direction": -1, "reason": "DAY_ONLY_无"},
            },
        },
        "has_position": False,
        "pool_count": 3,
        "pool_cap": 10,
        "t0_ref": {"low_buy": 45.0, "high_sell": 50.0},
        "key_levels": _DAILY_KL,
    }


class TestRenderDualTrack:
    def test_layout_b3c_b2a(self):
        r = _report()
        md = render_short_midline(r)
        assert "🧭 中线" in md
        assert "⚡ 短线" in md
        assert "阶段：蓄势偏强" in md
        # 看法已并入「阶段：… · 偏多/偏空」；短线仍可单独有看法行
        assert "中线：蓄势" not in md
        assert "🎯 结论" not in md
        assert "🗳️ 短线专家" not in md
        assert "🗺 空间参考" not in md
        mid_block = md.split("⚡ 短线")[0]
        short_block = md.split("⚡ 短线")[1]
        # 🌟 现价只允许出现在短线关键价（中线禁止）
        assert "🌟" not in mid_block
        assert "🌟" in short_block
        assert "关键价（中线）" in md
        assert "关键价（短线）" in md
        assert "生命线" in md
        assert "动作：" in md or "出手" in md
        assert "低吸区" in md or "买点区" in md
        assert "止损" in md
        inv = str((r.get("mistery_gate") or {}).get("invalidation") or "")
        if inv.strip():
            assert "失效：" in md
        assert "Mistery" not in md
        assert "mi姐" not in md
        assert "mistery" not in md
        errors = validate_trader(md)
        assert errors == [], errors

    def test_short_experts_day_only(self):
        md = render_short_midline(_report())
        short_block = md.split("⚡ 短线")[1]
        assert "DAY_ONLY_顶背驰" in short_block
        assert "DAY_ONLY_震荡" in short_block

    def test_midline_view_not_stage_words(self):
        md = render_short_midline(_report())
        for line in md.splitlines():
            if line.strip().startswith("看法："):
                assert "蓄势" not in line
                assert "主升" not in line
                break

    def test_no_markdown(self):
        md = render_short_midline(_report())
        assert "**" not in md
        assert "---" not in md


class TestMidShortPriceIsolation:
    """E2：日线 key_levels 与周线结果刻意相反 → 中线价 = 周线。"""

    def test_mid_life_from_weekly_not_daily_mid_support(self):
        r = _report()
        mk = r["mid_key_prices"]
        assert mk["engine"] == "weekly_v1"
        assert mk["source"] == "weekly_structure"
        assert mk["life_line"] == pytest.approx(48.0)
        # 日线 mid_support=40 不得出现在中线 life
        assert mk["life_line"] != pytest.approx(40.0)
        assert "daily_key_levels_proxy" not in mk["notes"]

        md = render_short_midline(r)
        mid_block = md.split("⚡ 短线")[0]
        assert "48.00" in mid_block or "生命线 48" in mid_block
        # 日线 mid_support 40 不应出现在中线关键价
        assert "生命线 40" not in mid_block

    def test_short_key_prices_unchanged_by_weekly_mid(self):
        """E5：短线 key_prices 数值不被中线改动破坏。"""
        r = _report()
        kp = r["key_prices"]
        assert kp["stop_sell"] == pytest.approx(44.0)
        assert kp["space_mid"] == pytest.approx(40.0)  # 短线仍可读日线 mid_support

    def test_data_status_warning_after_title(self):
        r = _report()
        r["data_status"] = "partial"
        r["missing_sources"] = ["weekly_bars", "bars_5m"]
        md = render_short_midline(r)
        head = md.split("现价")[0]
        assert "⚠️ 数据不完整" in head
        assert "weekly_bars" in head
        assert head.index("分析报告") < head.index("数据不完整")

    def test_data_status_full_no_warning(self):
        r = _report()
        r["data_status"] = "full"
        md = render_short_midline(r)
        assert "⚠️ 数据不完整" not in md
