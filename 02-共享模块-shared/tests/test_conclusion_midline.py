"""中线看法 B1A / B3C 单测。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.conclusion_block import (  # noqa: E402
    build_conclusion_block,
    chanlun_midline_dir,
    midline_theory_dirs,
    wyckoff_midline_bias,
)
from trader_shared.mistery_gate import compute_mistery_gate  # noqa: E402
from trader_shared.key_prices import build_key_prices  # noqa: E402

_STAGE_RE = re.compile(r"蓄势|主升|派发|衰退")


def _kp_no_chase():
    return build_key_prices(
        current=58.7,
        support=55.0,
        stop=55.51,
        confirm=60.0,
        low_zone_lower=55.62,
        low_zone_upper=57.74,
        ma20=56.72,
    )


class TestMidlineTheoryDirs:
    def test_chan_bear_from_structure(self):
        chan = {"chanlun": {"structure_type": "盘整", "trend_label": "下跌", "divergence": {}}}
        assert chanlun_midline_dir(chan) == -1

    def test_chan_bull_uptrend(self):
        chan = {
            "chanlun": {
                "structure_type": "上涨趋势",
                "trend_label": "回调段",
                "buy_points": [{"type": "二类买"}],
                "divergence": {},
            }
        }
        assert chanlun_midline_dir(chan) == 1

    def test_wyck_strong_bear_priority(self):
        w = {"spring_signal": True, "upthrust_signal": True, "bc_signal": False, "sow_signal": False, "sos_signal": False}
        assert wyckoff_midline_bias(w) == "strong_bear"

    def test_wyck_strong_bull(self):
        w = {"spring_signal": True, "sos_signal": False, "upthrust_signal": False, "bc_signal": False, "sow_signal": False}
        assert wyckoff_midline_bias(w) == "strong_bull"

    def test_wyck_premature_spring_not_strong_bull(self):
        w = {
            "spring_signal": True,
            "spring_premature": True,
            "sos_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
        }
        assert wyckoff_midline_bias(w) == "neutral"

    def test_wyck_weak_spring_not_strong_bull(self):
        w = {
            "spring_signal": True,
            "spring_strength": "weak",
            "spring_vol_class": "low_vol_confirm",
            "sos_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
        }
        assert wyckoff_midline_bias(w) == "neutral"

    def test_wyck_insufficient_neutral(self):
        w = {"timeframe": "insufficient", "spring_signal": True, "sos_signal": True}
        assert wyckoff_midline_bias(w) == "neutral"


class TestMidlineViewB1A:
    def test_stage_does_not_drive_midline(self):
        """华工锚点：stage=蓄势偏强 + 周线盘整看跌 → 看法暂缓，非可跟踪。"""
        chan = {
            "chanlun": {
                "structure_type": "盘整",
                "structure_confidence": "low",
                "trend_label": "下跌",
                "divergence": {},
            }
        }
        wyck = {
            "spring_signal": False,
            "sos_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
        }
        kp = _kp_no_chase()
        gate = compute_mistery_gate({
            "major_stage": "蓄势偏强",
            "short_term_momentum": "震荡",
            "scene": "冲高减仓",
            "regime": "偏弱",
            "current": 58.7,
            "stop": 55.51,
            "support": 55.0,
            "confirm": 60.0,
            "buy_ref": kp.get("buy_ref"),
            "risk": kp.get("risk"),
            "reward_near": kp.get("reward_near"),
            "min_rr": 1.0,
        })
        c = build_conclusion_block(
            major_stage="蓄势偏强",
            scene="冲高减仓",
            theory_status="冲高减仓",
            regime="偏弱",
            mistery_gate=gate,
            key_prices=kp,
            fusion={"action": "减仓", "weighted_score": -0.2},
            chanlun_midline=chan,
            wyckoff_midline=wyck,
        )
        assert c["stage_line"] == "蓄势偏强"
        # P2：缠论 low 置信 → chanlun_midline_dir 返回 0（中性），不靠兜底翻转方向
        # 下跌 + low 置信 → 中线观察（非暂缓/偏空，因为低置信不驱动方向）
        assert "可跟踪" not in c["midline"]
        assert not _STAGE_RE.search(c["midline"])

    def test_bull_weekly_trackable(self):
        chan = {
            "chanlun": {
                "structure_type": "上涨趋势",
                "structure_confidence": "low",
                "trend_label": "回调段",
                "buy_points": [{"type": "二类买", "confidence": 2}],
                "divergence": {},
            }
        }
        wyck = {
            "spring_signal": False,
            "sos_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
        }
        c = build_conclusion_block(
            major_stage="蓄势",
            scene="防守观察",
            mistery_gate={"action": "观望", "hard_block": "none", "position_cap_pct": 0},
            key_prices=_kp_no_chase(),
            fusion={"action": "减仓", "weighted_score": -0.2},
            chanlun_midline=chan,
            wyckoff_midline=wyck,
        )
        assert "可跟踪" in c["midline"]
        assert not _STAGE_RE.search(c["midline"])
        assert c["stage_line"] == "蓄势"

    def test_fight_chan_bear_wyck_bull(self):
        chan = {"chanlun": {"structure_type": "盘整", "trend_label": "下跌", "divergence": {}}}
        wyck = {
            "spring_signal": True,
            "sos_signal": False,
            "upthrust_signal": False,
            "bc_signal": False,
            "sow_signal": False,
        }
        c = build_conclusion_block(
            major_stage="蓄势偏强",
            mistery_gate={"action": "观望", "hard_block": "none", "position_cap_pct": 0},
            key_prices=_kp_no_chase(),
            fusion={"weighted_score": 0},
            chanlun_midline=chan,
            wyckoff_midline=wyck,
        )
        assert "打架" in c["midline"]
        assert not _STAGE_RE.search(c["midline"])

    def test_strong_bear_first(self):
        """主升阶段 upthrust 视为正常洗盘，不判偏空（P2 设计）。
        要触发 strong_bear 需要 bc_signal 或 sow_signal，或 major_stage 非主升。"""
        chan = {
            "chanlun": {
                "structure_type": "上涨趋势",
                "buy_points": [{"type": "二类买"}],
                "divergence": {},
            }
        }
        wyck = {
            "upthrust_signal": True,
            "spring_signal": False,
            "bc_signal": False,
            "sow_signal": False,
            "sos_signal": False,
        }
        # 主升 + upthrust → 正常洗盘，不偏空
        c = build_conclusion_block(
            major_stage="主升",
            mistery_gate={"action": "观望", "hard_block": "none", "position_cap_pct": 0},
            key_prices=_kp_no_chase(),
            fusion={},
            chanlun_midline=chan,
            wyckoff_midline=wyck,
        )
        # 主升阶段 upthrust 不判 strong_bear，chan 上涨 → 可跟踪
        assert "可跟踪" in c["midline"]
        assert not _STAGE_RE.search(c["midline"])

        # 非主升阶段 upthrust → strong_bear
        c2 = build_conclusion_block(
            major_stage="蓄势",
            mistery_gate={"action": "观望", "hard_block": "none", "position_cap_pct": 0},
            key_prices=_kp_no_chase(),
            fusion={},
            chanlun_midline=chan,
            wyckoff_midline=wyck,
        )
        assert "慎跟" in c2["midline"] or "偏空" in c2["midline"]

    def test_conflict_track_vs_no_chase(self):
        chan = {
            "chanlun": {
                "structure_type": "上涨趋势",
                "buy_points": [{"type": "二类买"}],
                "divergence": {},
            }
        }
        c = build_conclusion_block(
            major_stage="蓄势",
            scene="冲高减仓",
            mistery_gate={"action": "观望", "hard_block": "none", "position_cap_pct": 0},
            key_prices=_kp_no_chase(),
            fusion={"action": "减仓", "weighted_score": -0.2},
            chanlun_midline=chan,
            wyckoff_midline={},
        )
        assert "可跟踪" in c["midline"]
        assert "中线还能看" in c["conflict"]

    def test_execution_not_from_pretty_target_alone(self):
        """R9：gate 观望时出手仍不买，与中线目标无关。"""
        c = build_conclusion_block(
            major_stage="蓄势",
            mistery_gate={"action": "观望", "hard_block": "none", "position_cap_pct": 0},
            key_prices=_kp_no_chase(),
            fusion={"weighted_score": 0.5, "action": "加仓"},
            chanlun_midline={
                "chanlun": {
                    "structure_type": "上涨趋势",
                    "buy_points": [{"type": "一类买"}],
                    "divergence": {},
                }
            },
            wyckoff_midline={},
        )
        assert "不买" in c["execution"] or "不追" in c["execution"] or "观望" in c["execution"]

    def test_conflict_paifa_vs_chan_bull(self):
        """验收3：派发 + 缠论偏多 → 冲突双写 + 不新开。"""
        c = build_conclusion_block(
            major_stage="派发",
            scene="冲高减仓",
            mistery_gate={
                "action": "观望",
                "hard_block": "H3",
                "notes": "派发不加仓",
                "position_cap_pct": 0,
            },
            key_prices=_kp_no_chase(),
            fusion={"weighted_score": -0.1, "action": "减仓"},
            chanlun_midline={
                "chanlun": {
                    "structure_type": "上涨趋势",
                    "buy_points": [{"type": "一类买"}],
                    "divergence": {},
                }
            },
            wyckoff_midline={},
        )
        assert "可跟踪" in c["midline"] or "偏多" in c["midline"]
        assert "派发" in c["conflict"]
        assert "风控" in c["conflict"] or "不新开" in c["conflict"]
        assert "不买" in c["execution"] or "不追" in c["execution"] or "不新开" in c["execution"]
