"""选股池策略分道：可盯 / 等齐 / 先别碰 / 计划过时。

与单票短线同源字段（decision_view / 买点生命周期 / 共振 / 日威否决），
不另造平行打分王。
"""
from __future__ import annotations

from typing import Any

# 内部 lane 键 → 中文
LANE_ZH = {
    "ready": "可盯",
    "wait": "等齐",
    "avoid": "先别碰",
    "stale": "计划过时",
}

# 排序：越高越优先（reverse=True）
LANE_RANK = {
    "ready": 40,
    "wait": 30,
    "avoid": 10,
    "stale": 0,
}

# 过渡期 status 映射（plan/rank 以 lane 为准）
LANE_TO_STATUS = {
    "ready": "执行",
    "wait": "观察",
    "avoid": "观察",
    "stale": "观察",
}

# 日威否决：只认结构化事件码 / 阶段，禁止中文子串扫「派发」
_WYCKOFF_EVENT_VETO = frozenset({
    "upthrust",
    "ut",
    "utad",
    "sow",
    "distribution",
    "lpsy",
})


def _f(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def plan_stale(item_or_report: dict[str, Any]) -> bool:
    """计划买点相对现价偏离 >5% → 计划过时。"""
    current = _f(item_or_report.get("current"))
    trigger = _f(item_or_report.get("trigger") or item_or_report.get("confirm"))
    if not current or not trigger or current <= 0 or trigger <= 0:
        return False
    return abs((trigger - current) / current) > 0.05


def _is_offline_placeholder(report: dict[str, Any]) -> bool:
    if report.get("offline") is True:
        return True
    if str(report.get("data_freshness") or "") == "offline":
        return True
    if str(report.get("data_status") or "") == "offline":
        return True
    note = str(report.get("data_note") or "")
    return bool(note) and ("离线" in note or "offline" in note.lower())


def _lifecycle_status(report: dict[str, Any]) -> str:
    life = report.get("buy_point_lifecycle")
    if isinstance(life, dict) and life.get("status"):
        return str(life.get("status") or "none")
    flat = report.get("buy_point_status")
    if flat:
        return str(flat)
    return "none"


def buy_point_valid(report: dict[str, Any]) -> bool | None:
    """买点有效 / 失效。

    Returns:
        True=有效, False=失效, None=无买点/无盖
    """
    st = _lifecycle_status(report)
    if st == "failed":
        return False
    if st in {"active", "watching"}:
        return True
    return None


def _near_buy_zone(report: dict[str, Any]) -> bool:
    """价仍在计划买点附近或支撑-确认区内（仅作可盯辅助，不能单独代替买点有效）。"""
    current = _f(report.get("current")) or 0.0
    confirm = _f(report.get("confirm") or report.get("trigger")) or 0.0
    support = _f(report.get("support")) or 0.0
    if current <= 0:
        return False
    if confirm > 0 and abs(confirm - current) / current <= 0.03:
        return True
    if support > 0 and confirm > 0:
        lo, hi = min(support, confirm), max(support, confirm)
        if lo * 0.99 <= current <= hi * 1.01:
            return True
    return False


def _chan_signal(report: dict[str, Any], *, strategy_entry_lit: bool) -> bool:
    """日缠真信号：策略点亮 / buy_like / 买点类型；不用任意 signal_tier，不用纯距离。"""
    if strategy_entry_lit:
        return True
    if report.get("strategy_entry_lit") is True:
        return True
    cards = report.get("analysis_cards") if isinstance(report.get("analysis_cards"), dict) else {}
    chan_card = cards.get("chan") if isinstance(cards.get("chan"), dict) else {}
    if chan_card.get("buy_like") is True:
        return True
    tier = str(chan_card.get("signal_tier") or "").strip().lower()
    if tier in {"buy", "buy1", "buy2", "buy3", "long", "entry"}:
        return True
    if tier.startswith("buy"):
        return True
    bps = report.get("chan_buy_point_types") or []
    if isinstance(bps, (list, tuple)) and len(bps) > 0:
        return True
    return False


def _wyckoff_veto(report: dict[str, Any]) -> bool:
    """日威否决：派发阶段或结构化事件码；禁止「缺派发背景」类中文误伤。"""
    if str(report.get("major_stage") or "") == "派发":
        return True
    wyk = report.get("wyckoff") if isinstance(report.get("wyckoff"), dict) else {}
    if wyk.get("upthrust_premature"):
        return False
    if wyk.get("distribution_confirmed") or wyk.get("utad") is True:
        return True
    for key in ("event_type", "primary_event", "event_code"):
        raw = str(wyk.get(key) or "").strip().lower()
        if not raw:
            continue
        token = raw.replace(" ", "_").split("_")[0] if "_" in raw else raw
        # 完整码或首段
        if raw in _WYCKOFF_EVENT_VETO or token in _WYCKOFF_EVENT_VETO:
            return True
        if raw in {"sign_of_weakness", "upthrust_after_distribution"}:
            return True
    # 扁平字段若是英文事件码
    flat = str(report.get("wyckoff_event") or "").strip().lower()
    if flat in _WYCKOFF_EVENT_VETO:
        return True
    return False


def _extract_decision(report: dict[str, Any]) -> dict[str, Any]:
    dv = report.get("decision_view")
    if isinstance(dv, dict) and dv:
        return dv
    try:
        from trader_shared.decision_view import build_decision_view

        return build_decision_view(report)
    except Exception:
        return {}


def _resonance_grade(report: dict[str, Any]) -> str:
    from trader_shared.resonance import extract_resonance_grade

    return extract_resonance_grade(report)


def classify_lane(report: dict[str, Any]) -> dict[str, Any]:
    """从报告或 pool record 分类（始终可据现价重算）。"""
    dv = _extract_decision(report)
    discipline_allow = bool(dv.get("discipline_allow", True)) if dv else True
    strategy_entry_lit = bool(dv.get("strategy_entry_lit", False))
    decision_allow = bool(dv.get("allow_new_recommend", False))
    if "discipline_allow" in report and report.get("decision_view") is None:
        discipline_allow = bool(report.get("discipline_allow"))
    if "strategy_entry_lit" in report and report.get("decision_view") is None:
        strategy_entry_lit = bool(report.get("strategy_entry_lit"))
    if "decision_allow" in report and report.get("decision_view") is None:
        decision_allow = bool(report.get("decision_allow"))

    grade = _resonance_grade(report)
    resonance_ok = grade == "aligned"
    bp = buy_point_valid(report)
    chan_sig = _chan_signal(report, strategy_entry_lit=strategy_entry_lit)
    near = _near_buy_zone(report)
    chan_ok = chan_sig or near  # 展示用；可盯另有更严门槛
    major = str(report.get("major_stage") or "蓄势")
    current = _f(report.get("current")) or 0.0
    defense = _f(report.get("defense") or report.get("stop")) or 0.0

    reasons: list[str] = []

    # 0) 离线占位：不得可盯
    if _is_offline_placeholder(report):
        reasons.append("离线占位，等实时数据")
        return _pack(
            "wait",
            reasons,
            bp=bp,
            decision_allow=decision_allow,
            discipline_allow=discipline_allow,
            strategy_entry_lit=strategy_entry_lit,
            resonance_ok=resonance_ok,
            chan_followable=chan_ok,
            grade=grade,
        )

    # 1) 硬先别碰（优先于计划过时，避免衰退被 stale 盖住）
    if major == "衰退":
        reasons.append("衰退期")
        return _pack(
            "avoid",
            reasons,
            bp=bp,
            decision_allow=decision_allow,
            discipline_allow=discipline_allow,
            strategy_entry_lit=strategy_entry_lit,
            resonance_ok=resonance_ok,
            chan_followable=chan_ok,
            grade=grade,
            status_override="淘汰",
        )
    if defense > 0 and current > 0 and current <= defense:
        reasons.append("现价跌破防守")
        return _pack(
            "avoid",
            reasons,
            bp=bp,
            decision_allow=decision_allow,
            discipline_allow=discipline_allow,
            strategy_entry_lit=strategy_entry_lit,
            resonance_ok=resonance_ok,
            chan_followable=chan_ok,
            grade=grade,
            status_override="淘汰",
        )

    # 2) 计划过时（仍带上买点失效近因）
    if plan_stale(report):
        reasons.append("计划买点与现价差太远")
        if bp is False:
            reasons.append("买点失效")
        return _pack(
            "stale",
            reasons,
            bp=bp,
            decision_allow=decision_allow,
            discipline_allow=discipline_allow,
            strategy_entry_lit=strategy_entry_lit,
            resonance_ok=resonance_ok,
            chan_followable=chan_ok,
            grade=grade,
        )

    # 3) 先别碰（共振 / 威 / 买点失效）
    if grade in {"conflict", "momentum_veto"}:
        reasons.append("共振冲突" if grade == "conflict" else "动能唱反调")
        return _pack(
            "avoid",
            reasons,
            bp=bp,
            decision_allow=decision_allow,
            discipline_allow=discipline_allow,
            strategy_entry_lit=strategy_entry_lit,
            resonance_ok=resonance_ok,
            chan_followable=chan_ok,
            grade=grade,
        )
    if _wyckoff_veto(report):
        reasons.append("威科夫派发/弱势否决")
        return _pack(
            "avoid",
            reasons,
            bp=bp,
            decision_allow=decision_allow,
            discipline_allow=discipline_allow,
            strategy_entry_lit=strategy_entry_lit,
            resonance_ok=resonance_ok,
            chan_followable=chan_ok,
            grade=grade,
        )
    if bp is False:
        reasons.append("买点失效")
        return _pack(
            "avoid",
            reasons,
            bp=bp,
            decision_allow=decision_allow,
            discipline_allow=discipline_allow,
            strategy_entry_lit=strategy_entry_lit,
            resonance_ok=resonance_ok,
            chan_followable=chan_ok,
            grade=grade,
        )

    # 纪律不允许 → 不得进可盯（降为等齐，除非完全无信号则先别碰）
    if discipline_allow is False:
        reasons.append("纪律不允许新开")
        if not chan_sig and bp is not True:
            return _pack(
                "avoid",
                reasons,
                bp=bp,
                decision_allow=decision_allow,
                discipline_allow=discipline_allow,
                strategy_entry_lit=strategy_entry_lit,
                resonance_ok=resonance_ok,
                chan_followable=chan_ok,
                grade=grade,
            )
        return _pack(
            "wait",
            reasons,
            bp=bp,
            decision_allow=decision_allow,
            discipline_allow=discipline_allow,
            strategy_entry_lit=strategy_entry_lit,
            resonance_ok=resonance_ok,
            chan_followable=chan_ok,
            grade=grade,
        )

    # 4) 可盯：必须买点有效 +（真缠信号或仍在附近）
    if bp is True and (chan_sig or near):
        reasons.append("买点有效")
        if resonance_ok:
            reasons.append("共振齐")
        elif grade.startswith("missing_"):
            reasons.append("共振未齐")
        return _pack(
            "ready",
            reasons,
            bp=bp,
            decision_allow=decision_allow,
            discipline_allow=discipline_allow,
            strategy_entry_lit=strategy_entry_lit,
            resonance_ok=resonance_ok,
            chan_followable=chan_ok,
            grade=grade,
            status_override="执行",
        )

    # 5) 等齐
    if bp is None:
        reasons.append("买点条件不足")
    if not chan_sig:
        reasons.append("缠论买点未成型")
    if grade.startswith("missing_") or grade in {"empty", ""}:
        reasons.append("共振未齐")
    if not strategy_entry_lit:
        reasons.append("策略未点亮")
    if not reasons:
        reasons.append("条件未齐")
    return _pack(
        "wait",
        reasons,
        bp=bp,
        decision_allow=decision_allow,
        discipline_allow=discipline_allow,
        strategy_entry_lit=strategy_entry_lit,
        resonance_ok=resonance_ok,
        chan_followable=chan_ok,
        grade=grade,
    )


def _pack(
    lane: str,
    reasons: list[str],
    *,
    bp: bool | None,
    decision_allow: bool,
    discipline_allow: bool,
    strategy_entry_lit: bool,
    resonance_ok: bool,
    chan_followable: bool,
    grade: str,
    status_override: str | None = None,
) -> dict[str, Any]:
    status = status_override or LANE_TO_STATUS.get(lane, "观察")
    return {
        "lane": lane,
        "lane_zh": LANE_ZH.get(lane, lane),
        "lane_reason": "；".join(reasons),
        "buy_point_valid": bp,
        "decision_allow": decision_allow,
        "discipline_allow": discipline_allow,
        "strategy_entry_lit": strategy_entry_lit,
        "resonance_ok": resonance_ok,
        "chan_followable": chan_followable,
        "resonance_grade": grade,
        "status": status,
    }


def lane_rank(lane: str | None) -> int:
    return LANE_RANK.get(str(lane or "wait"), 0)


def ensure_lane(item: dict[str, Any]) -> dict[str, Any]:
    """展示/排序前始终按现价重分道（刷价后不能沿用旧 lane=ready）。"""
    classified = classify_lane(item)
    # 信号降级：不得继续占可盯
    if item.get("_signal_downgrade") and classified["lane"] == "ready":
        classified = dict(classified)
        classified["lane"] = "wait"
        classified["lane_zh"] = LANE_ZH["wait"]
        classified["lane_reason"] = (
            (classified.get("lane_reason") or "") + "；近期信号失败"
        ).lstrip("；")
        classified["status"] = "观察"

    it = dict(item)
    it.update(
        {
            "lane": classified["lane"],
            "lane_zh": classified["lane_zh"],
            "lane_reason": classified["lane_reason"],
            "buy_point_valid": classified["buy_point_valid"],
            "decision_allow": classified["decision_allow"],
            "discipline_allow": classified["discipline_allow"],
            "strategy_entry_lit": classified["strategy_entry_lit"],
            "chan_followable": classified["chan_followable"],
            "status": classified["status"],
        }
    )
    return it


def counts_by_lane(items: list[dict[str, Any]]) -> dict[str, int]:
    out = {"可盯": 0, "等齐": 0, "先别碰": 0, "计划过时": 0}
    for item in items:
        it = ensure_lane(item)
        zh = it.get("lane_zh") or LANE_ZH.get(str(it.get("lane")), "等齐")
        if zh in out:
            out[zh] += 1
    return out


__all__ = [
    "LANE_RANK",
    "LANE_TO_STATUS",
    "LANE_ZH",
    "buy_point_valid",
    "classify_lane",
    "counts_by_lane",
    "ensure_lane",
    "lane_rank",
    "plan_stale",
]
