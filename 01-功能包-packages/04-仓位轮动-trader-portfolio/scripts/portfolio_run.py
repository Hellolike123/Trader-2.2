#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SHARED_MARKET = ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
SHARED_CANDIDATE = ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
SHARED_SCRIPTS = ROOT / "02-共享模块-shared" / "scripts"
SHARED_ROOT = ROOT / "02-共享模块-shared"
SHARED_TS = SHARED_ROOT / "trader_shared"
CONTRACTS = ROOT / "02-共享模块-shared" / "03-输出校验-contracts"
for _p in (SHARED_MARKET, SHARED_CANDIDATE, SHARED_SCRIPTS, SHARED_ROOT, CONTRACTS):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from candidate_model import analyze_target, sort_candidates
from config import DEFAULT_CASH_FLOOR, DEFAULT_MAIN_CAP, DEFAULT_MAX_TOTAL, LOOKBACK_DAYS
from trader_shared.data_provider import get_provider
from signal_contract import assert_valid_signal

try:
    from trader_shared import get_market_level, get_market_note, add_warning
    _SHARED_OK = True
except ImportError:
    import warnings
    warnings.warn("[portfolio] shared module not available — market status will be unavailable.", stacklevel=2)
    _SHARED_OK = False

    def get_market_level() -> str: return ""
    def get_market_note() -> str: return ""
    def add_warning(msg: str, related_stock: str = "") -> None: pass


CONTRACT_VERSION = "trader_portfolio_v1"
SNAPSHOT_CONTRACT_VERSION = "trader_portfolio_rotation_v1"

# ========== Market Filter Constants & Functions ==========

MARKET_DRAINAGE = {
    ("很差", "低吸观察"): "防守观察",
    ("很差", "防守观察"): "防守观察",
    ("很差", "等转强"): "防守观察",
    ("很差", "冲高减仓"): "减仓加倍",
    ("偏弱", "等转强"): "低吸观察",
    ("偏弱", "冲高减仓"): "减仓加倍",
}


def climate_adjust(status: str, market_level: str) -> str:
    if not market_level or market_level in ("正常", "", "未知"):
        return status
    return MARKET_DRAINAGE.get((market_level, status), status)


def portfolio_total_cap(market_level: str, has_high_atr: bool) -> int:
    if not market_level or market_level in ("正常", "", "未知"):
        return DEFAULT_MAX_TOTAL
    if market_level == "很差":
        return 60
    if market_level == "偏弱" and has_high_atr:
        return 60
    if market_level == "偏弱":
        return 70
    return DEFAULT_MAX_TOTAL


def dual_index_market_decision(csi1000_level: str, csi300_level: str) -> str:
    c1 = csi1000_level if csi1000_level and csi1000_level not in ("", "未知") else "缺失"
    c2 = csi300_level if csi300_level and csi300_level not in ("", "未知") else "缺失"
    if c1 == "缺失" and c2 == "缺失":
        return "偏弱"
    if c1 == "缺失" or c2 == "缺失":
        return "偏弱"
    if c1 in {"偏弱", "很差"} and c2 in {"偏弱", "很差"}:
        return "很差"
    if c1 in {"偏弱", "很差"} or c2 in {"偏弱", "很差"}:
        return "偏弱"
    return "正常"


def price(value: float | None) -> str:
    return "无" if value is None else f"{value:.2f}元"


def percent(value: float | int | None) -> str:
    return "0%" if value is None else f"{int(round(float(value)))}%"


