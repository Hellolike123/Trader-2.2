"""选股池打分与排序。"""
from __future__ import annotations

from typing import Any

from pool_cmds import pool_io as _pool_io
from pool_cmds.pool_io import *  # noqa: F403
from config import (
    ADMISSION_SCORE_EXECUTE,
    ADMISSION_SCORE_OBSERVE,
    CHAN_BASE,
    CHAN_STAGE_BONUS,
    CHAN_SCENE_BONUS,
    CHAN_CONFIRM_CLOSE_BONUS,
    CHAN_CONFIRM_FAR_BONUS,
    CHAN_BUYPOINT_BONUS,
    CHAN_DATA_INSUFFICIENT_PENALTY,
    CHIP_BASE,
    CHIP_ABOVE_STOP_BONUS,
    CHIP_IN_ZONE_BONUS,
    CHIP_UPSIDE_BONUS,
    FUSION_BONUS_SCALE,
    FUSION_DISAGREEMENT_CAP,
    ENABLE_RISK_REWARD_FILTER,
    RISK_REWARD_THRESHOLDS,
)
from trader_shared import candidate_core as core

def to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def momentum_passes(report: dict[str, Any]) -> bool:
    current = to_float(report.get("current")) or 0.0
    confirm = to_float(report.get("confirm")) or current
    ma = report.get("ma") or {}
    ma5 = to_float(ma.get("ma5"))
    ma10 = to_float(ma.get("ma10"))
    ma20 = to_float(ma.get("ma20"))
    near_confirm = current >= confirm * 0.985
    ma_support = ma5 is not None and ma10 is not None and ma20 is not None and ma5 >= ma10 and current >= ma20
    stage_ok = report.get("stage") in {"走强", "修复"}
    scene_ok = report.get("scene") in {"等转强", "突破确认", "突破观察", "冲高减仓"}
    return bool((near_confirm and ma_support) or (stage_ok and scene_ok and ma_support))


