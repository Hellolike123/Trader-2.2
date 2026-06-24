"""主力行为复盘输出格式化。

用法:
    from trader_shared.main_force import format_main_force_section
    text = format_main_force_section(mf_result)
"""

from __future__ import annotations

from typing import Any

from trader_shared.main_force import STAGE_LABELS


def format_main_force_score_section(result: dict[str, Any], score_result: dict[str, Any] | None = None) -> str:
    """生成主力行为评分段落（微信纯文本格式）。

    Args:
        result: detect_main_force_stage() 返回值
        score_result: score_main_force() 返回值（15分制），None 时降级输出

    Returns:
        微信端纯文本格式的主力行为评分段落
    """
    stage = result.get("stage", "unknown")
    if stage == "unknown" and not result.get("daily_flow_5d"):
        return "💰 主力行为 ｜ 🔴数据暂不可用"

    stage_cn = STAGE_LABELS.get(stage, "未知")

    if score_result and score_result.get("total_score") is not None:
        total = score_result["total_score"]
        label = score_result.get("label", "🔴无数据")
        flow = score_result.get("flow_score", 0)
        chip = score_result.get("chip_score", 0)
        order = score_result.get("order_score", 0)
        detail = score_result.get("detail", {})
        signals = detail.get("signals", [])

        lines = [
            "💰 主力行为",
            f"阶段：{stage_cn} ｜ 综合 {total}/15（{label}）",
            f"  资金 {flow}/6 ｜ 筹码 {chip}/5 ｜ 大单 {order}/4",
        ]

        if signals:
            # 只显示前3个关键信号
            for s in signals[:3]:
                lines.append(f"  ·{s}")

        return "\n".join(lines)
    else:
        # 降级：只显示阶段
        return f"💰 主力行为 ｜ {stage_cn}"


def format_main_force_section(result: dict[str, Any]) -> str:
    """生成主力行为复盘段落。

    Args:
        result: detect_main_force_stage() 的返回值

    Returns:
        遵守微信端纯文本规范的主力行为段落
    """
    stage = result.get("stage", "unknown")
    confidence = result.get("confidence", 0)
    cum_5 = result.get("cum_flow_5d_wan", 0)
    cum_10 = result.get("cum_flow_10d_wan", 0)
    con_in = result.get("consecutive_inflow_days", 0)
    con_out = result.get("consecutive_outflow_days", 0)
    relation = result.get("flow_price_relation", "无数据")
    signals = result.get("signals", [])
    daily_5d = result.get("daily_flow_5d", [])

    if stage == "unknown" and not daily_5d:
        return "💰 主力行为\n资金流向数据暂不可用"

    stage_cn = STAGE_LABELS.get(stage, "未知")

    # 趋势符号
    trend_str = _format_trend(daily_5d)

    # 今日净流入
    today_flow = daily_5d[-1] if daily_5d else 0

    # 关键提示
    hint = _build_hint(stage, con_in, con_out, signals)

    lines = [
        "💰 主力行为",
        f"阶段：{stage_cn}（置信度 {confidence:.1f}）",
        f"资金：近5日累计净流入 {cum_5:+.0f}万 ｜ 今日净流入 {today_flow:+.0f}万",
        f"关系：{relation}",
        f"趋势：{trend_str}",
    ]

    if hint:
        lines.append(f"提示：{hint}")

    # 主力派发/砸盘警告
    if stage == "distribution":
        lines.append("⚠️ 高位派发，资金持续流出，谨防接盘")
    elif stage == "markdown":
        lines.append("⚠️ 砸盘进行中，资金持续流出，不宜抄底")

    return "\n".join(lines)


def _format_trend(daily_5d: list[float]) -> str:
    """将近5日每日净流入转为趋势符号。"""
    if not daily_5d:
        return "无数据"
    symbols = []
    in_count = 0
    out_count = 0
    for v in daily_5d[-5:]:
        if v > 0:
            symbols.append("↑")
            in_count += 1
        elif v < 0:
            symbols.append("↓")
            out_count += 1
        else:
            symbols.append("→")
    return f"{''.join(symbols)}（近5日，{in_count}流入{out_count}流出）"


