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
for _p in (CONTRACTS, SHARED_SCRIPTS, SHARED_ROOT):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from price_point_engine import price
from signal_store import append_signal
from t0_run import build_plan, build_t0_event_signal

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
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def state_lock_path(path: Path = CACHE_PATH) -> Path:
    return path.with_name(f"{path.name}.lock")


@contextmanager
def state_lock(path: Path = CACHE_PATH) -> Iterator[None]:
    lock_path = state_lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def save_state(state: dict[str, Any], path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, path)


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
        append_signal(build_t0_event_signal(event, plan), store_path)
        try:
            if event in {BUY_TRIGGERED, SELL_TRIGGERED}:
                signal_type = "low_buy_triggered" if event.startswith("BUY") else "high_sell_triggered"
                track_t0_signal("t0-trader", plan["name"], plan["symbol"], signal_type, float(plan.get("current_price") or 0), get_market_level(), get_market_note())
            elif event in {BUY_EXPIRED, SELL_EXPIRED}:
                track_t0_signal("t0-trader", plan["name"], plan["symbol"], "low_buy_watch" if event.startswith("BUY") else "high_sell_watch", float(plan.get("current_price") or 0), get_market_level(), get_market_note())
        except Exception:
            # signal tracking is best-effort; persistence to signal_store already succeeded
            pass


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


def _build_trigger_line(event: str, plan: dict[str, Any]) -> str:
    buy = plan["buy"]
    sell = plan["sell"]
    name = plan["name"]
    current = plan["current_price"]
    is_buy = event.startswith("BUY")
    model = buy if is_buy else sell

    emoji_map = {
        BUY_TRIGGERED: "🟢", SELL_TRIGGERED: "🔴",
        BUY_EXPIRED: "⏸️", SELL_EXPIRED: "⏸️",
        BUY_BLOCKED: "🚫", SELL_BLOCKED: "🚫",
        BUY_INVALIDATED: "⚠️", SELL_INVALIDATED: "⚠️",
    }
    emoji = emoji_map.get(event, "🔍")
    direction = "低吸" if is_buy else "高抛"
    state_map = {
        BUY_TRIGGERED: "触发", SELL_TRIGGERED: "触发",
        BUY_EXPIRED: "已错过", SELL_EXPIRED: "已错过",
        BUY_BLOCKED: "被阻断", SELL_BLOCKED: "被阻断",
        BUY_INVALIDATED: "失效", SELL_INVALIDATED: "失效",
    }
    state_text = state_map.get(event, "")

    obs = model.get('observation_price')
    exec_p = model.get('execution_price')
    acceptable = model.get('acceptable_price')
    invalid = model.get('invalid_price')

    if event in {BUY_TRIGGERED, SELL_TRIGGERED}:
        core = f"{emoji} {name} ｜ T0 {direction}{state_text}"
        if acceptable:
            core += f"（最高 {price(acceptable)}）"
        if exec_p:
            core += f" ｜ 执行 {price(exec_p)}"
        if invalid:
            core += f" ｜ 止损 {price(invalid)}"
        return core

    if event in {BUY_INVALIDATED, SELL_INVALIDATED}:
        core = f"{emoji} {name} ｜ T0 {direction}{state_text}"
        if invalid:
            if is_buy:
                core += f" ｜ 跌破 {price(invalid)}"
            else:
                core += f" ｜ 突破 {price(invalid)}"
        return core

    if event in {BUY_EXPIRED, SELL_EXPIRED}:
        core = f"{emoji} {name} ｜ T0 {direction}{state_text}"
        if acceptable:
            core += f" ｜ 现价 {current:.2f} 已超 {price(acceptable)}"
        return core

    if event in {BUY_BLOCKED, SELL_BLOCKED}:
        blocked_reasons = model.get('blocked_reasons') or ['强阻断']
        core = f"{emoji} {name} ｜ T0 {direction}{state_text}"
        core += f"（{'、'.join(str(r) for r in blocked_reasons)}）"
        return core

    # Note: BUY_WATCHED/SELL_WATCHED are no longer emitted by side_event().
    # Kept for future use.
    return f"{emoji} {name} ｜ T0 {direction}{state_text}"


def _build_context_line(event: str, plan: dict[str, Any]) -> str:
    buy = plan.get('buy') or {}
    sell = plan.get('sell') or {}
    level = get_market_level()
    note = get_market_note()

    if event in {BUY_TRIGGERED, BUY_INVALIDATED, SELL_TRIGGERED, SELL_INVALIDATED}:
        intraday_tape = buy.get('t0_tape', {}) if isinstance(buy, dict) else {}
        tape_key = 'buy_tape' if event.startswith('BUY') else 'sell_tape'
        tape = intraday_tape.get(tape_key, {}) if isinstance(intraday_tape, dict) else {}
        tape_time = tape.get('time', '')
        tape_reason = tape.get('reason', '')
        tape_text = f"{tape_time} {tape_reason}".strip() if tape_time and tape_reason else ""
    elif event == BUY_EXPIRED:
        tape_time = ''
        tape_text = plan.get('expired_reason', '') or ''
    elif event == SELL_EXPIRED:
        tape_time = ''
        tape_text = plan.get('expired_reason', '') or ''
    else:
        tape_time = ''
        tape_text = ''

    env_parts = []
    if level:
        env_parts.append(f"🌍 大盘 {level}")
    if note:
        env_parts.append(f"（{note}）")
    if tape_text:
        env_parts.append(f"| 📈 盘口 {tape_text}")

    return "".join(env_parts) if env_parts else ""


def build_alert_message(event: str, plan: dict[str, Any], cost: float | None = None, position: int | None = None, previous_state: dict[str, Any] | None = None) -> str:
    line1 = _build_trigger_line(event, plan)
    line2 = _build_context_line(event, plan)

    lines = [line1]
    if line2:
        lines.append(line2)

    # Add stop-loss reminder for triggered alerts
    if event in {BUY_TRIGGERED, SELL_TRIGGERED}:
        lines.append(_stop_loss_reminder(event, plan))

    return "\n".join(lines)


def _stop_loss_reminder(event: str, plan: dict[str, Any]) -> str:
    is_buy = event.startswith("BUY")
    invalid = plan.get('buy', {}).get('invalid_price') if is_buy else plan.get('sell', {}).get('invalid_price')
    if invalid:
        action = "跌破不接" if is_buy else "突破不追"
        return f"止损 {price(invalid)} {action}"
    return "严格按失效价执行，破位不接"


def _trigger_reason_lines(model: dict[str, Any]) -> list[str]:
    matched = model.get("matched_conditions") or []
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
    plan = build_plan(target)
    target_key = str(plan.get("symbol") or target)
    with state_lock(state_path):
        state = load_state(state_path)
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
        save_state(state, state_path)
    if allowed_events:
        try:
            persist_event_signals(allowed_events, plan)
        except Exception:
            pass
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
