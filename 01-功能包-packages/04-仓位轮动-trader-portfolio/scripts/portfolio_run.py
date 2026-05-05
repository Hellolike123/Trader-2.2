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
for _p in (SHARED_MARKET, SHARED_CANDIDATE, SHARED_SCRIPTS, SHARED_ROOT, SHARED_TS, CONTRACTS):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from candidate_model import analyze_target, sort_candidates
from config import DEFAULT_CASH_FLOOR, DEFAULT_MAIN_CAP, DEFAULT_MAX_TOTAL
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


def signal_state_for_item(item: dict[str, Any]) -> tuple[str, str, str, str]:
    status = str(item.get("status") or "")
    current = number(item.get("current"))
    confirm = number(item.get("confirm"))
    if status in {"暂不碰", "数据失败"} or is_risk_exit(item):
        return "defensive", "bearish_lean", "wait", "low"
    if status == "冲高减仓":
        return "reduce", "neutral", "reduce", "medium"
    if confirm > 0 and current >= confirm:
        return "track", "bullish", "track", "medium"
    if status in {"等转强", "突破确认", "突破观察"}:
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if status in {"低吸观察", "防守观察"}:
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


def build_signal_for_item(item: dict[str, Any], *, max_total: int, max_single_move: int) -> dict[str, Any]:
    signal_type, direction, action, confidence = signal_state_for_item(item)
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


def build_signal_summaries(items: list[dict[str, Any]], *, max_total: int, max_single_move: int) -> list[dict[str, Any]]:
    return [build_signal_for_item(item, max_total=max_total, max_single_move=max_single_move) for item in items]


PYRAMID_SCALES = {0: 0, 1: 0.15, 2: 0.35, 3: 0.6, 4: 0.85, 5: 1.0}

def target_weight(role: str, item: dict[str, Any], *, main_cap: int) -> int:
    status = str(item.get("status") or "")
    atr_level_str = str(item.get("atr_level") or "")
    score = float(item.get("livermore_score") or item.get("score") or 0)
    atr_cap = int(item.get("atr_cap") or 10)
    if status in {"暂不碰", "数据失败"}:
        return 0
    from candidate_core import base_weight, livermore_scale
    bw = base_weight(atr_level_str)
    tier = livermore_scale(status, score)
    scale = PYRAMID_SCALES.get(tier, 0)
    raw = round(bw * scale / max(scale, 0.01)) if scale > 0 else 0
    raw = max(raw, 0)
    raw = min(raw, atr_cap)
    return raw


