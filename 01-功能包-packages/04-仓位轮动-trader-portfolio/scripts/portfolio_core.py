from __future__ import annotations

from typing import Any

import candidate_core as core
from light_data import pct_change, to_float

STATUS_PRIORITY = {
    "低吸观察": 4,
    "等转强": 3,
    "防守观察": 2,
    "防守观察，趋势下行谨慎": 2,
    "冲高减仓": 2,
    "暂不碰": 1,
    "数据失败": 0,
}


def analyze_target(target: str, provider: Any, lookback_days: int) -> dict[str, Any]:
    sec = provider.resolve_security(target)
    try:
        quote = provider.fetch_quote(sec)
        bars = provider.fetch_qfq_daily(sec, days=lookback_days)
        current = quote.get("current_price") or bars[-1].get("close")
        if current is None:
            raise RuntimeError("current price unavailable")
        current = float(current)
        change_pct = quote.get("current_change_pct")
        levels = core.build_structure_context(current, bars, change_pct)
        status = levels["status"]
        downside_pct = abs(pct_change(current, levels["main_support"]))
        risk_reward = levels["upside_pct"] / max(downside_pct, 0.2)
        last_bar = bars[-1] if bars else {}
        atr14_val = float(last_bar.get("atr14") or 0)
        atr7_val = float(last_bar.get("atr7") or 0)
        atr_ratio_val = float(last_bar.get("atr_ratio") or 0)
        atr_level, atr_cap = core.atr_volatility_level(atr_ratio_val)
        score_val = round(
            core.score_for(
                {
                    "status": status,
                    "current": current,
                    "low_zone_upper": levels["low_zone_upper"],
                    "confirm_price": levels["confirm_price"],
                    "hard_stop": levels["hard_stop"],
                    "position_ratio": levels["position_ratio"],
                    "change_pct": change_pct,
                    "low_zone": levels["low_zone"],
                    "below_ma_count": levels["below_ma_count"],
                }
            ),
            2,
        )
        livermore_tier = core.livermore_scale(status, score_val)
        lw_base = core.base_weight(atr_level)
        t0_action = t0_action_for(current, levels["main_support"], levels["support"], levels["resistance"], status)
        return {
            "ok": True,
            "target": target,
            "name": quote.get("name") or sec.name,
            "symbol": quote.get("symbol") or sec.ts_code,
            "current": round(current, 2),
            "change_pct": change_pct,
            "defense": levels["main_support"],
            "support": levels["support"],
            "resistance": levels["resistance"],
            "stop": levels["hard_stop"],
            "buy_low": levels["low_zone_lower"],
            "buy_high": levels["low_zone_upper"],
            "confirm": levels["confirm_price"],
            "take": levels["take"],
            "upside_pct": levels["upside_pct"],
            "downside_pct": round(downside_pct, 2),
            "risk_reward": round(risk_reward, 2),
            "status": status,
            "score": score_val,
            "t0_action": t0_action,
            "reason": reason_for(status, current, levels["main_support"], levels["confirm_price"], levels["upside_pct"], downside_pct, risk_reward),
            "atr14": atr14_val,
            "atr7": atr7_val,
            "atr_ratio": atr_ratio_val,
            "atr_level": atr_level,
            "atr_cap": atr_cap,
            "livermore_tier": livermore_tier,
            "livermore_base_weight": lw_base,
        }
    except Exception as exc:
        return {
            "ok": False,
            "target": target,
            "name": target,
            "symbol": "",
            "status": "数据失败",
            "score": -999,
            "t0_action": "不做",
            "reason": f"数据获取失败：{exc}",
        }


def t0_action_for(current: float, defense: float, support: float, resistance: float, status: str) -> str:
    if status in {"暂不碰", "数据失败"} or current < defense:
        return "不做"
    position = (current - support) / max(resistance - support, current * 0.01)
    return "等待高抛触发" if position >= 0.55 else "等待低吸触发"


def reason_for(status: str, current: float, defense: float, confirm: float, upside: float, downside: float, rr: float) -> str:
    if status == "暂不碰":
        return f"现价 {current:.2f}元 已跌破或贴近防守位 {defense:.2f}元，先不参与。"
    if status == "优先候选":
        return f"防守位 {defense:.2f}元 清楚，确认位 {confirm:.2f}元，向上 {upside:.2f}%、向下 {downside:.2f}%，盈亏比约 {rr:.2f}。"
    if status in ("防守观察", "防守观察，趋势下行谨慎"):
        return f"仍在防守位 {defense:.2f}元 上方，但确认位 {confirm:.2f}元 还没收回，先观察承接。"
    return f"现价离确认位 {confirm:.2f}元 仍需确认，未放量站上前不排第一。"


def score_for(status: str, current: float, defense: float, confirm: float, rr: float, change_pct: Any) -> float:
    base = STATUS_PRIORITY.get(status, 0) * 100
    confirm_distance = abs(pct_change(current, confirm))
    defense_distance = abs(pct_change(current, defense))
    change = to_float(change_pct) or 0.0
    chase_penalty = max(change - 5, 0) * 8
    return base + min(rr, 4) * 12 - confirm_distance * 2 - defense_distance - chase_penalty


def sort_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (STATUS_PRIORITY.get(str(item.get("status")), 0), float(item.get("score") or -999)), reverse=True)
