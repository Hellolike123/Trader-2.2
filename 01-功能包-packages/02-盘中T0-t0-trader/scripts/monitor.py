from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

CONTRACTS = Path(__file__).resolve().parents[3] / "02-共享模块-shared" / "03-输出校验-contracts"
SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "02-共享模块-shared" / "scripts"
SHARED_ROOT = Path(__file__).resolve().parents[3] / "02-共享模块-shared"
SHARED_MARKET = Path(__file__).resolve().parents[3] / "02-共享模块-shared" / "01-行情数据-market-data"
for _p in (CONTRACTS, SHARED_SCRIPTS, SHARED_ROOT, SHARED_MARKET):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from trader_shared.data_manager import DataManager
from price_point_engine import price
from signal_store import append_signal
from t0_run import build_plan, build_t0_event_signal
from config import FREQUENCY_STOP_LIMIT
from light_data import is_trading_time

try:
    from trader_shared import get_market_level, add_warning, get_market_note, log_safe, fill_by_target
    track_t0_signal = log_safe
except ImportError:
    import warnings
    warnings.warn(
        "[t0-trader] shared module not available — market status, signal tracking, and state sync are disabled. "
        "T0 monitor will still work but without shared state integration.",
        stacklevel=2,
    )

    def get_market_level() -> str: return ""
    def get_market_note() -> str: return ""
    def add_warning(msg: str, related_stock: str = "") -> None: pass
    def track_t0_signal(skill, target, symbol, signal_type, price, env_level, env_note): pass
    def fill_by_target(target, pnl_pct, days_held, outcome): pass


CACHE_DIR = Path(os.environ.get("T0_TRADER_CACHE_DIR", Path.home() / ".t0-trader"))
CACHE_PATH = Path(os.environ.get("T0_TRADER_STATE_PATH", CACHE_DIR / "state.json"))
COOLDOWN_MINUTES = 15

BUY_TRIGGERED = "BUY_TRIGGERED"
BUY_EXPIRED = "BUY_EXPIRED"
BUY_BLOCKED = "BUY_BLOCKED"
BUY_INVALIDATED = "BUY_INVALIDATED"
SELL_TRIGGERED = "SELL_TRIGGERED"
SELL_EXPIRED = "SELL_EXPIRED"
SELL_BLOCKED = "SELL_BLOCKED"
SELL_INVALIDATED = "SELL_INVALIDATED"


def load_state(path: Path = CACHE_PATH) -> dict[str, Any]:
    return DataManager.load_state("t0_state", {}, path=path)


def state_lock_path(path: Path = CACHE_PATH) -> Path:
    return path.with_name(f"{path.name}.lock")


@contextmanager
def state_lock(path: Path = CACHE_PATH) -> Iterator[None]:
    with DataManager.state_lock("t0_state", path=path):
        yield


def save_state(state: dict[str, Any], path: Path = CACHE_PATH) -> None:
    DataManager.save_state("t0_state", state, path=path)


def reset_target_cache(target_key: str | None = None, path: Path = CACHE_PATH) -> None:
    with state_lock(path):
        if target_key is None:
            if path.exists():
                path.unlink()
            return
        state = load_state(path)
        targets = state.get("targets") if isinstance(state.get("targets"), dict) else {}
        targets.pop(target_key, None)
        state["targets"] = targets
        save_state(state, path)


