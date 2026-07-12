from __future__ import annotations
import os
import json
from datetime import datetime
from typing import Any
from trader_shared.signal_contract import assert_valid_signal
from trader_shared.signal_utils import normalize_signal_id
from trader_shared.light_data import to_float

DATA_STATUS_MAP = {
    "complete": "full",
    "partial": "partial",
    "degraded": "degraded",
    "failed": "degraded",
}

_FUSION_ACTION_MAP: dict[str, tuple[str, str, str]] = {
    "半仓试 (多方主导)": ("track", "bullish", "track"),
    "半仓试 (多方主导但有分歧)": ("track", "bullish", "track"),
    "增持": ("track", "bullish", "track"),
    "等转强观察": ("wait_for_confirmation", "bullish_lean", "observe"),
    "持股观望": ("observe", "neutral", "observe"),
    "减仓": ("defensive", "bearish", "wait"),
    "空仓/止损": ("defensive", "bearish", "wait"),
    "空仓 (大盘很差, 一票否决)": ("risk_stop", "bearish", "stop"),
    "观望 (信号冲突)": ("observe", "neutral", "observe"),
    "等转强": ("wait_for_confirmation", "bullish_lean", "observe"),
    "回调观望": ("wait_for_confirmation", "neutral", "observe"),
    "高位观望": ("no_entry", "neutral", "observe"),
    "减1/3 (高位松动)": ("defensive", "bearish_lean", "wait"),
    "高位松动": ("defensive", "bearish_lean", "wait"),
}

# ── 进程内 signals.jsonl 缓存（批量刷新时避免每票重读文件）──
_signals_cache_data: list[str] | None = None
_signals_cache_mtime: float = 0.0
_signals_cache_path: str = ""

def clear_signals_cache() -> None:
    global _signals_cache_data, _signals_cache_mtime, _signals_cache_path
    _signals_cache_data = None
    _signals_cache_mtime = 0.0
    _signals_cache_path = ""

def _get_major_stage(r: dict[str, Any]) -> str:
    major_stage = str(r.get("major_stage") or "")
    if not major_stage:
        old_stage = str(r.get("stage") or "")
        stage_map = {
            "修复": "蓄势",
            "走强": "主升",
            "震荡": "蓄势",
            "转弱": "衰退",
        }
        major_stage = stage_map.get(old_stage, old_stage)
    return major_stage

def _map_fusion_to_signal(fusion_action: str) -> tuple[str, str, str] | None:
    if not fusion_action:
        return None
    return _FUSION_ACTION_MAP.get(fusion_action.strip())

def today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def one_sentence(r: dict[str, Any], low_zone: str) -> str:
    major_stage = _get_major_stage(r)
    momentum = str(r.get("short_term_momentum") or "")
    confirm = float(r.get("confirm") or 0)
    if major_stage == "衰退":
        return "衰退期，不参与。等站上250日线再说。"
    if major_stage == "蓄势" and momentum == "转弱":
        return "蓄势期转弱，不碰。"
    if major_stage == "蓄势" and momentum == "修复":
        return f"蓄势期，不动手。等放量站稳 {confirm:.2f} 再说。"
    if major_stage == "蓄势" and momentum in ("走强", "震荡"):
        return f"蓄势期，等突破 {confirm:.2f} 确认后再动手。"
    if major_stage == "主升" and momentum == "走强":
        return "主升期走强，持有。"
    if major_stage == "主升" and momentum == "修复":
        return f"主升期修复，回踩可加仓。站稳 {confirm:.2f} 确认。"
    if major_stage == "主升" and momentum == "震荡":
        return "主升期震荡，持有底仓，回踩确认。"
    if major_stage == "主升" and momentum == "转弱":
        return "主升期转弱，风险信号，考虑减仓。"
    if major_stage == "派发":
        return "派发期，逢高减仓。"
    stage = r.get("stage") or ""
    scene = r.get("scene") or ""
    theory_status = str(r.get("theory_status") or r.get("state_label") or "")
    current = float(r.get("current", 0))
    support = float(r.get("support", 0))
    if stage == "转弱" or theory_status == "暂不碰":
        return f"现在先不参与；等重新站回 {support:.2f}元 上方并稳定后再看。"
    if theory_status == "体系转强确认":
        return f"已形成体系确认，放量站稳回踩不破可评估加仓。"
    if scene == "冲高减仓":
        return f"上方空间受限，有底仓的逢高减仓，空仓需等回调。"
    if current >= confirm:
        return f"已越过确认位，放量站稳回踩不破可评估加仓。"
    return f"现在还不是进攻点；先守纪律等确认，跌到 {low_zone} 止跌才轻试，站不上 {confirm:.2f}元 不加仓。"

