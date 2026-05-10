"""Trader output contracts — per-skill validation rules, exact copy of originals."""
from __future__ import annotations

import sys
from pathlib import Path

_shared = Path(__file__).resolve().parents[1]
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))

from contract_utils import (
    nonempty_lines,
    read_text,
    section,
    validate_banned,
    validate_headings,
    validate_plain_output_format,
)

# ═══════════════════════════════════════════════
# 01-trader
# ═══════════════════════════════════════════════

TRADER_BANNED = (
    "必涨", "必跌", "主力入场第一枪", "出货日", "行情结束",
    "enhanced_v1", "daily_basic_v1", "buyback_price", "精确筹码分布",
    "t0-trader", "做T", "做 T", "执行价",
    "规则版本", "分析时间",
    "📱 单票分析报告", "✅ 先给结论", "⏱️ T0 简版",
    "🎯 今日行动", "📏 仓位上限", "🧭 为什么",
    "⚠️ 如果走势不对", "📌 最终行动卡",
    "需要盘中 T0 精细买卖点分析的话，说一声",
    "ATR14=", "ATR/价格=", "极端波动", "高波动", "低波动",
    "T0买入价", "T0卖出价", "T0失效价", "T0卖出观察",
)

TRADER_LOGIC_PREFIXES = ("结构：", "量价：", "压力：", "反向：")


def _validate_plain_report_format(lines: list[str], markdown: str) -> list[str]:
    errors: list[str] = []
    if not lines or not lines[0].startswith(("分析报告 — ", "📍")):
        errors.append("report must start with 分析报告 —")
    if any(line.startswith("#") for line in lines):
        errors.append("markdown heading syntax is not allowed")
    if any(line in {"---", "***", "___"} for line in lines):
        errors.append("horizontal rules are not allowed")
    if any(line.startswith(">") for line in lines):
        errors.append("blockquotes are not allowed")
    if "**" in markdown:
        errors.append("bold markdown markers are not allowed")
    if any(line.startswith(("- ", "* ")) for line in lines):
        errors.append("markdown bullet lists are not allowed")
    if not any("MA5" in line and "MA10" in line and "MA20" in line and "MA30" in line for line in lines):
        errors.append("top summary must include MA5 / MA10 / MA20 / MA30")
    return errors


def _validate_fixed_content(lines: list[str], markdown: str) -> list[str]:
    errors: list[str] = []
    for required in ("止跌确认", "止损", "最多"):
        if required not in markdown:
            errors.append(f"missing fixed panel text: {required}")
    return errors


def validate_trader(markdown: str) -> list[str]:
    errors: list[str] = []
    lines = nonempty_lines(markdown)
    errors.extend(_validate_plain_report_format(lines, markdown))
    
    # Refactoring in progress — headings validated only after finalized
    #errors.extend(validate_headings(lines, TRADER_HEADINGS_V2, "headings must follow Trader V2 panel order"))
    
    errors.extend(_validate_fixed_content(lines, markdown))
    errors.extend(validate_banned(markdown, TRADER_BANNED, "report must not contain banned old-template term"))
    return errors


# ═══════════════════════════════════════════════
# 02-t0-trader
# ═══════════════════════════════════════════════

T0_BANNED = (
    "必涨", "必跌", "主力入场第一枪", "出货日", "行情结束", "满仓",
    "📊 今日5分钟线复盘", "开盘急杀", "止跌尝试", "反弹修复", "横盘蓄力",
    "⏱️ 盘中 T0", "T0 执行卡", "🎯 价格地图", "🚦 执行条件", "一句话",
    "📉 低吸计划", "📈 高抛计划", "最多动：",
    "T0卖出观察：", "T0买入价", "T0卖出价", "T0失效价",
    "规则版本：", "数据状态：", "今日做法：", "当前动作：",
    "先买后卖", "先卖后买",
    "极端波动", "高波动", "低波动",
)


def validate_t0(markdown: str) -> list[str]:
    errors: list[str] = []
    lines = nonempty_lines(markdown)
    errors.extend(validate_plain_output_format(markdown, lines))
    if not lines or not lines[0].startswith("🎯 T0"):
        errors.append("report must start with 🎯 T0")
    for label in ("买入", "卖出", "仓位", "止损"):
        if not any(label in line for line in lines):
            errors.append(f"missing line: {label}")
    errors.extend(validate_banned(markdown, T0_BANNED, "T0 output contains banned old-template term"))
    return errors


# ═══════════════════════════════════════════════
# 03-trader-pool  (no banned list, special logic)
# ═══════════════════════════════════════════════

POOL_REQUIRED_PLAN = ("选股池盘后分析", "明日优先级", "结构评分", "上涨动能过滤", "明日交易指导卡", "仓位纪律", "一句话")
POOL_REQUIRED_REVIEW = ("选股池次日复盘", "复盘命中表", "复盘短评", "明日调整")


