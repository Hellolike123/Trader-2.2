"""选股池信号校验 / watch 辅助。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pool_cmds import scoring as _scoring
from pool_cmds.scoring import *  # noqa: F403

def rank_status(item: dict[str, Any]) -> str:
    if item.get("_stop_broken"):
        return "已破止损"
    if item.get("status") == "执行":
        return "等转强" if item.get("momentum_state") != "通过" else "低吸观察"
    if item.get("status") == "观察":
        return "防守观察"
    return "暂不碰"


def atr_inline(item: dict[str, Any]) -> str:
    atr14 = to_float(item.get("atr14")) or 0.0
    atr_ratio = to_float(item.get("atr_ratio")) or 0.0
    if atr14 <= 0 or atr_ratio <= 0:
        return ""
    level = str(item.get("atr_level") or "")
    pct_str = f"{atr_ratio*100:.1f}%" if atr_ratio else "数据不足"
    return f"ATR {atr14:.2f}元（{pct_str}） {level}" if level else f"ATR {atr14:.2f}元（{pct_str}）"


def low_watch_text(item: dict[str, Any]) -> str:
    support = to_float(item.get("support"))
    current = to_float(item.get("current"))
    if support is None or current is None:
        return "无"
    low = min(support, current)
    high = max(support, current)
    return f"{low:.2f}-{high:.2f}元"


def t0_tendency(item: dict[str, Any]) -> str:
    if item.get("status") == "淘汰":
        return "不做"
    if item.get("status") == "执行":
        return "等待低吸触发"
    if item.get("momentum_state") == "通过":
        return "等待高抛触发"
    return "不做"


STAR_MAP = {
    "低吸观察": "⭐⭐⭐⭐⭐",
    "等转强": "⭐⭐⭐⭐",
    "防守观察": "⭐⭐⭐",
    "冲高减仓": "⭐⭐",
    "暂不碰": "⭐",
    "已破止损": "🔴",
}


def _price_freshness_warning(item: dict[str, Any]) -> str | None:
    """检测价格是否过期（超过 1 小时），返回警告文本或 None。"""
    fetched_at = item.get("price_fetched_at")
    if not fetched_at:
        return None
    try:
        fetched_dt = datetime.fromisoformat(str(fetched_at))
        age_minutes = (datetime.now() - fetched_dt).total_seconds() / 60
        if age_minutes > 60:
            return f"⚠️ 价格过期（{age_minutes:.0f}分钟前）"
    except (ValueError, TypeError):
        pass
    return None


def _trigger_distance_warning(item: dict[str, Any]) -> str | None:
    """检测触发价与现价的偏离程度，返回警告文本或 None。"""
    current = to_float(item.get("current"))
    trigger = to_float(item.get("trigger"))
    if not current or not trigger or current <= 0 or trigger <= 0:
        return None
    pct = (trigger - current) / current * 100
    if abs(pct) > 15:
        return f"⚠️ 触发价偏离 {pct:+.0f}%，可能已过期"
    if abs(pct) > 5:
        return f"触发价偏离 {pct:+.0f}%，建议运行 pool refresh"
    return None


def _is_trigger_stale(item: dict[str, Any]) -> bool:
    """触发价偏离现价超过 5%，视为过期。"""
    current = to_float(item.get("current"))
    trigger = to_float(item.get("trigger"))
    if not current or not trigger or current <= 0 or trigger <= 0:
        return False
    return abs((trigger - current) / current) > 0.05


def _days_lapsed(item: dict[str, Any], today: date) -> int:
    """Calculate days since item was added to pool."""
    try:
        added_str = str(item.get("added_at", today_text()))
        return (today - date.fromisoformat(added_str)).days
    except Exception:
        return 0


def _verify_observe_track(sig_type: str, item: dict[str, Any], current: float, days: int, summary: dict) -> str:
    """Verify observe/low_buy_watch/track signals: expect price to rise from support."""
    support = to_float(item.get("support") or item.get("current") or 0)
    confirmed_up = current > support * 1.01 if support > 0 else False
    if days <= 2:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 第1天" if days == 1 else "⏳ 第2天"
    if confirmed_up:
        summary["已验证"] = summary.get("已验证", 0) + 1
        return "✅ 确认上涨中"
    summary["守支撑"] = summary.get("守支撑", 0) + 1
    return "⏳ 支撑位守住了"


def _verify_high_sell(sig_type: str, item: dict[str, Any], current: float, days: int, summary: dict) -> str:
    """Verify high_sell_watch/high_sell_triggered signals: expect price to fall from resistance."""
    expect_down = current < to_float(item.get("resistance") or current * 1.05 or current)
    if days <= 2:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 第1天" if days == 1 else "⏳ 第2天"
    if expect_down:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 继续等"
    summary["信号错了"] = summary.get("信号错了", 0) + 1
    return "⚠️ 信号存疑"


def _verify_reduce(sig_type: str, item: dict[str, Any], current: float, days: int, summary: dict) -> str:
    """Verify reduce signals: expect price near resistance for confirmation."""
    resistance = to_float(item.get("resistance") or 0)
    hit_resistance = current >= resistance * 0.98 if resistance > 0 else False
    close_under_resistance = current < resistance * 0.99 if resistance > 0 else False
    if hit_resistance:
        summary["已验证"] = summary.get("已验证", 0) + 1
        return "⚠️ 已触压"
    if close_under_resistance:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 远离压力，暂不操作"
    summary["未验证"] = summary.get("未验证", 0) + 1
    return "⏳ 等确认"


def _verify_defensive(sig_type: str, item: dict[str, Any], current: float, defense: float, summary: dict) -> str:
    """Verify defensive signals: expect price to hold above defense."""
    if current < defense:
        summary["信号错了"] = summary.get("信号错了", 0) + 1
        return "❌ 破防守"
    summary["已验证"] = summary.get("已验证", 0) + 1
    return "⏳ 守住了"


def _verify_review_result(sig_type: str, matched: dict, item: dict[str, Any], current: float, summary: dict) -> str:
    """Verify review_result signals: check if direction matches."""
    expected_up = str(matched.get("direction", "")) in ("bullish", "bullish_lean")
    support = to_float(item.get("support") or current * 0.995 or 0)
    if current > support:
        if expected_up:
            summary["已验证"] = summary.get("已验证", 0) + 1
            return "✅ 对方向"
        summary["信号错了"] = summary.get("信号错了", 0) + 1
        return "⚠️ 方向反了"
    summary["未验证"] = summary.get("未验证", 0) + 1
    return "⏳ 没到位"


# Signal type → handler mapping
_SIGNAL_HANDLERS: dict[str, Any] = {
    "observe": _verify_observe_track,
    "low_buy_watch": _verify_observe_track,
    "track": _verify_observe_track,
    "high_sell_watch": _verify_high_sell,
    "high_sell_triggered": _verify_high_sell,
    "reduce": _verify_reduce,
    "defensive": _verify_defensive,
    "review_result": _verify_review_result,
}


def _verify_by_signal_type(
    sig_type: str, matched: dict, item: dict[str, Any],
    current: float, defense: float, today: date, summary: dict,
) -> tuple[str, dict]:
    """Dispatch to per-type signal verifier. Returns (verify_status, updated_summary)."""
    handler = _SIGNAL_HANDLERS.get(sig_type)
    if handler is None:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 等结果", summary

    days = _days_lapsed(item, today)
    if sig_type in ("observe", "low_buy_watch", "track"):
        return handler(sig_type, item, current, days, summary), summary
    if sig_type in ("high_sell_watch", "high_sell_triggered"):
        return handler(sig_type, item, current, days, summary), summary
    if sig_type == "reduce":
        return handler(sig_type, item, current, days, summary), summary
    if sig_type == "defensive":
        return handler(sig_type, item, current, defense, summary), summary
    if sig_type == "review_result":
        return handler(sig_type, matched, item, current, summary), summary
    summary["未验证"] = summary.get("未验证", 0) + 1
    return "⏳ 等结果", summary


def _pool_signal_verifications(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    from trader_shared.signal_store import load_recent_signals

    today = date.today()
    summary = {"已验证": 0, "信号错了": 0, "未验证": 0, "暂无信号": 0}
    results: list[dict[str, Any]] = []

    for item in items:
        current = to_float(item.get("current")) or 0
        trigger = to_float(item.get("trigger")) or 0
        defense = to_float(item.get("defense")) or 0
        name = item.get("name", "?")
        symbol = item.get("symbol") or name
        status = str(item.get("status") or "")

        sig_text = "无"
        verify_status = "暂无信号"

        if trigger <= 0 or defense <= 0:
            sig_text = "无触发/防守位"
            verify_status = "暂无信号"
        else:
            try:
                signals = load_recent_signals(name, limit=10)
                if not signals:
                    signals = load_recent_signals(symbol, limit=10)
            except Exception:
                signals = []

            # FIX-T-BIAS-177: match signal to pool item's trigger/defense, not just latest
            matched = None
            if signals:
                for s in signals:
                    s_trigger = to_float(s.get("trigger", {}).get("price") or 0)
                    s_invalidation = to_float(s.get("invalidation", {}).get("price") or 0)
                    s_sig_type = str(s.get("signal_type", ""))
                    # Match by price proximity: signal trigger ~= pool trigger, signal invalidation ~= pool defense
                    trigger_ok = s_trigger > 0 and abs(s_trigger - trigger) / max(trigger, 0.01) < 0.05
                    invalidation_ok = s_invalidation > 0 and abs(s_invalidation - defense) / max(defense, 0.01) < 0.05
                    if trigger_ok and invalidation_ok:
                        matched = s
                        break
                    # Fallback: signal_type must match pool item's implied type
                    pool_type = _pool_item_signal_type(item)
                    if pool_type and s_sig_type == pool_type:
                        matched = s
                        break
                if matched is None:
                    # FIX: filter signals by stock name/symbol to avoid cross-stock contamination
                    for s in signals:
                        s_name = str(s.get("name", ""))
                        s_symbol = str(s.get("symbol", ""))
                        if s_name == name or s_symbol == symbol:
                            matched = s
                            break

            if matched:
                sig_type = str(matched.get("signal_type", ""))
                confidence = str(matched.get("confidence", ""))
                conf_map = {"low": "低", "medium": "中等", "high": "高"}
                conf_txt = conf_map.get(confidence, confidence)
                sig_text = f"{_signal_type_label(sig_type)} {conf_txt}"

                # 通用检查：破防守 / 已触发
                if current < defense:
                    verify_status = "❌ 破防守"
                    summary["信号错了"] = summary.get("信号错了", 0) + 1
                elif current >= trigger:
                    if current > trigger * 1.01:
                        verify_status = "✅ 已触发"
                        summary["已验证"] = summary.get("已验证", 0) + 1
                    else:
                        verify_status = "⏳ 触碰但未确认"
                        summary["未验证"] = summary.get("未验证", 0) + 1
                else:
                    # 按信号类型分支验证
                    verify_status, summary = _verify_by_signal_type(
                        sig_type, matched, item, current, defense, today, summary
                    )
            else:
                sig_text = "无记录"
                verify_status = "暂无信号"
                summary["暂无信号"] = summary.get("暂无信号", 0) + 1

        results.append({
            "name": name,
            "current": current,
            "sig_text": sig_text,
            "verify_status": verify_status,
        })

    return results, summary


def _apply_signal_adjustments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """根据信号回测结果调整排序：失败信号降级，已触发标记。"""
    from trader_shared.signal_store import load_recent_signals

    adjusted = []
    for item in items:
        item = dict(item)  # shallow copy
        name = item.get("name", "?")
        symbol = item.get("symbol") or name
        current = to_float(item.get("current")) or 0
        defense = to_float(item.get("defense")) or 0

        try:
            signals = load_recent_signals(name, limit=5)
            if not signals:
                signals = load_recent_signals(symbol, limit=5)
        except Exception:
            signals = []

        if signals:
            latest = signals[-1]
            # 检查信号结果字段
            result = str(latest.get("result") or latest.get("verify_status") or "")
            sig_status = str(latest.get("status") or "")

            # 信号失败（破防守 / 方向反了）→ 降级为观察
            if "❌" in result or "破防守" in result or "方向反" in result:
                if item.get("status") != "淘汰":
                    item["status"] = "观察"
                    item["_signal_downgrade"] = True

            # 信号已触发 → 标记
            if "✅" in result or "已触发" in result:
                item["_signal_triggered"] = True

            # 现价跌破防守位 → 降级
            if defense > 0 and current > 0 and current < defense:
                if item.get("status") != "淘汰":
                    item["status"] = "观察"
                    item["_defense_broken"] = True

        adjusted.append(item)
    return adjusted


def action_summary_for_scene(scene: str) -> str:
    """One-line action advice for pool items."""
    if scene in {"低吸观察", "防守观察", "防守观察，趋势下行谨慎"}:
        return "守纪律不追，等止跌确认"
    if scene in {"等转强"}:
        return "等放量确认"
    if scene in {"冲高减仓"}:
        return "冲高减仓，不追"
    if scene in {"突破确认", "突破观察"}:
        return "持有观察"
    if scene in {"空间不足"}:
        return "不追，等回落"
    if scene in {"暂不碰"}:
        return "不参与"
    if not scene:
        return "信息不足，暂不操作"
    return "等待，不主动追"


def _build_report_or_offline(name: str) -> dict[str, Any]:
    """Try live report, fallback to offline mock report."""
    try:
        from run_analysis import build_report
        return build_report(name)
    except Exception:
        base = 10 + (sum(ord(char) for char in name) % 700) / 100
        return {
            "name": name, "symbol": name, "current": round(base, 2),
            "change_pct": 0.0, "confirm": round(base * 1.035, 2),
            "stop": round(base * 0.945, 2), "support": round(base * 0.975, 2),
            "trigger": round(base * 1.035, 2), "stage": "震荡",
            "scene": "震荡", "bars": [], "daily_bars": [],
        }


def _pool_item_signal_type(item: dict[str, Any]) -> str | None:
    """Derive expected signal_type from pool item's trigger/defense/stop configuration."""
    trigger = to_float(item.get("trigger"))
    defense = to_float(item.get("defense"))
    support = to_float(item.get("support"))
    current = to_float(item.get("current"))
    resistance = to_float(item.get("resistance"))
    if current is None or defense is None or trigger is None:
        return None
    # If current is below defense: defensive/risk_stop scenario
    if current < defense:
        return "risk_stop"
    # If current is above trigger: track scenario
    if current >= trigger:
        return "track"
    # If current is near resistance: reduce scenario
    if resistance and current >= resistance * 0.95:
        return "reduce"
    # If current is near support: low_buy scenario
    if support and current <= support * 1.03:
        return "low_buy_watch"
    # Default: waiting for confirmation
    return "wait_for_confirmation"


