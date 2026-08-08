"""D4 / #1 语义回归：fusion 决策路径的确定性快照场景。

设计目标
--------
#1 修复（动量席 insufficient 重归一化）只影响「动量数据不足」的决策路径。
本模块用**合成三卡**直接喂 `merge_decisions(analysis_cards=...)`，零网络、全确定，
覆盖矩阵：动量 insufficient / 真中性 / 多空 / 分歧 / 偏弱 regime。

指纹（fingerprint）抓取 fusion 决策的关键输出，供改前/改后 diff 与回归断言：
  weighted_score, raw_weighted_score, action, confidence, disagreement,
  signals_detail(chan/momentum/vpf 的 direction/confidence), weights_used(chan/momentum/vpf)

用法
----
  from tests.fusion_regression_helpers import SCENARIOS, run_scenario
  fp = run_scenario(SCENARIOS[0])
"""
from __future__ import annotations

from typing import Any

from trader_shared.fusion_core import merge_decisions


def make_bars(n: int = 30, price: float = 10.0) -> list[dict]:
    """最小合法 bars（仅供 pos_pct 计算，不触发网络）。"""
    bars = []
    for i in range(n):
        bars.append({
            "open": price, "high": price + 1.0, "low": price - 1.0,
            "close": price, "volume": 1000, "amount": 1_000_000.0,
        })
    return bars


def _chan_card(direction: int, type_raw: str = "", conf_hint: float | None = None) -> dict:
    c = {
        "direction": direction,
        "raw_available": True,
        "summary_line": "",
        "note": "",
        "point_confidence": None,
        "nesting_confirmed": None,
        "lower_confirmed": None,
        "same_level": None,
    }
    if type_raw:
        c["type_raw"] = type_raw
    if conf_hint is not None:
        c["confidence"] = conf_hint
    return c


def _mom_card(direction: int, score: float | None, confidence: float = 0.0,
              reason: str = "动量中性") -> dict:
    # 注意：卡路径 momentum_card_to_fusion_signal 经 _as_dir() 读方向，须传整数
    # （对齐 build_momentum_card 真实产出）；字符串方向会被抹成 0。
    return {
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "reason": reason,
        "strength": "insufficient" if direction == 0 and reason == "动量数据不足" else "",
        "raw_available": True,
    }


def _vpf_card(direction: int, confidence: float, reason: str = "价量资金") -> dict:
    return {
        "direction": direction,
        "confidence": confidence,
        "reason": reason,
        "raw_available": True,
        "fund_quality": "ok",
        "vp_direction": direction,
        "fund_direction": 0,
        "warning_type": "",
    }


def _mom_result(direction: str, score: float | None) -> dict:
    return {"momentum": {"direction": direction, "score": score}}


