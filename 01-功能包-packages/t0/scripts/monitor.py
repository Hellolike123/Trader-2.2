from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

try:
    import trader_shared
except ImportError:
    _d = Path(__file__).resolve().parent
    for _ in range(8):
        if (_d / "trader_shared").is_dir():
            if str(_d) not in sys.path:
                sys.path.insert(0, str(_d))
            import trader_shared
            break
        _d = _d.parent
    else:
        raise

from trader_shared.data_manager import DataManager
from trader_shared.safe_cast import safe_dict
from price_point_engine import price
from trader_shared.signal_store import append_signal
from t0_run import build_plan, build_t0_event_signal
from t0_config import FREQUENCY_STOP_LIMIT

# Phase 2 接入：T0 实时缠论（opt-in，默认关；仅 T0_REALTIME_CHAN=1 时启用）
try:
    from trader_shared.realtime_chan import get_realtime_chan, _chan_signature
except ImportError:
    get_realtime_chan = None  # type: ignore
    _chan_signature = None  # type: ignore
try:
    from trader_shared.trading_calendar import is_trading_time, next_trading_open
except ImportError:
    from trader_shared.light_data import is_trading_time
    next_trading_open = None

try:
    from trader_shared import get_market_level, add_warning, get_market_note, log_safe, fill_by_target
    track_t0_signal = log_safe
except ImportError:
    warnings.warn(
        "[t0] shared module not available — market status, signal tracking, and state sync are disabled. "
        "T0 monitor will still work but without shared state integration.",
        stacklevel=2,
    )

    def get_market_level() -> str: return ""
    def get_market_note() -> str: return ""
    def add_warning(msg: str, related_stock: str = "") -> None: pass
    def track_t0_signal(skill, target, symbol, signal_type, price, env_level, env_note): pass
    def fill_by_target(target, pnl_pct, days_held, outcome): pass


CACHE_DIR = Path(os.environ.get("T0_CACHE_DIR", Path.home() / ".t0-trader"))
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
    # [P1 Fix] 事件冷却 key 不再包含 trigger_price（动态价格导致冷却可绕过）
    # 改用 side + source 作为稳定 key，同一侧的同一事件类型共享冷却
    zone = model.get("zone") if isinstance(model.get("zone"), dict) else {}
    source = zone.get("source") or ""
    return f"{event}:{model.get('trigger_time', '')}:{source}"


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
    model = safe_dict(plan, "buy") if is_buy else safe_dict(plan, "sell")
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
    matched = model.get("matched") or []
    if not matched:
        return []
    core = [m for m in matched if any(kw in m for kw in ("MACD", "RSI", "VWAP"))]
    core_str = " + ".join(core[:2]) if core else matched[0]
    return [f"🔥 {core_str} | {len(matched)}个信号"]


def _monitor_position_lines(plan: dict[str, Any], position: int | None) -> list[str]:
    # Use the already-computed max_move from price_point_engine (no duplicate logic)
    max_move = str(plan.get("max_move") or "")
    if max_move == "不动":
        pos_range = "不动"
    else:
        pos_range = max_move.replace("底仓的 ", "") if "底仓的" in max_move else max_move
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


def _check_volume_vacuum_t0(plan: dict[str, Any]) -> str | None:
    """检查量能真空区风险（T0 盘中监控用）。

    使用 30m K 线计算成交量分布，如果现价跌破 POC 且下方量能
    不足 POC 峰值的 10%，触发强烈预警。
    """
    try:
        from trader_shared.volume_profile import check_volume_vacuum
        data = plan.get("data") or {}
        # 优先用 30m 线（日内视角好），其次用 15m
        bars = data.get("kline_30m") or data.get("kline_15m") or data.get("kline_5m")
        if not bars:
            return None
        current = float(plan.get("current_price") or 0)
        if current <= 0:
            return None
        result = check_volume_vacuum(bars, current)
        if result.get("vacuum_warning"):
            return result["warning_text"]
    except Exception:
        pass
    return None