def read_signals_for_report(target: str, daily_bars: list[dict[str, Any]]) -> tuple[float, dict | None]:
    global _signals_cache_data, _signals_cache_mtime, _signals_cache_path
    signals_path = os.path.expanduser("~/.trader/signals.jsonl")

    try:
        current_mtime = os.path.getmtime(signals_path)
    except OSError:
        current_mtime = 0.0

    if (_signals_cache_data is not None and
            _signals_cache_path == signals_path and
            _signals_cache_mtime == current_mtime):
        all_lines = _signals_cache_data
    else:
        if not os.path.exists(signals_path):
            _signals_cache_data = []
            _signals_cache_mtime = current_mtime
            _signals_cache_path = signals_path
            return 0.0, None
        with open(signals_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()[-100:]
        _signals_cache_data = all_lines
        _signals_cache_mtime = current_mtime
        _signals_cache_path = signals_path

    normalized_target = target.replace(".SH", "").replace(".SZ", "").strip()

    sorted_bars = sorted(daily_bars, key=lambda x: str(x.get("date", ""))[:10])
    dates = [str(b.get("date", ""))[:10] for b in sorted_bars if b.get("date")]
    close_map: dict[str, float] = {}
    for b in sorted_bars:
        d = str(b.get("date", ""))[:10]
        if d and b.get("close") is not None:
            close_map[d] = float(b["close"])

    if not close_map:
        return 0.0, None

    date_to_idx: dict[str, int] = {d: i for i, d in enumerate(dates)}

    buy_signals: list[float] = []
    sell_signals: list[float] = []
    cost_price: float = 0.0

    try:
        for line in reversed(all_lines):
            line = line.strip()
            if not line:
                continue
            try:
                sig = json.loads(line)
            except json.JSONDecodeError:
                continue

            sig_symbol = str(sig.get("symbol", "")).replace(".SH", "").replace(".SZ", "").strip()
            sig_name = str(sig.get("name", "")).strip()
            if normalized_target not in (sig_symbol, sig_name):
                continue

            sig_type = str(sig.get("signal_type", ""))
            trade_date = str(sig.get("trade_date") or "")[:10]
            analysis_time = str(sig.get("analysis_time") or "")
            time_part = analysis_time[11:].strip() if len(analysis_time) >= 16 else ""

            if cost_price == 0.0:
                if sig_type in ("low_buy_triggered", "track"):
                    trigger = sig.get("trigger", {})
                    price = trigger.get("price", 0)
                    if price > 0:
                        cost_price = float(price)

            if sig_type not in ("review_result", "low_buy_triggered", "high_sell_triggered"):
                continue
            if sig_type == "review_result" and not (time_part >= "15:00"):
                continue
            if trade_date not in date_to_idx:
                continue

            idx = date_to_idx[trade_date]
            if idx + 5 >= len(dates):
                continue

            entry_price = close_map.get(trade_date, 0)
            if entry_price <= 0:
                continue
            exit_price = close_map.get(dates[idx + 5], 0)
            if exit_price <= 0:
                continue
            return_pct = round(((exit_price - entry_price) / entry_price) * 100, 2)

            direction = str(sig.get("direction", ""))
            if sig_type == "low_buy_triggered":
                buy_signals.append(return_pct)
            elif sig_type == "high_sell_triggered":
                sell_signals.append(return_pct)
            elif direction in ("bullish", "bullish_lean"):
                buy_signals.append(return_pct)
            elif direction in ("bearish", "bearish_lean"):
                sell_signals.append(return_pct)
    except Exception:
        return cost_price, None

    win_rate_data: dict | None = None
    total = len(buy_signals) + len(sell_signals)
    if total > 0:
        def _stats(signals: list[float]) -> dict | None:
            if not signals:
                return None
            wins = sum(1 for s in signals if s > 0)
            n = len(signals)
            win_rate = round((wins / n) * 100)
            avg = round(sum(signals) / n, 2)
            return {"count": n, "wins": wins, "win_rate": win_rate, "avg_pnl": avg}

        win_rate_data = {
            "total": total,
            "buy": _stats(buy_signals),
            "sell": _stats(sell_signals),
        }

    return cost_price, win_rate_data

def load_historical_win_rate(target: str) -> dict | None:
    # For compatibility, returns the win_rate_data from signals log
    # run_analysis.py previously read signals to load win_rate
    # We can implement this simply by calling read_signals_for_report with an empty daily_bars list, 
    # but win rate calculations require close_map, so it needs real bars. 
    # We let read_signals_for_report handle the actual parsing.
    return None

def get_pool_count() -> int:
    from pathlib import Path
    path = Path.home() / ".trader" / "pool.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items", [])
        return sum(1 for i in items if i.get("status") not in {"淘汰", "已退出"})
    except Exception:
        return 0

def signal_max_total_pct(signal_type: str) -> int:
    if signal_type in ("defensive", "risk_stop"):
        return 0
    if signal_type in ("trigger_expired", "blocked"):
        return 0
    if signal_type == "no_entry":
        return 0
    if signal_type == "track":
        return 30
    if signal_type == "reduce":
        return 20
    return 30

