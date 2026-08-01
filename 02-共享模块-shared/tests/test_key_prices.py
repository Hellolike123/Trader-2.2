"""关键价 + 两句亏赚单测。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.key_prices import build_key_prices  # noqa: E402
from trader_shared.mid_key_prices import build_mid_key_prices  # noqa: E402
from trader_shared.report_core import render_short_midline  # noqa: E402
from trader_shared.schema.v1 import validate_trader  # noqa: E402
from trader_shared.conclusion_block import build_conclusion_block  # noqa: E402
from trader_shared.mistery_gate import compute_mistery_gate  # noqa: E402


class TestKeyPricesBasics:
    def test_buy_ref_is_midpoint(self):
        kp = build_key_prices(
            current=12.0,
            support=10.0,
            stop=9.5,
            confirm=13.0,
            resistance=13.5,
            ma20=12.8,
            low_zone_lower=10.0,
            low_zone_upper=10.2,
            key_levels={"short_resist": 13.2, "long_resist": 14.0},
        )
        assert kp["buy_ref"] == pytest.approx(10.1)
        assert kp["stop_sell"] == 9.5
        assert kp["buy_zone_low"] == 10.0
        assert kp["buy_zone_high"] == 10.2
        assert kp["risk"] is not None and abs(kp["risk"] - 0.6) < 0.05
        # 卖点必须在现价上方
        assert kp["short_sell_high"] is not None and kp["short_sell_high"] > 12.0
        assert "买" in kp["line_buy"]
        assert "追" in kp["line_chase"]
        assert "2.1R" not in kp["line_buy"]
        assert "不足 1R" not in kp["line_chase"]

    def test_support_fallback_zone(self):
        kp = build_key_prices(current=20, support=18, stop=17.5, confirm=21)
        assert kp["buy_zone_low"] is not None and kp["buy_zone_low"] <= 18.5
        assert kp["buy_ref"] is not None
        assert kp["stop_sell"] == 17.5
        assert kp["short_sell_low"] is not None and kp["short_sell_low"] > 20

    def test_chase_not_ok_when_reward_leq_risk(self):
        # 现价高、近端卖点近 → 不追
        kp = build_key_prices(
            current=12.5,
            support=10.0,
            stop=9.5,
            confirm=12.8,
            low_zone_lower=10.0,
            low_zone_upper=10.2,
            ma20=12.7,
        )
        assert kp["chase_ok"] is False
        assert "不追" in kp["line_chase"]

    def test_buy_zone_not_above_current(self):
        # low_zone 在现价上方时，应改用下方支撑带
        kp = build_key_prices(
            current=100,
            support=95,
            stop=93,
            confirm=108,
            ma20=105,
            low_zone_lower=102,
            low_zone_upper=106,
            key_levels={"short_resist": 110, "mid_support": 90, "short_support": 94, "long_support": 80},
        )
        assert kp["buy_zone_high"] is not None and kp["buy_zone_high"] <= 100
        assert kp["short_sell_low"] is not None and kp["short_sell_low"] > 100
        assert kp["space_mid"] == 90

    def test_always_outputs_lines_without_position_param(self):
        # 无 has_position 参数 —— 买卖点始终有
        kp = build_key_prices(current=10, support=9, stop=8.5, confirm=11)
        assert kp["line_buy"]
        assert kp["line_chase"]
        assert kp["stop_sell"] == 8.5


class TestRenderShortMidline:
    def _sample_report(self) -> dict:
        kp = build_key_prices(
            current=48.5,
            support=45.0,
            stop=44.0,
            confirm=49.0,
            resistance=50.0,
            ma20=46.0,
            low_zone_lower=44.9,
            low_zone_upper=45.2,
            key_levels={"short_resist": 49.5, "mid_resist": 51.0, "long_resist": 55.0},
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
        chan_mid = {
            "chanlun": {
                "structure_type": "盘整",
                "trend_label": "下跌",
                "divergence": {},
                "timeframe": "weekly",
            }
        }
        wyck_mid = {
            "spring_signal": False,
            "sos_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
        }
        conclusion = build_conclusion_block(
            major_stage="蓄势偏强",
            short_term_momentum="震荡",
            scene="冲高减仓",
            theory_status="冲高减仓",
            regime="偏弱",
            mistery_gate=gate,
            key_prices=kp,
            fusion={"action": "减仓", "weighted_score": -0.15, "signals_detail": {
                "chan": {"direction": -1, "reason": "顶背驰"},
                "momentum": {"direction": 0, "reason": "震荡"},
                "wyckoff": {"direction": -1, "reason": "无"},
            }},
            has_position=False,
            chanlun_midline=chan_mid,
            wyckoff_midline=wyck_mid,
        )
        _weekly = []
        _wp = 45.0
        for _i in range(40):
            _c = _wp * (1.01 if _i % 3 else 0.99)
            _weekly.append({
                "open": _c, "high": _c * 1.02, "low": _c * 0.98,
                "close": _c, "volume": 1000, "date": f"2024-01-{(_i % 28)+1:02d}",
            })
            _wp = _c
        mk = build_mid_key_prices(
            current=48.5,
            weekly_bars=_weekly,
            chanlun_midline={
                "chanlun": {
                    "timeframe": "weekly",
                    "strokes": [
                        {"direction": "up", "end_price": 55.0},
                        {"direction": "down", "end_price": 48.0},
                        {"direction": "up", "end_price": 62.0},
                    ],
                    "segments": [
                        {"direction": "up", "high": 62.0, "low": 48.0},
                    ],
                    "zones": [],
                }
            },
            # 日线参数默认忽略
            key_levels={
                "short_support": 44.0,
                "mid_support": 40.0,
                "mid_resist": 51.0,
                "long_resist": 55.0,
            },
            ma20=46.0,
            stop=44.0,
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
            "fusion": {
                "action": "减仓",
                "weighted_score": -0.15,
                "signals_detail": {
                    "chan": {"direction": -1, "reason": "顶背驰"},
                    "momentum": {"direction": 0, "reason": "震荡"},
                    "wyckoff": {"direction": -1, "reason": "无"},
                },
            },
            "has_position": False,
            "pool_count": 3,
            "pool_cap": 10,
            "t0_ref": {"low_buy": 45.0, "high_sell": 50.0},
        }

    def test_template_keywords(self):
        md = render_short_midline(self._sample_report())
        assert "｜短中线" in md
        assert "🧭 中线" in md
        assert "⚡ 短线" in md
        # 面板「阶段：」= 周线威科夫短词（不足→无阶段）；禁止日线 major_stage=蓄势偏强 冒充
        assert "阶段：无阶段" in md
        assert "阶段：蓄势偏强" not in md
        assert "阶段：无阶段 ·" in md  # 定论偏多/偏空附在阶段行
        assert "中线：蓄势" not in md
        assert "🎯 结论" not in md
        assert "威科夫" in md
        assert "缠论" in md
        # A 版短线：动作（不再用「出手」）
        assert "动作：" in md
        assert "出手：" not in md
        assert "缠论：" in md
        assert "日线三专家" not in md
        assert "🗳️ 短线专家" not in md
        assert "关键价（中线）" in md
        assert "关键价（短线）" in md
        assert "止损" in md
        assert "买" in md
        assert "🗺 空间参考" not in md
        assert "2.1R" not in md
        assert "不足 1R" not in md
        assert "本周：" not in md or "📌 本周只做" in md
        assert md.count("本周只做") <= 1
        # 纪律展示：有 invalidation 则出失效；禁止 mi 品牌
        inv = str((self._sample_report().get("mistery_gate") or {}).get("invalidation") or "")
        if inv.strip():
            assert "破位看：" in md or "失效：" in md
        assert "Mistery" not in md
        assert "mi姐" not in md
        assert "mistery" not in md
        for line in md.splitlines():
            if line.strip().startswith("动作："):
                assert line.strip() != "动作：减仓"
                # 不新开 / 等站稳 / 试探 等均可
                assert any(
                    k in line
                    for k in ("不新开", "不追", "不买", "观望", "等站稳", "等确认", "仓 ", "试探")
                )
        # 关键价区：报告用「低吸区/止盈区」表述（原「买点区」已改名）
        assert "低吸区" in md or "止盈区" in md or "买点区" in md
        assert "无底仓" in md or "T0：" in md
        # render_short_midline 是短中线子区块，无完整报告顶部「MA20/MA250」摘要；
        # validate_trader 为完整报告设计，此处仅校验与本子区块相关的规则
        _top_ma_err = "top summary must include MA20 / MA250"
        errors = [e for e in validate_trader(md) if e != _top_ma_err]
        assert errors == [], errors

    def test_no_markdown_syntax(self):
        md = render_short_midline(self._sample_report())
        assert "**" not in md
        assert "---" not in md
        assert not any(l.startswith("#") for l in md.splitlines())
        assert not any(l.startswith("|") for l in md.splitlines() if l.strip())