def _signal_type_label(sig_type: str) -> str:
    labels = {
        "observe": "观察",
        "wait_for_confirmation": "等待确认",
        "track": "跟踪",
        "low_buy_watch": "低吸观察",
        "low_buy_triggered": "低吸触发",
        "high_sell_watch": "高抛观察",
        "high_sell_triggered": "高抛触发",
        "reduce": "减仓",
        "defensive": "防守",
        "risk_stop": "止损",
        "trigger_expired": "信号过期",
        "blocked": "受压",
        "review_result": "复盘",
    }
    return labels.get(sig_type, sig_type)

__all__ = list(_scoring.__all__) + [
    "STAR_MAP",
    "action_summary_for_scene",
    "atr_inline",
    "low_watch_text",
    "rank_status",
    "t0_tendency",
    "_SIGNAL_HANDLERS",
    "_apply_signal_adjustments",
    "_build_report_or_offline",
    "_days_lapsed",
    "_is_trigger_stale",
    "_pool_item_signal_type",
    "_pool_signal_verifications",
    "_price_freshness_warning",
    "_signal_type_label",
    "_trigger_distance_warning",
    "_verify_by_signal_type",
    "_verify_defensive",
    "_verify_high_sell",
    "_verify_observe_track",
    "_verify_reduce",
    "_verify_review_result",
]
