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

from trader_shared._logging import get_logger
from trader_shared.config import ACCUMULATION_DAYS_LIMIT, MARKUP_DAYS_LIMIT

_logger = get_logger(__name__)

# ── 阶段状态持久化（多日确认 + 锁定期）──────────────────────
_STATE_FILE = Path.home() / ".trader" / "stage_state.json"


def _load_stage_state() -> dict[str, Any]:
    """加载阶段状态（用于多日确认和锁定期）。"""
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("Stage state load failed: %s", exc)
    return {}


def _save_stage_state(state: dict[str, Any]) -> None:
    """保存阶段状态。"""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        _logger.debug("Stage state save failed: %s", exc)


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
    expma10: float | None,
    expma20: float | None,
    change_pct: float,
    position_ratio: float,
) -> tuple[str, str]:
    """判定短期动能：走强/修复/震荡/转弱"""
    if expma10 is None or expma20 is None:
        return "震荡", "EXPMA数据不足"

    dist_to_expma20 = (current - expma20) / max(expma20, 1)

    # 走强 (Strong)：现价站上 EXPMA(10) 且 EXPMA(10) > EXPMA(20)
    if current >= expma10 and expma10 > expma20:
        return "走强", "站上EXPMA(10)且多头排列"

    # 修复 (Recovery)：现价在 EXPMA(10) 与 EXPMA(20) 之间
    if min(expma10, expma20) <= current < max(expma10, expma20):
        return "修复", "回踩生命线(EXPMA10/20之间)"

    # 均线粘合优先判断为震荡
    if abs(expma10 - expma20) / max(expma20, 1) < 0.01:
        return "震荡", "EXPMA均线粘合"

    if current < expma20:
        if change_pct < -2.0 or expma10 < expma20:
            return "转弱", "跌破EXPMA(20)且走势破位"
        if abs(dist_to_expma20) < 0.03:
            return "震荡", "跌破EXPMA(20)但距离不远"
        return "转弱", "跌破EXPMA(20)且偏离较大"

    return "震荡", "走势未匹配极强/极弱特征"


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
    """第二层：置信度评分。< 50% 保持上次阶段。

    Returns:
        (final_stage, final_confidence)
    """
    if confidence < 50:
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
        "走强": ("低吸试盘", 20),
        "修复": ("回调低吸", 15),
        "震荡": ("观望等待", 0),
        "转弱": ("观望等待", 0),
    },
    "主升": {
        "走强": ("顺势加仓", 60),
        "修复": ("回踩加仓", 40),
        "震荡": ("底仓持有", 20),
        "转弱": ("跌破防线减仓", 20),
    },
    "派发": {
        "走强": ("逢高减磅", 20),
        "修复": ("逢反弹减仓", 10),
        "震荡": ("逢反弹减仓", 10),
        "转弱": ("清仓逃命", 0),
    },
    "衰退": {
        "走强": ("空仓规避", 0),
        "修复": ("空仓规避", 0),
        "震荡": ("空仓规避", 0),
        "转弱": ("空仓规避", 0),
    },
}


# ── 大盘环境对仓位的影响 ──────────────────────────────────────

_ENV_LIMITS: dict[str, dict[str, int]] = {
    #                单票上限  总仓位上限  新建仓
    "牛市": {"single": 40, "total": 80, "init": 10},
    "震荡市": {"single": 30, "total": 60, "init": 10},
    "熊市": {"single": 20, "total": 30, "init": 10},
}


def compute_position_with_env(
    stage: str,
    momentum: str,
    market_env: str = "震荡市",
    pnl_pct: float = 0.0,
    total_position_pct: float = 0.0,
) -> dict[str, Any]:
    """根据阶段+大盘环境计算建议仓位。

    Returns:
        {
            "stage_position_pct": int,   # 阶段仓位
            "env_limit_pct": int,        # 大盘环境单票上限
            "total_limit_pct": int,      # 大盘环境总仓位上限
            "suggested_pct": int,        # 建议仓位（取较小值）
            "market_env": str,
            "hard_rule_blocked": bool,   # 硬规则阻止
            "hard_rule_reason": str,
        }
    """
    # 阶段仓位
    stage_pct = _DECISION_MATRIX.get(stage, {}).get(momentum, ("观察", 0))[1]

    # 大盘环境限制
    env = _ENV_LIMITS.get(market_env, _ENV_LIMITS["震荡市"])
    single_limit = env["single"]
    total_limit = env["total"]

    # 硬规则检查
    hard_blocked = False
    hard_reason = ""

    if pnl_pct < 0:
        hard_blocked = True
        hard_reason = "持仓亏损，禁止加仓"

    if stage == "衰退":
        hard_blocked = True
        hard_reason = "衰退期，禁止建仓"

    if total_position_pct >= total_limit:
        hard_blocked = True
        hard_reason = f"总仓位 {total_position_pct}% 已达上限 {total_limit}%"

    # 建议仓位
    if hard_blocked:
        suggested = 0
    else:
        suggested = min(stage_pct, single_limit)

    return {
        "stage_position_pct": stage_pct,
        "env_limit_pct": single_limit,
        "total_limit_pct": total_limit,
        "suggested_pct": suggested,
        "market_env": market_env,
        "hard_rule_blocked": hard_blocked,
        "hard_rule_reason": hard_reason,
    }