def price_range(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "无"
    return f"{low:.2f}-{high:.2f}元"


def number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def percent_decimal(value: float | int | None) -> str:
    if value is None:
        return "0%"
    rounded = round(float(value), 1)
    return f"{int(rounded)}%" if rounded.is_integer() else f"{rounded:.1f}%"


def compact_fraction(value: float) -> str:
    mapping = {
        round(1 / 6, 4): "1/6",
        0.25: "1/4",
        round(1 / 3, 4): "1/3",
        0.5: "1/2",
    }
    return mapping.get(round(value, 4), f"{value:.2f}")


def signal_state_for_item(item: dict[str, Any], *, market_level: str = "") -> tuple[str, str, str, str]:
    if market_level and market_level not in ("正常", "", "未知"):
        adj = item.get("adjusted_status")
        status = str(adj) if adj else str(item.get("status") or "")
    else:
        status = str(item.get("status") or "")
    current = number(item.get("current"))
    confirm = number(item.get("confirm"))
    if status in {"暂不碰", "数据失败"} or is_risk_exit(item):
        return "defensive", "bearish_lean", "wait", "low"
    if status == "冲高减仓":
        return "reduce", "neutral", "reduce", "medium"
    if status == "减仓加倍":
        return "reduce", "bearish", "reduce", "high"
    if confirm > 0 and current >= confirm:
        return "track", "bullish", "track", "medium"
    if status in {"等转强", "突破确认", "突破观察"}:
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if status in {"低吸观察", "防守观察", "防守观察，趋势下行谨慎", "空间不足"}:
        return "low_buy_watch", "bullish_lean", "observe", "medium"
    return "observe", "neutral", "observe", "low"


def signal_risk_flags_for_item(item: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if is_risk_exit(item):
        flags.append("risk_exit")
    if is_high_stalled(item):
        flags.append("high_stall")
    if candidate_level(item) == "unconfirmed":
        flags.append("confirmation_missing")
    if number(item.get("upside_pct")) and number(item.get("upside_pct")) < 2:
        flags.append("limited_upside_space")
    return flags


def build_signal_for_item(item: dict[str, Any], *, max_total: int, max_single_move: int, market_level: str = "") -> dict[str, Any]:
    signal_type, direction, action, confidence = signal_state_for_item(item, market_level=market_level)
    symbol = str(item.get("symbol") or item.get("target") or item.get("name") or "")
    name = str(item.get("name") or item.get("target") or symbol)
    confirm = number(item.get("confirm"), number(item.get("current")))
    stop = number(item.get("stop"), number(item.get("defense"), number(item.get("current"))))
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "trader-portfolio",
        "symbol": symbol,
        "name": name,
        "trade_date": str(item.get("trade_date") or date.today().isoformat()),
        "analysis_time": str(item.get("analysis_time") or item.get("trade_date") or "--"),
        "signal_type": signal_type,
        "direction": direction,
        "action": action,
        "confidence": confidence,
        "data_status": "degraded" if item.get("ok") else "insufficient",
        "trigger": {
            "type": "price_confirm",
            "price": round(confirm, 2),
            "text": f"{confirm:.2f}元 放量站稳或回踩不破后再提高仓位",
        },
        "invalidation": {
            "type": "price_break",
            "price": round(stop, 2),
            "text": f"跌破 {stop:.2f}元 或跌破后反抽站不回，轮动逻辑失效",
        },
        "position": {
            "max_total_pct": max_total if signal_type not in {"defensive", "risk_stop"} else 0,
            "max_single_move_pct": min(max_single_move, max_total if signal_type not in {"defensive", "risk_stop"} else 0),
        },
        "risk_flags": signal_risk_flags_for_item(item),
        "summary": signal_summary_for_item(item, signal_type),
    }
    assert_valid_signal(signal)
    return signal


def signal_summary_for_item(item: dict[str, Any], signal_type: str) -> str:
    name = str(item.get("name") or item.get("target") or "标的")
    if signal_type == "reduce":
        return f"{name}进入减仓观察，优先让出部分仓位。"
    if signal_type == "track":
        return f"{name}已接近或站上确认位，可作为承接候选。"
    if signal_type == "defensive":
        return f"{name}进入防守状态，不用于接仓。"
    return f"{name}继续观察，等待确认。"


def build_signal_summaries(items: list[dict[str, Any]], *, max_total: int, max_single_move: int, market_level: str = "") -> list[dict[str, Any]]:
    return [build_signal_for_item(item, max_total=max_total, max_single_move=max_single_move, market_level=market_level) for item in items]


def allocate_weights(
    sorted_items: list[dict[str, Any]],
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
) -> dict[str, int]:
    tradable = [
        item for item in sorted_items
        if item.get("ok")
        and (item.get("adjusted_status") or item.get("status") or "")
        not in {"暂不碰", "数据失败"}
    ]
    if not tradable:
        return {}

    alloc_pool = max_total

    scores: list[float] = []
    for item in tradable:
        raw = item.get("score") or item.get("livermore_score")
        s = float(raw) if raw is not None and raw != "" else 30.0
        if s <= 0:
            s = 30.0
        scores.append(s)

    total_score = sum(scores)
    if total_score <= 0:
        n = len(tradable)
        each = max(1, round(alloc_pool / n))
        return {item["name"]: each for item in tradable}

    # 筹码降权系数（软调整，不硬限速）
    # 使用 portfolio_core.analyze_target 预计算的 chip_weight 值
    weights: dict[str, int] = {}
    for item, score in zip(tradable, scores):
        raw_w = round(score / total_score * alloc_pool)
        raw_w = max(raw_w, 0)
        # 筹码降权（套牢盘越重，仓位越低）
        cw = float(item.get("chip_weight") or 1.0)
        weight = round(raw_w * cw)
        weights[item["name"]] = weight

    actual_total = sum(weights.values())
    if actual_total > max_total:
        excess = actual_total - max_total
        sorted_by_score = sorted(
            tradable,
            key=lambda i: float(i.get("score") or i.get("livermore_score") or 30),
        )
        for item in sorted_by_score:
            if excess <= 0:
                break
            name = item["name"]
            w = weights.get(name, 0)
            cut = min(w, excess)
            weights[name] = w - cut
            excess -= cut

    return weights


def build_roles(sorted_items: list[dict[str, Any]], *, max_total: int, main_cap: int = 50) -> dict[str, Any]:
    # main_cap 预留参数：仓位分配由 allocate_weights 的 Score 占比 + 筹码降权决定
    tradable = [
        item for item in sorted_items
        if item.get("ok")
        and (item.get("adjusted_status") or item.get("status") or "")
        not in {"暂不碰", "数据失败"}
    ]
    roles = {
        "主仓": tradable[0] if len(tradable) >= 1 else None,
        "副仓": tradable[1] if len(tradable) >= 2 else None,
        "观察": tradable[2] if len(tradable) >= 3 else None,
    }
    weights = allocate_weights(sorted_items, max_total=max_total)
    total = sum(weights.values())
    actual_cash = max(0, 100 - total)
    avoid = [
        item["name"]
        for item in sorted_items
        if not item.get("ok") or item.get("status") in {"暂不碰", "数据失败"}
    ]
    return {"roles": roles, "weights": weights, "avoid": avoid, "total": total, "cash": actual_cash}


def role_name(plan: dict[str, Any], role: str) -> str:
    item = plan["roles"].get(role)
    return str(item["name"]) if item else "无"


def snapshot_targets(snapshot: dict[str, Any]) -> list[str]:
    targets: list[str] = []
    for key in ("targets", "holdings", "candidates"):
        values = snapshot.get(key) or []
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, str):
                target = item.strip()
            elif isinstance(item, dict):
                target = str(item.get("target") or item.get("name") or item.get("symbol") or "").strip()
            else:
                target = ""
            if target and target not in targets:
                targets.append(target)
    return targets