def validate_pool(markdown: str) -> list[str]:
    errors: list[str] = []
    if "选股池盘后分析" in markdown:
        required_headings = ("选股池盘后分析", "明日优先级", "结构评分", "上涨动能过滤", "明日交易指导卡", "仓位纪律", "一句话")
        for item in required_headings:
            if item not in markdown:
                errors.append(f"plan output missing section: {item}")
    elif "选股池次日复盘" in markdown:
        required_headings = ("选股池次日复盘", "复盘命中表", "复盘短评", "明日调整")
        for item in required_headings:
            if item not in markdown:
                errors.append(f"review output missing section: {item}")
    elif "选股池" in markdown:
        if "/" not in markdown:
            errors.append("show output missing pool capacity")
    elif "入池建议" in markdown:
        for item in ("结果：", "理由：", "建议状态：", "下一步：如确认，请说“加入选股池”"):
            if item not in markdown:
                errors.append(f"analyze output missing field: {item}")
    else:
        errors.append("output is not a recognized trader-pool panel")
    return errors


# ═══════════════════════════════════════════════
# 04-trader-portfolio
# ═══════════════════════════════════════════════

PORTFOLIO_HEADINGS = ["📌 组合", "🎯 操作", "📍 关键价位", "🧭 结论"]
PORTFOLIO_SNAPSHOT_HEADINGS = [
    "🧺 高切低轮动面板", "📌 当前结论", "📊 当前仓位",
    "🔁 轮动动作", "🎯 关键价位", "🛑 卖完条件",
    "🚫 禁止动作", "📈 后续复盘", "👉 一句话",
]
PORTFOLIO_BANNED = (
    "必涨", "必跌", "主力入场第一枪", "出货日", "行情结束",
    "先买后卖", "先卖后买",
    "pandas", "requests", "akshare",
    "ATR14=", "极端波动", "高波动", "低波动",
)


def validate_portfolio(markdown: str) -> list[str]:
    errors: list[str] = []
    lines = nonempty_lines(markdown)
    if lines and lines[0].startswith("🧺 高切低轮动面板"):
        if "规则版本：trader_portfolio_rotation_v1" not in lines:
            errors.append("missing contract marker: 规则版本：trader_portfolio_rotation_v1")
        errors.extend(validate_headings(lines, PORTFOLIO_SNAPSHOT_HEADINGS,
                       "headings must follow snapshot portfolio fixed order"))
        errors.extend(validate_banned(markdown, PORTFOLIO_BANNED))
        return errors
    if not lines or not lines[0].startswith("轮动仓位 — "):
        errors.append("report must start with 轮动仓位 —")
    errors.extend(validate_headings(lines, PORTFOLIO_HEADINGS, "headings must follow portfolio V2 order"))
    for required in ("仓位", "操作", "止损"):
        if required not in markdown:
            errors.append(f"missing content: {required}")
    errors.extend(validate_banned(markdown, PORTFOLIO_BANNED))
    return errors


# ═══════════════════════════════════════════════
# 05-review-trader
# ═══════════════════════════════════════════════

REVIEW_COMPARE_REQUIRED = ["结论：", "排序：", "主盯：", "副盯：", "只观察 / 先防守：", "明日动作："]
REVIEW_BANNED = (
    "必涨", "必跌", "无脑加仓", "主力吸筹", "主力锁仓", "行情结束",
    "T0 执行卡", "T0买入价", "T0卖出价", "执行价",
    "|---|", "| 角色 | 行动 |", "| 操作 | 条件 |",
)


def _validate_review_single(lines: list[str], markdown: str) -> list[str]:
    errors: list[str] = []
    if not lines[0].startswith("📌 "):
        errors.append("single review must start with 📌 股票｜日期")
    # Compact panel — no fixed heading order enforced
    # Just check for required five-layer theory lines
    for required in ("缠论：", "威科夫：", "筹码：", "资金行为："):
        if required not in markdown:
            errors.append(f"missing five-layer theory line: {required}")
    if "资金行为：" in markdown and not any(term in markdown for term in ("嫌疑", "可能", "证据不足")):
        errors.append("fund behavior must be probabilistic")
    return errors


def _validate_review_compare(lines: list[str]) -> list[str]:
    errors: list[str] = []
    if not lines[0].startswith("📌 多股复盘比较｜"):
        errors.append("compare output must start with 📌 多股复盘比较｜日期")
    for required in REVIEW_COMPARE_REQUIRED:
        if required not in lines:
            errors.append(f"compare output missing section: {required}")
    return errors


def validate_review(markdown: str) -> list[str]:
    lines = nonempty_lines(markdown)
    if not lines:
        return ["empty output"]
    errors: list[str] = []
    if any(line.startswith("#") for line in lines):
        errors.append("markdown heading syntax is not allowed")
    if any(line.startswith(("- ", "* ")) for line in lines):
        errors.append("markdown bullet lists are not allowed")
    if any(line.startswith("|") and line.endswith("|") for line in lines):
        errors.append("markdown tables are not allowed; keep WeChat block format")
    if lines[0].startswith("📌 多股复盘比较｜"):
        errors.extend(_validate_review_compare(lines))
    else:
        errors.extend(_validate_review_single(lines, markdown))
    errors.extend(validate_banned(markdown, REVIEW_BANNED, "review output contains banned term"))
    return errors