def assess_stage(
    current: float,
    ma_values: dict[str, float | None],
    change_pct: float,
    bars: list[dict[str, Any]] | None = None,
    position_ratio: float = 0.5,
    chan_result: dict[str, Any] | None = None,
    momentum_result: dict[str, Any] | None = None,
    support: float = 0.0,
    pnl_pct: float = 0.0,
    atr14: float = 0.0,
    chip_migration: dict[str, Any] | None = None,
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
    ma20 = ma_values.get("ma20")

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
    expma10 = ma_values.get("expma10")
    expma20 = ma_values.get("expma20")
    momentum, momentum_reason = _detect_short_term_momentum(
        current, expma10, expma20, change_pct, position_ratio
    )

    # 决策矩阵
    action, max_position = _DECISION_MATRIX.get(final_stage, {}).get(
        momentum, ("观察", 0)
    )

    stage_label = f"{final_stage}期 + {momentum}"

    # 硬规则同步: 亏损/衰退期 → action 强制改为"不碰"，position 归零
    if pnl_pct < 0 and action not in ("不碰", "清仓"):
        action = "不碰"
        max_position = 0
        stage_label = f"{final_stage}期 + {momentum}（亏损不加仓）"
    elif final_stage == "衰退" and action not in ("不碰", "清仓"):
        action = "不碰"
        max_position = 0

    # 三层止损体系
    stop_losses = compute_stop_losses(
        stage=final_stage,
        current=current,
        support=support,
        ma20=ma20,
        bars=bars,
        atr14=atr14,
        chip_migration=chip_migration,
    )

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
        "stop_losses": stop_losses,
    }


# ── 三层止损体系 ──────────────────────────────────────────────