def keyed_snapshot_items(snapshot: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    values = snapshot.get(key) or []
    if not isinstance(values, list):
        return result
    for item in values:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target") or item.get("name") or item.get("symbol") or "").strip()
        if target:
            result[target] = item
    return result


def attach_snapshot_data(items: list[dict[str, Any]], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    holdings = keyed_snapshot_items(snapshot, "holdings")
    candidates = keyed_snapshot_items(snapshot, "candidates")
    merged: list[dict[str, Any]] = []
    for item in items:
        next_item = dict(item)
        keys = {str(next_item.get("target") or ""), str(next_item.get("name") or ""), str(next_item.get("symbol") or "")}
        holding = next((holdings[key] for key in keys if key in holdings), None)
        candidate = next((candidates[key] for key in keys if key in candidates), None)
        if holding:
            next_item["holding_weight_pct"] = number(holding.get("weight_pct", holding.get("position_pct")))
            if holding.get("cost") is not None:
                next_item["cost"] = number(holding.get("cost"))
            if holding.get("current") is not None:
                next_item["current"] = number(holding.get("current"))
            next_item["snapshot_role"] = "holding"
        elif candidate:
            next_item["holding_weight_pct"] = 0
            next_item["snapshot_role"] = "candidate"
        merged.append(next_item)
    return merged


def is_risk_exit(item: dict[str, Any]) -> bool:
    current = number(item.get("current"))
    stop = number(item.get("stop"))
    return item.get("status") == "暂不碰" or (stop > 0 and current <= stop)


def is_high_stalled(item: dict[str, Any]) -> bool:
    current = number(item.get("current"))
    take = number(item.get("take"))
    status = str(item.get("status") or "")
    if status == "冲高减仓":
        return True
    return take > 0 and current >= take * 0.98


def is_near_reduce(item: dict[str, Any]) -> bool:
    current = number(item.get("current"))
    confirm = number(item.get("confirm"))
    status = str(item.get("status") or "")
    return status in {"等转强", "突破观察"} or (confirm > 0 and current >= confirm)


def candidate_level(item: dict[str, Any]) -> str:
    current = number(item.get("current"))
    confirm = number(item.get("confirm"))
    status = str(item.get("status") or "")
    if confirm > 0 and current >= confirm:
        return "confirmed"
    if status in {"等转强", "低吸观察"} or (confirm > 0 and current >= confirm * 0.97):
        return "near"
    return "unconfirmed"


def choose_rotation(items: list[dict[str, Any]], snapshot: dict[str, Any]) -> dict[str, Any]:
    account = snapshot.get("account") if isinstance(snapshot.get("account"), dict) else {}
    max_move = number(account.get("max_move_pct"), 10)
    holdings = [item for item in items if number(item.get("holding_weight_pct")) > 0]
    candidates = [item for item in items if number(item.get("holding_weight_pct")) <= 0 and item.get("ok")]
    a = next((item for item in holdings if is_risk_exit(item)), None)
    if a:
        level = "风控退出"
        fraction = 0.5
        reason = f"{a['name']}跌破硬止损或进入暂不碰，先按风控处理。"
        b = next((item for item in candidates if candidate_level(item) == "confirmed"), None)
    else:
        stalled = [item for item in holdings if is_high_stalled(item)]
        near = [item for item in holdings if is_near_reduce(item)]
        b_confirmed = next((item for item in candidates if candidate_level(item) == "confirmed"), None)
        b_near = next((item for item in candidates if candidate_level(item) == "near"), None)
        if stalled and b_confirmed:
            a = stalled[0]
            b = b_confirmed
            level = "强轮动"
            fraction = 1 / 3
            reason = f"{a['name']}高位钝化，{b['name']}已站上确认位。"
        elif stalled:
            a = stalled[0]
            b = b_near
            level = "轻轮动"
            fraction = 1 / 6
            reason = f"{a['name']}接近减仓位但接力股未充分确认。"
        elif near and b_near:
            a = near[0]
            b = b_near
            level = "标准轮动"
            fraction = 0.25
            reason = f"{a['name']}性价比下降，{b['name']}接近确认。"
        else:
            return {
                "action": "不轮动",
                "level": "不轮动",
                "reason": "A 未钝化，B 未确认。",
                "max_move_pct": max_move,
            }
    released = number(a.get("holding_weight_pct")) * fraction
    if level != "风控退出":
        released = min(released, max_move)
    b_level = candidate_level(b) if b else "unconfirmed"
    transfer = min(released, max_move) if b and b_level == "confirmed" else 0
    cash_keep = max(released - transfer, 0)
    return {
        "action": f"触发{level}",
        "level": level,
        "reason": reason,
        "from": a,
        "to": b if b and b_level == "confirmed" else None,
        "watch_to": b if b and b_level != "confirmed" else None,
        "fraction": fraction,
        "released_pct": released,
        "transfer_pct": transfer,
        "cash_keep_pct": cash_keep,
        "max_move_pct": max_move,
    }


def holding_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        weight = number(item.get("holding_weight_pct"))
        if weight <= 0:
            continue
        cost_text = f"｜成本 {number(item.get('cost')):.2f}" if item.get("cost") is not None else ""
        lines.append(f"{item['name']}：{percent_decimal(weight)}｜现价 {price(number(item.get('current')))}{cost_text}｜状态：{item.get('status')}")
    return lines or ["当前无持仓。"]


def key_price_lines(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        if not item.get("ok"):
            continue
        lines.append(f"{item['name']}：确认 {price(item.get('confirm'))}｜防守 {price(item.get('defense'))}｜硬止损 {price(item.get('stop'))}｜减仓 {price(item.get('take'))}")
    return lines


def render_snapshot_markdown(
    items: list[dict[str, Any]],
    snapshot: dict[str, Any],
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
    cash_floor: int = DEFAULT_CASH_FLOOR,
) -> str:
    merged = attach_snapshot_data(items, snapshot)
    decision = choose_rotation(merged, snapshot)
    account = snapshot.get("account") if isinstance(snapshot.get("account"), dict) else {}
    total_position = number(account.get("total_position_pct"), sum(number(item.get("holding_weight_pct")) for item in merged))
    cash = number(account.get("cash_pct"), max(0, 100 - total_position))
    max_move = number(account.get("max_move_pct"), 10)
    lines: list[str] = [
        "🧺 高切低轮动面板",
        f"规则版本：{SNAPSHOT_CONTRACT_VERSION}",
        "",
        "📌 当前结论",
        f"今日动作：{decision['action']}",
        f"原因：{decision['reason']}",
        "",
        "📊 当前仓位",
        f"总仓位：{percent_decimal(total_position)}",
        f"现金：{percent_decimal(cash)}",
        f"今日最多可动：{percent_decimal(max_move)}总仓",
    ]
    lines.extend(holding_lines(merged))
    lines.extend(["", "🔁 轮动动作"])
    source = decision.get("from")
    target = decision.get("to")
    watch_target = decision.get("watch_to")
    if source:
        lines.append(f"从{source['name']}减当前仓位的{compact_fraction(decision['fraction'])}，释放约{percent_decimal(decision['released_pct'])}总仓。")
        if target:
            lines.append(f"{target['name']}承接{percent_decimal(decision['transfer_pct'])}总仓，剩余{percent_decimal(decision['cash_keep_pct'])}留现金。")
        elif watch_target:
            lines.append(f"{watch_target['name']}还未确认，释放仓位先留现金。")
        else:
            lines.append("没有合格接力，释放仓位先留现金。")
    else:
        lines.append("今天不做高切低，继续等待盘面触发。")
    lines.extend(["", "🎯 关键价位"])
    lines.extend(key_price_lines(merged))
    lines.extend(["", "🛑 卖完条件"])
    sell_out_count = 0
    for item in merged:
        if number(item.get("holding_weight_pct")) > 0:
            lines.append(f"{item['name']}：跌破{price(item.get('stop'))}，或跌破后反抽站不回，卖完。")
            sell_out_count += 1
    if sell_out_count == 0:
        lines.append("无持仓：没有卖完条件。")
    lines.extend(
        [
            "",
            "🚫 禁止动作",
            "低位票未确认前，不接满仓位。",
            "持仓趋势未破前，不因为有候选股就清仓。",
            "没有合格接力时，减出来的钱先进现金。",
            "",
            "📈 后续复盘",
            "明天：看 B 是否站稳，A 是否卖飞。",
            "一周后：比较 A 和 B 谁更强。",
            "一月后：判断这次高切低是否真的成功。",
            "",
            "👉 一句话",
        ]
    )
    if source and target:
        lines.append(f"{source['name']}让出仓位，{target['name']}确认后承接；其余现金保留主动权。")
    elif source:
        lines.append(f"{source['name']}先让出风险仓位，但没有确认接力就不强行买。")
    else:
        lines.append("今天没有高切低条件，继续等盘面触发。")
    return "\n".join(lines)


def render_markdown(
    items: list[dict[str, Any]],
    plan: dict[str, Any],
    sorted_items: list[dict[str, Any]],
    market_level: str,
    market_note: str,
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
    cash_floor: int = DEFAULT_CASH_FLOOR,
    main_cap: int = DEFAULT_MAIN_CAP,
) -> str:
    weights = plan["weights"]
    total_alloc = plan["total"]
    cash = plan["cash"]
    
    tradable = [i for i in sorted_items if i.get("ok")]
    if not tradable:
        return "错误：无可用标的数据"

    main = plan["roles"].get("主仓")
    secondary = plan["roles"].get("副仓")
    
    # 1. 标题
    lines = [f"轮动仓位 — {' + '.join(sorted(i['name'] for i in tradable))}"]
    lines.append("")
    
    # 2. 决策段
    lines.append(_render_decision(tradable, main, secondary))
    lines.append("")
    
    # 3. 持仓速览
    lines.append("📊 持仓速览")
    for it in tradable:
        nm = it["name"]
        cur = it.get("current", 0)
        cost = it.get("cost")
        sh = it.get("shares")
        if cost is not None and sh:
            pl_pct = round((cur - float(cost)) / float(cost) * 100, 1)
            pl_amt = round((cur - float(cost)) * sh, 0)
            lines.append(f"  {nm}: 现价{cur:.2f}  成本{float(cost):.2f}  {int(sh)}股  浮盈{pl_pct:+.1f}%  ({pl_amt:+,.0f}元)")
        else:
            lines.append(f"  {nm}: 现价{cur:.2f}  未持仓")
    lines.append("")
    
    # 4. 仓位建议
    lines.append("📈 仓位建议")
    for nm, wt in weights.items():
        it = next((i for i in tradable if i["name"] == nm), None)
        if not it:
            continue
        role_txt = ""
        for role_nm in ("主仓", "副仓", "观察"):
            r = plan["roles"].get(role_nm)
            if r and r["name"] == nm:
                role_txt = "（得分最高）" if role_nm == "主仓" else "（得分次优）" if role_nm == "副仓" else "（观察）"
                break
        lines.append(f"  {nm} → {wt}%  {role_txt}")
    lines.append(f"  现金 → {cash}%")
    has_high_atr = any(float(i.get("atr_ratio") or 0) >= 0.03 for i in tradable)
    if has_high_atr:
        lines.append("  （有标的波动偏高，得分+筹码降权决定比例）")
    else:
        lines.append("  （得分占比决定比例，ATR仅作降权参考）")
    lines.append("")
    
    # 5. 仓位对比（建议 vs 实际）
    lines.append("📋 仓位对比")
    total_mv = sum((i["shares"] * i.get("current", 0)) for i in tradable if i.get("shares") and i.get("current"))
    for nm, wt in weights.items():
        it = next((i for i in tradable if i["name"] == nm), None)
        if not it:
            continue
        act = 0
        if total_mv > 0 and it.get("shares") and it.get("current"):
            act = round(it["shares"] * it["current"] / total_mv * 100)
        diff = act - wt
        flag = "✅ 接近" if abs(diff) <= 5 else f"⚠️ 超{diff}%" if diff > 0 else f"⚠️ 少{abs(diff)}%"
        lines.append(f"  {nm}| 建议{wt}%  实际{act}%  → 差{diff:+d}%  {flag}")
    lines.append("")
    
    # 6. 今日行动
    lines.append("📎 今日行动")
    for nm in weights:
        it = next((i for i in tradable if i["name"] == nm), None)
        if not it or not it.get("confirm"):
            continue
        dist = round((it["confirm"] - it["current"]) / it["current"] * 100, 1)
        lines.append(f"  · {nm} 距确认位 {it['confirm']:.2f} 还差 {dist}%, 关注盘中")
    lines.append("")

    # 7. 轮动触发（仅协同换股条件）
    lines.append("🔄 轮动触发")
    if len(tradable) >= 2:
        a, b = tradable[0], tradable[1]
        a_stop = f"{a['stop']:.2f}" if a.get("stop") else "--"
        b_cfm = f"{b['confirm']:.2f}" if b.get("confirm") else "--"
        lines.append(f"  换股条件: {a['name']} 破 {a_stop} 且 {b['name']} 稳 {b_cfm}")
    is_trig = any(i.get("status") in ("暂不碰", "数据失败") or (i.get("stop") and i.get("current") <= i["stop"]) for i in tradable)
    lines.append(f"  当前: {'已触发' if is_trig else '未触发'}")
    lines.append("")

    # 8. 操作信号（个股买卖点 + 目标价 + 盈亏比）
    lines.append("💡 操作信号")
    for it in tradable:
        nm = it["name"]
        cur = it.get("current", 0)
        cfm = it.get("confirm")
        defense = it.get("defense")
        stop = it.get("stop")
        take = it.get("take")
        if cfm and take:
            up = round((take - cfm) / cfm * 100, 1)
            dist_to_stop = round((cur - stop) / cur * 100, 1) if stop else None
            dist_to_cfm = round((cfm - cur) / cur * 100, 1)
            # 买入信号：站上确认位 → 看高减仓位
            lines.append(f"  {nm}（现价{cur:.2f}）：")
            lines.append(f"    🟢 站上 {cfm:.2f} → 看高 {take:.2f}（最多赚{up}%）")
            if dist_to_stop is not None and dist_to_stop > 0:
                lines.append(f"    🔴 跌破 {stop:.2f} → 清仓（最多亏{dist_to_stop}%）")
            else:
                lines.append(f"    🔴 跌破 {stop:.2f} → 清仓")
            lines.append(f"    距触发差 {dist_to_cfm}%, {'快到' if dist_to_cfm < 3 else '还需确认'}")
            if defense:
                lines.append(f"    支撑位: {defense:.2f}（止损参考）")
        elif stop:
            lines.append(f"  {nm}: 暂无明确信号，继续观望")
        lines.append("")
    
    return "\n".join(lines)


def _render_decision(tradable, main, secondary):
    """生成决策段"""
    st = [i.get("status", "") for i in tradable]
    if "暂不碰" in st:
        n = [i["name"] for i in tradable if i.get("status") == "暂不碰"]
        return f"🔔 决策：卖出\n  {n[0] if n else '某'}进入暂不碰，建议减仓或清仓。"
    if any("防守" in s for s in st):
        miss = []
        for i in tradable:
            if i.get("confirm") and i.get("current") < i["confirm"]:
                d = round((i["confirm"] - i["current"]) / i["current"] * 100, 1)
                miss.append(f"{i['name']}({d}%)")
        return f"🔔 决策：不动\n  全部待确认{','.join(miss)}，暂不操作。" if miss else "🔔 决策：不动\n  暂无明确信号。"
    if "低吸观察" in st:
        n = [i["name"] for i in tradable if i.get("status") == "低吸观察"]
        return f"🔔 决策：观察买盘\n  {', '.join(n[:2])}进入低吸观察。"
    if "冲高减仓" in st:
        n = [i["name"] for i in tradable if i.get("status") == "冲高减仓"]
        return f"🔔 决策：减仓\n  {', '.join(n[:2])}冲高减仓，建议降低仓位。"
    return "🔔 决策：等待\n  信号不明确，继续观察盘面。"


def build_advice(
    main: dict | None,
    secondary: dict | None,
    sorted_items: list[dict[str, Any]],
    market_level: str,
    weights: dict[str, int],
) -> list[str]:
    adv: list[str] = []
    if not main:
        adv.append("没有可用的标的，今天不操作。")
        return adv

    trades: list[dict] = []
    for item in [main, secondary]:
        if item:
            trades.append(item)
    for item in sorted_items:
        if item != main and item != secondary and item.get("status") not in {"暂不碰", "数据失败"}:
            trades.append(item)

    for t in trades:
        name = t["name"]
        current = float(t.get("current") or 0)
        confirm = t.get("confirm")
        take = t.get("take") or 0
        stop = t.get("stop") or 0
        status = t.get("status", "")
        current_txt = f"{current:.2f}" if current > 0 else "--"
        adv.append(f"  {name}  现价{current_txt}  现状{status}")
        if confirm and take > 0 and current < confirm:
            upside_pct = round((take - confirm) / confirm * 100)
            loss_pct = round((confirm - stop) / confirm * 100) if stop > 0 else 0
            adv.append(f"    站稳后看{confirm:.2f}→{take:.2f}（+{upside_pct}%）  跌破止损{stop:.2f}（-{loss_pct}%）")
        elif confirm and take > 0 and current >= confirm:
            upside_pct = round((take - confirm) / confirm * 100)
            adv.append(f"    站稳后看已站上当→{take:.2f}（+{upside_pct}%）  跌破止损无")
        elif stop > 0:
            adv.append(f"    站稳后看无  跌破止损{stop:.2f}")
        else:
            adv.append(f"    站稳后看无  跌破止损无")
    adv.append("")
    if len(trades) > 1:
        adv.append(f"轮动节奏：")
        for t in trades[:2]:
            confirm = t.get("confirm")
            t_text = f"{confirm:.2f}" if confirm else "确认信号"
            adv.append(f"  · {t['name']} 先不动，等 {t_text} 确认后再考虑动")
    if market_level in ("偏弱", "很差"):
        adv.append(f"\n  大盘{market_level}，不加仓不轮动，先活着再说。")
    return adv


def _with_climate_adjusted(
    sorted_items: list[dict[str, Any]],
    market_level: str,
) -> list[dict[str, Any]]:
    result = []
    for item in sorted_items:
        adj = dict(item)
        orig = str(item.get("status") or "")
        adj["adjusted_status"] = climate_adjust(orig, market_level)
        result.append(adj)
    return result


def build_portfolio(
    targets: list[str],
    *,
    holdings: dict[str, dict] | None = None,
    max_total: int = DEFAULT_MAX_TOTAL,
    cash_floor: int = DEFAULT_CASH_FLOOR,
    main_cap: int = DEFAULT_MAIN_CAP,
) -> dict[str, Any]:
    valid_targets = [item.strip() for item in targets if isinstance(item, str) and item.strip()]
    if len(valid_targets) < 2:
        raise RuntimeError("轮动仓位计划至少需要两只股票")
    provider = get_provider()
    items = [analyze_target(target, provider, LOOKBACK_DAYS) for target in valid_targets]
    if not any(item.get("ok") for item in items):
        raise RuntimeError("所有股票数据都获取失败，无法做仓位计划")
    if holdings:
        for item in items:
            name = str(item.get("name") or "")
            h = holdings.get(name)
            if h:
                if h.get("cost") is not None:
                    item["cost"] = float(h["cost"])
                item["shares"] = int(h.get("shares", 0))
    sorted_items = sort_candidates(items)

    market_level_raw = get_market_level() or ""
    market_note = get_market_note()
    market_level = market_level_raw if market_level_raw in ("正常", "偏弱", "很差", "") else "正常"
    if not market_level:
        market_level = "正常"

    has_high_atr = any(
        float(it.get("atr_ratio") or 0) >= 0.03
        for it in sorted_items
        if it.get("ok")
    )
    effective_max = portfolio_total_cap(market_level, has_high_atr)

    if market_level not in ("正常", "", "未知"):
        sorted_items = _with_climate_adjusted(sorted_items, market_level)

    plan = build_roles(sorted_items, max_total=effective_max, main_cap=main_cap)
    markdown = render_markdown(
        items, plan, sorted_items, market_level, market_note,
        max_total=max_total, cash_floor=cash_floor, main_cap=main_cap,
    )
    signal_summaries = build_signal_summaries(
        sorted_items,
        max_total=main_cap,
        max_single_move=10,
        market_level=market_level,
    )
    return {
        "items": items,
        "sorted": sorted_items,
        "plan": plan,
        "signal_summaries": signal_summaries,
        "portfolio_markdown": markdown,
    }


def load_snapshot(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("snapshot must be a JSON object")
    return data


def build_snapshot_portfolio(
    snapshot: dict[str, Any],
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
    cash_floor: int = DEFAULT_CASH_FLOOR,
) -> dict[str, Any]:
    valid_targets = snapshot_targets(snapshot)
    if len(valid_targets) < 2:
        raise RuntimeError("快照至少需要两只股票：持仓和候选合计不少于2只")
    provider = get_provider()
    items = [analyze_target(target, provider, LOOKBACK_DAYS) for target in valid_targets]
    if not any(item.get("ok") for item in items):
        raise RuntimeError("所有股票数据都获取失败，无法做仓位计划")
    merged = attach_snapshot_data(items, snapshot)
    account = snapshot.get("account") if isinstance(snapshot.get("account"), dict) else {}
    max_move = int(round(number(account.get("max_move_pct"), 10)))
    markdown = render_snapshot_markdown(items, snapshot, max_total=max_total, cash_floor=cash_floor)
    signal_summaries = build_signal_summaries(merged, max_total=max_total, max_single_move=max_move)
    return {"items": items, "snapshot": snapshot, "signal_summaries": signal_summaries, "portfolio_markdown": markdown}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a 2-3 stock rotation and position plan.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--targets", nargs="+", help="A-share names or codes")
    group.add_argument("--snapshot", help="JSON portfolio snapshot path")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--max-total", type=int, default=DEFAULT_MAX_TOTAL)
    parser.add_argument("--cash-floor", type=int, default=DEFAULT_CASH_FLOOR)
    parser.add_argument("--main-cap", type=int, default=DEFAULT_MAIN_CAP)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.main_cap > 50:
        print("轮动仓位失败：主仓上限不能超过 50%", file=sys.stderr)
        return 1
    if args.max_total > 100 - args.cash_floor:
        print("轮动仓位失败：组合上限不能高于现金底线后的可用仓位", file=sys.stderr)
        return 1
    try:
        if args.snapshot:
            result = build_snapshot_portfolio(load_snapshot(args.snapshot), max_total=args.max_total, cash_floor=args.cash_floor)
        else:
            result = build_portfolio(args.targets, max_total=args.max_total, cash_floor=args.cash_floor, main_cap=args.main_cap)
    except Exception as exc:
        print(f"轮动仓位失败：{exc}", file=sys.stderr)
        return 1
    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(result["portfolio_markdown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