def trade_day_key(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d")


def target_state_for(symbol: str, path: Path = CACHE_PATH, now: datetime | None = None) -> dict[str, Any]:
    state = load_state(path)
    targets = state.get("targets") if isinstance(state.get("targets"), dict) else {}
    target_state = targets.get(symbol)
    if not isinstance(target_state, dict):
        return {}
    if target_state.get("trade_day") != trade_day_key(now):
        return {}
    return target_state


def recent_history(symbol: str, path: Path = CACHE_PATH, limit: int = 3, now: datetime | None = None) -> list[dict[str, Any]]:
    target_state = target_state_for(symbol, path, now)
    history = target_state.get("history") if isinstance(target_state.get("history"), list) else []
    current_day = trade_day_key(now)
    filtered = [item for item in history if isinstance(item, dict) and str(item.get("trade_day") or "") == current_day]
    return filtered[-limit:]


def round_lot(shares: float | int | None) -> int:
    if shares is None:
        return 0
    return int(float(shares) // 100 * 100)


def parse_move_range(max_move: str) -> tuple[float, float] | None:
    if "10%-20%" in max_move:
        return 0.10, 0.20
    if "20%-30%" in max_move:
        return 0.20, 0.30
    return None


def position_text(plan: dict[str, Any], position: int | None) -> str | None:
    if position is None:
        return None
    move = parse_move_range(str(plan.get("max_move") or ""))
    if not move:
        return "建议T仓：不动"
    low = round_lot(position * move[0])
    high = round_lot(position * move[1])
    if high < 100:
        return "建议T仓：底仓不足，暂不建议拆分T仓"
    return f"建议T仓：{low}-{high}股"


def profit_text(plan: dict[str, Any], cost: float | None) -> str | None:
    if cost is None or cost <= 0:
        return None
    current = float(plan.get("current_price") or 0)
    if current <= 0:
        return None
    profit = (current / cost - 1) * 100
    return f"成本：{cost:.2f}，当前盈亏：{profit:+.2f}%"


def trigger_key(side: str, model: dict[str, Any]) -> str:
    trigger_price = model.get("trigger_price") or model.get("execution_price") or model.get("observation_price")
    trigger_time = model.get("trigger_time") or ""
    zone = model.get("zone") if isinstance(model.get("zone"), dict) else {}
    source = zone.get("source") or ""
    return f"{side}:{trigger_time}:{trigger_price}:{source}"


def event_id(event: str, plan: dict[str, Any]) -> str:
    model = plan["buy"] if event.startswith("BUY") else plan["sell"]
    return f"{event}:{trigger_key('BUY' if event.startswith('BUY') else 'SELL', model)}"


def is_executable(model: dict[str, Any]) -> bool:
    return model.get("status") == "已触发" and model.get("execution_price") is not None


def is_expired(model: dict[str, Any]) -> bool:
    return model.get("status") == "触发过期"


def side_event(side: str, previous: str | None, model: dict[str, Any], *, first_run: bool = False) -> str | None:
    current = str(model.get("status") or "")
    if current == previous and not first_run:
        return None
    if current == "观察中" or current == "未进入候选区" or current == "数据不足":
        return None
    if current == "已触发":
        return BUY_TRIGGERED if side == "buy" else SELL_TRIGGERED
    if current == "触发过期":
        return None if first_run else (BUY_EXPIRED if side == "buy" else SELL_EXPIRED)
    if current == "被阻断":
        return None if first_run else (BUY_BLOCKED if side == "buy" else SELL_BLOCKED)
    return None


def detect_state_change(previous_state: dict[str, Any] | None, plan: dict[str, Any]) -> list[str]:
    previous_state = previous_state or {}
    if plan.get("data_status") in {"insufficient", "non_trading"}:
        return []
    first_run = not bool(previous_state)
    events: list[str] = []
    current_price = float(plan.get("current_price") or 0)
    buy = plan["buy"]
    sell = plan["sell"]
    if previous_state.get("buy_status") in {"观察中", "已触发"} and current_price < float(buy.get("invalid_price") or 0):
        events.append(BUY_INVALIDATED)
    if previous_state.get("sell_status") in {"观察中", "已触发"} and current_price > float(sell.get("invalid_price") or 10**12):
        events.append(SELL_INVALIDATED)
    buy_event = side_event("buy", previous_state.get("buy_status"), buy, first_run=first_run)
    sell_event = side_event("sell", previous_state.get("sell_status"), sell, first_run=first_run)
    if buy_event and (buy_event != BUY_TRIGGERED or is_executable(buy)):
        events.append(buy_event)
    if sell_event and (sell_event != SELL_TRIGGERED or is_executable(sell)):
        events.append(sell_event)
    return events


def is_in_cooldown(target_state: dict[str, Any], event_key: str, now: datetime | None = None, cooldown_minutes: int = COOLDOWN_MINUTES) -> bool:
    now = now or datetime.now()
    last_events = target_state.get("last_events") if isinstance(target_state.get("last_events"), dict) else {}
    last_text = last_events.get(event_key)
    if not last_text:
        return False
    try:
        last_time = datetime.fromisoformat(last_text)
    except Exception:
        return False
    return now - last_time < timedelta(minutes=cooldown_minutes)


def alert_level(event: str, plan: dict[str, Any]) -> str:
    if event in {BUY_EXPIRED, SELL_EXPIRED, BUY_BLOCKED, SELL_BLOCKED, BUY_INVALIDATED, SELL_INVALIDATED}:
        return "别犯错"
    model = plan["buy"] if event.startswith("BUY") else plan["sell"]
    if str(plan.get("data_status")) == "delayed" or str(plan.get("space_state")) != "good" or int(model.get("matched_count") or 0) <= 4:
        return "轻仓做"
    return "可执行"


def event_action_text(event: str) -> str:
    return {
        BUY_TRIGGERED: "低吸触发",
        SELL_TRIGGERED: "高抛触发",
        BUY_EXPIRED: "低吸已过期",
        SELL_EXPIRED: "高抛已过期",
        BUY_BLOCKED: "低吸被阻断",
        SELL_BLOCKED: "高抛被阻断",
        BUY_INVALIDATED: "停止低吸",
        SELL_INVALIDATED: "停止高抛",
    }.get(event, "提醒")


def mark_events(target_state: dict[str, Any], plan: dict[str, Any], events: list[str], now: datetime | None = None) -> None:
    now = now or datetime.now()
    last_events = target_state.get("last_events") if isinstance(target_state.get("last_events"), dict) else {}
    history = target_state.get("history") if isinstance(target_state.get("history"), list) else []
    for event in events:
        key = event_id(event, plan)
        last_events[key] = now.isoformat(timespec="seconds")
        history.append({
            "event": event,
            "event_id": key,
            "trade_day": trade_day_key(now),
            "time": now.strftime("%H:%M"),
            "level": alert_level(event, plan),
            "text": event_action_text(event),
            "price": plan.get("current_price"),
        })
    target_state["last_events"] = last_events
    target_state["history"] = history[-20:]


def persist_event_signals(events: list[str], plan: dict[str, Any], store_path: Path | None = None) -> None:
    for event in events:
        sig = build_t0_event_signal(event, plan)
        # Populate market env metrics inside the signal record
        level = get_market_level()
        note = get_market_note()
        if level:
            sig["env_level"] = level
        if note:
            sig["env_note"] = note
        if level or note:
            env_str = f"（大盘：{level or '正常'} {note or ''}）"
            sig["summary"] = (sig.get("summary") or "") + env_str
            
        # Standard append to unified signals.jsonl
        append_signal(sig, store_path)


def snapshot(plan: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    buy = plan["buy"]
    sell = plan["sell"]
    return {
        "trade_day": trade_day_key(now),
        "name": plan["name"],
        "symbol": plan["symbol"],
        "current_price": plan["current_price"],
        "data_status": plan["data_status"],
        "buy_status": buy["status"],
        "sell_status": sell["status"],
        "buy_observation": buy.get("observation_price"),
        "sell_observation": sell.get("observation_price"),
        "buy_invalid": buy.get("invalid_price"),
        "sell_invalid": sell.get("invalid_price"),
        "updated_at": (now or datetime.now()).isoformat(timespec="seconds"),
    }


def _build_ladder_levels(plan: dict[str, Any]) -> list[tuple[float, str]]:
    levels = []
    buy = plan.get("buy") or {}
    sell = plan.get("sell") or {}
    
    if sell.get("observation_price"):
        levels.append((sell["observation_price"], "高抛压力"))
    if buy.get("acceptable_price"):
        levels.append((buy["acceptable_price"], "突破确认" if not buy.get("observation_price") else "最高追高"))
    if buy.get("observation_price"):
        levels.append((buy["observation_price"], "黄金低吸位"))
    if buy.get("invalid_price"):
        levels.append((buy["invalid_price"], "硬性止损"))
        
    unique_levels = {}
    for p, label in levels:
        if p not in unique_levels:
            unique_levels[p] = label
            
    sorted_levels = sorted(unique_levels.items(), key=lambda x: x[0], reverse=True)
    return sorted_levels


def _render_price_ladder(current: float, levels: list[tuple[float, str]]) -> str:
    lines = ["📈 价格天梯："]
    all_points = []
    current_inserted = False
    
    for p, label in levels:
        if abs(p - current) < 0.001:
            all_points.append({"price": p, "type": "merged", "label": label})
            current_inserted = True
        elif not current_inserted and current > p:
            all_points.append({"price": current, "type": "current"})
            all_points.append({"price": p, "type": "level", "label": label})
            current_inserted = True
        else:
            all_points.append({"price": p, "type": "level", "label": label})
            
    if not current_inserted:
        all_points.append({"price": current, "type": "current"})
        
    for i, pt in enumerate(all_points):
        p = pt["price"]
        if pt["type"] == "merged":
            lines.append(f"   ● {p:.2f} 元 ── ({pt['label']}) 📍 当前现价已达此位")
        elif pt["type"] == "current":
            if i == 0:
                lines.append(f"   ● {p:.2f} 元 ── (最新现价) 🚀 突破上方")
            elif i == len(all_points) - 1:
                lines.append(f"   ● {p:.2f} 元 ── (最新现价) 🔴 急速下跌中")
            else:
                lines.append(f"   ● {p:.2f} 元 ── (最新现价) 🟡 运行区间")
        else:
            symbol = "│"
            if i == 0 or (i == 1 and all_points[0]["type"] == "current"):
                symbol = "▲"
            elif i == len(all_points) - 1 or (i == len(all_points) - 2 and all_points[-1]["type"] == "current"):
                symbol = "▼"
            lines.append(f"   {symbol} {p:.2f} 元 ── ({pt['label']})")
            
    return "\n".join(lines)


def build_alert_message(event: str, plan: dict[str, Any], cost: float | None = None, position: int | None = None, previous_state: dict[str, Any] | None = None) -> str:
    name = plan.get("name", "未知")
    symbol = plan.get("symbol", "未知")
    current = plan.get("current_price", 0.0)
    
    header_map = {
        BUY_TRIGGERED: "🟢 今日决策：【低吸已触发】 (共振完美，可执行)",
        SELL_TRIGGERED: "🟢 今日决策：【高抛已触发】 (压力显现，请止盈)",
        BUY_EXPIRED: "⏸️ 今日决策：【已错过】 (价格已涨超，勿追)",
        SELL_EXPIRED: "⏸️ 今日决策：【已错过】 (价格已回落)",
        BUY_BLOCKED: "🚨 今日决策：【被阻断】 (禁止接飞刀！)",
        SELL_BLOCKED: "🚨 今日决策：【被阻断】 (高抛失效！)",
        BUY_INVALIDATED: "⚠️ 今日决策：【支撑跌破】 (已失效)",
        SELL_INVALIDATED: "⚠️ 今日决策：【阻力突破】 (已失效)",
    }
    header = f"🎯 {name} ({symbol}) ─ 盘中极简导航\n{header_map.get(event, '🔍 今日决策：【观察中】')}"
    
    levels = _build_ladder_levels(plan)
    ladder = _render_price_ladder(current, levels)
    
    summary = ["🔍 发生了什么 & 怎么做："]
    is_buy = event.startswith("BUY")
    model = plan.get("buy", {}) if is_buy else plan.get("sell", {})
    tape = model.get("t0_tape", {}).get("buy_tape" if is_buy else "sell_tape", {})
    tape_reason = tape.get("reason", "")
    
    if event == BUY_TRIGGERED:
        summary.append(f"价格在 {price(model.get('observation_price'))} 企稳，{tape_reason or '多头反攻确认'}！")
        summary.append(f"* 📥 【做T指令】：动用部分现金，在 **{(model.get('execution_price') or current):.2f} - {(model.get('acceptable_price') or current):.2f}** 之间分批低吸。")
        if model.get("acceptable_price"):
            summary.append(f"* 🚫 【追高防线】：最高不超 **{model.get('acceptable_price'):.2f}**，再高不追。")
        if model.get("invalid_price"):
            summary.append(f"* ⚠️ 【日内止损】：跌破 **{model.get('invalid_price'):.2f}** 做T单必须止损。")
    elif event == SELL_TRIGGERED:
        summary.append(f"价格接近 {price(model.get('observation_price'))} 压力位，{tape_reason or '空头压制明显'}！")
        summary.append(f"* 📤 【做T指令】：在 **{(model.get('acceptable_price') or current):.2f} - {(model.get('execution_price') or current):.2f}** 之间分批高抛。")
    elif event == BUY_BLOCKED:
        reasons = model.get("blocked_reasons") or ["强阻断"]
        summary.append(f"盘中发现抛压：{'、'.join(str(r) for r in reasons)}。")
        summary.append("目前空头力量较大，千万不要伸手接飞刀！底仓卧倒，做T现金锁死，今天直接放弃低吸。")
    elif event == BUY_INVALIDATED:
        summary.append(f"价格放量跌破了 **{model.get('invalid_price', '支撑线')}**。")
        summary.append("该位置已失效，多头防线失守，今天放弃该位置的低吸计划。")
    elif event == BUY_EXPIRED:
        summary.append(f"价格已反弹至 **{current:.2f}**，超过了我们的最高心理价位 **{model.get('acceptable_price', '上限')}**。")
        summary.append("虽然错过了最低点，但不要追高，宁可错过也不要做错。")
    else:
        summary.append(f"触发了 {event}，请根据交易纪律严格执行。")
        
    return f"{header}\n{ladder}\n" + "\n".join(summary)


# ═══════════════════════════════════════════════
# 03-System Fuse：单日止损次数熔断机制
# ═══════════════════════════════════════════════

def _fuse_alert(target_key: str, count: int, name: str = "") -> str:
    """生成熔断告警"""
    time_str = datetime.now().strftime("%H:%M")
    parts = [
        "🚨熔断（当天止损次数上限）",
        f"累计止损：{count} 次（阈值：{FREQUENCY_STOP_LIMIT} 次）",
        f"标的：{name or target_key}",
        "",
        "当前标的当日停止 T0 检查",
        f"时间：{time_str}",
        "请手动确认或等待明日重置",
    ]
    return "\n".join(parts)


def _trigger_reason_lines(model: dict[str, Any]) -> list[str]:
    if not matched:
        return []
    core = [m for m in matched if any(kw in m for kw in ("MACD", "RSI", "VWAP"))]
    core_str = " + ".join(core[:2]) if core else matched[0]
    return [f"🔥 {core_str} | {len(matched)}个信号"]


def _monitor_position_lines(plan: dict[str, Any], position: int | None) -> list[str]:
    atr_info = plan.get("atr_info") or {}
    atr_ratio = float(atr_info.get("atr_ratio", 0) or 0)
    pos_range = "底仓10%-20%" if atr_ratio >= 0.02 else "底仓10%-30%"
    lines = [f"仓位 {pos_range}"]
    if position:
        try:
            lot = round_lot(position * 0.1)
            lines[-1] += f"，最多{lot}股"
        except Exception:
            pass
    return lines


def transition_line(event: str, plan: dict[str, Any], previous_state: dict[str, Any]) -> str | None:
    if event.startswith("BUY"):
        previous = previous_state.get("buy_status") or "无"
        current = "失效" if event == BUY_INVALIDATED else plan["buy"]["status"]
        return f"状态：{previous} → {current}"
    if event.startswith("SELL"):
        previous = previous_state.get("sell_status") or "无"
        current = "失效" if event == SELL_INVALIDATED else plan["sell"]["status"]
        return f"状态：{previous} → {current}"
    return None


def buy_alert_lines(event: str, buy: dict[str, Any]) -> list[str]:
    if event == BUY_TRIGGERED:
        return [
            f"执行参考：{price(buy['execution_price'])}",
            f"最高可接受：{price(buy['acceptable_price'])}，超过不追",
            f"失效：{price(buy['invalid_price'])}",
        ]
    if event == BUY_EXPIRED:
        return ["低吸已错过，当前价高于最高可接受价。", "动作：不追，等待下一次回落确认。"]
    if event == BUY_BLOCKED:
        return [f"原因：{'、'.join(buy.get('blocked_reasons') or ['强阻断'])}", "动作：被阻断，不接。"]
    if event == BUY_INVALIDATED:
        return [f"原因：跌破低吸失效价 {price(buy['invalid_price'])}", "动作：今日停止低吸，不再接。"]
    return []


def sell_alert_lines(event: str, sell: dict[str, Any]) -> list[str]:
    if event == SELL_TRIGGERED:
        return [
            f"执行参考：{price(sell['execution_price'])}",
            f"最低可接受：{price(sell['acceptable_price'])}，低于不砸",
            f"失效：{price(sell['invalid_price'])}",
        ]
    if event == SELL_EXPIRED:
        return ["高抛已错过，当前价低于最低可接受价。", "动作：不砸，等待下一次冲高确认。"]
    if event == SELL_BLOCKED:
        return [f"原因：{'、'.join(sell.get('blocked_reasons') or ['强阻断'])}", "动作：被阻断，不卖。"]
    if event == SELL_INVALIDATED:
        return [f"原因：突破高抛失效价 {price(sell['invalid_price'])}", "动作：取消高抛，不卖飞。"]
    return []


def run_once(
    target: str,
    *,
    cost: float | None = None,
    position: int | None = None,
    verbose: bool = False,
    reset_cache: bool = False,
    state_path: Path = CACHE_PATH,
) -> str:
    # 非交易时间直接静默退出，避免周末/节假日发垃圾消息
    if not is_trading_time():
        return ""
    plan = build_plan(target)
    target_key = str(plan.get("symbol") or target)
    now = datetime.now()
    
    with state_lock(state_path):
        state = load_state(state_path)
        fuse_state = state.get("_fuse", {})
        day = trade_day_key(now)
        
        # If already fused today, mark flag but still allow state updates
        already_fused = False
        day_fuse = fuse_state.get(day) if isinstance(fuse_state, dict) else None
        if isinstance(day_fuse, dict) and day_fuse.get("fused"):
            already_fused = True
        
        targets = state.get("targets") if isinstance(state.get("targets"), dict) else {}
        if reset_cache:
            targets.pop(target_key, None)
        previous = targets.get(target_key)
        if isinstance(previous, dict) and previous.get("trade_day") != trade_day_key():
            previous = None
        events = detect_state_change(previous, plan)
        target_state = previous if isinstance(previous, dict) else {}
        allowed_events = [event for event in events if not is_in_cooldown(target_state, event_id(event, plan))]
        new_snapshot = snapshot(plan)
        new_snapshot["last_events"] = dict(target_state.get("last_events") or {})
        new_snapshot["history"] = list(target_state.get("history") or [])
        mark_events(new_snapshot, plan, allowed_events)
        targets[target_key] = new_snapshot
        state["targets"] = targets
        
        # Count STOP losses and check fuse trigger
        if allowed_events:
            stop_count = day_fuse.get("count", 0) if isinstance(day_fuse, dict) else 0
            fused_targets = day_fuse.get("fused_targets", []) if isinstance(day_fuse, dict) else []
            for event in allowed_events:
                if event == BUY_INVALIDATED:
                    stop_count += 1
                    if target_key not in fused_targets:
                        fused_targets = fused_targets + [target_key]
            
            if fused_targets is None:
                fused_targets = []
            day_fuse = {"count": stop_count, "fused_targets": fused_targets}
            if stop_count >= FREQUENCY_STOP_LIMIT and not day_fuse.get("fused"):
                day_fuse["fused"] = True
                day_fuse["fused_at"] = now.strftime("%H:%M")
            fuse_state[day] = day_fuse
            state["_fuse"] = fuse_state
        
        save_state(state, state_path)
    
    # If fuse activated (or already active), return fuse alert
    if already_fused:
        name = plan.get("name", "")
        # Persist original events BEFORE fuse alert, so signals.jsonl has correct provenance
        if allowed_events:
            try:
                persist_event_signals(allowed_events, plan)
            except Exception as e:
                warnings.warn(f"[t0-monitor] 信号持久化失败: {e}")
            allowed_events = []
        alert = _fuse_alert(target_key, day_fuse["count"], name)
        return alert
    
    if allowed_events:
        try:
            persist_event_signals(allowed_events, plan)
        except Exception as e:
            warnings.warn(f"[t0-monitor] 信号持久化失败: {e}")
    if not allowed_events:
        return "无新提醒" if verbose else ""
    return "\n\n".join(build_alert_message(event, plan, cost=cost, position=position, previous_state=target_state) for event in allowed_events)


def sleep_until_next_interval(interval_minutes: int) -> None:
    time.sleep(max(1, int(interval_minutes)) * 60)


def run_monitor(
    target: str,
    interval: int = 5,
    *,
    cost: float | None = None,
    position: int | None = None,
    once: bool = False,
    max_alerts: int = 20,
    verbose: bool = False,
    reset_cache: bool = False,
) -> int:
    alerts = 0
    first = True
    try:
        while True:
            message = run_once(target, cost=cost, position=position, verbose=verbose, reset_cache=reset_cache and first)
            first = False
            if message:
                print(message)
                if message != "无新提醒":
                    alerts += 1
            if once or alerts >= max_alerts:
                return 0
            sleep_until_next_interval(interval)
    except KeyboardInterrupt:
        return 0
