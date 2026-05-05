from __future__ import annotations

from typing import Any

from light_data import to_float


def pct_text(value: float | None) -> str:
    return "数据不足" if value is None else f"{value:+.2f}%"


def observation_valid(model: dict[str, Any]) -> bool:
    return bool(model.get("observation_valid", True))


def bar_num(bar: dict[str, Any], key: str) -> float | None:
    try:
        value = bar.get(key)
        return None if value is None else float(value)
    except Exception:
        return None


def segment_avg_volume(segment: list[dict[str, Any]]) -> float:
    volumes = [value for value in (bar_num(bar, "volume") for bar in segment) if value is not None]
    return sum(volumes) / len(volumes) if volumes else 0.0


def summarize_intraday_segment(name: str, segment: list[dict[str, Any]], prev_avg_volume: float | None = None) -> str:
    first_open = bar_num(segment[0], "open") if segment else None
    last_close = bar_num(segment[-1], "close") if segment else None
    if first_open is None or last_close is None:
        return f"{name}：数据不足，只作观察。"
    avg_volume = segment_avg_volume(segment)
    if prev_avg_volume is None or prev_avg_volume <= 0:
        volume_text = "量能正常"
    elif avg_volume > prev_avg_volume * 1.25:
        volume_text = "量能放大"
    elif avg_volume < prev_avg_volume * 0.75:
        volume_text = "量能收缩"
    else:
        volume_text = "量能平稳"
    if last_close > first_open * 1.002:
        move_text = "上行"
        read_text = "有承接，但仍要等触发"
    elif last_close < first_open * 0.998:
        move_text = "回落"
        read_text = "抛压仍在，不能急接"
    else:
        move_text = "横盘"
        read_text = "多空暂时均衡"
    return f"{name}：{first_open:.2f}→{last_close:.2f}，{move_text}，{volume_text}，{read_text}。"


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def review_lines(history: list[dict[str, Any]] | None) -> list[str]:
    if not history:
        return ["暂无关键事件。"]
    lines = []
    for item in history[-3:]:
        time_text = str(item.get("time") or "--:--")
        level = str(item.get("level") or "")
        text = str(item.get("text") or "提醒")
        event_price = item.get("price")
        price_text = f"，现价{float(event_price):.2f}元" if isinstance(event_price, (int, float)) else ""
        lines.append(f"{time_text} {level}｜{text}{price_text}。")
    return lines


def numeric_or_none(value: Any) -> float | None:
    try:
        return None if value is None else round(float(value), 2)
    except Exception:
        return None


def side_status(model: dict[str, Any]) -> str:
    status = str(model.get("status") or "")
    if status == "已触发" and model.get("execution_price") is not None:
        return "可执行"
    if status == "触发过期":
        return "已错过"
    if status == "被阻断":
        return "被阻断"
    if status == "数据不足":
        return "数据不足"
    return "未触发"


def observation_value(model: dict[str, Any], suffix: str) -> str:
    if not observation_valid(model):
        return "暂无有效观察价"
    return f"{price(model.get('observation_price'))}{suffix}"


def price(value: float | None) -> str:
    return "无" if value is None else f"{value:.2f}元"


def normalize_t0_data_status(value: str) -> str:
    if value == "delayed":
        return "stale"
    if value in {"fresh", "insufficient", "non_trading"}:
        return value
    return "partial"


def side_signal_type(side: str, side_state: str) -> str:
    if side_state == "可执行":
        return "low_buy_triggered" if side == "buy" else "high_sell_triggered"
    if side_state == "已错过":
        return "trigger_expired"
    if side_state == "被阻断":
        return "blocked"
    return "low_buy_watch" if side == "buy" else "high_sell_watch"


def side_action(side: str, side_state: str) -> str:
    if side_state == "可执行":
        return "low_buy" if side == "buy" else "high_sell"
    if side_state == "被阻断":
        return "stop_low_buy" if side == "buy" else "stop_high_sell"
    return "observe"


def side_trigger_price(model: dict[str, Any], side_state: str) -> Any:
    if side_state == "可执行":
        return model.get("execution_price")
    return model.get("observation_price")


def side_summary(side: str, side_state: str, trigger_price: Any) -> str:
    if side == "buy":
        if side_state == "可执行":
            return f"低吸已触发，参考 {price(trigger_price)}，超过可接受价不追。"
        return f"低吸未触发，只盯 {price(trigger_price)} 以下是否 5m 止跌。"
    if side_state == "可执行":
        return f"高抛已触发，参考 {price(trigger_price)}，低于可接受价不砸。"
    return f"高抛未触发，只盯 {price(trigger_price)} 附近是否冲高失败。"


def side_risk_flags(model: dict[str, Any]) -> list[str]:
    flags = [str(item) for item in (model.get("blocked_reasons") or []) if str(item)]
    if side_status(model) == "数据不足":
        flags.append("intraday_data_insufficient")
    if side_status(model) == "已错过":
        flags.append("trigger_expired")
    return flags


def t0_position(plan: dict[str, Any]) -> dict[str, int]:
    max_move = str(plan.get("max_move") or "")
    if "20%-30%" in max_move:
        return {"max_total_pct": 30, "max_single_move_pct": 30}
    if "10%-20%" in max_move:
        return {"max_total_pct": 20, "max_single_move_pct": 20}
    return {"max_total_pct": 0, "max_single_move_pct": 0}


def normalize_t0_data_status(value: str) -> str:
    if value == "delayed":
        return "stale"
    if value in {"fresh", "insufficient", "non_trading"}:
        return value
    return "partial"
