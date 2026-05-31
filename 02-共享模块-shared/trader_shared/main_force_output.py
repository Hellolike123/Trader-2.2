"""主力行为复盘输出格式化。

用法:
    from trader_shared.main_force import format_main_force_section
    text = format_main_force_section(mf_result)
"""

from __future__ import annotations

from typing import Any

from trader_shared.main_force import STAGE_LABELS


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

    # 派发/砸盘警告
    if stage in ("distribution", "markdown"):
        lines.append("⚠️ 主力资金持续流出，谨慎追高")

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
