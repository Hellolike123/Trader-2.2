#!/usr/bin/env python3
"""每日简报（daily-briefing）— 从大量候选池中自动分析、排序、分层。

用法：
    # 刷新选股池
    python3 briefing.py

    # 只分析指定票
    python3 briefing.py --watch A B C

    # 分析候选文件
    python3 briefing.py --candidates candidates.json

    # 刷新全池数据
    python3 briefing.py --refresh

    # 快速分析并加入池
    python3 briefing.py --candidate A --add
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

# Suppress noisy stdout during analysis
class _Silencer:
    def write(self, *args, **kwargs):
        pass
    def flush(self, *args, **kwargs):
        pass
_silencer = _Silencer()

# Ensure the project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "02-共享模块-shared"))
sys.path.insert(0, str(PROJECT_ROOT / "01-功能包-packages" / "trader" / "scripts"))

from trader_shared.light_data import to_float
from trader_shared.config import LOOKBACK_DAYS


# ── Paths ────────────────────────────────────────────────────────────────
POOLS_DIR = Path(os.path.expanduser("~/.trader"))
POOL_FILE = POOLS_DIR / "pool.json"
CANDIDATES_FILE = POOLS_DIR / "candidates.json"
LAST_PLAN_FILE = POOLS_DIR / "last_plan.json"


# ── Pool helpers ─────────────────────────────────────────────────────────
def load_pool() -> dict[str, Any]:
    """Load pool.json, returning empty dict if missing."""
    if not POOL_FILE.exists():
        return {"items": []}
    try:
        with open(POOL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"items": []}


def save_pool(data: dict[str, Any]) -> None:
    """Save pool.json."""
    POOLS_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Build report (parallel) ─────────────────────────────────────────────
def _build_report_one(target: str) -> dict[str, Any]:
    """Run build_report for a single stock, returning result dict."""
    try:
        from run_analysis import build_report
        from final_pool import score_report
        report = build_report(target)
        scores = score_report(report)
        report.update(scores)
        return {"target": target, "success": True, "report": report}
    except Exception as exc:
        return {"target": target, "success": False, "error": str(exc), "report": None}


def build_reports_parallel(targets: list[str], max_workers: int = 8) -> list[dict[str, Any]]:
    """Build reports for multiple stocks in parallel."""
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_build_report_one, t): t for t in targets}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
    return results


# ── Admission & Layering ─────────────────────────────────────────────────
# Reuse existing admission thresholds
ADMISSION_SCORE_EXECUTE = {
    "蓄势": 80,
    "主升": 60,
    "派发": 999,  # disabled for execution
    "衰退": 999,  # disabled
}
ADMISSION_SCORE_OBSERVE = {
    "蓄势": 70,
    "主升": 999,  # disabled (main-sheng is always execution)
    "派发": 70,
    "衰退": 999,  # disabled
}


def evaluate_admission(major_stage: str, total_score: int, current: float, stop: float) -> dict[str, Any]:
    """Evaluate admission and determine layer."""
    # Layer 1: stage screening
    if major_stage == "衰退":
        return {"result": "拒绝", "reason": "衰退期，直接拒绝入池。", "status": "放弃"}

    # Layer 2: score thresholds
    exec_threshold = ADMISSION_SCORE_EXECUTE.get(major_stage, 999)
    obs_threshold = ADMISSION_SCORE_OBSERVE.get(major_stage, 999)

    if total_score >= exec_threshold:
        status = "执行"
    elif total_score >= obs_threshold:
        status = "观察"
    else:
        return {"result": "待补", "reason": f"{major_stage}期但评分不足，暂不入池。", "status": "待补"}

    # Layer 3: risk check
    if stop > 0 and current <= stop:
        return {"result": "拒绝", "reason": "破防守位。", "status": "放弃"}

    return {"result": "入池", "reason": "结构成立，触发位和防守位清楚。", "status": status}


def layer_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Layer items into: 执行 / 观察 / 待补 / 放弃."""
    layers = {"执行": [], "观察": [], "待补": [], "放弃": []}
    for item in items:
        status = item.get("status", "放弃")
        if status in layers:
            layers[status].append(item)
        else:
            layers["放弃"].append(item)
    return layers