# ── 场景矩阵 ────────────────────────────────────────────────────────────────
# changed_by_fix=True 标记「动量 insufficient」场景——#1 修复后应改变其指纹。
SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "all_bullish",
        "regime": "正常", "current_price": 10.0,
        "cards": {
            "chan": _chan_card(1, "二类买"),
            "momentum": _mom_card(1, 80, 0.85, "RSI超买"),
            "vpf": _vpf_card(1, 0.6, "放量上攻"),
        },
        "momentum_result": _mom_result("bullish", 80),
        "changed_by_fix": False,
    },
    {
        "name": "all_bearish",
        "regime": "正常", "current_price": 10.0,
        "cards": {
            "chan": _chan_card(-1, "二类卖"),
            "momentum": _mom_card(-1, 20, 0.85, "RSI超卖"),
            "vpf": _vpf_card(-1, 0.6, "放量下跌"),
        },
        "momentum_result": _mom_result("bearish", 20),
        "changed_by_fix": False,
    },
    {
        # ★ #1 核心：动量数据不足 + 缠多 + 价量多 → 应让 chan/vpf 主导
        "name": "mom_insufficient_chan_vpf_bull",
        "regime": "正常", "current_price": 10.0,
        "cards": {
            "chan": _chan_card(1, "二类买"),
            "momentum": _mom_card(0, None, 0.0, "动量数据不足"),
            "vpf": _vpf_card(1, 0.6, "放量上攻"),
        },
        "momentum_result": _mom_result("insufficient", None),
        "changed_by_fix": True,
    },
    {
        # ★ #1：动量数据不足 + 缠空 + 价量空
        "name": "mom_insufficient_chan_vpf_bear",
        "regime": "正常", "current_price": 10.0,
        "cards": {
            "chan": _chan_card(-1, "二类卖"),
            "momentum": _mom_card(0, None, 0.0, "动量数据不足"),
            "vpf": _vpf_card(-1, 0.6, "放量下跌"),
        },
        "momentum_result": _mom_result("insufficient", None),
        "changed_by_fix": True,
    },
    {
        # ★ #1：动量数据不足 + 缠多 + 价量中性（弱多）
        "name": "mom_insufficient_chan_bull_vpf_neutral",
        "regime": "正常", "current_price": 10.0,
        "cards": {
            "chan": _chan_card(1, "二类买"),
            "momentum": _mom_card(0, None, 0.0, "动量数据不足"),
            "vpf": _vpf_card(0, 0.3, "量价中性"),
        },
        "momentum_result": _mom_result("insufficient", None),
        "changed_by_fix": True,
    },
    {
        # ★ #1：动量数据不足，但 chan 空 / vpf 多 → 真实分歧应保留（不强行偏多）
        "name": "mom_insufficient_chan_bear_vpf_bull",
        "regime": "正常", "current_price": 10.0,
        "cards": {
            "chan": _chan_card(-1, "二类卖"),
            "momentum": _mom_card(0, None, 0.0, "动量数据不足"),
            "vpf": _vpf_card(1, 0.6, "放量上攻"),
        },
        "momentum_result": _mom_result("insufficient", None),
        "changed_by_fix": True,
    },
    {
        # 动量真中性（score=50）：#1 修复后**不应**重归一化，指纹须不变
        "name": "mom_real_neutral_chan_bull",
        "regime": "正常", "current_price": 10.0,
        "cards": {
            "chan": _chan_card(1, "二类买"),
            "momentum": _mom_card(0, 50, 0.25, "动量中性"),
            "vpf": _vpf_card(1, 0.6, "放量上攻"),
        },
        "momentum_result": _mom_result("neutral", 50),
        "changed_by_fix": False,
    },
    {
        # ★ #1：动量数据不足 + 偏弱 regime（正阈值右移）
        "name": "mom_insufficient_weak_regime",
        "regime": "偏弱", "current_price": 10.0,
        "cards": {
            "chan": _chan_card(1, "二类买"),
            "momentum": _mom_card(0, None, 0.0, "动量数据不足"),
            "vpf": _vpf_card(1, 0.6, "放量上攻"),
        },
        "momentum_result": _mom_result("insufficient", None),
        "changed_by_fix": True,
    },
    {
        # 三席全中性（参考基准）
        "name": "all_neutral",
        "regime": "正常", "current_price": 10.0,
        "cards": {
            "chan": _chan_card(0),
            "momentum": _mom_card(0, 50, 0.25, "动量中性"),
            "vpf": _vpf_card(0, 0.3, "量价中性"),
        },
        "momentum_result": _mom_result("neutral", 50),
        "changed_by_fix": False,
    },
]


def run_scenario(scn: dict[str, Any]) -> dict[str, Any]:
    """跑单个场景，返回 fusion 决策指纹。"""
    result = merge_decisions(
        chan_result={},
        momentum_result=scn["momentum_result"],
        regime=scn.get("regime", "正常"),
        current_price=scn.get("current_price", 10.0),
        bars=make_bars(),
        analysis_cards=scn["cards"],
        fusion_from_cards="cards",
    )
    sig = result.get("signals_detail", {}) or {}
    chan_s = sig.get("chan", {}) or {}
    mom_s = sig.get("momentum", {}) or {}
    vpf_s = sig.get("vpf", {}) or {}
    wu = result.get("weights_used", {}) or {}
    return {
        "weighted_score": round(float(result.get("weighted_score", 0.0)), 4),
        "raw_weighted_score": round(float(result.get("raw_weighted_score", 0.0) or 0.0), 4),
        "action": result.get("action"),
        "confidence": round(float(result.get("confidence", 0.0)), 4),
        "disagreement": result.get("disagreement"),
        "signals_detail": {
            "chan": {"direction": chan_s.get("direction"), "confidence": round(float(chan_s.get("confidence", 0.0) or 0.0), 4)},
            "momentum": {"direction": mom_s.get("direction"), "confidence": round(float(mom_s.get("confidence", 0.0) or 0.0), 4)},
            "vpf": {"direction": vpf_s.get("direction"), "confidence": round(float(vpf_s.get("confidence", 0.0) or 0.0), 4)},
        },
        "weights_used": {
            "chan": round(float(wu.get("chan", 0.0) or 0.0), 4),
            "momentum": round(float(wu.get("momentum", 0.0) or 0.0), 4),
            "vpf": round(float(wu.get("vpf", 0.0) or 0.0), 4),
        },
    }


def capture_all() -> dict[str, dict[str, Any]]:
    return {scn["name"]: run_scenario(scn) for scn in SCENARIOS}
