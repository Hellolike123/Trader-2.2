"""主力行为独立评分模块（15分制）。

在 main_force.py 阶段识别的基础上，提供细粒度的 15 分制评分，
用于选股池打分和输出展示。

评分维度：
  - 资金流向（6分）：累计净流入、连续流入天数、净流入占比
  - 筹码搬家（5分）：支撑稳定性、阻力变化、警告级别
  - 大单异动（4分）：大单密度、净买卖比、有效性

用法:
    from trader_shared.main_force_scoring import score_main_force
    result = score_main_force(features, chip_migration, big_order_summary, bars)
"""

from __future__ import annotations

from typing import Any


def score_main_force(
    features: dict[str, Any],
    chip_migration: dict[str, Any],
    big_order: dict[str, Any],
    bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """主力行为 15 分制评分。

    Args:
        features: calc_fund_flow_features() 返回值
        chip_migration: check_chip_migration() 返回值
        big_order: analyze_big_orders() 返回值
        bars: 近期K线数据（可选，用于补充计算）

    Returns:
        {
            "total_score": int,        # 总分 0-15
            "flow_score": int,         # 资金流向分 0-6
            "chip_score": int,         # 筹码搬家分 0-5
            "order_score": int,        # 大单异动分 0-4
            "detail": { ... },         # 各维度详细解释
            "label": str,              # 中文等级标签
        }
    """
    flow = _score_flow(features)
    chip = _score_chip(chip_migration)
    order = _score_order(big_order)
    total = flow + chip + order

    label = _score_to_label(total)

    detail: dict[str, Any] = {
        "flow_points": flow,
        "flow_max": 6,
        "chip_points": chip,
        "chip_max": 5,
        "order_points": order,
        "order_max": 4,
        "signals": _build_signals(features, chip_migration, big_order),
    }

    return {
        "total_score": total,
        "flow_score": flow,
        "chip_score": chip,
        "order_score": order,
        "detail": detail,
        "label": label,
    }


# ── 资金流向评分（6分） ──────────────────────────────────────────

def _score_flow(features: dict[str, Any]) -> int:
    """资金流向 0-6 分。

    评分因子：
      - 累计净流入方向（2分）
      - 连续流入天数（2分）
      - 净流入占成交额比（2分）
    """
    cum_5 = features.get("cum_flow_5d_wan", 0)
    cum_10 = features.get("cum_flow_10d_wan", 0)
    con_in = features.get("consecutive_inflow_days", 0)
    net_pct = features.get("net_flow_pct", 0)
    relation = features.get("flow_price_relation", "")

    score = 0

    # 累计净流入方向（2分）
    if cum_5 > 0:
        score += 1
    if cum_5 > 1000:
        score += 1  # 大额流入加分
    elif cum_5 > 500:
        score += 0  # 中等不额外加分

    # 连续流入天数（2分）
    if con_in >= 5:
        score += 2
    elif con_in >= 3:
        score += 1
    elif con_in >= 1 and cum_5 > 0:
        score += 0  # 仅1天不加分

    # 净流入占成交额比（2分）
    if net_pct > 0.05:
        score += 2
    elif net_pct > 0.02:
        score += 1
    elif net_pct > 0:
        score += 0

    # 价资关系加分/减分
    if relation == "价跌资入":
        score = min(6, score + 1)  # 最健康的吸筹信号
    elif relation == "价涨资出":
        score = max(0, score - 1)  # 高位出货信号

    return min(6, max(0, score))


# ── 筹码搬家评分（5分） ──────────────────────────────────────────

def _score_chip(chip_migration: dict[str, Any]) -> int:
    """筹码搬家 0-5 分。

    评分因子：
      - 支撑稳定性（2分）
      - 阻力变化（2分）
      - 警告级别（1分）
    """
    score = 0
    warning_level = chip_migration.get("warning_level", "none")
    support_info = chip_migration.get("support_migration")
    resistance_info = chip_migration.get("resistance_migration")

    # 支撑稳定性（2分）
    if support_info:
        diff = support_info.get("diff", 0)
        if diff >= 0.5:
            score += 2  # 支撑增强
        elif diff >= 0:
            score += 1  # 支撑稳定
        elif diff >= -0.5:
            score += 0  # 支撑小幅减弱
        else:
            score += -1  # 支撑大幅减弱（扣分后归零）

    # 阻力变化（2分）
    if resistance_info:
        diff = resistance_info.get("diff", 0)
        if diff <= -0.5:
            score += 2  # 阻力减轻
        elif diff <= 0:
            score += 1  # 阻力稳定
        elif diff <= 0.5:
            score += 0  # 阻力小幅增加
        else:
            score += -1  # 阻力大幅增加

    # 警告级别（1分）
    if warning_level == "none":
        score += 1
    elif warning_level == "warning":
        score += 0  # 警告不加分也不减分
    elif warning_level == "critical":
        score = max(0, score - 1)  # 危险信号

    return min(5, max(0, score))


# ── 大单异动评分（4分） ──────────────────────────────────────────

def _score_order(big_order: dict[str, Any]) -> int:
    """大单异动 0-4 分。

    评分因子：
      - 大单密度（1分）
      - 净买卖比（2分）
      - 走势验证（1分）
    """
    score = 0
    events = big_order.get("events", [])
    by_side = big_order.get("by_side", {})
    validation = big_order.get("validation")

    # 大单密度（1分）
    if len(events) >= 3:
        score += 1
    elif len(events) >= 1:
        score += 0  # 至少有一次记录

    # 净买卖比（2分）
    buy_hands = by_side.get("主动买入", {}).get("hands", 0) or 0
    sell_hands = by_side.get("主动卖出", {}).get("hands", 0) or 0
    total_hands = buy_hands + sell_hands
    if total_hands > 0:
        buy_ratio = buy_hands / total_hands
        if buy_ratio > 0.6:
            score += 2
        elif buy_ratio > 0.5:
            score += 1
        elif buy_ratio > 0.4:
            score += 0  # 接近平衡
        else:
            score = max(0, score - 1)  # 卖方主导

    # 走势验证（1分）
    if validation:
        verdict = validation.get("verdict", "")
        if verdict == "有效":
            score += 1
        elif verdict == "背离":
            score = max(0, score - 1)
        # "无效" 不加分不扣分

    return min(4, max(0, score))


# ── 等级标签 ─────────────────────────────────────────────────────

def _score_to_label(total: int) -> str:
    """总分 0-15 → 等级标签。"""
    if total >= 13:
        return "🟢主力强势"
    elif total >= 9:
        return "🟡主力参与"
    elif total >= 5:
        return "🟠主力观望"
    else:
        return "🔴主力撤离"


# ── 信号聚合 ─────────────────────────────────────────────────────

def _build_signals(
    features: dict[str, Any],
    chip_migration: dict[str, Any],
    big_order: dict[str, Any],
) -> list[str]:
    """聚合来自三个子维度的关键信号。"""
    signals: list[str] = []

    # 资金流向信号
    cum_5 = features.get("cum_flow_5d_wan", 0)
    con_in = features.get("consecutive_inflow_days", 0)
    con_out = features.get("consecutive_outflow_days", 0)
    relation = features.get("flow_price_relation", "")

    if con_in >= 3:
        signals.append(f"连续{con_in}日主力净流入")
    if con_out >= 3:
        signals.append(f"连续{con_out}日主力净流出")
    if relation == "价跌资入":
        signals.append("价跌资入（健康吸筹）")
    elif relation == "价涨资出":
        signals.append("价涨资出（警惕派发）")
    if cum_5 > 5000:
        signals.append(f"5日累计净流入{cum_5:.0f}万")

    # 筹码搬家信号
    warning_text = chip_migration.get("warning_text", "")
    if warning_text:
        signals.append(warning_text)

    # 大单信号
    direction = big_order.get("direction_summary", "")
    if direction:
        signals.append(direction)
    validation = big_order.get("validation")
    if validation:
        v_text = f"大单{validation.get('verdict', '')}"
        signals.append(v_text)

    return signals