# ── Sorting ──────────────────────────────────────────────────────────────
def sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort items by: status_rank > total_score > -atr_ratio > fusion_confidence."""
    status_rank = {"执行": 4, "观察": 3, "待补": 2, "放弃": 1}
    stage_priority = {"主升": 1, "蓄势": 2, "派发": 3, "衰退": 4}

    def _fusion_rank(fc: Any) -> int:
        if isinstance(fc, str):
            return {"high": 3, "medium": 2, "low": 1}.get(fc, 0)
        return 0

    return sorted(items, key=lambda item: (
        status_rank.get(item.get("status", "放弃"), 0),
        -stage_priority.get(item.get("major_stage", ""), 5),
        int(item.get("total_score") or 0),
        -float(item.get("atr_ratio") or 0),
        _fusion_rank(item.get("fusion_confidence", "")),
    ), reverse=True)


# ── Rendering ────────────────────────────────────────────────────────────
def _trade_hint(item: dict[str, Any]) -> list[str]:
    """Generate a vertical trade hint for an item."""
    current = to_float(item.get("current")) or 0
    trigger = to_float(item.get("trigger") or item.get("confirm")) or 0
    defense = to_float(item.get("defense")) or 0
    support = to_float(item.get("support")) or 0

    if item.get("status") == "执行":
        if trigger > 0:
            return [f"买 {support:.2f}-{trigger:.2f}", f"止损 {defense:.2f}"]
        return [f"买 {support:.2f} 附近", f"止损 {defense:.2f}"]
    elif item.get("status") == "观察":
        if trigger > 0:
            return [f"关注 {trigger:.2f} 是否站稳，不买"]
        return ["关注支撑位，等确认"]
    elif item.get("status") == "待补":
        return ["评分不足，等转强（≥70）再观察"]
    return ["放弃"]


def _theory_level(score: int, max_score: int) -> str:
    """Determine if a theory score is strong/adequate/weak."""
    ratio = score / max_score
    if ratio >= 0.75:
        return "强"
    elif ratio >= 0.5:
        return "及格"
    return "弱"


def _classification_reason(item: dict[str, Any]) -> str:
    """Explain why an item landed in its layer."""
    cl = int(item.get("chanlun_score", 0))
    wy = int(item.get("wyckoff_score", 0))
    cp = int(item.get("chip_score", 0))
    score = cl + wy + cp
    status = item.get("status", "")

    # Ratio >= 0.75 = strong, >= 0.5 = pass, else = weak
    cl_ratio = cl / 45 if 45 > 0 else 0
    wy_ratio = wy / 30 if 30 > 0 else 0
    cp_ratio = cp / 25 if 25 > 0 else 0

    strong_count = sum(1 for r in (cl_ratio, wy_ratio, cp_ratio) if r >= 0.75)
    weak_count = sum(1 for r in (cl_ratio, wy_ratio, cp_ratio) if r < 0.5)

    scores = [("缠论", cl, cl_ratio), ("威科夫", wy, wy_ratio), ("筹码", cp, cp_ratio)]
    scores.sort(key=lambda x: x[2], reverse=True)
    weakest = scores[-1]

    if status == "执行":
        if strong_count == 3:
            return f"缠{cl}｜威{wy}｜筹{cp}，结构全面成立"
        elif strong_count >= 2:
            return f"缠{cl}｜威{wy}｜筹{cp}，结构基本成立"
        return f"缠{cl}｜威{wy}｜筹{cp}，勉强过线"
    elif status == "观察":
        trigger = item.get("trigger", 0) or item.get("confirm", 0)
        if trigger > 0:
            return f"还没站稳{trigger:.2f}，等确认"
        return f"暂无明确信号，等确认"
    elif status == "待补":
        if weak_count >= 2:
            return f"缠{cl}｜威{wy}｜筹{cp}，多个理论偏弱"
        return f"缠{cl}｜威{wy}｜筹{cp}，{weakest[0]}未过关"
    return "放弃"


def _gap_pct(current: float, target: float) -> float:
    """当前价距目标的百分比（正数表示目标更高）。"""
    if current <= 0 or target <= 0:
        return 0.0
    return (target - current) / current * 100


def _theory_assess(cl: int, wy: int, cp: int) -> tuple[str, str, str]:
    """评估三大理论各处于什么水平，返回 (最强, 最弱) 的名称。"""
    cl_r = cl / 45
    wy_r = wy / 30
    cp_r = cp / 25
    entries = [("缠论", cl_r), ("威科夫", wy_r), ("筹码", cp_r)]
    entries.sort(key=lambda x: x[1], reverse=True)
    return entries[0][0], entries[-1][0]


def _theory_verdict(ratio: float) -> str:
    """判断理论比例对应的结论。"""
    if ratio >= 0.75:
        return "强"
    if ratio >= 0.5:
        return "及格"
    return "弱"


def _analysis_lines(item: dict[str, Any]) -> list[str]:
    """生成每只票的多维度技术分析解读。"""
    lines = []
    cl = int(item.get("chanlun_score", 0))
    wy = int(item.get("wyckoff_score", 0))
    cp = int(item.get("chip_score", 0))
    status = item.get("status", "")
    current = to_float(item.get("current")) or 0
    confirm = to_float(item.get("confirm", 0)) or 0
    support = to_float(item.get("support")) or 0
    resistance = to_float(item.get("resistance", 0)) or 0
    low_zone = str(item.get("low_zone", "") or "").strip()
    scene_label = str(item.get("scene", "") or "").strip()
    structure_note = str(item.get("structure_note", "") or "").strip()
    major_reason = str(item.get("major_reason", "") or "").strip()
    upward_momentum = str(item.get("upward_momentum", "") or "").strip()
    expma_trend = str(item.get("expma_trend", "") or "").strip()
    fusion_action = item.get("fusion_action", "") or ""
    stage_label = str(item.get("stage_status", "") or "")

    # 额外维度
    macd = item.get("macd_status", {}) or {}
    fib = item.get("fib_retrace", {}) or {}
    fusion = item.get("fusion", {}) or {}
    wyckoff = item.get("wyckoff") or {}
    time_window = item.get("time_window") or {}
    volume_text = str(item.get("volume_text", "") or "").strip()
    volume_note = str(item.get("volume_note", "") or "").strip()
    volume_vacuum = item.get("volume_vacuum") or {}
    chip_support = to_float(item.get("chip_support")) or 0
    chip_resistance = to_float(item.get("chip_resistance")) or 0
    chip_current_pct = to_float(item.get("chip_current_pct")) or 0
    chip_mid_price = to_float(item.get("chip_mid_price")) or 0
    expma20 = to_float(item.get("expma20")) or 0
    expma50 = to_float(item.get("expma50")) or 0
    ma_values = item.get("ma", {}) or {}
    ma5 = to_float(ma_values.get("ma5", 0))
    ma10 = to_float(ma_values.get("ma10", 0))
    ma20 = to_float(ma_values.get("ma20", 0))
    ma30 = to_float(ma_values.get("ma30", 0))
    support_source = str(item.get("support_source", "") or "").strip()
    resistance_source = str(item.get("resistance_source", "") or "").strip()
    stage_action = str(item.get("stage_action", "") or "").strip()
    momentum_reason = str(item.get("momentum_reason", "") or "").strip()

    cl_v = _theory_verdict(cl / 45)
    wy_v = _theory_verdict(wy / 30)
    cp_v = _theory_verdict(cp / 25)

    # ── 结构线（缠论 + 均线排列）──
    parts = []
    if structure_note:
        note = structure_note
        for suffix in ["，不是主升", "，不是主升"]:
            note = note.replace(suffix, "").strip()
        note = note.rstrip("，,，").strip()
        if note:
            parts.append(f"{note}，缠论{cl_v}（{cl}分）")
    else:
        parts.append(f"缠论{cl_v}，{cl}分")
    if expma_trend:
        parts.append(f"均线{expma_trend}")
    lines.append(f"结构：{'，'.join(parts)}")

    # ── 量价线（量比 + 均线关系 + 量能日）──
    if major_reason:
        vol_part = ""
        ma_part = ""
        atr_part = ""
        for seg in major_reason.split("|"):
            seg = seg.strip()
            if seg.startswith("量价:"):
                vol_part = seg.split(":", 1)[1].strip()
            elif seg.startswith("均线:"):
                ma_part = seg.split(":", 1)[1].strip()
            elif seg.startswith("ATR:"):
                atr_part = seg.split(":", 1)[1].strip()
        detail = vol_part
        if ma_part:
            detail += f" | {ma_part}"
        if atr_part:
            detail += f" | {atr_part}"
        # 补充量能日信息
        if volume_text:
            detail += f" | 量能日{volume_text.split('在 ', 1)[-1].split('，')[0] if '在 ' in volume_text else volume_text[:20]}"
        lines.append(f"量价：{detail}")
    else:
        lines.append(f"量价：威科夫{wy_v}，{wy}分")

    # ── 威科夫线（信号 + 摘要）──
    spring = wyckoff.get("spring_signal", False)
    upthrust = wyckoff.get("upthrust_signal", False)
    bc = wyckoff.get("bc_signal", False)
    sow = wyckoff.get("sow_signal", False)
    wy_summary = str(wyckoff.get("wyckoff_summary", "") or "").strip()
    bullish_vol_div = wyckoff.get("bullish_volume_divergence", False)
    bearish_vol_div = wyckoff.get("bearish_volume_divergence", False)
    wy_parts = []
    if spring:
        wy_parts.append("弹簧信号确认")
    elif upthrust:
        wy_parts.append("上冲回落信号")
    elif bc:
        wy_parts.append("购买高潮")
    elif sow:
        wy_parts.append("放弃下跌")
    elif bullish_vol_div:
        wy_parts.append("量能底背离")
    elif bearish_vol_div:
        wy_parts.append("量能顶背离")
    elif wy_summary and wy_summary != "无明显威科夫信号":
        wy_parts.append(wy_summary[:20])
    elif wy_v in ("强", "及格") and wy > 20:
        wy_parts.append(f"量价健康（{wy}分）")
    if wy_parts:
        lines.append(f"威科夫：{'，'.join(wy_parts[:2])}")

    # ── MACD线 ──
    if macd:
        cross_type = macd.get("golden_cross") or macd.get("death_cross")
        positive = macd.get("positive")
        cross_text = ""
        if cross_type == "macd_golden_cross":
            cross_text = "MACD金叉"
        elif cross_type == "macd_death_cross":
            cross_text = "MACD死叉"
        else:
            cross_text = "MACD"
        if positive is True:
            cross_text += "零轴上方"
        elif positive is False:
            cross_text += "零轴下方"
        if cross_text:
            lines.append(f"MACD：{cross_text}")

    # ── 筹码线 ──
    if chip_support > 0 and chip_resistance > 0:
        in_range = chip_support <= current <= chip_resistance
        pos_text = "内" if in_range else "上方" if current > chip_resistance else "下方"
        chip_detail = f"密集区{chip_support:.2f}-{chip_resistance:.2f}，现价{pos_text}"
        if chip_current_pct > 0:
            chip_detail += f"，集中度{chip_current_pct:.0f}%"
        if chip_mid_price > 0 and current > 0:
            dist_from_mid = (current - chip_mid_price) / chip_mid_price * 100
            chip_detail += f"，距中价{dist_from_mid:+.1f}%"
        lines.append(f"筹码：{chip_detail}")
    else:
        lines.append(f"筹码：{cp_v}（{cp}分）")

    # ── 关键位线（支撑 + 阻力来源）──
    support_info = f"{support:.2f}({support_source})" if support > 0 else ""
    resistance_info = f"{resistance:.2f}({resistance_source})" if resistance > 0 else ""
    if support_info or resistance_info:
        lines.append(f"关键位：{support_info} ｜ {resistance_info}")

    # ── 黄金挂单位（斐波那契分割低吸区）──
    golden_bid = fib.get("golden_bid")
    if golden_bid is not None:
        bid_val = to_float(golden_bid)
        if bid_val > 0:
            lines.append(f"黄金位：斐波那契38.2%挂单区{bid_val:.2f}附近")

    # ── 时间窗口（近期 pivot 天数）──
    bars_pivot = time_window.get("bars_since_pivot")
    if bars_pivot is not None and bars_pivot > 0:
        window_type = time_window.get("window_type", "")
        if window_type:
            lines.append(f"时间窗口：pivot后{bars_pivot}日，{window_type}")
        else:
            lines.append(f"时间窗口：pivot后{bars_pivot}日，窗口未激活")

    # ── 动能线（突破准备度 + 理论交叉验证）──
    # 理论一致性判断（只在有矛盾或都弱时显示）
    theory_note = ""
    if cl_v == "弱" and wy_v == "弱":
        theory_note = "结构与量价双弱"
    elif cl_v != wy_v:
        theory_note = "结构量价分歧"

    # 动能结论（去冗余：如果结论太长只取核心）
    if upward_momentum and "结论：" in upward_momentum:
        conclusion = upward_momentum.split("结论：", 1)[1].strip()
        # 截断过长的结论
        if len(conclusion) > 25:
            conclusion = conclusion[:25] + "…"
    elif upward_momentum:
        conclusion = upward_momentum[:60]
    else:
        conclusion = "未触发极值条件"

    # 量价备注
    vol_detail = volume_note if volume_note else ""

    # 组装动能行：理论验证 + 核心结论 + 差异化细节
    momentum_parts = [conclusion]
    if theory_note:
        momentum_parts.insert(0, theory_note)
    if vol_detail:
        momentum_parts.append(vol_detail)
    if momentum_reason and momentum_reason != "走势未匹配极强/极弱特征":
        momentum_parts.append(momentum_reason)
    lines.append(f"动能：{' ｜ '.join(momentum_parts)}")

    # ── 亮点/风险线（为什么关注 / 为什么谨慎）──
    highlights = []
    risks = []

    # 亮点判断
    if cl >= 35:
        highlights.append("结构强（缠论>35）")
    elif cl >= 25:
        highlights.append("结构及格（缠论25-35）")
    if wy >= 23:
        highlights.append("量价健康（威科夫>23）")
    if chip_current_pct > 0 and chip_support <= current <= chip_resistance:
        highlights.append("筹码锁定良好")
    if volume_text and "收涨" in volume_text:
        highlights.append("最近量能日收涨")
    if current >= confirm:
        highlights.append("已突破确认位")
    if current > 0 and support > 0 and current < support * 1.02:
        highlights.append("靠近支撑支撑位")

    # 风险判断
    macd_positive = macd.get("positive")
    if macd_positive is False:
        risks.append("MACD零轴下方")
    if expma_trend == "空头排列":
        risks.append("均线空头排列")
    elif expma_trend and "交叉" in expma_trend:
        risks.append("均线方向不明")
    if current > 0 and resistance > 0:
        if current > resistance * 1.03:
            risks.append("远离上方阻力，短期难触达")
    if wy < 15:
        risks.append("威科夫得分偏低")
    if current > 0 and chip_support > 0 and current < chip_support * 0.97:
        risks.append("跌破筹码密集区")
    if fusion_action in ("减仓", "空仓/止损"):
        risks.append(f"融合层{fusion_action}")

    # 至少显示一个亮点或风险
    if highlights or risks:
        hl_text = "；".join(highlights[:2]) if highlights else "无显著亮点"
        rl_text = "；".join(risks[:2]) if risks else "无显著风险"
        lines.append(f"亮点/风险：{hl_text} ｜ {rl_text}")

    # ── 决策线（价格位置 + 理论交叉验证）──
    if status == "执行":
        if fusion_action == "减仓" or "减仓" in scene_label:
            lines.append(f"决策：{scene_label}，逢高减一部分")
        elif current > 0 and support > 0 and confirm > 0:
            if current >= confirm:
                lines.append(f"决策：现价{current:.2f}站稳确认位{confirm:.2f}，结构成立")
            elif current >= support:
                gap = _gap_pct(current, confirm)
                lines.append(f"决策：现价{current:.2f}在支撑上方，距确认位{gap:.0f}%")
            else:
                lines.append(f"决策：现价{current:.2f}跌破支撑{support:.2f}，注意防守")
        else:
            lines.append("决策：在支撑区间等信号")
    elif status == "观察":
        if fusion_action in ("空仓/止损", "减仓"):
            lines.append("决策：融合层提示减仓，短期动能不足")
        elif current > 0 and confirm > 0:
            gap = _gap_pct(current, confirm)
            if gap <= 2:
                lines.append(f"决策：现价{current:.2f}距确认位{confirm:.2f}仅差{gap:.0f}%，等放量突破")
            elif gap <= 5:
                lines.append(f"决策：现价{current:.2f}距确认位{confirm:.2f}差{gap:.0f}%，量价确认后才跟进")
            else:
                lines.append(f"决策：现价{current:.2f}距确认位{confirm:.2f}差{gap:.0f}%，短期难到达")
        elif current > 0 and support > 0:
            lines.append(f"决策：现价{current:.2f}在支撑附近，等止跌确认")
        else:
            lines.append("决策：还没到触发位，先观望")
    elif status == "待补":
        if current > 0 and support > 0 and current < support:
            lines.append(f"决策：现价{current:.2f}跌破支撑{support:.2f}，结构未稳")
        elif current > 0 and confirm > 0:
            gap = _gap_pct(current, confirm)
            lines.append(f"决策：现价{current:.2f}距确认位{confirm:.2f}差{gap:.0f}%，短期难到达")
        else:
            lines.append("决策：结构未成型，等信号")

    return lines


def _briefing_one_liner(item: dict[str, Any]) -> str:
    """生成一句技术分析逻辑：为什么做 / 为什么不做。

    主行已显示分数和状态，这里不再复述，只给出交易决策的技术依据。
    """
    status = item.get("status", "")
    current = to_float(item.get("current")) or 0
    confirm = to_float(item.get("confirm", 0)) or 0
    support = to_float(item.get("support")) or 0
    stage = item.get("major_stage", "蓄势")
    scene_label = str(item.get("scene", "") or "").strip()
    structure_note = str(item.get("structure_note", "") or "").strip()
    volume_note = str(item.get("volume_note", "") or "").strip()
    major_reason = str(item.get("major_reason", "") or "").strip()
    fusion_action = item.get("fusion_action", "") or ""
    cl = int(item.get("chanlun_score", 0))
    wy = int(item.get("wyckoff_score", 0))
    cp = int(item.get("chip_score", 0))
    total = item.get("total_score", 0)

    # 评估三大理论
    strongest, weakest = _theory_assess(cl, wy, cp)
    cl_v = _theory_verdict(cl / 45)
    wy_v = _theory_verdict(wy / 30)
    cp_v = _theory_verdict(cp / 25)

    # ── 执行区：为什么可以做 ──────────────────────────────────────────
    if status == "执行":
        # 减仓场景
        if "减仓" in scene_label or fusion_action == "减仓":
            return "冲高到压力位，逢高减一部分"
        # 有结构备注 → 用结构备注（技术分析结论）
        if structure_note:
            return f"缠论结构{cl_v}，{structure_note}"
        # 有量能备注 → 用量能备注
        if volume_note:
            return f"量价{wy_v}，{volume_note}"
        # 三理论都及格 → 结构完整
        if cl_v != "弱" and wy_v != "弱" and cp_v != "弱":
            return f"缠论结构{cl_v}，量价{wy_v}，筹码{cp_v}，回踩支撑低吸"
        # 单一理论主导
        if strongest == "缠论" and cl_v == "强":
            return f"缠论结构{cl_v}，回踩支撑低吸"
        if strongest == "威科夫" and wy_v == "强":
            return f"威科夫量价{wy_v}，支撑位承接确认"
        return f"缠{cl_v}威{wy_v}筹{cp_v}，在支撑区间等机会"

    # ── 观察区：为什么还不做 ──────────────────────────────────────────
    elif status == "观察":
        gap = _gap_pct(current, confirm) if confirm > 0 else 999
        # fusion 给出负面信号
        if fusion_action == "减仓":
            return "冲不上去，逢高减一部分"
        if fusion_action == "空仓/止损":
            return "转弱信号，减仓观望"
        # 有结构备注 → 用结构备注解释
        if structure_note:
            return f"结构{structure_note}，等确认"
        # 有量能备注 → 用量能备注解释
        if volume_note:
            return f"量能{volume_note}，等确认"
        # 最弱理论拖累 → 解释什么没到位
        if weakest == "缠论" and cl_v == "弱":
            return f"缠论结构{cl_v}，等结构成型"
        if weakest == "威科夫" and wy_v == "弱":
            return f"威科夫量价{wy_v}，等量价确认"
        if weakest == "筹码" and cp_v == "弱":
            return f"筹码{cp_v}，等筹码集中"
        # 差得少 → 即将突破
        if gap <= 2:
            return "快到了，就差确认位这一下"
        # 差中等
        if gap <= 5:
            return "差一点到确认位，等放量突破"
        # 差得多
        if gap > 5:
            return "还有段距离，等回到确认位"
        return "还没到触发位，先不操作"

    # ── 待补区：为什么不够 ────────────────────────────────────────────
    elif status == "待补":
        gap = _gap_pct(current, confirm) if confirm > 0 else 999
        # 跌破支撑
        if current > 0 and support > 0 and current < support:
            return "跌破支撑，还没企稳"
        # 缠论结构特别弱
        if cl_v == "弱" and cl < 20:
            return f"缠论结构{cl_v}（{cl}分），结构未成型"
        # 有结构备注
        if structure_note:
            return f"结构{structure_note}，等转强"
        # 多数理论弱
        weak_count = sum(1 for v in [cl_v, wy_v, cp_v] if v == "弱")
        if weak_count >= 2:
            return f"缠{cl_v}威{wy_v}筹{cp_v}，多个理论未达标"
        # 差太多
        if gap > 10:
            return "差太多，等回到关键位再看"
        return "结构还没成型，先放着看"

    return "等信号"


def _format_layer_name(layer: str, count: int) -> str:
    desc_map = {
        "执行": "执行区",
        "观察": "观察区",
        "待补": "待补区",
        "放弃": "",
    }
    desc = desc_map.get(layer, layer)
    if not desc:
        return ""
    return f"{desc}  {count}只"


def render_briefing(layers: dict[str, list[dict[str, Any]]], date_str: str) -> str:
    """Render the briefing output in mobile vertical format."""
    lines = []

    # Header
    total = sum(len(v) for v in layers.values())
    exec_count = len(layers["执行"])
    obs_count = len(layers["观察"])
    lines.append(f"📊 每日简报")
    lines.append(f"📅 {date_str}")
    lines.append(f"容量{total}  执行{exec_count}  观察{obs_count}")
    lines.append("")

    # Layer order: 执行 → 观察 → 待补 → 放弃
    layer_order = ["执行", "观察", "待补", "放弃"]
    rank_counters = {layer: 0 for layer in layer_order}

    for layer in layer_order:
        items = layers[layer]
        if not items:
            continue

        sorted_items = sort_items(items)
        layer_header = _format_layer_name(layer, len(sorted_items))
        lines.append(layer_header)

        for item in sorted_items:
            rank_counters[layer] += 1
            rank = rank_counters[layer]
            name = item.get("name") or item.get("target", "?")
            score = item.get("total_score", 0)
            major_stage = item.get("major_stage", "")
            momentum = item.get("momentum", "")

            # Rank emoji
            if rank == 1:
                rank_emoji = "🥇"
            elif rank == 2:
                rank_emoji = "🥈"
            elif rank == 3:
                rank_emoji = "🥉"
            else:
                rank_emoji = f"{rank}."

            # Main line
            if major_stage:
                stage_label = f"{major_stage}+{momentum}" if momentum else major_stage
            else:
                stage_label = momentum
            lines.append(f"  {rank_emoji} {name}    {score}分  {stage_label}")

            # 技术分析解读（替代原来的一句话）
            for analysis_line in _analysis_lines(item):
                lines.append(f"    {analysis_line}")

            lines.append("")

    # Footer
    lines.append("---")
    lines.append("仓位纪律 执行首次1成 确认加至3成 单票风险1R 总仓位≤5成")

    return "\n".join(lines)


# ── Candidates file ──────────────────────────────────────────────────────
def load_candidates(filepath: str | None = None) -> list[str]:
    """Load candidate stock identifiers from JSON file or stdin."""
    path = filepath or str(CANDIDATES_FILE)
    if not Path(path).exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "candidates" in data:
            return data["candidates"]
        return []
    except (json.JSONDecodeError, IOError):
        return []


# ── Main command ─────────────────────────────────────────────────────────
def cmd_briefing(args: argparse.Namespace) -> None:
    """Main briefing command."""
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Collect targets
    targets = set()
    refresh_requested = getattr(args, "refresh", False)
    quick_add = getattr(args, "candidate", None)
    add_to_pool = getattr(args, "add", False)

    # 1. Pool items
    if not getattr(args, "watch", None):
        pool = load_pool()
        for item in pool.get("items", []):
            if item.get("status", "") not in ("淘汰", "淘汰"):
                targets.add(item.get("target") or item.get("name", ""))

    # 2. Candidates
    if getattr(args, "candidates", None):
        candidates = load_candidates(args.candidates)
        for c in candidates:
            if isinstance(c, dict):
                targets.add(c.get("target") or c.get("name", ""))
            else:
                targets.add(str(c))

    # 3. Watch list
    if getattr(args, "watch", None):
        for w in args.watch:
            targets.add(w)

    # 4. Quick add
    if quick_add:
        targets.add(quick_add)

    if not targets:
        print("没有需要分析的标的。请提供 --watch 或 --candidates。")
        return

    target_list = sorted(targets)
    print(f"🔍 分析 {len(target_list)} 只标的...")

    # Suppress noisy stdout during report building
    old_stdout = sys.stdout
    sys.stdout = _silencer

    # Build reports
    t0 = time.time()
    results = build_reports_parallel(target_list, max_workers=8)
    elapsed = time.time() - t0

    sys.stdout = old_stdout

    # Process results
    scored_items: list[dict[str, Any]] = []
    errors = []
    for r in results:
        if not r["success"]:
            errors.append(f"  {r['target']}: {r['error']}")
            continue
        report = r["report"]
        target = r["target"]
        name = report.get("name") or target
        symbol = report.get("symbol") or target

        # Extract key fields
        major_stage = report.get("major_stage", "") or ""
        momentum = report.get("momentum", "") or ""
        total_score = report.get("total_score", 0)
        current = to_float(report.get("current")) or 0
        confirm = to_float(report.get("confirm")) or 0
        stop = to_float(report.get("stop")) or 0

        # Evaluate admission
        admission = evaluate_admission(major_stage, total_score, current, stop)

        item = {
            "target": target,
            "name": name,
            "symbol": symbol,
            "major_stage": major_stage,
            "momentum": momentum,
            "total_score": total_score,
            "chanlun_score": report.get("chanlun_score", 0),
            "wyckoff_score": report.get("wyckoff_score", 0),
            "chip_score": report.get("chip_score", 0),
            "fusion_score": report.get("fusion_score", 0),
            "momentum_score": report.get("momentum_score", 0),
            "momentum_tag": report.get("momentum_tag", ""),
            "current": current,
            "trigger": to_float(report.get("trigger", 0)),
            "confirm": confirm,
            "support": to_float(report.get("support", 0)),
            "resistance": to_float(report.get("resistance", 0)),
            "stop": stop,
            "defense": to_float(report.get("defense", 0)),
            "status": admission["status"],
            "admission_result": admission["result"],
            "admission_reason": admission["reason"],
            "atr14": report.get("atr14", 0),
            "atr_ratio": report.get("atr_ratio", 0),
            "fusion_action": (report.get("fusion") or {}).get("action", ""),
            "fusion_confidence": (report.get("fusion") or {}).get("confidence", ""),
            "fusion_score_val": report.get("fusion_score", 0),
            "fusion": report.get("fusion") or {},
            "one_liner": report.get("one_liner", ""),
            "scene": report.get("scene", ""),
            "structure_note": report.get("structure_note", ""),
            "volume_note": report.get("volume_note", ""),
            "volume_text": report.get("volume_text", ""),
            "major_reason": report.get("major_reason", ""),
            "momentum_reason": report.get("momentum_reason", ""),
            "stage_action": report.get("stage_action", ""),
            "upward_momentum": report.get("upward_momentum", ""),
            "stage_status": report.get("stage_status") or report.get("stage_label") or "",
            "expma_trend": report.get("expma_trend", ""),
            "trade_hint": _trade_hint({**report, "status": admission["status"]}),

            # 额外分析维度
            "macd_status": report.get("macd_status"),
            "fib_retrace": report.get("fib_retrace"),
            "chip_support": report.get("chip_support"),
            "chip_resistance": report.get("chip_resistance"),
            "chip_current_pct": report.get("chip_current_pct"),
            "expma20": report.get("expma20"),
            "expma50": report.get("expma50"),
            "ma": report.get("ma"),
            "support_source": report.get("support_source") or "",
            "resistance_source": report.get("resistance_source") or "",
        }
        scored_items.append(item)

    # Layer items
    layers = layer_items(scored_items)

    # Render
    output = render_briefing(layers, date_str)
    print(output)

    # Save last briefing
    POOLS_DIR.mkdir(parents=True, exist_ok=True)
    last_briefing = {
        "contract_version": "daily_briefing_v1",
        "date": date_str,
        "total_analyzed": len(target_list),
        "success": len(scored_items),
        "errors": len(errors),
        "layers": {k: len(v) for k, v in layers.items()},
        "executed_at": datetime.now().isoformat(),
    }
    with open(POOLS_DIR / "last_briefing.json", "w", encoding="utf-8") as f:
        json.dump(last_briefing, f, ensure_ascii=False, indent=2)

    # Quick add to pool
    if quick_add and add_to_pool:
        item = next((i for i in scored_items if i["target"] == quick_add), None)
        if item and item["status"] in ("执行", "观察"):
            pool = load_pool()
            # Check if already in pool
            existing = None
            for p in pool.get("items", []):
                if p.get("target") == quick_add or p.get("name") == quick_add:
                    existing = p
                    break
            if existing:
                existing.update(item)
            else:
                pool.setdefault("items", []).append(item)
            save_pool(pool)
            print(f"\n✅ {quick_add} 已加入选股池（{item['status']}）")

    # Show errors
    if errors:
        print(f"\n⚠️ {len(errors)} 只分析失败:")
        for e in errors:
            print(e)

    print(f"\n📊 完成：{len(scored_items)}/{len(target_list)} 只成功（{elapsed:.1f}s）")
    print(f"   执行 {len(layers['执行'])} 观察 {len(layers['观察'])} 待补 {len(layers['待补'])} 放弃 {len(layers['放弃'])}")


def main():
    parser = argparse.ArgumentParser(description="每日简报 — 从候选池中自动分析、排序、分层")
    parser.add_argument("--candidates", type=str, help="候选文件路径（JSON）")
    parser.add_argument("--watch", nargs="+", help="只分析指定标的")
    parser.add_argument("--refresh", action="store_true", help="刷新全池数据")
    parser.add_argument("--candidate", type=str, help="快速分析一只候选")
    parser.add_argument("--add", action="store_true", help="加入选股池（配合 --candidate）")
    parser.add_argument("--output", type=str, default="text", help="输出格式：text/markdown/json")
    parser.add_argument("--json", action="store_true", dest="use_json", help="JSON 输出")

    args = parser.parse_args()
    cmd_briefing(args)


if __name__ == "__main__":
    main()
