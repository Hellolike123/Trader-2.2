"""combo_strategy 单元测试：共振矩阵 + 定论 + 合成买卖点。

离线确定性，无网络。覆盖：多源共振 / 冲突 / 单源 / 无框 / 无源 / 突破态 / 破止损。
"""
from __future__ import annotations

import pytest

from trader_shared.combo_strategy import synthesize_combo_verdict


# ── 原子模块输出构造器 ──
def _mistery(action: str, position_cap: float | None = None) -> dict:
    return {"action": action, "position_cap": position_cap}


def _box(state: str, *, found: bool = True, top: float = 100.0, bottom: float = 90.0,
         stop_loss: float = 87.0) -> dict:
    return {
        "found": found, "state": state if found else "none",
        "top": top, "bottom": bottom, "stop_loss": stop_loss if found else None,
    }


def _chan(buy: list = None, sell: list = None) -> dict:
    return {
        "buy_points": [{"type": t} for t in (buy or [])],
        "sell_points": [{"type": t} for t in (sell or [])],
    }


def _key(*, stop_sell: float = 85.0, buy_zone_low: float = 92.0,
        chase_ok: bool = False, swing_sell: float = 110.0) -> dict:
    return {
        "stop_sell": stop_sell, "buy_zone_low": buy_zone_low,
        "buy_ref": buy_zone_low, "chase_ok": chase_ok,
        "swing_sell": swing_sell, "short_sell_high": swing_sell,
    }


# ───────────────────────────────────────────────────────────────────────────
# 共振定论
# ───────────────────────────────────────────────────────────────────────────
def test_bull_resonance_buy():
    """四源全多 → buy / high。"""
    r = synthesize_combo_verdict(
        mistery=_mistery("持有", 30),
        box=_box("up_confirmed"),
        chan=_chan(buy=["一类买"]),
        key=_key(chase_ok=True),
        current=98.0,
    )
    assert r["verdict"] == "buy"
    assert r["bias"] == "bull"
    assert r["confidence"] == "high"
    assert r["agree_count"] == 4
    assert r["contributing"] == 4


def test_bear_resonance_sell():
    """四源全空 → sell / high。"""
    r = synthesize_combo_verdict(
        mistery=_mistery("减仓", 0),
        box=_box("down_confirmed"),
        chan=_chan(sell=["一类卖"]),
        key=_key(stop_sell=99.0),  # 现价 < stop → 空
        current=95.0,
    )
    assert r["verdict"] == "sell"
    assert r["bias"] == "bear"
    assert r["confidence"] == "high"


def test_conflict_hold():
    """两多两空（对称权重）→ net=0 → hold / neutral。"""
    r = synthesize_combo_verdict(
        mistery=_mistery("持有", 20),
        box=_box("up_confirmed"),
        chan=_chan(sell=["一类卖"]),
        key=_key(stop_sell=99.0),  # 空
        current=95.0,
        weights={"mistery": 0.25, "box": 0.25, "chan": 0.25, "key": 0.25},
    )
    # 对称权重下 +1,+1,-1,-1 → net=0 → hold / neutral
    assert r["verdict"] == "hold"
    assert r["bias"] == "neutral"
    assert r["score"] == 0.0


def test_single_source_bull_watch():
    """仅 520 多，其余中性 → watch / bull / low。"""
    r = synthesize_combo_verdict(
        mistery=_mistery("回踩低吸", 15),
        box=_box("inside"),
        chan=_chan(),  # 无买卖点
        key=_key(chase_ok=False),
        current=95.0,
    )
    assert r["bias"] == "bull"
    assert r["verdict"] in ("watch", "hold")
    assert r["confidence"] in ("low", "mid")


def test_no_box_fallback():
    """无箱体 → 仍由其余三源合成，不崩。"""
    r = synthesize_combo_verdict(
        mistery=_mistery("持有", 30),
        box=_box("none", found=False),
        chan=_chan(buy=["二类买"]),
        key=_key(chase_ok=True),
        current=98.0,
    )
    assert r["sources_present"]["box"] is False
    assert r["verdict"] == "buy"
    # 无框 → entry 回退关键价买点区
    assert r["entry"] == 92.0
    # 无框 → stop 回退关键价止损
    assert r["stop"] == 85.0


def test_no_sources_hold_neutral():
    """全空输入 → hold / neutral / low，不崩。"""
    r = synthesize_combo_verdict(current=100.0)
    assert r["verdict"] == "hold"
    assert r["bias"] == "neutral"
    assert r["confidence"] == "low"
    assert r["contributing"] == 0


def test_breakout_entry_is_current():
    """突破态 → entry 取现价（回踩加仓位=箱体上沿另行处理）。"""
    r = synthesize_combo_verdict(
        mistery=_mistery("轻仓试错", 15),
        box=_box("up_confirmed", top=100.0, bottom=90.0),
        chan=_chan(buy=["三类买"]),
        key=_key(chase_ok=True),
        current=102.0,
    )
    assert r["entry"] == 102.0
    assert r["take"] == 100.0  # 箱体上沿作目标


def test_box_inside_entry_bottom():
    """箱体内 → entry 取箱底低吸。"""
    r = synthesize_combo_verdict(
        mistery=_mistery("观望"),
        box=_box("inside", top=100.0, bottom=90.0, stop_loss=87.0),
        chan=_chan(),
        key=_key(),
        current=95.0,
    )
    assert r["entry"] == 90.0
    assert r["stop"] == 87.0
    assert r["take"] == 100.0


def test_position_cap_from_mistery():
    """仓位上限优先取 520 体系的 position_cap。"""
    r = synthesize_combo_verdict(
        mistery=_mistery("持有", 25),
        box=_box("up_confirmed"),
        chan=_chan(buy=["一类买"]),
        key=_key(chase_ok=True),
        current=98.0,
    )
    assert r["position_cap"] == 25.0


def test_matrix_dirs_and_weights():
    """矩阵方向/权重正确性。"""
    r = synthesize_combo_verdict(
        mistery=_mistery("持有", 30),
        box=_box("up_confirmed"),
        chan=_chan(buy=["一类买"]),
        key=_key(chase_ok=True),
        current=98.0,
    )
    by_name = {m["name"]: m for m in r["matrix"]}
    assert by_name["520体系"]["dir"] == 1
    assert by_name["箱体"]["dir"] == 1
    assert by_name["缠论买卖点"]["dir"] == 1
    assert by_name["关键价"]["dir"] == 1
    # 权重归一前合计 = 1.0
    assert abs(sum(m["weight"] for m in r["matrix"]) - 1.0) < 1e-9