def build_roles(sorted_items: list[dict[str, Any]], *, max_total: int, main_cap: int) -> dict[str, Any]:
    tradable = [item for item in sorted_items if item.get("status") not in {"暂不碰", "数据失败"}]
    roles = {
        "主仓": tradable[0] if len(tradable) >= 1 else None,
        "副仓": tradable[1] if len(tradable) >= 2 else None,
        "观察": tradable[2] if len(tradable) >= 3 else None,
    }
    weights: dict[str, int] = {}
    for role, item in roles.items():
        if item:
            weights[item["name"]] = target_weight(role, item, main_cap=main_cap)
    total = sum(weights.values())
    if total > max_total:
        for role in ("观察", "副仓", "主仓"):
            item = roles.get(role)
            if not item:
                continue
            name = item["name"]
            cut = min(weights.get(name, 0), total - max_total)
            weights[name] = weights.get(name, 0) - cut
            total -= cut
            if total <= max_total:
                break
    avoid = [item["name"] for item in sorted_items if item.get("status") in {"暂不碰", "数据失败"}]
    return {"roles": roles, "weights": weights, "avoid": avoid, "total": total, "cash": max(0, 100 - total)}


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
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
    cash_floor: int = DEFAULT_CASH_FLOOR,
    main_cap: int = DEFAULT_MAIN_CAP,
) -> str:
    sorted_items = sort_candidates(items)
    plan = build_roles(sorted_items, max_total=max_total, main_cap=main_cap)
    weights = plan["weights"]
    total = plan["total"]
    cash = plan["cash"]

    market_level = get_market_level()

    lines = [f"轮动仓位 — {' + '.join(sorted(set(str(it['name']) for it in sorted_items if it.get('ok'))))}"]
    lines.append("")
    if market_level:
        lines.append(f"🌍 大盘{market_level} | {get_market_note()}")
        lines.append("")

    lines.append("📌 组合")
    lines.append("")

    livermore_scale_func = None
    base_weight_func = None
    try:
        from candidate_core import base_weight, livermore_scale
        livermore_scale_func = livermore_scale
        base_weight_func = base_weight
    except ImportError:
        pass
    for role in ("主仓", "副仓", "观察"):
        item = plan["roles"].get(role)
        if not item:
            continue
        name = item["name"]
        actual = int(weights.get(name, 0))
        status = str(item.get("status") or "")
        atr_level_str = str(item.get("atr_level") or "")
        atr_cap_val = int(item.get("atr_cap") or 10)
        atr_ratio_val = float(item.get("atr_ratio") or 0)

        note = ""
        sbw = 0
        if livermore_scale_func and base_weight_func:
            score = float(item.get("livermore_score") or item.get("score") or 0)
            tier = livermore_scale_func(status, score)
            sc = PYRAMID_SCALES.get(tier, 0)
            sbw = base_weight_func(atr_level_str)
            if sbw > 0:
                target_pct = round(sbw * sc / max(sc, 0.01))
                if sbw != actual:
                    change = actual - sbw
                    if change > 0:
                        note = f"（{sbw}%起→加至{actual}%）"
                    elif change < 0 and actual > 0:
                        note = f"（{sbw}%起→{actual}%）"
                    else:
                        note = f"（{sbw}%起）"
        elif atr_cap_val < 10:
            note = f"（ATR上限{atr_cap_val}%）"

        lines.append(f"    {role}  {name}  仓位 {actual}%  {note}")
        lines.append(f"         状态：{status}")

    lines.append(f"    现金  {cash}%")
    lines.append("")

    if market_level in ("偏弱", "很差"):
        safe_total = 60 if any(float(it.get("atr_ratio") or 0) >= 0.03 for it in sorted_items if it.get("ok")) else 70
        lines.append(f"    ⚠️ 大盘{market_level} → 总仓不超过{safe_total}%，别轮入新票")

    lines.extend(["", "🎯 操作", ""])
    main = plan["roles"].get("主仓")
    secondary = plan["roles"].get("副仓")
    main_actual = int(weights.get(main["name"], 0)) if main else 0
    sec_actual = int(weights.get(secondary["name"], 0)) if secondary else 0

    def fmt_ops(item, current_pct):
        if not item:
            return ""
        name = item["name"]
        confirm = item.get("confirm")
        stop = item.get("stop")
        defense = item.get("defense")
        parts = [f"  {name}（现价{item.get('current', 0):.2f}元）"]
        parts.append(f"    · 当前仓位：{current_pct}%")
        if confirm and current_pct < 20:
            target = 20 if current_pct < 10 else 30
            parts.append(f"    · 加仓：站稳 {confirm:.2f} + 回踩不破 → 加到 {target}%")
        elif confirm and current_pct >= 20:
            parts.append(f"    · 已{current_pct}%，不加了")
        if defense and current_pct > 0:
            reduce_val = min(int(current_pct * 0.7), 10)
            parts.append(f"    · 防守：跌破 {defense:.2f} → 减至 {reduce_val}%")
        if stop:
            parts.append(f"    · 止损：跌破 {stop:.2f} → 清仓")
        return "\n".join(parts)

    lines.append(fmt_ops(main, main_actual))
    lines.append("")
    sec_ops = fmt_ops(secondary, sec_actual)
    if sec_ops:
        lines.append(sec_ops)
    for item in sorted_items:
        if not item.get("ok") or item.get("status") in {"暂不碰", "数据失败"}:
            continue
        name = item["name"]
        if name == main.get("name"):
            continue
        if secondary and name == secondary.get("name"):
            continue
        current_pct = int(weights.get(name, 0))
        line = fmt_ops(item, current_pct)
        if line:
            lines.append("")
            lines.append(line)

    # Replace price_range import with price
    lines.extend(["", "📍 关键价位", ""])
    for item in sorted_items:
        if not item.get("ok"):
            continue
        lines.append(f"  {item['name']}  买{price_range(item['buy_low'], item['buy_high'])}  防{price(item['defense'])}  损{price(item['stop'])}  减{price(item['take'])}")

    lines.extend(["", "🧭 结论", ""])
    active_tradable = [item for item in sorted_items if item.get("ok") and item.get("status") not in {"暂不碰", "数据失败"}]
    for i, item in enumerate(active_tradable[:2], 1):
        name = item["name"]
        role_name_str = "主仓" if main and main["name"] == name else "副仓" if secondary and secondary["name"] == name else "观察"
        pct = int(weights.get(name, 0))
        status = item.get("status", "")
        lines.append(f"  {role_name_str}  {name}  {pct}%（{status}）")
    lines.append("")
    extreme_count = sum(1 for it in active_tradable if float(it.get("atr_ratio") or 0) >= 0.03)
    if market_level in ("偏弱", "很差") and extreme_count >= 1:
        lines.append("大盘偏弱+高波动，不加仓不轮动，先活着再说。")
    elif market_level in ("偏弱", "很差"):
        lines.append(f"大盘{market_level}，不加仓不轮动。")
    elif extreme_count >= 1:
        lines.append("有标的波动放大，仓位给到最低一档，确认后再加。")
    else:
        lines.append("按计划执行，等信号确认后逐步建仓。")

    lines.extend(["", "💡 分析", ""])
    lines.extend(build_advice(main, secondary, sorted_items, market_level, weights))

    return "\n".join(lines)


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

    adv.append("")
    adv.append("| 标的 | 现价 | 现状 | 站稳后看 | 跌破止损 |")
    adv.append("| :--- | :--- | :--- | :--- | :--- |")
    for t in trades:
        name = t["name"]
        current = float(t.get("current") or 0)
        confirm = t.get("confirm")
        take = t.get("take") or 0
        stop = t.get("stop") or 0
        status = t.get("status", "")
        current_txt = f"{current:.2f}" if current > 0 else "--"
        if confirm and take > 0 and current < confirm:
            upside_pct = round((take - confirm) / confirm * 100)
            loss_pct = round((confirm - stop) / confirm * 100) if stop > 0 else 0
            adv.append(f"| {name} | {current_txt} | {status} | {confirm:.2f}→{take:.2f}（+{upside_pct}%） | {stop:.2f}（-{loss_pct}%） |")
        elif confirm and take > 0 and current >= confirm:
            upside_pct = round((take - confirm) / confirm * 100)
            adv.append(f"| {name} | {current_txt} | {status} | 已站上→{take:.2f}（+{upside_pct}%） | -- |")
        elif stop > 0:
            adv.append(f"| {name} | {current_txt} | {status} | -- | {stop:.2f} |")
        else:
            adv.append(f"| {name} | {current_txt} | {status} | -- | -- |")
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


def build_portfolio(
    targets: list[str],
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
    cash_floor: int = DEFAULT_CASH_FLOOR,
    main_cap: int = DEFAULT_MAIN_CAP,
) -> dict[str, Any]:
    valid_targets = [item.strip() for item in targets if isinstance(item, str) and item.strip()]
    if len(valid_targets) < 2:
        raise RuntimeError("轮动仓位计划至少需要两只股票")
    items = [analyze_target(target) for target in valid_targets]
    if not any(item.get("ok") for item in items):
        raise RuntimeError("所有股票数据都获取失败，无法做仓位计划")
    sorted_items = sort_candidates(items)
    plan = build_roles(sorted_items, max_total=max_total, main_cap=main_cap)
    markdown = render_markdown(items, max_total=max_total, cash_floor=cash_floor, main_cap=main_cap)
    signal_summaries = build_signal_summaries(sorted_items, max_total=main_cap, max_single_move=10)
    return {"items": items, "sorted": sorted_items, "plan": plan, "signal_summaries": signal_summaries, "portfolio_markdown": markdown}


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
    items = [analyze_target(target) for target in valid_targets]
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