def _check_5m_chan_t0(plan: dict[str, Any]) -> tuple:
    """T0 盘中 5m 缠论预警源（始终开启，独立于 T0_REALTIME_CHAN 与事件系统）。

    复用本模块已支持的 ``ChanlunPlugin``（已支持 minute_bars 入参）：传入 5m K 线，
    插件内部 5m 优先、日线兜底。返回 ``(signature, flat_result)``：
    - ``signature`` 为可跨 tick 比对的指纹（来自 realtime_chan._chan_signature）；
      5m 数据不足（<20 根）或模块不可用时返回 ``(None, None)``，不产生告警。
    - ``flat_result`` 为解包 fusion 包装层后的扁平缠论结果（含 strokes/buy_points，
      供 _chan_realtime_alert 复用），无则 None。
    注意：ChanlunPlugin.analyze 返回 ``{"chanlun": result}`` 包装层，这里解包取扁平 dict，
    才能与 _chan_signature / _chan_realtime_alert 的键约定对齐。
    """
    try:
        from trader_shared.plugins.chan_plugin import ChanlunPlugin
        from trader_shared.realtime_chan import _chan_signature as _chan_sig
    except Exception:
        return (None, None)
    # 注：_chan_realtime_alert / _norm_sig 均在本模块定义，4.3 直接调用即可，
    # 勿从 realtime_chan import。
    data = plan.get("data") or {}
    k5 = data.get("kline_5m") or []
    if not isinstance(k5, list) or len(k5) < 20:
        return (None, None)  # 早盘 5m 不足 20 根，噪声大，暂不告警
    daily = data.get("daily_bars") or []
    quote = data.get("quote") or plan.get("quote") or {}
    current = float(plan.get("current_price") or 0)
    if current <= 0:
        return (None, None)
    change_pct = plan.get("current_change_pct")
    try:
        res = ChanlunPlugin().analyze(current, daily, change_pct, quote, minute_bars=k5)
    except Exception:
        return (None, None)
    if not isinstance(res, dict):
        return (None, None)
    flat = res.get("chanlun") or res  # 解包 fusion 包装层
    sig = _chan_sig(flat)
    return (sig, flat)


def _chan_realtime_alert(result: dict | None, prev_sig) -> str | None:
    """对比前后缠论指纹，生成人话预警行；无变化返回 None。

    仅在 ``T0_REALTIME_CHAN=1`` 分支内被调用（run_once 中已比对 chan_sig != prev_sig
    才触发），此处专注于把变化翻译成可读文本：结构/趋势变化、日内新成笔方向、出现/消失买卖点。
    指纹可能仅在末笔端点（价格抖动）层面变化，故末尾有兜底，保证检测到变化即产出文本。
    """
    if not isinstance(result, dict):
        return None

    strokes = result.get("strokes") or []
    last_dir = strokes[-1].get("direction") if strokes else None
    last_end = strokes[-1].get("end_price") if strokes else None
    structure_type = result.get("structure_type")
    trend_label = result.get("trend_label")
    buy_points = [bp.get("type") for bp in (result.get("buy_points") or [])]
    sell_points = [sp.get("type") for sp in (result.get("sell_points") or [])]

    if isinstance(prev_sig, tuple):
        (prev_struct, prev_trend, prev_dir, prev_end, prev_buy, prev_sell) = (
            list(prev_sig) + [None] * 6
        )[:6]
    else:
        prev_struct = prev_trend = prev_dir = prev_end = prev_buy = prev_sell = None

    parts: list[str] = []
    # 结构/趋势变化
    if prev_struct != structure_type or prev_trend != trend_label:
        parts.append(f"结构由 {prev_trend or '未知'} 转为 {trend_label or '未知'}（{structure_type or '未知'}）")
    # 末笔方向变化
    if last_dir != prev_dir:
        if last_dir == "up":
            parts.append("日内新成上升笔")
        elif last_dir == "down":
            parts.append("日内新成下降笔")
    # 买卖点出现/消失
    if buy_points:
        parts.append("出现买点：" + "、".join(buy_points))
    elif prev_buy:
        parts.append("买点消失")
    if sell_points:
        parts.append("出现卖点：" + "、".join(sell_points))
    elif prev_sell:
        parts.append("卖点消失")

    # 兜底：仅末笔端点（价格抖动）变化时也给出可读提示，保证有变化即发声
    if not parts and prev_end is not None and last_end is not None and round(float(prev_end), 2) != round(float(last_end), 2):
        parts.append(f"末笔价格更新至 {round(float(last_end), 2)}")

    if not parts:
        return None
    return "缠论：" + "；".join(parts)