def _build_hint(stage: str, con_in: int, con_out: int, signals: list[str]) -> str:
    """生成关键提示。"""
    if stage == "accumulation" and con_in >= 3:
        return f"连续{con_in}日净流入，关注是否放量突破"
    if stage == "markup" and con_in >= 3:
        return f"连续{con_in}日净流入，拉升进行中"
    if stage == "distribution" and con_out >= 2:
        return f"连续{con_out}日净流出，注意风险"
    if stage == "markdown" and con_out >= 3:
        return f"连续{con_out}日净流出，建议回避"
    if signals:
        return signals[0]
    return ""


def format_flow_trend(daily_5d: list[float]) -> str:
    """Format daily flow trend with arrow symbols.

    Args:
        daily_5d: list of daily net flow values (万元)

    Returns:
        Trend string like "↑↑↓↑↓" or "无数据"
    """
    if not daily_5d:
        return "无数据"
    symbols = []
    for v in daily_5d[-5:]:
        if v > 0:
            symbols.append("↑")
        elif v < 0:
            symbols.append("↓")
        else:
            symbols.append("→")
    return "".join(symbols)


def format_main_force_enhanced(
    result: dict[str, Any],
    today_super_large: float = 0.0,
    today_large: float = 0.0,
) -> str:
    """Generate enhanced main force section with super-large/large order breakdown.

    Args:
        result: detect_main_force_stage() return value
        today_super_large: today's super-large order net flow (万元)
        today_large: today's large order net flow (万元)

    Returns:
        Formatted section following WeChat plain-text rules
    """
    stage = result.get("stage", "unknown")
    confidence = result.get("confidence", 0)
    cum_5 = result.get("cum_flow_5d_wan", 0)
    con_in = result.get("consecutive_inflow_days", 0)
    con_out = result.get("consecutive_outflow_days", 0)
    relation = result.get("flow_price_relation", "无数据")
    signals = result.get("signals", [])
    daily_5d = result.get("daily_flow_5d", [])

    if stage == "unknown" and not daily_5d:
        return "💰 主力资金\n资金流向数据暂不可用"

    stage_cn = STAGE_LABELS.get(stage, "未知")
    trend_str = format_flow_trend(daily_5d)
    today_flow = daily_5d[-1] if daily_5d else 0
    hint = _build_hint(stage, con_in, con_out, signals)

    # Consecutive days info
    consecutive_text = ""
    if con_in >= 2:
        consecutive_text = f"连续{con_in}日净流入"
    elif con_out >= 2:
        consecutive_text = f"连续{con_out}日净流出"

    lines = [
        "💰 主力资金",
        f"阶段：{stage_cn}（置信度 {confidence:.1f}）",
    ]

    # 近5日累计 + 趋势 + 连续天数
    cum_line = f"近5日：{cum_5:+.0f}万（{trend_str}）"
    if consecutive_text:
        cum_line += f" {consecutive_text}"
    lines.append(cum_line)

    # 今日明细（超大单/大单拆分）
    today_line = f"今日：{today_flow:+.0f}万"
    if today_super_large != 0 or today_large != 0:
        today_line += f"（超大单 {today_super_large:+.0f}万｜大单 {today_large:+.0f}万）"
    lines.append(today_line)

    lines.append(f"价资关系：{relation}")

    if hint:
        lines.append(f"提示：{hint}")

    # 主力派发/砸盘警告
    if stage == "distribution":
        lines.append("⚠️ 高位派发，资金持续流出，谨防接盘")
    elif stage == "markdown":
        lines.append("⚠️ 砸盘进行中，资金持续流出，不宜抄底")

    return "\n".join(lines)