def signal_risk_flags(r: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    pre_flags = r.get("risk_flags", []) or []
    flags.extend(pre_flags)
    if _get_major_stage(r) == "衰退":
        flags.append("structure_weak")
    if str(r.get("scene") or "") == "空间不足":
        flags.append("limited_upside_space")
    if "不足" in str(r.get("volume_text") or ""):
        flags.append("volume_confirmation_missing")
    return flags

def signal_state(r: dict[str, Any]) -> tuple[str, str, str, str]:
    major_stage = _get_major_stage(r)
    scene = str(r.get("scene") or "")
    theory_status = str(r.get("theory_status") or r.get("state_label") or scene)
    current = float(r.get("current") or 0)
    confirm = float(r.get("confirm") or current)

    if major_stage == "衰退" or theory_status == "暂不碰":
        return "defensive", "bearish_lean", "wait", "low"

    if current >= confirm or scene in {"突破确认", "突破观察"} or theory_status in {"突破确认", "突破观察"}:
        return "track", "bullish", "track", "medium"

    if theory_status == "体系转强确认":
        return "track", "bullish", "track", "medium"
    if theory_status == "未确认转强":
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if theory_status == "承接存在":
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if theory_status == "转强不足":
        return "wait_for_confirmation", "neutral", "observe", "low"

    if scene == "冲高减仓" or theory_status == "冲高减仓":
        return "reduce", "bearish_lean", "reduce", "medium"

    if theory_status in {"风险回避", "数据不足"}:
        return "defensive", "bearish_lean", "wait", "low"

    if scene in {"低吸观察", "防守观察", "防守观察，趋势下行谨慎", "空间不足", "等转强"}:
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    if theory_status in {"防守观察", "修复观察", "低吸观察", "等转强", "观望", "中性整理",
                         "低位修复", "均线修复", "防守整理", "临近确认", "空间偏紧"}:
        return "wait_for_confirmation", "bullish_lean", "observe", "medium"
    return "observe", "neutral", "observe", "low"

def state_text(stage: str, theory_status: str) -> str:
    if theory_status == "暂不碰":
        return "暂不碰"
    if theory_status == "体系转强确认":
        return "体系转强确认"
    if theory_status == "未确认转强":
        return "未确认转强"
    if theory_status == "承接存在":
        return "承接存在"
    if theory_status == "转强不足":
        return "转强不足"
    if theory_status == "修复观察":
        return "修复观察"
    if theory_status:
        return theory_status
    return "震荡观察"

def build_signal(r: dict[str, Any]) -> dict[str, Any]:
    signal_type, direction, action, confidence = signal_state(r)

    fusion_override = False
    fusion = r.get("fusion")
    if isinstance(fusion, dict):
        fc = fusion.get("confidence", 0)
        sd = fusion.get("signals_detail", {})
        has_signal = isinstance(sd, dict) and any(
            isinstance(v, dict) and v.get("direction") != 0
            for v in sd.values()
        )
        if fc > 0.4 and has_signal:
            mapped = _map_fusion_to_signal(fusion.get("action", ""))
            if mapped is not None:
                ft, fd, fa = mapped
                if fd != direction:
                    signal_type, direction, action = ft, fd, fa
                    fusion_override = True

    raw_time = str(r.get("analysis_time") or "") or today_text()
    trade_date = raw_time.split(" ")[0]
    if signal_type == "reduce":
        trigger_price = float(r.get("resistance") or r.get("confirm") or r.get("current"))
        invalid_price = float(r.get("stop") or r.get("support") or r.get("current"))
    else:
        trigger_price = float(r.get("confirm") or r.get("resistance") or r.get("current"))
        invalid_price = float(r.get("stop") or r.get("support") or r.get("current"))
    signal = {
        "contract": "trader_signal_v1",
        "source_skill": "trader",
        "symbol": str(r.get("symbol") or ""),
        "name": str(r.get("name") or ""),
        "trade_date": trade_date,
        "analysis_time": raw_time,
        "signal_type": signal_type,
        "direction": direction,
        "action": action,
        "confidence": confidence,
        "data_status": DATA_STATUS_MAP.get(str(r.get("data_status")), "degraded"),
        "trigger": {
            "type": "price_confirm",
            "price": round(trigger_price, 2),
            "text": f"{trigger_price:.2f}元 放量站稳并回踩不破后再评估",
        },
        "invalidation": {
            "type": "price_break",
            "price": round(invalid_price, 2),
            "text": f"跌破 {invalid_price:.2f}元 后停止低吸",
        },
        "position": {
            "max_total_pct": signal_max_total_pct(signal_type),
            "max_single_move_pct": min(10, signal_max_total_pct(signal_type)),
        },
        "risk_flags": signal_risk_flags(r),
        "summary": one_sentence(r, str(r.get("low_zone") or f"{float(r.get('support') or 0):.2f}元")),
    }
    if fusion_override:
        signal["fusion_override"] = True
    assert_valid_signal(signal)
    return signal