def score_report(report: dict[str, Any]) -> dict[str, int]:
    current = to_float(report.get("current")) or 0.0
    confirm = to_float(report.get("confirm")) or current
    from trader_shared.structure_core import effective_stop_price

    stop = (
        effective_stop_price(report.get("stop"), report.get("trailing_stop"))
        or to_float(report.get("stop"))
        or current
    )
    support = to_float(report.get("support")) or current
    take = to_float(report.get("take")) or confirm
    stage = str(report.get("stage") or "")
    scene = str(report.get("scene") or "")
    chan = CHAN_BASE
    chip = CHIP_BASE

    # ── 缠论分：阶段 + 场景 + 确认位距离 ──
    chan += CHAN_STAGE_BONUS.get(stage, 0)
    chan += CHAN_SCENE_BONUS.get(scene, 0)

    if current and confirm:
        distance = abs(confirm - current) / max(current, 0.01)
        if distance <= 0.02:
            chan += CHAN_CONFIRM_CLOSE_BONUS
        elif distance <= 0.05:
            chan += CHAN_CONFIRM_FAR_BONUS

    # ── 威科夫分：基于 Wyckoff 信号规则的独立打分 ──
    # 先计算 0-100 分数，再缩放至 [0, 30]（与旧契约 max=30 保持一致）
    from trader_shared.wyckoff_core import calculate_wyckoff_score
    daily_bars = report.get("bars") or report.get("daily_bars") or []
    wyckoff_result = calculate_wyckoff_score(daily_bars)
    wyckoff = int(wyckoff_result["score"] / 100 * 30)

    # ── 筹码分：价格位置 ──
    if current > stop:
        chip += CHIP_ABOVE_STOP_BONUS
    if support <= current <= max(confirm, support):
        chip += CHIP_IN_ZONE_BONUS
    if take > current:
        chip += CHIP_UPSIDE_BONUS

    # ── 缠论分：买点 + 数据充分性 ──
    # 使用结构化 buy_point_types 列表而非字符串 in 匹配
    chan_bps = [str(bp) for bp in report.get("chan_buy_point_types", [])]
    for bp_key, bp_bonus in CHAN_BUYPOINT_BONUS.items():
        if bp_key in chan_bps:
            chan += bp_bonus
            break
    # 数据充分性：笔数不足 2 笔或趋势标签为"数据不足"
    if report.get("chan_strokes_count", 0) < 2 and str(report.get("chan_trend_label", "")) == "数据不足":
        chan -= CHAN_DATA_INSUFFICIENT_PENALTY
    chan = max(0, min(45, chan))
    wyckoff = max(0, min(30, wyckoff))
    chip = max(0, min(25, chip))

    # ── 融合层仪表分（仅展示；不进 total_score / 入池门槛）──
    # weighted_score(-1.35~1.35) → -20~+20；高分歧时收窄到 ±cap
    fusion = report.get("fusion", {}) or {}
    fw = to_float(fusion.get("weighted_score")) if isinstance(fusion, dict) else None
    fd = to_float(fusion.get("disagreement")) if isinstance(fusion, dict) else None
    fw = fw or 0.0
    fd = fd or 0.0
    fusion_score = max(-20, min(20, round(fw * FUSION_BONUS_SCALE)))
    if fd > 1:
        fusion_score = max(-FUSION_DISAGREEMENT_CAP, min(FUSION_DISAGREEMENT_CAP, fusion_score))

    from trader_shared.momentum_core import assess_momentum
    daily_bars = report.get("bars") or report.get("daily_bars") or []
    momentum_result = assess_momentum(daily_bars) if len(daily_bars) >= 30 else {"direction": "insufficient", "score": None}
    momentum_dir = momentum_result.get("direction", "insufficient")
    # 数据不足时 score=None，(or 0) 防止 None // 5 抛错，且不贡献动量分
    momentum_score_val = min(20, max(0, (momentum_result.get("score") or 0) // 5))
    mom_tag = {"bullish": "🟢看多", "bearish": "🔴看空", "neutral": "🟡中性"}.get(momentum_dir, "⚪数据不足")
    # 入池总分 = 结构四席（缠/威/筹/动）；融合分仅仪表，不抬/压门槛
    total = max(0, min(100, chan + wyckoff + chip + momentum_score_val))
    return {
        "chanlun_score": chan,
        "wyckoff_score": wyckoff,
        "chip_score": chip,
        "fusion_score": fusion_score,
        "total_score": total,
        "momentum_score": momentum_score_val,
        "momentum_tag": mom_tag,
    }


def _evaluate_admission(major_stage: str, total_score: int, current: float, confirm: float, stop: float) -> dict[str, str]:
    """三关筛选统一实现：阶段筛选 → 结构评分门槛 → 风控检查。

    total_score 不含 fusion 仪表分；融合分不得抬高/压低入池门槛。

    Returns:
        {"result": "入池"|"待补"|"拒绝", "reason": str, "status": "执行"|"观察"|"淘汰"}
    """
    # 第一关：阶段筛选 — 衰退期直接拒绝
    if major_stage == "衰退":
        return {"result": "拒绝", "reason": "衰退期，直接拒绝入池。", "status": "淘汰"}

    # 第二关：结构评分门槛（查表；不含 fusion）
    exec_threshold = ADMISSION_SCORE_EXECUTE.get(major_stage, 999)
    obs_threshold = ADMISSION_SCORE_OBSERVE.get(major_stage, 999)

    if total_score >= exec_threshold:
        status = "执行"
    elif total_score >= obs_threshold:
        status = "观察"
    else:
        threshold = min(exec_threshold, obs_threshold)
        return {"result": "待补", "reason": f"{major_stage}期但评分不足{threshold}，暂不入池。", "status": "观察"}

    # 第三关：风控检查 — 现价跌破止损
    if stop > 0 and current <= stop:
        return {"result": "拒绝", "reason": "现价跌破防守位，结构审查失败。", "status": "淘汰"}
    if confirm <= 0 or stop <= 0:
        return {"result": "待补", "reason": "触发位或防守位不清楚，暂不参与排序。", "status": "观察"}

    return {"result": "入池", "reason": "结构成立，触发位和防守位清楚。", "status": status}


def admission_for(report: dict[str, Any], scores: dict[str, int]) -> dict[str, str]:
    """三关筛选入口（从 report/scores 提取参数后委托 _evaluate_admission）。

    共振档只做离散收紧：冲突 / 动能拆台不得入「执行」。
    """
    from trader_shared.resonance import apply_resonance_admission, extract_resonance_grade

    current = to_float(report.get("current")) or 0.0
    confirm = to_float(report.get("confirm")) or current
    from trader_shared.structure_core import effective_stop_price

    stop = (
        effective_stop_price(report.get("stop"), report.get("trailing_stop"))
        or to_float(report.get("stop"))
        or current
    )
    major_stage = str(report.get("major_stage") or "蓄势")
    total_score = scores["total_score"]
    out = _evaluate_admission(major_stage, total_score, current, confirm, stop)
    grade = extract_resonance_grade(report)
    status, reason = apply_resonance_admission(out["status"], out["reason"], grade)
    out["status"] = status
    out["reason"] = reason
    return out


def structure_summary(report: dict[str, Any]) -> str:
    stage = str(report.get("stage") or "待补")
    scene = str(report.get("scene") or "待补")
    if scene in {"等转强", "突破确认", "突破观察", "冲高减仓"}:
        return f"{stage}中，接近确认位，等待放量站稳。"
    if scene in {"低吸观察", "防守观察", "防守观察，趋势下行谨慎"}:
        return f"{stage}观察，防守位未破，等待止跌确认。"
    if scene == "暂不碰":
        return "结构偏弱，防守逻辑不清。"
    return f"{stage}结构，{scene}。"


def momentum_text(report: dict[str, Any]) -> str:
    ma = report.get("ma") or {}
    if momentum_passes(report):
        return f"通过｜MA5 {ma.get('ma5', '--')} / MA10 {ma.get('ma10', '--')} 向上，价格接近确认位。"
    return f"未通过｜量价或均线未形成执行确认，MA5 {ma.get('ma5', '--')} / MA10 {ma.get('ma10', '--')}。"


def record_from_report(target: str, report: dict[str, Any], offline: bool = False) -> dict[str, Any]:
    from pool_cmds.classify import classify_lane

    scores = score_report(report)
    # 旧三关仅作诊断标签；入池不再硬拒（容量除外）。分类以 lane 为准。
    if offline:
        admission = {
            "result": "入池",
            "reason": "离线占位，跳过三关。",
            "status": "观察",
        }
    else:
        admission = admission_for(report, scores)
    now = today_text()
    atr14 = to_float(report.get("atr14")) or 0.0
    atr_ratio = to_float(report.get("atr_ratio")) or 0.0
    atr_level, atr_cap = core.atr_volatility_level(atr_ratio) if atr14 > 0 and atr_ratio > 0 else ("", 0)
    from trader_shared.resonance import (
        extract_resonance_grade,
        resonance_grade_label,
    )

    major_stage = str(report.get("major_stage") or "蓄势")
    momentum = str(report.get("short_term_momentum") or "震荡")
    stage_status = str(report.get("stage_label") or f"{major_stage}期+{momentum}")
    res = report.get("resonance") if isinstance(report.get("resonance"), dict) else {}
    resonance_grade = extract_resonance_grade(report)
    resonance_summary = str(res.get("summary_line") or "") or f"共振：{resonance_grade_label(resonance_grade)}"
    life = report.get("buy_point_lifecycle") if isinstance(report.get("buy_point_lifecycle"), dict) else {}
    record = {
        "target": target,
        "name": report.get("name") or target,
        "symbol": report.get("symbol") or target,
        "added_at": now,
        "updated_at": now,
        "status": admission["status"],
        "admission_result": "入池",  # 软门槛：容量内均可进；坏票靠 lane=先别碰
        "admission_reason": admission["reason"],
        "admission_diag": admission["result"],  # 旧三关诊断：入池/待补/拒绝
        "structure_summary": structure_summary(report),
        "trigger": round(float(report.get("confirm") or 0), 2),
        # defense = 有效止损（hard ∪ trailing），盯盘破位与状态机一致
        "defense": round(
            max(
                float(report.get("stop") or 0),
                float(report.get("trailing_stop") or 0),
            ),
            2,
        ),
        "trailing_stop": (
            round(float(report.get("trailing_stop")), 2)
            if report.get("trailing_stop")
            else None
        ),
        "confirm": round(float(report.get("confirm") or 0), 2),
        "support": round(float(report.get("support") or 0), 2),
        "current": round(float(report.get("current") or 0), 2),
        "momentum_state": "通过" if momentum_passes(report) else "未通过",
        "momentum_text": momentum_text(report),
        "offline": offline or bool(report.get("data_note")),
        "data_freshness": report.get("data_freshness", "live"),
        "atr14": atr14,
        "atr_ratio": atr_ratio,
        "atr_level": atr_level,
        "atr_cap": atr_cap,
        "fusion_action": (report.get("fusion") or {}).get("action"),
        "fusion_confidence": (report.get("fusion") or {}).get("confidence"),
        "major_stage": major_stage,
        "momentum": momentum,
        "stage_status": stage_status,
        "resonance_grade": resonance_grade,
        "resonance_summary": resonance_summary,
        "risk_flags": report.get("risk_flags", []) or [],
        "buy_point_status": str(life.get("status") or ""),
        "buy_point_lid": life.get("lid_price"),
        **scores,
    }
    trigger_val = record.get("trigger") or 0.0
    stop_val = record.get("defense", 0.0)
    take_val = round(float(report.get("take") or 0), 2)
    risk_reward = None
    if stop_val > 0 and trigger_val > stop_val and take_val > trigger_val:
        risk_reward = round((take_val - trigger_val) / (trigger_val - stop_val), 1)
    record["take"] = take_val
    record["risk_reward"] = risk_reward

    # 策略分道（短线同源）；覆盖 status。离线/失败占位由 classify 强制等齐。
    if offline:
        record["offline"] = True
        record["data_freshness"] = record.get("data_freshness") or "offline"
        record["data_note"] = record.get("data_note") or "离线占位，跳过三关。"
    classified = classify_lane({**report, **record})
    record["lane"] = classified["lane"]
    record["lane_zh"] = classified["lane_zh"]
    record["lane_reason"] = classified["lane_reason"]
    record["buy_point_valid"] = classified["buy_point_valid"]
    record["decision_allow"] = classified["decision_allow"]
    record["discipline_allow"] = classified["discipline_allow"]
    record["strategy_entry_lit"] = classified["strategy_entry_lit"]
    record["chan_followable"] = classified["chan_followable"]
    record["status"] = classified["status"]
    try:
        from pool_cmds.wyckoff_rank import attach_wyckoff_chain_fields

        attach_wyckoff_chain_fields(record, report)
    except Exception:
        record.setdefault("wyckoff_chain", [])
        record.setdefault("wyckoff_chain_plain", "威：吸筹链未成型")
        record.setdefault("wyckoff_chain_rank", 0)
    return record


def active_items(pool: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in pool.get("items", []) if item.get("status") in {"执行", "观察", "淘汰"}]


STAGE_STRENGTH = {"主升": 1.0, "拉升": 0.9, "蓄势偏强": 0.8, "蓄势": 0.5, "蓄势偏弱": 0.3, "派发": 0.2, "衰退": 0.0}


def _tighten_status_by_resonance(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """展示/排序前：冲突·拆台票若仍标执行则收紧为观察（不写回 pool.json）。"""
    from trader_shared.resonance import apply_resonance_admission, extract_resonance_grade

    out: list[dict[str, Any]] = []
    for item in items:
        it = dict(item)
        grade = extract_resonance_grade(it)
        st, reason = apply_resonance_admission(
            str(it.get("status") or ""),
            str(it.get("admission_reason") or ""),
            grade,
        )
        it["status"] = st
        if reason:
            it["admission_reason"] = reason
        out.append(it)
    return out


def _trigger_stale_for_sort(item: dict[str, Any]) -> bool:
    """计划买点相对现价偏离 >5% 视为过期（与 verify._is_trigger_stale 同口径）。"""
    current = to_float(item.get("current"))
    trigger = to_float(item.get("trigger"))
    if not current or not trigger or current <= 0 or trigger <= 0:
        return False
    return abs((trigger - current) / current) > 0.05


def _actionability_rank(item: dict[str, Any]) -> tuple[int, int]:
    """可碰性：未过期优先；盈亏比分档（未知中性）。越高越优先。"""
    fresh = 0 if _trigger_stale_for_sort(item) else 1
    rr = to_float(item.get("risk_reward")) or 0.0
    if not ENABLE_RISK_REWARD_FILTER or rr <= 0:
        rr_band = 1  # 过滤关 / 算不出 → 不抬不压
    elif rr >= 2.0:
        rr_band = 3
    elif rr >= 1.5:
        rr_band = 2
    elif rr >= 1.0:
        rr_band = 1
    else:
        rr_band = 0
    return (fresh, rr_band)


def _score_tiebreak(item: dict[str, Any]) -> float:
    """同共振、同可碰时的弱决胜：结构分主、阶段辅。fusion 不参与。"""
    score = int(item.get("total_score") or 0)
    stage = str(item.get("major_stage") or "蓄势")
    stage_str = STAGE_STRENGTH.get(stage, 0.5)
    return (score / 100.0) * 0.7 + stage_str * 0.3


def sort_items_unified(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """统一排序：plan / rank / list 共用。

    主键：lane（可盯 > 等齐 > 先别碰 > 计划过时）
    次键：共振档
    再次：威科夫吸筹链完整度（同道内）
    再次：可碰性（盈亏比）
    末键：结构总分弱决胜
    fusion 不参与。
    """
    from pool_cmds.classify import ensure_lane, lane_rank
    from pool_cmds.wyckoff_rank import wyckoff_chain_rank
    from trader_shared.resonance import extract_resonance_grade, resonance_pool_rank

    prepared = [ensure_lane(it) for it in items]

    return sorted(
        prepared,
        key=lambda item: (
            lane_rank(item.get("lane")),
            resonance_pool_rank(extract_resonance_grade(item)),
            wyckoff_chain_rank(item),
            _actionability_rank(item),
            _score_tiebreak(item),
        ),
        reverse=True,
    )


def sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """兼容旧名：委托 sort_items_unified（lane 主轴，不再用分数双轨）。"""
    return sort_items_unified(items)


def sort_items_by_stage(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_rank = {"执行": 3, "观察": 2, "淘汰": 1}
    return sorted(
        items,
        key=lambda item: (
            STAGE_PRIORITY.get(str(item.get("major_stage") or "蓄势"), 5),
            status_rank.get(str(item.get("status")), 0),
            int(item.get("total_score") or 0),
        ),
    )


def counts(items: list[dict[str, Any]]) -> dict[str, int]:
    """兼容旧计数 + lane 计数。"""
    from pool_cmds.classify import counts_by_lane, ensure_lane

    base = {
        "执行": len([item for item in items if item.get("status") == "执行"]),
        "观察": len([item for item in items if item.get("status") == "观察"]),
        "淘汰": len([item for item in items if item.get("status") == "淘汰"]),
    }
    base.update(counts_by_lane([ensure_lane(it) for it in items]))
    return base

__all__ = list(_pool_io.__all__) + [
    "STAGE_STRENGTH",
    "active_items",
    "admission_for",
    "counts",
    "momentum_passes",
    "momentum_text",
    "record_from_report",
    "score_report",
    "sort_items",
    "sort_items_by_stage",
    "sort_items_unified",
    "structure_summary",
    "to_float",
    "_evaluate_admission",
    "_tighten_status_by_resonance",
]