def _norm_sig(sig):
    """递归将签名中的 list 归一为 tuple，抵消 JSON 往返导致的 tuple→list 差异。"""
    if isinstance(sig, (list, tuple)):
        return tuple(_norm_sig(x) for x in sig)
    return sig


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
    
    # ── [2.5] 量能真空区预警检查 ──
    vacuum_alert = _check_volume_vacuum_t0(plan)

    # ── 5m 缠论盘中预警源（始终开启，独立于 T0_REALTIME_CHAN 与事件系统）──
    min5_sig, min5_result = _check_5m_chan_t0(plan)

    # ── Phase 2：实时缠论 diff（opt-in，默认关，绝不改变批量路径） ──
    # 所有改动均在 T0_REALTIME_CHAN=1 分支内；未设 env 时 chan_sig/chan_alert_line
    # 保持默认空值，控制流与改造前逐字节等价。
    chan_sig: Any = None
    chan_result: dict | None = None
    chan_alert_line = ""
    chan5_alert_line = ""
    if os.environ.get("T0_REALTIME_CHAN") == "1" and get_realtime_chan is not None:
        try:
            rc = get_realtime_chan(target_key, plan)
            chan_sig = rc.get("signature")
            chan_result = rc.get("result")
        except Exception:
            chan_sig = None  # 容错：绝不阻断主流程
    
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
        if isinstance(previous, dict) and previous.get("trade_day") != trade_day_key(now):
            previous = None
        events = detect_state_change(previous, plan)
        target_state = previous if isinstance(previous, dict) else {}
        allowed_events = [event for event in events if not is_in_cooldown(target_state, event_id(event, plan))]
        new_snapshot = snapshot(plan)
        new_snapshot["last_events"] = dict(target_state.get("last_events") or {})
        new_snapshot["history"] = list(target_state.get("history") or [])
        # Phase 2：写入缠论指纹（默认值 None 不影响现有逻辑）
        new_snapshot["chan_signature"] = chan_sig
        # 5m 缠论指纹（始终记录；默认 None 不影响逻辑）
        new_snapshot["chan5_signature"] = min5_sig
        if chan_sig is not None and chan_result is not None:
            prev_sig = (previous or {}).get("chan_signature")
            # 状态文件经 JSON 往返后 tuple→list（含嵌套），需归一后再比对，
            # 否则下一 tick 总会因 tuple≠list 误判为变化而重复告警。
            if _norm_sig(chan_sig) != _norm_sig(prev_sig):
                try:
                    chan_alert_line = _chan_realtime_alert(chan_result, prev_sig)
                except Exception:
                    chan_alert_line = ""
        # 5m 缠论：跨 tick 指纹变化才发声（独立于日线 realtime_chan 与事件系统）
        if min5_sig is not None and min5_result is not None:
            prev5 = (previous or {}).get("chan5_signature")
            # prev5 为 None 表示首轮（无基线）→ 只建基线、不发声，避免开盘第一 tick 误报
            if prev5 is not None and _norm_sig(min5_sig) != _norm_sig(prev5):
                try:
                    a = _chan_realtime_alert(min5_result, prev5)
                    if a:
                        chan5_alert_line = "5m" + a  # 前缀 → "5m缠论：..."
                except Exception:
                    chan5_alert_line = ""
        mark_events(new_snapshot, plan, allowed_events)
        targets[target_key] = new_snapshot
        state["targets"] = targets
        
        # Count STOP losses and check fuse trigger
        if allowed_events and not (isinstance(day_fuse, dict) and day_fuse.get("fused", False)):
            # [P1 Fix] 熔断后不再统计 stop_count，避免计数超过阈值
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
            if stop_count >= FREQUENCY_STOP_LIMIT:
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
        alert = _fuse_alert(target_key, day_fuse.get("count", 0) if isinstance(day_fuse, dict) else 0, name)
        return alert
    
    # ── 量能真空预警（独立于事件系统，每次检查都触发） ──
    vacuum_line = ""
    if vacuum_alert:
        vacuum_line = vacuum_alert + "\n"

    # ── 实时缠论预警（opt-in，独立于事件系统） ──
    chan_line = ""
    if chan_alert_line:
        chan_line = chan_alert_line + "\n"

    # ── 5m 缠论预警（始终开启，独立于事件系统） ──
    chan5_line = ""
    if chan5_alert_line:
        chan5_line = chan5_alert_line + "\n"

    if allowed_events:
        try:
            persist_event_signals(allowed_events, plan)
        except Exception as e:
            warnings.warn(f"[t0-monitor] 信号持久化失败: {e}")
    if not allowed_events:
        prefix = (vacuum_line + chan_line + chan5_line).strip()
        if prefix:
            return prefix
        return "无新提醒" if verbose else ""
    events_text = "\n\n".join(build_alert_message(event, plan, cost=cost, position=position, previous_state=target_state) for event in allowed_events)
    prefix = vacuum_line + chan_line + chan5_line
    if prefix:
        return prefix + events_text
    return events_text


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
            # 收盘后长休眠：计算到下一个交易时段的 sleep 时长
            try:
                from trader_shared.trading_calendar import is_trading_time, next_trading_open
                if not is_trading_time():
                    next_open = next_trading_open()
                    sleep_seconds = max(60, (next_open - datetime.now()).total_seconds())
                    if verbose:
                        print(f"非交易时段，休眠到 {next_open.strftime('%Y-%m-%d %H:%M')}")
                    time.sleep(min(sleep_seconds, 3600))  # 最多睡 1 小时后重新检查
                    continue
            except ImportError:
                pass

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
