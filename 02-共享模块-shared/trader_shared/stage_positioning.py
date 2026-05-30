"""四阶段定位模型（Stage Positioning Model）— 威科夫量价驱动版

两层嵌套：
  第一层：大阶段（蓄势/主升/派发/衰退）→ 威科夫量价关系为核心 + MA 结构 + ATR
  第二层：短期动能（走强/修复/震荡/转弱）→ 基于 MA5/MA10 + change_pct

四层防护：
  1. 多日确认（连续 3 日信号一致才确认阶段转换）
  2. 置信度评分（<60% 保持上次阶段）
  3. 缠论+动量交叉验证（冲突时降级）
  4. 阶段锁定期（转换后锁定 5 天）

用法:
    from stage_positioning import assess_stage
    result = assess_stage(current, ma_values, change_pct, bars)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── 阶段状态持久化（多日确认 + 锁定期）──────────────────────
_STATE_FILE = Path.home() / ".trader" / "stage_state.json"


def _load_stage_state() -> dict[str, Any]:
    """加载阶段状态（用于多日确认和锁定期）。"""
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_stage_state(state: dict[str, Any]) -> None:
    """保存阶段状态。"""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── 量价关系判定（核心维度，权重 50%）──────────────────────

def _assess_volume_price(bars: list[dict[str, Any]]) -> tuple[str, float, str]:
    """威科夫量价关系判定四阶段。

    Returns:
        (stage, score, reason)
        score: 0-100，该维度对阶段判定的置信度
    """
    if not bars or len(bars) < 20:
        return "蓄势", 30, "数据不足，默认蓄势"

    recent5 = bars[-5:]
    recent20 = bars[-20:]

    # 计算量能比率
    vol_5 = [float(b.get("volume") or 0) for b in recent5]
    vol_20 = [float(b.get("volume") or 0) for b in recent20]
    avg_vol_5 = sum(vol_5) / max(len(vol_5), 1)
    avg_vol_20 = sum(vol_20) / max(len(vol_20), 1)
    vol_ratio = avg_vol_5 / max(avg_vol_20, 1)

    # 计算价格变化
    close_5_start = float(recent5[0].get("close") or 0)
    close_5_end = float(recent5[-1].get("close") or 0)
    if close_5_start > 0:
        price_change_5 = (close_5_end - close_5_start) / close_5_start
    else:
        price_change_5 = 0.0

    # 计算振幅
    highs = [float(b.get("high") or 0) for b in recent5]
    lows = [float(b.get("low") or 0) for b in recent5]
    if close_5_start > 0:
        amplitude = (max(highs) - min(lows)) / close_5_start
    else:
        amplitude = 0.0

    # 威科夫四阶段判定
    is_low_volume = vol_ratio < 0.8    # 缩量
    is_high_volume = vol_ratio > 1.2   # 放量
    is_rising = price_change_5 > 0.03  # 涨幅 > 3%
    is_falling = price_change_5 < -0.03  # 跌幅 > 3%
    is_flat = abs(price_change_5) < 0.01  # 振幅 < 1%

    if is_low_volume and is_flat and amplitude < 0.05:
        return "蓄势", 70, f"缩量横盘（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"
    if is_high_volume and is_rising:
        return "主升", 80, f"放量上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
    if is_high_volume and is_flat:
        return "派发", 65, f"放量不涨（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"
    if is_high_volume and is_falling:
        return "衰退", 75, f"放量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"

    # 弱信号：缩量下跌（可能是衰退末期的缩量筑底）
    if is_low_volume and is_falling:
        return "蓄势", 50, f"缩量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%），可能筑底"

    # 弱信号：放量但方向不明确
    if is_high_volume:
        return "派发", 45, f"放量方向不明（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"

    # 默认
    return "蓄势", 40, f"量价无明确信号（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"


# ── MA 结构辅助判定（权重 30%）─────────────────────────────

def _assess_ma_structure(
    ma5: float | None,
    ma10: float | None,
    ma20: float | None,
    ma30: float | None,
) -> tuple[str, float, str]:
    """MA 结构辅助判定。

    Returns:
        (stage_hint, score, reason)
    """
    has_ma = [v is not None and v > 0 for v in [ma5, ma10, ma20, ma30]]
    if not all(has_ma):
        return "蓄势", 20, "均线数据不足"

    bullish = ma5 > ma10 > ma20 > ma30
    bearish = ma5 < ma10 < ma20 < ma30
    convergence = abs(ma20 - ma30) / max(ma30, 1)

    if bullish:
        return "主升", 75, "均线多头排列"
    if bearish:
        return "衰退", 70, "均线空头排列"
    if convergence < 0.03:
        return "蓄势", 60, "均线收敛"
    if ma20 > ma30:
        return "派发", 45, "MA20>MA30 但未多头排列"
    return "蓄势", 40, "均线无明确方向"


# ── ATR 波动辅助判定（权重 20%）─────────────────────────────

def _assess_atr_volatility(bars: list[dict[str, Any]]) -> tuple[str, float, str]:
    """ATR 波动辅助判定。

    Returns:
        (stage_hint, score, reason)
    """
    if not bars or len(bars) < 20:
        return "蓄势", 20, "数据不足"

    recent10 = bars[-10:]
    recent20 = bars[-20:]

    def _atr(bars_slice: list[dict]) -> float:
        trs = []
        for i, b in enumerate(bars_slice):
            h = float(b.get("high") or 0)
            l = float(b.get("low") or 0)
            if i > 0:
                pc = float(bars_slice[i-1].get("close") or 0)
                tr = max(h - l, abs(h - pc), abs(l - pc))
            else:
                tr = h - l
            trs.append(tr)
        return sum(trs) / max(len(trs), 1)

    atr_10 = _atr(recent10)
    atr_20 = _atr(recent20)
    close = float(bars[-1].get("close") or 0)

    if close <= 0 or atr_20 <= 0:
        return "蓄势", 20, "ATR 数据异常"

    atr_ratio = atr_10 / atr_20
    atr_pct = atr_20 / close

    # ATR 上升 → 阶段活跃
    if atr_ratio > 1.3:
        if atr_pct > 0.03:
            return "主升", 55, f"ATR 上升（比值{atr_ratio:.1f}），高波动"
        return "主升", 45, f"ATR 上升（比值{atr_ratio:.1f}）"
    # ATR 下降 → 阶段收敛
    if atr_ratio < 0.7:
        return "蓄势", 55, f"ATR 下降（比值{atr_ratio:.1f}），收敛中"
    # ATR 平稳
    return "蓄势", 35, f"ATR 平稳（比值{atr_ratio:.1f}）"


# ── 综合阶段判定 ──────────────────────────────────────────

def _detect_major_stage(
    current: float,
    ma_values: dict[str, float | None],
    bars: list[dict[str, Any]] | None = None,
) -> tuple[str, float, str]:
    """综合三个维度判定大阶段。

    Returns:
        (stage, confidence, reason)
    """
    # 量价关系（核心，权重 50%）
    vp_stage, vp_score, vp_reason = _assess_volume_price(bars)

    # MA 结构（辅助，权重 30%）
    ma5 = ma_values.get("ma5")
    ma10 = ma_values.get("ma10")
    ma20 = ma_values.get("ma20")
    ma30 = ma_values.get("ma30")
    ma_stage, ma_score, ma_reason = _assess_ma_structure(ma5, ma10, ma20, ma30)

    # ATR 波动（辅助，权重 20%）
    atr_stage, atr_score, atr_reason = _assess_atr_volatility(bars)

    # 加权投票
    stage_votes: dict[str, float] = {"蓄势": 0, "主升": 0, "派发": 0, "衰退": 0}
    stage_votes[vp_stage] += vp_score * 0.5
    stage_votes[ma_stage] += ma_score * 0.3
    stage_votes[atr_stage] += atr_score * 0.2

    best_stage = max(stage_votes, key=stage_votes.get)  # type: ignore[arg-type]
    total_score = stage_votes[best_stage]
    confidence = min(100, int(total_score))

    reason = f"量价:{vp_reason} | 均线:{ma_reason} | ATR:{atr_reason}"
    return best_stage, confidence, reason


# ── 短期动能判定 ──────────────────────────────────────────────

def _detect_short_term_momentum(
    current: float,
    ma5: float | None,
    ma10: float | None,
    change_pct: float,
    position_ratio: float,
) -> tuple[str, str]:
    """判定短期动能：走强/修复/震荡/转弱"""
    if ma5 is None or ma10 is None:
        return "震荡", "均线数据不足"

    above_ma5 = current >= ma5
    above_ma10 = current >= ma10
    ma5_above_ma10 = ma5 > ma10

    if above_ma5 and ma5_above_ma10 and change_pct > 1.0:
        return "走强", "站上MA5且放量上涨"
    if above_ma5 and ma5_above_ma10 and position_ratio >= 0.60:
        return "走强", "站上MA5且接近确认区"
    if above_ma5 and not ma5_above_ma10:
        return "修复", "站上MA5但均线未确认"
    if abs(current - ma10) / max(ma10, 1) < 0.02:
        return "修复", "在MA10附近震荡"
    if not above_ma5 and not ma5_above_ma10:
        if change_pct < -2.0:
            return "转弱", "跌破MA5且放量下跌"
        return "转弱", "跌破MA5且均线死叉"
    if not above_ma5 and ma5_above_ma10:
        return "震荡", "跌破MA5但均线未死叉"
    return "震荡", "无明确方向"


# ── 四层防护机制 ──────────────────────────────────────────────

def _layer1_multi_day_confirm(
    raw_stage: str,
    state: dict[str, Any],
) -> tuple[str, bool]:
    """第一层：多日确认。连续 3 日信号一致才确认阶段转换。

    Returns:
        (confirmed_stage, is_transition)
    """
    prev_stage = state.get("last_confirmed_stage", "蓄势")
    pending_stage = state.get("pending_stage", "")
    pending_count = state.get("pending_count", 0)

    if raw_stage == prev_stage:
        # 信号一致，重置 pending
        return prev_stage, False

    if raw_stage == pending_stage:
        # 连续相同的非当前信号
        pending_count += 1
        if pending_count >= 3:
            # 确认转换
            return raw_stage, True
        # 还没到 3 天，保持当前阶段
        state["pending_count"] = pending_count
        return prev_stage, False
    else:
        # 新的非当前信号，重新计数
        state["pending_stage"] = raw_stage
        state["pending_count"] = 1
        return prev_stage, False


def _layer2_confidence_gate(
    stage: str,
    confidence: int,
    state: dict[str, Any],
) -> tuple[str, int]:
    """第二层：置信度评分。< 60% 保持上次阶段。

    Returns:
        (final_stage, final_confidence)
    """
    if confidence < 60:
        prev_stage = state.get("last_confirmed_stage", "蓄势")
        return prev_stage, confidence
    return stage, confidence


def _layer3_cross_validation(
    stage: str,
    chan_result: dict[str, Any] | None,
    momentum_result: dict[str, Any] | None,
) -> tuple[str, str | None]:
    """第三层：缠论+动量交叉验证。冲突时降级。

    Returns:
        (final_stage, conflict_note)
    """
    if chan_result is None and momentum_result is None:
        return stage, None

    # 缠论冲突检查
    if chan_result and isinstance(chan_result, dict):
        chan = chan_result.get("chanlun", {})
        if isinstance(chan, dict):
            divergence = chan.get("divergence", {})
            if stage == "主升" and divergence.get("top_divergence"):
                return "派发", "缠论顶背离与主升冲突，降级为派发"
            if stage == "衰退" and divergence.get("bottom_divergence"):
                return "蓄势", "缠论底背离与衰退冲突，降级为蓄势"

    # 动量冲突检查
    if momentum_result and isinstance(momentum_result, dict):
        mom = momentum_result.get("momentum", {})
        if isinstance(mom, dict):
            direction = mom.get("direction", "neutral")
            if stage == "主升" and direction == "bearish":
                return "派发", "动量看空与主升冲突，降级为派发"
            if stage == "衰退" and direction == "bullish":
                return "蓄势", "动量看多与衰退冲突，降级为蓄势"

    return stage, None


def _layer4_stage_lock(
    stage: str,
    state: dict[str, Any],
    is_transition: bool,
) -> tuple[str, bool]:
    """第四层：阶段锁定期。转换后锁定 5 天。

    Returns:
        (final_stage, is_locked)
    """
    lock_remaining = state.get("lock_remaining", 0)

    if is_transition:
        # 新转换，设置锁定期
        state["lock_remaining"] = 5
        return stage, True

    if lock_remaining > 0:
        # 锁定期内
        state["lock_remaining"] = lock_remaining - 1
        prev_stage = state.get("last_confirmed_stage", "蓄势")
        return prev_stage, True

    return stage, False


# ── 组合决策矩阵 ──────────────────────────────────────────────

_DECISION_MATRIX: dict[str, dict[str, tuple[str, int]]] = {
    "蓄势": {
        "走强": ("试探买", 10),
        "修复": ("观察", 0),
        "震荡": ("等待", 0),
        "转弱": ("不碰", 0),
    },
    "主升": {
        "走强": ("加仓", 70),
        "修复": ("持有", 50),
        "震荡": ("持有", 50),
        "转弱": ("减仓", 30),
    },
    "派发": {
        "走强": ("减仓", 30),
        "修复": ("减仓", 20),
        "震荡": ("减仓", 20),
        "转弱": ("清仓", 0),
    },
    "衰退": {
        "走强": ("不碰", 0),
        "修复": ("不碰", 0),
        "震荡": ("不碰", 0),
        "转弱": ("不碰", 0),
    },
}


def assess_stage(
    current: float,
    ma_values: dict[str, float | None],
    change_pct: float,
    bars: list[dict[str, Any]] | None = None,
    position_ratio: float = 0.5,
    chan_result: dict[str, Any] | None = None,
    momentum_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """四阶段定位主函数（威科夫量价驱动 + 四层防护）

    Returns:
        {
            "major_stage": str,       # 蓄势/主升/派发/衰退
            "major_reason": str,
            "momentum": str,          # 走强/修复/震荡/转弱
            "momentum_reason": str,
            "action": str,            # 操作建议
            "max_position_pct": int,  # 最大仓位百分比
            "stage_label": str,       # "蓄势期 + 修复"
            "confidence": int,        # 阶段置信度 0-100
            "protection_notes": list, # 四层防护触发说明
        }
    """
    ma5 = ma_values.get("ma5")
    ma10 = ma_values.get("ma10")

    # 第一步：综合阶段判定（量价 + MA + ATR）
    raw_stage, raw_confidence, raw_reason = _detect_major_stage(
        current, ma_values, bars
    )

    # 加载阶段状态
    state = _load_stage_state()
    protection_notes: list[str] = []

    # 第二层：置信度门控
    gated_stage, gated_confidence = _layer2_confidence_gate(raw_stage, raw_confidence, state)
    if gated_stage != raw_stage:
        protection_notes.append(f"置信度{raw_confidence}%<60%，保持{gated_stage}")

    # 第一层：多日确认
    confirmed_stage, is_transition = _layer1_multi_day_confirm(gated_stage, state)
    if confirmed_stage != gated_stage:
        protection_notes.append(f"多日确认中（{state.get('pending_count', 0)}/3）")

    # 第三层：交叉验证
    validated_stage, conflict_note = _layer3_cross_validation(
        confirmed_stage, chan_result, momentum_result
    )
    if conflict_note:
        protection_notes.append(conflict_note)

    # 第四层：阶段锁定期
    final_stage, is_locked = _layer4_stage_lock(validated_stage, state, is_transition)
    if is_locked:
        protection_notes.append(f"阶段锁定5天")
    elif is_locked and final_stage != validated_stage:
        protection_notes.append(f"锁定期内保持{final_stage}")

    # 保存状态
    if is_transition:
        state["last_confirmed_stage"] = final_stage
        state["pending_stage"] = ""
        state["pending_count"] = 0
    _save_stage_state(state)

    # 短期动能判定
    momentum, momentum_reason = _detect_short_term_momentum(
        current, ma5, ma10, change_pct, position_ratio
    )

    # 决策矩阵
    action, max_position = _DECISION_MATRIX.get(final_stage, {}).get(
        momentum, ("观察", 0)
    )

    stage_label = f"{final_stage}期 + {momentum}"

    return {
        "major_stage": final_stage,
        "major_reason": raw_reason,
        "momentum": momentum,
        "momentum_reason": momentum_reason,
        "action": action,
        "max_position_pct": max_position,
        "stage_label": stage_label,
        "confidence": gated_confidence,
        "protection_notes": protection_notes,
    }