def compute_stop_losses(
    stage: str,
    current: float,
    support: float,
    ma20: float | None,
    bars: list[dict[str, Any]] | None = None,
    atr14: float = 0.0,
    chip_migration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """三层止损体系（ATR + 筹码驱动）。

    第一层：技术止损（支撑位 - 1.5×ATR，牛市防洗盘）
    第二层：阶段止损（随阶段变化）
    第三层：时间止损（买入后 N 天不涨走人）

    筹码驱动移动止损：
      底部筹码峰没松动 → 止损跟 MA10
      底部筹码峰松动 > 40% → 止损收紧到 MA20
      底部筹码峰搬家 > 50% → 清仓

    Args:
        stage: 当前阶段
        current: 当前价
        support: 支撑位
        ma20: 20 日均线
        bars: K线数据
        atr14: 14日ATR值
        chip_migration: 筹码搬家监控结果

    Returns:
        {
            "technical": {"price": float, "reason": str},
            "stage_based": {"price": float, "reason": str},
            "time_limit": {"days": int, "reason": str},
            "chip_trailing": {"price": float, "reason": str} | None,
        }
    """
    # 第一层：技术止损（ATR-based）
    if support > 0 and atr14 > 0:
        # 支撑位 - 1.5×ATR
        tech_stop = round(support - 1.5 * atr14, 2)
        tech_reason = f"支撑 {support:.2f} - 1.5×ATR({atr14:.2f})"
    elif support > 0:
        # 无 ATR 数据，退回旧逻辑
        tech_stop = round(support * 0.975, 2)
        tech_reason = f"关键支撑 {support:.2f} 下方2.5%"
    else:
        tech_stop = round(current * 0.95, 2)
        tech_reason = "无明确支撑，当前价下方5%"

    # 第二层：阶段止损
    if stage == "蓄势":
        if support > 0 and atr14 > 0:
            stage_stop = round(support - 1.5 * atr14, 2)
            stage_reason = f"蓄势期保护本金，支撑 - 1.5×ATR"
        elif support > 0:
            stage_stop = round(support * 0.98, 2)
            stage_reason = f"蓄势区间下沿 {support:.2f}"
        else:
            stage_stop = round(current * 0.95, 2)
            stage_reason = "蓄势期保护本金"
    elif stage == "主升":
        if ma20 is not None and ma20 > 0:
            stage_stop = round(ma20 * 0.98, 2)  # MA20 附近
            stage_reason = f"主升期保护利润，MA20 {ma20:.2f}"
        else:
            stage_stop = round(current * 0.92, 2)
            stage_reason = "主升期保护利润"
    elif stage == "派发":
        if ma20 is not None and ma20 > 0:
            stage_stop = round(ma20 * 0.98, 2)  # MA20 下方锁定收益
            stage_reason = f"派发期锁定收益，MA20上方 {ma20:.2f}"
        else:
            stage_stop = round(current * 0.95, 2)
            stage_reason = "派发期锁定收益"
    else:  # 衰退
        stage_stop = 0.0
        stage_reason = "衰退期不持有"

    # 第三层：时间止损
    if stage == "蓄势":
        time_days = 30
        time_reason = "蓄势期30天内不突破走人"
    elif stage == "主升":
        time_days = 15
        time_reason = "主升期15天内不创新高减仓"
    elif stage == "派发":
        time_days = 0
        time_reason = "派发期不建议买入"
    else:
        time_days = 0
        time_reason = "衰退期不持有"

    # 筹码驱动移动止损
    chip_trailing: dict[str, Any] | None = None
    if isinstance(chip_migration, dict) and chip_migration.get("has_history"):
        migration_pct = chip_migration.get("migration_pct", 0)
        warning_level = chip_migration.get("warning_level", "none")

        if warning_level == "critical":
            # 底部筹码峰搬家 > 50% → 清仓
            chip_trailing = {
                "price": 0.0,
                "reason": f"底部筹码搬家 {migration_pct:.0f}%，清仓信号",
                "action": "清仓",
            }
        elif warning_level == "warning":
            # 底部筹码峰松动 > 40% → 止损收紧到 MA20
            if ma20 is not None and ma20 > 0:
                chip_trailing = {
                    "price": round(ma20, 2),
                    "reason": f"筹码松动 {migration_pct:.0f}%，止损收紧到 MA20",
                    "action": "减仓",
                }
        else:
            # 底部筹码峰没松动 → 止损跟 MA10（如果有的话）
            # 这里返回 None，表示使用默认止损
            pass

    return {
        "technical": {"price": tech_stop, "reason": tech_reason},
        "stage_based": {"price": stage_stop, "reason": stage_reason},
        "time_limit": {"days": time_days, "reason": time_reason},
        "chip_trailing": chip_trailing,
    }


# ── 分批止盈计划 ──────────────────────────────────────────────

def compute_exit_plan(
    entry_price: float,
    stop_price: float,
    resistance_price: float | None,
    current_stage: str,
    bars: list[dict[str, Any]] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    atr14: float = 0.0,
) -> dict[str, Any]:
    """计算分批止盈计划（条件止盈，威科夫信号驱动）。

    三批退出：
      第一笔：BC 信号出现 → 卖 1/3（购买高潮，主力在出货）
      第二笔：1R 目标达到 → 卖 1/3（保本，锁定部分利润）
      第三笔：阶段转派发 或 筹码搬家 > 50% → 清仓（趋势变了）

    阻力位不再是"到了就卖"，而是"看信号决定"：
      - 大阳线突破 + 放量 → 继续持有
      - BC 信号 → 卖 1/3
      - UTAD 信号 → 立刻减仓

    Args:
        entry_price: 买入价
        stop_price: 止损价
        resistance_price: 最近阻力位（可选）
        current_stage: 当前阶段（蓄势/主升/派发/衰退）
        bars: K线数据（用于计算动态阻力位）
        wyckoff_result: 威科夫分析结果（包含 BC/UTAD 信号）
        atr14: 14日ATR值

    Returns:
        止盈计划字典
    """
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return {
            "risk_r": 0.0,
            "target_1r": 0.0,
            "resistance_exit": None,
            "stage_exit": current_stage,
            "exit_plan": [],
            "already_exited": [False, False, False],
            "wyckoff_signals": {},
        }

    # 1R 计算
    risk_r = round(entry_price - stop_price, 2)
    target_1r = round(entry_price + risk_r, 2)

    # 阻力位退出价
    resistance_exit: float | None = None
    if resistance_price is not None and resistance_price > entry_price:
        resistance_exit = round(resistance_price, 2)
    elif bars and len(bars) >= 20:
        # 动态计算阻力位：近 20 日最高价
        highs = [float(b.get("high") or 0) for b in bars[-20:]]
        max_high = max(highs) if highs else 0
        if max_high > entry_price:
            resistance_exit = round(max_high, 2)

    # 阶段退出条件
    stage_exit = "派发"  # 主升转派发时清仓

    # 提取威科夫信号
    bc_signal = False
    bc_reason = ""
    utad_signal = False
    utad_reason = ""
    if isinstance(wyckoff_result, dict):
        wyk = wyckoff_result.get("wyckoff", wyckoff_result)
        if isinstance(wyk, dict):
            bc_signal = wyk.get("bc_signal", False)
            bc_reason = wyk.get("bc_reason", "")
            utad_signal = wyk.get("upthrust_signal", False)
            utad_reason = wyk.get("upthrust_reason", "")

    # 构建三批退出计划（条件止盈）
    exit_plan: list[dict[str, Any]] = []

    # 第一笔：BC 信号（购买高潮）→ 卖 1/3
    if bc_signal:
        exit_plan.append({
            "price": None,
            "ratio": 0.33,
            "reason": "购买高潮（BC），减仓1/3",
            "condition": "BC 信号出现",
            "triggered": True,
        })
    else:
        exit_plan.append({
            "price": None,
            "ratio": 0.33,
            "reason": "等待 BC 信号",
            "condition": "BC 信号出现",
            "triggered": False,
        })

    # 第二笔：1R 目标
    exit_plan.append({
        "price": target_1r,
        "ratio": 0.33,
        "reason": "1R 目标，保本",
        "condition": "1R 达到",
        "triggered": False,
    })

    # 第三笔：阶段转派发
    exit_plan.append({
        "price": None,
        "ratio": 0.34,
        "reason": "阶段转派发，清仓",
        "condition": "阶段转派发",
        "triggered": False,
    })

    # 突破跟进逻辑
    breakout_followup: dict[str, Any] | None = None
    if resistance_exit is not None and atr14 > 0:
        # 突破阻力位后的新止损和新目标
        new_stop = resistance_exit  # 旧阻力位 → 新支撑位
        # 新目标：下一个阻力位或 2R
        next_resistance = None
        if bars and len(bars) >= 40:
            all_highs = [float(b.get("high") or 0) for b in bars[-40:]]
            above_resistance = [h for h in all_highs if h > resistance_exit * 1.01]
            if above_resistance:
                next_resistance = round(min(above_resistance), 2)
        if next_resistance is None:
            next_resistance = round(entry_price + risk_r * 2, 2)

        breakout_followup = {
            "new_stop": round(new_stop, 2),
            "new_target": next_resistance,
            "add_on_pullback": True,
            "note": "突破阻力位后止损上移，回踩新支撑不破可加仓",
        }

    # UTAD 假突破信号
    utad_action: dict[str, Any] | None = None
    if utad_signal:
        utad_action = {
            "signal": "UTAD",
            "reason": utad_reason,
            "action": "立刻减仓",
            "note": "上冲回落假突破，止损下移回原支撑位",
        }

    return {
        "risk_r": risk_r,
        "target_1r": target_1r,
        "resistance_exit": resistance_exit,
        "stage_exit": stage_exit,
        "exit_plan": exit_plan,
        "already_exited": [False, False, False],
        "wyckoff_signals": {
            "bc_signal": bc_signal,
            "bc_reason": bc_reason,
            "utad_signal": utad_signal,
            "utad_reason": utad_reason,
        },
        "breakout_followup": breakout_followup,
        "utad_action": utad_action,
    }


def compute_stage_stop(
    stage: str,
    ma20: float | None,
    range_low: float | None = None,
    atr_pct: float = 0.02,
    expma20: float | None = None,
) -> dict[str, Any]:
    """根据阶段计算止损位。

    蓄势期：蓄势区间下沿（保护本金）
    主升期：MA20（保护利润）
    派发期：EXPMA(20) 上方（锁定收益）
    衰退期：不持有

    Args:
        stage: 当前阶段
        ma20: 20 日均线
        range_low: 蓄势区间下沿（可选）
        atr_pct: ATR 占比
        expma20: 20 日 EXPMA（可选，派发期优先使用）

    Returns:
        {"price": float, "reason": str}
    """
    if stage == "蓄势":
        if range_low is not None and range_low > 0:
            return {"price": round(range_low, 2), "reason": f"蓄势区间下沿 {range_low:.2f}"}
        if ma20 is not None and ma20 > 0:
            return {"price": round(ma20 * 0.95, 2), "reason": f"蓄势期保护本金，MA20下方5%"}
        return {"price": 0.0, "reason": "数据不足"}
    elif stage == "主升":
        if ma20 is not None and ma20 > 0:
            return {"price": round(ma20, 2), "reason": f"主升期保护利润，MA20 {ma20:.2f}"}
        return {"price": 0.0, "reason": "数据不足"}
    elif stage == "派发":
        # 派发期优先使用 EXPMA(20)，fallback 到 MA20
        ref_price = expma20 if (expma20 is not None and expma20 > 0) else ma20
        ref_name = "EXPMA(20)" if (expma20 is not None and expma20 > 0) else "MA20"
        if ref_price is not None and ref_price > 0:
            return {"price": round(ref_price * (1 + atr_pct * 0.5), 2), "reason": f"派发期锁定收益，{ref_name}上方"}
        return {"price": 0.0, "reason": "数据不足"}
    else:  # 衰退
        return {"price": 0.0, "reason": "衰退期不持有"}


def check_time_stop(
    entry_date: str | None,
    current_stage: str,
    days_held: int,
    made_new_high: bool,
    has_position: bool = True,
) -> dict[str, Any]:
    """检查时间止损。

    蓄势期买入：30 天不突破 → 走人
    主升期买入：15 天不创新高 → 减仓
    派发期买入：不建议

    Args:
        entry_date: 买入日期（YYYY-MM-DD）
        current_stage: 当前阶段
        days_held: 已持有天数
        made_new_high: 是否创新高
        has_position: 是否有持仓（空仓时不触发清仓）

    Returns:
        {"triggered": bool, "action": str, "days_left": int}
    """
    if not has_position:
        return {"triggered": False, "action": "空仓不触发时间止损", "days_left": 0}

    if current_stage == "蓄势":
        limit = ACCUMULATION_DAYS_LIMIT
        if days_held >= limit and not made_new_high:
            return {"triggered": True, "action": f"蓄势期{limit}天不突破，走人", "days_left": 0}
        return {"triggered": False, "action": "等待突破", "days_left": max(0, limit - days_held)}
    elif current_stage == "主升":
        limit = MARKUP_DAYS_LIMIT
        if days_held >= limit and not made_new_high:
            return {"triggered": True, "action": f"主升期{limit}天不创新高，减仓", "days_left": 0}
        return {"triggered": False, "action": "等待创新高", "days_left": max(0, limit - days_held)}
    elif current_stage == "派发":
        return {"triggered": False, "action": "派发期不建议买入", "days_left": 0}
    else:  # 衰退
        return {"triggered": True, "action": "衰退期清仓", "days_left": 0}


def compute_stop_summary(
    technical_stop: float,
    stage_stop: float,
    time_stop: dict[str, Any],
    current_price: float,
) -> dict[str, Any]:
    """汇总三层止损，取最近的作为最终止损。

    Args:
        technical_stop: 技术止损价
        stage_stop: 阶段止损价
        time_stop: 时间止损结果
        current_price: 当前价

    Returns:
        {"final_stop": float, "stops": dict, "time_stop": dict}
    """
    stops: dict[str, float] = {}
    if technical_stop > 0:
        stops["技术止损"] = technical_stop
    if stage_stop > 0:
        stops["阶段止损"] = stage_stop

    # 取最高的止损价（最近当前价的）
    final_stop = max(stops.values()) if stops else 0.0

    return {
        "final_stop": final_stop,
        "stops": stops,
        "time_stop": time_stop,
    }


# ── 五状态仓位管理状态机 ──────────────────────────────────────

# 状态定义
POSITION_STATES = {
    "空仓": 0,
    "初始建仓": 1,
    "阻力位分歧": 2,
    "回踩加仓": 3,
    "主升浪跟踪": 4,
    "退出再买": 5,
}

# 状态转移矩阵：(当前状态, 条件) → 下一状态
# 条件由 evaluate_position_state() 返回


def evaluate_position_state(
    current_price: float,
    support: float,
    resistance: float,
    stop_price: float,
    confirm_price: float,
    atr14: float,
    major_stage: str,
    momentum: str,
    bars: list[dict[str, Any]] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    holding_days: int = 0,
    has_position: bool = False,
    entry_price: float = 0.0,
    highest_close: float = 0.0,
    expma10: float | None = None,
    chip_migration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """五状态仓位管理状态机。

    状态流转：
      空仓 → 初始建仓（支撑位买 10%，止损支撑位-1.5×ATR）
      初始建仓 → 阻力位分歧（到达阻力位，弱→卖1/3，强→不卖）
      初始建仓 → 回踩加仓（回踩支撑位，条件满足加仓）
      阻力位分歧 → 回踩加仓（回踩后条件满足）
      回踩加仓 → 主升浪跟踪（筹码没搬家+EXPMA(10)上→拿着）
      主升浪跟踪 → 退出再买（跌破止损/阶段转衰退）
      退出再买 → 初始建仓（回到支撑位+止跌信号+阶段没变）

    Returns:
        {
            "state": str,               # 当前状态
            "state_code": int,          # 状态代码 0-5
            "action": str,              # 建议动作
            "position_pct": int,        # 建议仓位 %
            "stop_price": float,        # 止损价
            "take_profit_price": float, # 止盈价（条件止盈）
            "conditions": dict,         # 各条件检查结果
            "transition_reason": str,   # 状态转移原因
        }
    """
    # 基础检查
    if current_price <= 0:
        return _empty_position_state("空仓", "数据不足")

    # ATR 止损计算
    atr_stop = round(support - 1.5 * atr14, 2) if support > 0 and atr14 > 0 else round(current_price * 0.95, 2)

    # 提取威科夫信号
    bc_signal = False
    utad_signal = False
    sow_signal = False
    if isinstance(wyckoff_result, dict):
        wyk = wyckoff_result.get("wyckoff", wyckoff_result)
        if isinstance(wyk, dict):
            bc_signal = wyk.get("bc_signal", False)
            utad_signal = wyk.get("upthrust_signal", False)
            sow_signal = wyk.get("sow_signal", False)

    # 筹码搬家检查
    chip_warning = "none"
    if isinstance(chip_migration, dict):
        chip_warning = chip_migration.get("warning_level", "none")

    # 条件检查
    conditions = {
        "at_support": support > 0 and abs(current_price - support) / max(support, 1) < 0.03,
        "at_resistance": resistance > 0 and abs(current_price - resistance) / max(resistance, 1) < 0.03,
        "above_stop": stop_price <= 0 or current_price > stop_price,
        "above_atr_stop": current_price > atr_stop,
        "breakout_confirmed": confirm_price > 0 and current_price >= confirm_price,
        "pullback_to_support": support > 0 and current_price <= support * 1.02 and current_price >= support * 0.98,
        "chip_stable": chip_warning not in ("critical", "warning"),
        "expma10_up": expma10 is not None and current_price > expma10,
        "bc_signal": bc_signal,
        "utad_signal": utad_signal,
        "sow_signal": sow_signal,
        "stage_accumulation": major_stage == "蓄势",
        "stage_markup": major_stage == "主升",
        "stage_distribution": major_stage == "派发",
        "stage_decline": major_stage == "衰退",
        "momentum_strong": momentum in ("走强", "修复"),
        "momentum_weak": momentum in ("转弱",),
    }

    # 状态判定
    if not has_position:
        # 空仓状态
        if conditions["stage_decline"]:
            return _make_position_state("空仓", "衰退期不碰", 0, conditions)
        if conditions["at_support"] and conditions["momentum_strong"] and not conditions["stage_decline"]:
            return _make_position_state(
                "初始建仓", "到达支撑位+短期走强，试探买10%",
                10, conditions, stop_price=atr_stop,
            )
        return _make_position_state("空仓", "等待到达支撑位", 0, conditions)

    # 有持仓的状态流转
    # 检查止损
    if not conditions["above_stop"] or not conditions["above_atr_stop"]:
        return _make_position_state(
            "退出再买", "跌破止损，清仓等待",
            0, conditions, stop_price=0,
        )

    # 检查 UTAD / SOW / 筹码搬家 → 退出
    if conditions["utad_signal"] or conditions["sow_signal"] or chip_warning == "critical":
        reason = "UTAD上冲回落" if conditions["utad_signal"] else "SOW弱势信号" if conditions["sow_signal"] else "筹码搬家清仓"
        return _make_position_state(
            "退出再买", f"{reason}，清仓等待",
            0, conditions, stop_price=0,
        )

    # 衰退期 → 退出
    if conditions["stage_decline"]:
        return _make_position_state(
            "退出再买", "阶段转衰退，清仓",
            0, conditions, stop_price=0,
        )

    # 派发期 → 阻力位分歧
    if conditions["stage_distribution"]:
        if conditions["at_resistance"]:
            if bc_signal:
                return _make_position_state(
                    "阻力位分歧", "派发期+BC信号，减仓1/3",
                    0, conditions, stop_price=atr_stop,
                )
            return _make_position_state(
                "阻力位分歧", "派发期到达阻力位，观察是否突破",
                0, conditions, stop_price=atr_stop,
            )
        return _make_position_state(
            "阻力位分歧", "派发期，逢高减仓",
            0, conditions, stop_price=atr_stop,
        )

    # 主升浪跟踪
    if conditions["stage_markup"]:
        # 底仓止损：上移到阻力位（更宽的止损）
        base_stop = round(resistance * 0.98, 2) if resistance > 0 else atr_stop
        
        if conditions["chip_stable"] and conditions["expma10_up"]:
            return _make_position_state(
                "主升浪跟踪", "主升期+筹码稳定+EXPMA(10)支撑，持有",
                0, conditions, stop_price=expma10 if expma10 else base_stop,
            )
        if not conditions["chip_stable"]:
            return _make_position_state(
                "主升浪跟踪", "主升期但筹码松动，收紧止损",
                0, conditions, stop_price=atr_stop,
            )
        return _make_position_state(
            "主升浪跟踪", "主升期，持有观察",
            0, conditions, stop_price=base_stop,
        )

    # 回踩加仓（蓄势期+回踩支撑+条件满足）
    if conditions["stage_accumulation"] and conditions["pullback_to_support"]:
        # 必要条件 + 加分条件评分
        add_score = _calc_pullback_add_score(
            conditions, bars, current_price, support, atr14,
        )
        
        # 加仓独立止损：设在回踩支撑位下方（比底仓止损更窄）
        # 使用 1.0×ATR 作为止损距离（可配置）
        _ADD_ON_STOP_ATR_MULTIPLE = 1.0
        add_on_stop = round(support - _ADD_ON_STOP_ATR_MULTIPLE * atr14, 2) if support > 0 and atr14 > 0 else round(current_price * 0.97, 2)
        
        if add_score >= 5:
            return _make_position_state(
                "回踩加仓", f"回踩支撑+条件满足（{add_score}/5），加仓15%",
                15, conditions, stop_price=add_on_stop,
            )
        if add_score >= 3:
            return _make_position_state(
                "回踩加仓", f"回踩支撑+部分条件满足（{add_score}/5），加仓10%",
                10, conditions, stop_price=add_on_stop,
            )
        return _make_position_state(
            "回踩加仓", f"回踩支撑但条件不足（{add_score}/5），观望",
            0, conditions, stop_price=add_on_stop,
        )

    # 阻力位分歧（到达阻力位）
    if conditions["at_resistance"]:
        # 阻力位由客观量价表现决定：弱→止盈，强→等回踩加仓
        resistance_strength = _assess_resistance_strength(bars, current_price, resistance)
        
        if bc_signal:
            return _make_position_state(
                "阻力位分歧", "到达阻力位+BC信号，减仓1/3",
                0, conditions, stop_price=atr_stop,
            )
        if conditions["breakout_confirmed"]:
            return _make_position_state(
                "阻力位分歧", "突破阻力位确认，继续持有",
                0, conditions, stop_price=atr_stop,
            )
        if resistance_strength == "weak":
            return _make_position_state(
                "阻力位分歧", "阻力位弱势，可以止盈",
                0, conditions, stop_price=atr_stop,
            )
        return _make_position_state(
            "阻力位分歧", "到达阻力位，观察量能",
            0, conditions, stop_price=atr_stop,
        )

    # 默认：持有观察
    return _make_position_state(
        "初始建仓", "持仓观察中",
        0, conditions, stop_price=atr_stop,
    )


def _calc_pullback_add_score(
    conditions: dict[str, bool],
    bars: list[dict[str, Any]] | None,
    current_price: float,
    support: float,
    atr14: float,
) -> int:
    """计算回踩加仓条件评分（满分5分）。

    必要条件（2分）：
      1. 到达支撑位附近（1分）
      2. 出现止跌信号（1分）

    加分条件（3分）：
      3. 缩量回踩（1分）
      4. RSI 超卖区反弹（1分）
      5. MACD 底背离或金叉（1分）
    """
    score = 0

    # 必要条件1：到达支撑位附近（1分）
    if support > 0 and abs(current_price - support) / max(support, 1) < 0.03:
        score += 1

    # 必要条件2：出现止跌信号（1分）— 价格企稳（近3天未创新低）
    if bars and len(bars) >= 3:
        recent_lows = [float(b.get("low") or 0) for b in bars[-3:]]
        if min(recent_lows) >= support * 0.98:
            score += 1

    # 加分条件3：缩量回踩（1分）
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        if earlier_vol > 0 and recent_vol < earlier_vol * 0.8:
            score += 1

    # 加分条件4：RSI 超卖区反弹（1分）
    if bars and len(bars) >= 14:
        closes = [float(b.get("close") or 0) for b in bars[-14:] if b.get("close")]
        if len(closes) >= 14:
            gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
            losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
            avg_gain = sum(gains) / len(gains) if gains else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            rs = avg_gain / max(avg_loss, 0.01)
            rsi = 100 - (100 / (1 + rs))
            if rsi < 40:
                score += 1

    # 加分条件5：MACD 金叉（1分）
    if bars and len(bars) >= 26:
        closes = [float(b.get("close") or 0) for b in bars[-26:] if b.get("close")]
        if len(closes) >= 26:
            ema12 = sum(closes[-12:]) / 12
            ema26 = sum(closes[-26:]) / 26
            macd_line = ema12 - ema26
            if macd_line > 0:
                score += 1

    return score


def _calc_reentry_score(
    conditions: dict[str, bool],
    bars: list[dict[str, Any]] | None,
    current_price: float,
    support: float,
    expma10: float | None,
) -> int:
    """计算退出再买条件评分（满分4分）。

    必要条件（1分）：
      1. 价格回到支撑位附近

    加分条件（3分）：
      2. 缩量止跌（1分）
      3. 价格站上 EXPMA(10)（1分）
      4. 阶段没变坏（1分）
    """
    score = 0
    
    # 必要条件：价格回到支撑位附近
    if support > 0 and abs(current_price - support) / max(support, 1) < 0.03:
        score += 1
    
    # 加分条件：缩量止跌
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        if earlier_vol > 0 and recent_vol < earlier_vol * 0.8:
            score += 1
    
    # 加分条件：价格站上 EXPMA(10)
    if expma10 and current_price > expma10:
        score += 1
    
    # 加分条件：阶段没变坏（不是衰退期）
    if not conditions.get("stage_decline", False):
        score += 1
    
    return score


def _assess_resistance_strength(
    bars: list[dict[str, Any]] | None,
    current_price: float,
    resistance: float,
) -> str:
    """评估阻力位强度。

    弱阻力（可以止盈）：
      - 连续2日缩量
      - 价格在阻力位附近震荡

    强阻力（等回踩加仓）：
      - 放量突破
      - 大阳线突破

    Returns:
        "weak" 或 "strong"
    """
    if not bars or len(bars) < 10 or resistance <= 0:
        return "strong"  # 默认认为强阻力
    
    recent3 = bars[-3:]
    
    # 检查是否缩量
    recent_vol = sum(float(b.get("volume") or 0) for b in recent3) / 3
    earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
    is_low_volume = earlier_vol > 0 and recent_vol < earlier_vol * 0.8
    
    # 检查是否在阻力位附近震荡
    near_resistance = abs(current_price - resistance) / max(resistance, 1) < 0.02
    
    # 检查是否有大阳线突破（含涨停板特殊处理）
    has_big_green = False
    has_limit_up = False
    for bar in recent3:
        open_p = float(bar.get("open") or 0)
        close_p = float(bar.get("close") or 0)
        high_p = float(bar.get("high") or 0)
        if open_p > 0 and close_p > open_p * 1.03:  # 涨幅 > 3%
            has_big_green = True
        # 涨停板判断：收盘价 = 最高价，且涨幅 > 9%
        if open_p > 0 and close_p == high_p and close_p > open_p * 1.09:
            has_limit_up = True
    
    # 弱阻力：缩量 + 在阻力位附近震荡 + 没有大阳线突破 + 没有涨停板
    if is_low_volume and near_resistance and not has_big_green and not has_limit_up:
        return "weak"
    
    return "strong"
    score = 0

    # 必要条件
    if conditions.get("pullback_to_support"):
        score += 1
    if conditions.get("above_atr_stop"):
        score += 1

    # 加分条件：缩量回踩
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        if earlier_vol > 0 and recent_vol < earlier_vol * 0.8:
            score += 1

    # 加分条件：RSI 超卖反弹
    if bars and len(bars) >= 20:
        try:
            from trader_shared.momentum_core import calc_rsi
            closes = [float(b.get("close") or 0) for b in bars]
            rsi_vals = calc_rsi(closes)
            if rsi_vals and len(rsi_vals) >= 2:
                latest_rsi = rsi_vals[-1]
                prev_rsi = rsi_vals[-2]
                if latest_rsi is not None and prev_rsi is not None:
                    if prev_rsi < 30 and latest_rsi > prev_rsi:
                        score += 1
        except Exception:
            pass

    # 加分条件：MACD 底背离或金叉
    if bars and len(bars) >= 30:
        try:
            from trader_shared.momentum_core import calc_macd
            closes = [float(b.get("close") or 0) for b in bars]
            macd = calc_macd(closes)
            if macd.get("golden_cross"):
                score += 1
        except Exception:
            pass

    return min(score, 5)


def _make_position_state(
    state: str,
    reason: str,
    position_pct: int,
    conditions: dict[str, bool],
    stop_price: float = 0.0,
    take_profit_price: float = 0.0,
) -> dict[str, Any]:
    """构建状态机返回值。"""
    return {
        "state": state,
        "state_code": POSITION_STATES.get(state, 0),
        "action": reason,
        "position_pct": position_pct,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "conditions": conditions,
        "transition_reason": reason,
    }


def _empty_position_state(state: str, reason: str) -> dict[str, Any]:
    """空状态返回值。"""
    return {
        "state": state,
        "state_code": POSITION_STATES.get(state, 0),
        "action": reason,
        "position_pct": 0,
        "stop_price": 0.0,
        "take_profit_price": 0.0,
        "conditions": {},
        "transition_reason": reason,
    }


# ── 条件止盈（威科夫信号驱动）──────────────────────────────────

def compute_conditional_take_profit(
    current_price: float,
    entry_price: float,
    stop_price: float,
    resistance_price: float,
    major_stage: str,
    wyckoff_result: dict[str, Any] | None = None,
    bars: list[dict[str, Any]] | None = None,
    atr14: float = 0.0,
) -> dict[str, Any]:
    """条件止盈（威科夫信号驱动，不是机械止盈）。

    三批退出：
      第一笔：BC 信号出现 → 卖 1/3（购买高潮，主力在出货）
      第二笔：1R 目标达到 → 卖 1/3（保本，锁定部分利润）
      第三笔：阶段转派发 或 筹码搬家 > 50% → 清仓（趋势变了）

    阻力位不再是"到了就卖"，而是"看信号决定"：
      - 大阳线突破 + 放量 → 继续持有
      - BC 信号 → 卖 1/3
      - UTAD 信号 → 立刻减仓
    """
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return {
            "risk_r": 0.0,
            "target_1r": 0.0,
            "exit_plan": [],
            "wyckoff_signals": {},
        }

    # 1R 计算
    risk_r = round(entry_price - stop_price, 2)
    target_1r = round(entry_price + risk_r, 2)

    # 提取威科夫信号
    bc_signal = False
    bc_reason = ""
    utad_signal = False
    utad_reason = ""
    if isinstance(wyckoff_result, dict):
        wyk = wyckoff_result.get("wyckoff", wyckoff_result)
        if isinstance(wyk, dict):
            bc_signal = wyk.get("bc_signal", False)
            bc_reason = wyk.get("bc_reason", "")
            utad_signal = wyk.get("upthrust_signal", False)
            utad_reason = wyk.get("upthrust_reason", "")

    # 构建三批退出计划
    exit_plan: list[dict[str, Any]] = []

    # 第一笔：BC 信号 → 卖 1/3
    if bc_signal:
        exit_plan.append({
            "price": None,
            "ratio": 0.33,
            "reason": "购买高潮（BC），减仓1/3",
            "condition": "BC 信号出现",
            "triggered": True,
        })
    else:
        exit_plan.append({
            "price": None,
            "ratio": 0.33,
            "reason": "等待 BC 信号",
            "condition": "BC 信号出现",
            "triggered": False,
        })

    # 第二笔：1R 目标
    exit_plan.append({
        "price": target_1r,
        "ratio": 0.33,
        "reason": "1R 目标，保本",
        "condition": "1R 达到",
        "triggered": current_price >= target_1r,
    })

    # 第三笔：阶段转派发
    exit_plan.append({
        "price": None,
        "ratio": 0.34,
        "reason": "阶段转派发，清仓",
        "condition": "阶段变化",
        "triggered": major_stage == "派发",
    })

    return {
        "risk_r": risk_r,
        "target_1r": target_1r,
        "exit_plan": exit_plan,
        "wyckoff_signals": {
            "bc_signal": bc_signal,
            "bc_reason": bc_reason,
            "utad_signal": utad_signal,
            "utad_reason": utad_reason,
        },
    }


# ── 止盈规则 ──────────────────────────────────────────────────

def compute_take_profit(
    stage: str,
    current: float,
    highest_close: float,
    atr_pct: float,
    market_env: str = "震荡市",
) -> dict[str, Any]:
    """止盈规则：不主动止盈，只在趋势反转时退出。

    移动止损（保护利润）:
      主升期不看止损，只看阶段
      阶段转派发后，移动止损生效
      移动止损 = 最高收盘价 × (1 - ATR% × 倍数)

    大盘环境决定参数:
      牛市: ATR×4.0，不主动止盈
      震荡市: ATR×3.0，阻力位减仓
      熊市: ATR×2.0，快止盈
    """
    # ATR 倍数根据大盘环境
    env_multipliers = {"牛市": 4.0, "震荡市": 3.0, "熊市": 2.0}
    mult = env_multipliers.get(market_env, 3.0)

    if stage == "主升":
        # 主升期不看止损，只看阶段
        trailing_stop = None
        action = "让利润跑，阶段转派发再减仓"
    elif stage == "派发":
        # 派发期移动止损生效
        trailing_stop = round(highest_close * (1 - atr_pct * mult), 2)
        action = f"移动止损 {trailing_stop:.2f}，跌破减仓"
    elif stage == "衰退":
        # 衰退期清仓
        trailing_stop = round(highest_close * (1 - atr_pct * 2.0), 2)
        action = "衰退期清仓"
    else:
        # 蓄势期用技术止损
        trailing_stop = None
        action = "蓄势期用技术止损"

    return {
        "trailing_stop": trailing_stop,
        "action": action,
        "atr_multiplier": mult,
        "market_env": market_env,
    }
