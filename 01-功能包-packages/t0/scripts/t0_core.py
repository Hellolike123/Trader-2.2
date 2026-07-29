from __future__ import annotations

from typing import Any

from trader_shared.light_data import to_float

try:
    from trader_shared.order_book import analyze as order_book_analyze
except ImportError:
    order_book_analyze = None

try:
    from trader_shared.big_order import analyze_big_orders
except ImportError:
    analyze_big_orders = None


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


# v2 价到关注区状态：只表示「价近关注区」，不构成下单许可
SIDE_ZONE_HIT = "到价关注"
_LEGACY_ZONE_HIT = "可执行"  # 旧枚举，读入时归一化为 SIDE_ZONE_HIT


def side_status(model: dict[str, Any]) -> str:
    status = str(model.get("status") or "")
    if status == "已触发" and model.get("execution_price") is not None:
        return SIDE_ZONE_HIT
    if status == "触发过期":
        return "已错过"
    if status == "被阻断":
        return "被阻断"
    if status == "数据不足":
        return "数据不足"
    return "未触发"


def normalize_side_display(state: str) -> str:
    """Normalize display status; map legacy 可执行 → 到价关注."""
    text = str(state or "")
    if text == _LEGACY_ZONE_HIT:
        return SIDE_ZONE_HIT
    return text


def is_zone_hit(state: str) -> bool:
    return normalize_side_display(state) == SIDE_ZONE_HIT


def side_display(model: dict[str, Any]) -> str:
    """Return display status string."""
    return side_status(model)


def observation_value(model: dict[str, Any], suffix: str) -> str:
    if not observation_valid(model):
        return "暂无有效观察价"
    return f"{price(model.get('observation_price'))}{suffix}"


def price(value: float | None) -> str:
    return "无" if value is None else f"{value:.2f}元"


def build_t0_signals(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        build_side_signal(plan, "buy"),
        build_side_signal(plan, "sell"),
    ]


def build_side_signal(plan: dict[str, Any], side: str) -> dict[str, Any]:
    model = plan[side]
    side_state = side_status(model)
    signal_type = side_signal_type(side, side_state)
    action = side_action(side, side_state)
    trigger_price = side_trigger_price(model, side_state)
    invalid_price = model.get("invalid_price")
    direction = "bullish_lean" if side == "buy" else "bearish_lean"
    trigger_text = "等观察价以下 5m 止跌确认" if side == "buy" else "等观察价附近冲高失败确认"
    invalid_text = (
        f"跌破 {price(invalid_price)} 后停止低吸" if side == "buy" else f"放量站上 {price(invalid_price)} 后取消高抛"
    )
    return {
        "contract": "trader_signal_v1",
        "source_skill": "t0",
        "symbol": str(plan.get("symbol") or ""),
        "name": str(plan.get("name") or ""),
        "trade_date": str((plan.get("analysis_time") or "").split(" ")[0] or "--"),
        "analysis_time": str(plan.get("analysis_time") or "--"),
        "signal_type": signal_type,
        "direction": direction,
        "action": action,
        "confidence": "high" if is_zone_hit(side_state) else "medium",
        "data_status": normalize_t0_data_status(str(plan.get("data_status") or "partial")),
        "trigger": {
            "type": "completed_5m_confirm" if is_zone_hit(side_state) else "watch_price",
            "price": numeric_or_none(trigger_price),
            "text": trigger_text,
        },
        "invalidation": {"type": "price_break", "price": numeric_or_none(invalid_price), "text": invalid_text},
        "position": t0_position(plan),
        "risk_flags": side_risk_flags(model),
        "summary": side_summary(model, side, trigger_price),
    }


def build_t0_event_signal(event: str, plan: dict[str, Any]) -> dict[str, Any]:
    side = "buy" if event.startswith("BUY") else "sell"
    signal = build_side_signal(plan, side)
    mapping = {
        "BUY_TRIGGERED": ("low_buy_triggered", "low_buy"),
        "SELL_TRIGGERED": ("high_sell_triggered", "high_sell"),
    }
    if event in mapping:
        signal["signal_type"], signal["action"] = mapping[event]
    return signal


def _build_realtime_signal_section(plan: dict[str, Any]) -> list[str]:
    """构建 🔔 实时信号 输出段落。

    检查威科夫信号（BC/UTAD/SOW）和筹码搬家信号。
    """
    lines: list[str] = []
    alerts: list[str] = []

    # 提取威科夫信号
    wyckoff = plan.get("wyckoff") or {}
    if isinstance(wyckoff, dict):
        bc_signal = wyckoff.get("bc_signal", False)
        bc_reason = wyckoff.get("bc_reason", "")
        utad_signal = wyckoff.get("upthrust_signal", False)
        utad_reason = wyckoff.get("upthrust_reason", "")
        sow_signal = wyckoff.get("sow_signal", False)
        sow_reason = wyckoff.get("sow_reason", "")
    else:
        bc_signal = utad_signal = sow_signal = False
        bc_reason = utad_reason = sow_reason = ""

    # 提取筹码搬家数据
    chip_migration = plan.get("chip_migration") or {}
    warning_level = chip_migration.get("warning_level", "none")
    warning_text = chip_migration.get("warning_text", "")

    # BC 信号
    if bc_signal:
        alerts.append(f"  🔴 购买高潮（BC）信号")
        alerts.append(f"    {bc_reason}")
        alerts.append(f"    动作：减仓 1/3")

    # UTAD 信号
    if utad_signal:
        alerts.append(f"  🔴 上冲回落（UTAD）信号")
        alerts.append(f"    {utad_reason}")
        alerts.append(f"    动作：立刻减仓")

    # SOW 信号
    if sow_signal:
        alerts.append(f"  ⚠️ 弱势信号（SOW）")
        alerts.append(f"    {sow_reason}")
        alerts.append(f"    动作：关注，准备减仓")

    # 筹码搬家
    if warning_level == "critical":
        alerts.append(f"  🔴 筹码搬家清仓信号")
        alerts.append(f"    {warning_text}")
        alerts.append(f"    动作：清仓")
    elif warning_level == "warning":
        alerts.append(f"  ⚠️ 筹码松动警告")
        alerts.append(f"    {warning_text}")
        alerts.append(f"    动作：关注，随时准备减仓")

    if alerts:
        lines.append("🔔 实时信号")
        lines.extend(alerts)

    return lines


def _build_emergency_guide(plan: dict[str, Any], buy: dict[str, Any], sell: dict[str, Any], current_price: float | None) -> list[str]:
    """构建应急指引段：覆盖非标准场景下的操作建议。"""
    lines: list[str] = []
    buy_state = side_status(buy)
    sell_state = side_status(sell)
    data_status_value = str(plan.get("data_status") or "")
    name = str(plan.get("name") or "")
    buy_obs_price = numeric_or_none(buy.get("observation_price"))
    sell_obs_price = numeric_or_none(sell.get("observation_price"))

    # 场景A：突然放量拉升但未到高抛区
    if current_price is not None and sell_obs_price is not None and current_price < sell_obs_price:
        vol_ratio = numeric_or_none(plan.get("volume_ratio")) or 1.0
        gap_pct = (sell_obs_price - current_price) / current_price
        if vol_ratio > 1.5 and gap_pct < 0.01:
            lines.append("🚨 应急：放量接近高抛区，可分批提前减仓，不必等触发")
        elif vol_ratio > 2.0 and gap_pct < 0.02:
            lines.append("🚨 应急：量能异常放大，接近高抛位，建议逐步减仓锁定利润")

    # 场景B：突然跳水但未到低吸区
    if current_price is not None and buy_obs_price is not None and current_price > buy_obs_price:
        buy_gap = (current_price - buy_obs_price) / buy_obs_price
        change_pct = numeric_or_none(plan.get("current_change_pct")) or 0
        if change_pct < -3.0 and buy_gap < 0.02:
            lines.append("🚨 应急：盘中急跌靠近低吸区，等5m止跌信号再动手，不接飞刀")
        elif change_pct < -5.0:
            lines.append("🚨 应急：跌幅超5%，暂停所有低吸计划，等企稳再评估")

    # 场景C：涨停/跌停临近
    quote = plan.get("data", {}).get("quote") or {}
    if current_price is not None:
        pre_close = numeric_or_none(quote.get("pre_close"))
        if pre_close:
           涨停价 = pre_close * 1.1
           跌停价 = pre_close * 0.9
           if abs(current_price - 涨停价) / 涨停价 < 0.005:
               lines.append("🚨 应急：临近涨停，不封板则高抛，封板则持仓观察")
           elif abs(current_price - 跌停价) / 跌停价 < 0.005:
               lines.append("🚨 应急：临近跌停，不接货，等次日企稳再看")

    # 场景D：双侧关注区同时触及（仅结构提醒，非指令）
    if is_zone_hit(buy_state) and is_zone_hit(sell_state):
        lines.append("🚨 结构：低吸与高抛关注区同时触及 · 是否动手由人决定")

    # 场景E：ICT信号辅助提示
    ict = plan.get("ict_signal") or {}
    if current_price is not None and ict.get("signal_grade") in ("A", "B"):
        sweep_type = ict.get("sweep_type", "")
        swept = ict.get("swept_level")
        shift = ict.get("structure_shift", "")
        if "sweep" in str(sweep_type):
            lines.append(f"🚨 ICT: {ict.get('summary', '')}")

    return lines



def render_markdown(plan: dict[str, Any]) -> str:
    # 今天不做：振幅 < 1% 且量比 < 0.8，无操作价值
    # amplitude_pct 是小数（0.089 = 8.9%），比较时转为百分比
    amp = numeric_or_none(plan.get("amplitude_pct"))
    amp_pct = amp * 100 if amp is not None and amp < 1 else amp
    vol_ratio = numeric_or_none(plan.get("volume_ratio"))
    if amp_pct is not None and amp_pct < 1.0 and (vol_ratio is None or vol_ratio < 0.8):
        return (
            f"{plan.get('name','')}（{plan.get('symbol','')}）"
            f"｜现价 {plan.get('current_price','?')}｜振幅 {amp:.2f}% 量能不足，今天不做"
        )

    buy = plan["buy"]
    sell = plan["sell"]
    buy_state = normalize_side_display(str(plan.get("buy_display_status") or side_display(buy)))
    sell_state = normalize_side_display(str(plan.get("sell_display_status") or side_display(sell)))
    buy_obs = str(plan.get("buy_display_obs") or observation_value(buy, "以下"))
    sell_obs = str(plan.get("sell_display_obs") or observation_value(sell, "附近"))

    current_price = numeric_or_none(plan.get('current_price'))
    current_text = "无" if current_price is None else f"{current_price:.2f}"
    big_order = None
    if analyze_big_orders and plan.get("data"):
        focus_prices = []
        buy_focus = numeric_or_none(buy.get("observation_price"))
        sell_focus = numeric_or_none(sell.get("observation_price"))
        if buy_focus is not None:
            focus_prices.append(("低吸关注区", buy_focus))
        if sell_focus is not None:
            focus_prices.append(("高抛关注区", sell_focus))
        bars = (plan.get("data") or {}).get("kline_5m") or []
        trade_date = str(plan.get("analysis_time") or "").split(" ", 1)[0] or None
        tick_data = (plan.get("data") or {}).get("tick_data") or []
        big_order = analyze_big_orders(
            bars,
            tick_data=tick_data,
            focus_prices=focus_prices,
            trade_date=trade_date,
            order_book=(plan.get("data") or {}).get("order_book"),
        )

    from t0_config import TREND_FILTER_EXTREME_ONLY  # noqa: F401 — keep import side for config loaders

    stop_price = price(numeric_or_none(buy.get("invalid_price")))

    # ── 距关注价距离（提示，非指令） ──
    distance_lines: list[str] = []
    if current_price is not None:
        buy_obs_price = numeric_or_none(buy.get("observation_price"))
        sell_obs_price = numeric_or_none(sell.get("observation_price"))
        if (
            buy_obs_price is not None
            and buy_state not in (SIDE_ZONE_HIT, "数据不足", "")
            and not _is_fake_zone_price(buy_obs_price, current_price)
        ):
            gap_pct = (current_price - buy_obs_price) / buy_obs_price
            est_bars = int(gap_pct / 0.003) if gap_pct > 0 else 0
            if gap_pct > 0.005:
                distance_lines.append(f"低吸关注区还差 {gap_pct*100:.1f}%（约{est_bars}根5m线）")
            elif gap_pct > 0:
                distance_lines.append(f"接近低吸关注区，差 {gap_pct*100:.1f}%")
        if (
            sell_obs_price is not None
            and sell_state not in (SIDE_ZONE_HIT, "数据不足", "")
            and not _is_fake_zone_price(sell_obs_price, current_price)
        ):
            gap_pct = (sell_obs_price - current_price) / current_price
            est_bars = int(gap_pct / 0.003) if gap_pct > 0 else 0
            if gap_pct > 0.005:
                distance_lines.append(f"高抛关注区还差 {gap_pct*100:.1f}%（约{est_bars}根5m线）")
            elif gap_pct > 0:
                distance_lines.append(f"接近高抛关注区，差 {gap_pct*100:.1f}%")

    structure_lines = _build_structure_block(
        plan,
        buy=buy,
        sell=sell,
        buy_state=buy_state,
        sell_state=sell_state,
        buy_obs=buy_obs,
        sell_obs=sell_obs,
        stop_price=stop_price,
        distance_lines=distance_lines,
    )
    checklist_lines = _build_human_checklist(plan, buy=buy, sell=sell)

    # ── 资金：大单异动（仅净流入进主卡） ──
    capital_lines = []
    if big_order and big_order.get("events"):
        by_side = big_order.get("by_side") or {}
        buy_info = by_side.get("主动买入") or {}
        sell_info = by_side.get("主动卖出") or {}
        buy_total = round(buy_info.get("amount_wan") or 0)
        sell_total = round(sell_info.get("amount_wan") or 0)
        net = buy_total - sell_total
        capital_lines.append(
            f"净流入 {'+' if net >= 0 else ''}{net}万"
            f"{'，主力偏多' if net > 0 else '，主力偏空' if net < 0 else ''}"
        )

    account_lines = _build_account_section(plan)

    # ── 组装输出：结构参考卡（v2.1，人决策） ──
    lines = [
        f"🎯 {plan.get('name','')}（{plan.get('symbol','')}）{current_text}（{pct_text(numeric_or_none(plan.get('current_change_pct')))}）",
    ]

    conclusion = _build_conclusion(plan, buy_state, sell_state)
    lines.append(f"  → {conclusion}")

    lines.append("")
    lines.extend(structure_lines)

    if checklist_lines:
        lines.append("")
        lines.extend(checklist_lines)

    lines.append("")
    lines.append("🔗 参考")
    resonance_lines_short = _build_resonance_section(plan)
    if resonance_lines_short:
        lines.extend(resonance_lines_short)
    else:
        lines.append("  暂无评分/结构明细 · 仅供参考，不构成执行指令")

    failure = _build_failure_conditions(plan, buy, sell, stop_price, buy_state, sell_state)
    if failure:
        lines.append(f"  看法失效：{failure}")

    if capital_lines:
        lines.append(f"💰 {capital_lines[0]}")

    if account_lines:
        lines.append("")
        lines.extend(account_lines)

    return "\n".join(lines)


def _has_position(plan: dict[str, Any]) -> bool:
    acct = plan.get("t0_account") or {}
    try:
        return int(acct.get("total_shares") or 0) > 0
    except (TypeError, ValueError):
        return False


# 价区与现价过近视为「假结构」（数据不足时常见：低吸=高抛=现价）
_FAKE_ZONE_EPS = 0.002


def _amplitude_pct_display(plan: dict[str, Any]) -> float | None:
    """振幅统一为百分点（如 3.2）；amplitude_pct 可能是小数或已是百分数。"""
    amp = numeric_or_none(plan.get("amplitude_pct"))
    if amp is None:
        return None
    return amp * 100 if amp < 1 else amp


def _quote_day_range(plan: dict[str, Any]) -> tuple[float | None, float | None]:
    quote = (plan.get("data") or {}).get("quote") or {}
    high = numeric_or_none(quote.get("high"))
    low = numeric_or_none(quote.get("low"))
    return high, low


def _is_fake_zone_price(zone_px: float | None, current: float | None) -> bool:
    if zone_px is None or current is None or current <= 0:
        return False
    return abs(zone_px - current) / current < _FAKE_ZONE_EPS


def _vwap_rel_text(plan: dict[str, Any]) -> str | None:
    vwap = numeric_or_none(plan.get("vwap"))
    current = numeric_or_none(plan.get("current_price"))
    if not vwap or not current or vwap <= 0:
        return None
    if abs(vwap - current) / current > 0.2:
        return None
    rel = (current - vwap) / vwap
    if rel > 0.005:
        return "价在VWAP上"
    if rel < -0.005:
        return "价在VWAP下"
    return "价近VWAP"


def _box_position_text(plan: dict[str, Any]) -> str | None:
    current = numeric_or_none(plan.get("current_price"))
    high, low = _quote_day_range(plan)
    if current is None or high is None or low is None or high <= low:
        return None
    span = high - low
    if span <= 0:
        return None
    pos = (current - low) / span
    if pos >= 0.7:
        return "靠近今日高区"
    if pos <= 0.3:
        return "靠近今日低区"
    return "靠近今日中轴"


def _volume_label(plan: dict[str, Any]) -> str:
    try:
        from t0_config import VOLUME_EXPAND_RATIO, VOLUME_SHRINK_RATIO
    except Exception:
        VOLUME_EXPAND_RATIO, VOLUME_SHRINK_RATIO = 1.2, 0.8
    vol = numeric_or_none(plan.get("volume_ratio"))
    if vol is None:
        return "量能不足"
    if vol >= VOLUME_EXPAND_RATIO:
        return f"量比{vol:.1f}（放量）"
    if vol <= VOLUME_SHRINK_RATIO:
        return f"量比{vol:.1f}（缩量）"
    return f"量比{vol:.1f}（平量）"


def _data_thin(plan: dict[str, Any]) -> bool:
    ds = str(plan.get("data_status") or "")
    if ds in {"degraded", "insufficient", "non_trading"}:
        return True
    vwap = numeric_or_none(plan.get("vwap"))
    current = numeric_or_none(plan.get("current_price"))
    if vwap is None or current is None:
        return True
    return False


def _build_conclusion(plan: dict[str, Any], buy_state: str, sell_state: str) -> str:
    """一句话结构结论（v2.1）：位置叙事优先；评分不进主语。"""
    parts: list[str] = []
    thin = _data_thin(plan)

    if thin and not _vwap_rel_text(plan) and _box_position_text(plan) is None:
        parts.append("数据不足，仅现价")
    else:
        vwap_txt = _vwap_rel_text(plan)
        parts.append(vwap_txt if vwap_txt else "VWAP不足")
        box_txt = _box_position_text(plan)
        if box_txt:
            parts.append(box_txt)
        else:
            high, low = _quote_day_range(plan)
            if high is None or low is None:
                parts.append("今日高低不足")
        vol_txt = _volume_label(plan)
        if "不足" in vol_txt:
            parts.append("量不足")
        elif "放量" in vol_txt:
            parts.append("量放")
        elif "缩量" in vol_txt:
            parts.append("量缩")
        else:
            parts.append("量平")

    if is_zone_hit(buy_state):
        parts.append("近低吸关注区")
    if is_zone_hit(sell_state):
        parts.append("近高抛关注区")

    if not _has_position(plan):
        parts.append("无底仓")

    parts.append("宜观察 · 人决策")
    return " · ".join(parts)


def _format_zone_ref_line(
    side: str,
    *,
    state: str,
    model: dict[str, Any],
    obs_text: str,
    zone_px: float | None,
    ab_px: float | None,
    wyck_px: float | None,
    current: float | None,
) -> str:
    """关注价行；假价区（≈现价）不展示，避免低吸=高抛=现价假结构。"""
    label = "低吸" if side == "buy" else "高抛"
    if is_zone_hit(state):
        _exec = numeric_or_none(model.get("execution_price"))
        _acc = numeric_or_none(model.get("acceptable_price"))
        if _exec and _acc and not (
            _is_fake_zone_price(_exec, current) and _is_fake_zone_price(_acc, current)
        ):
            return f"{label}：关注 {_exec:.2f}～{_acc:.2f}（参考）"
        return f"{label}：价近关注区 · {obs_text}"

    parts: list[str] = []
    if zone_px is not None and not _is_fake_zone_price(zone_px, current):
        parts.append(f"价区{zone_px:.2f}")
    if ab_px is not None and not _is_fake_zone_price(ab_px, current):
        parts.append(f"价格行为{ab_px:.2f}")
    if wyck_px is not None and not _is_fake_zone_price(wyck_px, current):
        parts.append(f"威科夫{wyck_px:.2f}")
    if not parts:
        # 双侧价区都塌到现价 → 诚实降级
        if zone_px is not None and _is_fake_zone_price(zone_px, current):
            return f"{label}：暂无有效关注价（结构数据不足）"
        return f"{label}：暂无"
    return f"{label}：{'｜'.join(parts)}"


def _build_structure_block(
    plan: dict[str, Any],
    *,
    buy: dict[str, Any],
    sell: dict[str, Any],
    buy_state: str,
    sell_state: str,
    buy_obs: str,
    sell_obs: str,
    stop_price: str,
    distance_lines: list[str],
) -> list[str]:
    """📌 结构四块：位置 / 量能 / 空间 / 关注价。"""
    has_pos = _has_position(plan)
    current = numeric_or_none(plan.get("current_price"))
    lines = ["📌 结构"]

    # 1) 位置
    pos_parts: list[str] = []
    vwap = numeric_or_none(plan.get("vwap"))
    vwap_txt = _vwap_rel_text(plan)
    if vwap_txt and vwap is not None:
        pos_parts.append(f"{vwap_txt}（VWAP {vwap:.2f}）")
    else:
        pos_parts.append("VWAP不足")
    high, low = _quote_day_range(plan)
    if high is not None and low is not None and high >= low:
        pos_parts.append(f"今日 {low:.2f}-{high:.2f}")
        box = _box_position_text(plan)
        if box:
            pos_parts.append(box)
    else:
        pos_parts.append("今日高低不足")
    lines.append("位置：" + " · ".join(pos_parts))

    # 2) 量能
    lines.append(f"量能：{_volume_label(plan)}")

    # 3) 空间
    amp_pct = _amplitude_pct_display(plan)
    space_state = str(plan.get("space_state") or "unknown")
    space_map = {"too_small": "偏小", "normal": "正常", "good": "够用", "unknown": "未知"}
    space_lbl = space_map.get(space_state, space_state)
    if amp_pct is not None:
        space_line = f"空间：振幅 {amp_pct:.2f}%（{space_lbl}）"
    else:
        space_line = "空间：振幅不足"
    if has_pos:
        worth = (plan.get("t0_account") or {}).get("worth_t") or {}
        if worth:
            if worth.get("worth"):
                space_line += " · 费后约盖住门槛（纪律提醒）"
            else:
                space_line += " · 空间可能盖不住费用（纪律提醒）"
        elif space_state == "too_small":
            space_line += " · 空间可能盖不住费用（纪律提醒）"
    lines.append(space_line)

    if not has_pos:
        lines.append("持仓：无底仓 · 仅结构参考，不做 T 召唤")

    lines.append(f"当前：观望 ｜ 止损参考：{stop_price}")

    # 4) 关注价
    _mzones = (plan.get("model") or {}).get("zones") or {}
    _res = plan.get("resonance") or {}
    _lights = _res.get("lights") or {}
    _cur = current or 0
    _zone_buy = _mzones.get("buy_zone", {}).get("main_support")
    _zone_sell = _mzones.get("sell_zone", {}).get("main_resistance")
    _ab_bp_raw = (_lights.get("ab") or {}).get("buy_price")
    _ab_sp_raw = (_lights.get("ab") or {}).get("sell_price")
    _ab_bp = None
    _ab_sp = None
    if _ab_bp_raw and _cur and abs(_ab_bp_raw - _cur) / _cur <= 0.2:
        _ab_bp = _ab_bp_raw
    if _ab_sp_raw and _cur and abs(_ab_sp_raw - _cur) / _cur <= 0.2:
        _ab_sp = _ab_sp_raw
    _wyck_bp = (_lights.get("wyckoff") or {}).get("buy_price")
    _wyck_sp = (_lights.get("wyckoff") or {}).get("sell_price")

    # 双侧价区同时塌到现价 → 统一降级一行说明即可
    buy_fake = _is_fake_zone_price(
        numeric_or_none(_zone_buy) if _zone_buy is not None else None, current
    )
    sell_fake = _is_fake_zone_price(
        numeric_or_none(_zone_sell) if _zone_sell is not None else None, current
    )
    if (
        not is_zone_hit(buy_state)
        and not is_zone_hit(sell_state)
        and buy_fake
        and sell_fake
    ):
        lines.append("低吸：暂无有效关注价（结构数据不足）")
        lines.append("高抛：暂无有效关注价（结构数据不足）")
    else:
        lines.append(
            _format_zone_ref_line(
                "buy",
                state=buy_state,
                model=buy,
                obs_text=buy_obs,
                zone_px=numeric_or_none(_zone_buy) if _zone_buy is not None else None,
                ab_px=_ab_bp,
                wyck_px=numeric_or_none(_wyck_bp) if _wyck_bp is not None else None,
                current=current,
            )
        )
        lines.append(
            _format_zone_ref_line(
                "sell",
                state=sell_state,
                model=sell,
                obs_text=sell_obs,
                zone_px=numeric_or_none(_zone_sell) if _zone_sell is not None else None,
                ab_px=_ab_sp,
                wyck_px=numeric_or_none(_wyck_sp) if _wyck_sp is not None else None,
                current=current,
            )
        )

    exit_plan = plan.get("exit_plan") or {}
    exit_items = exit_plan.get("exit_plan") or []
    if exit_items and exit_plan.get("risk_r", 0) > 0 and current:
        buy_tp = []
        sell_tp = []
        for item in exit_items:
            p = item.get("price")
            if p is not None:
                if p > current:
                    buy_tp.append(f"{p:.2f}")
                else:
                    sell_tp.append(f"{p:.2f}")
        if buy_tp:
            lines.append(f"低吸止盈：{'｜'.join(buy_tp)}")
        if sell_tp:
            lines.append(f"高抛止盈：{'｜'.join(sell_tp)}")

    atr_info = plan.get("atr_info") or {}
    level_advice = atr_info.get("level_advice")
    if level_advice:
        lines.append(f"波动：{level_advice}")
    if distance_lines:
        lines.extend(distance_lines)
    return lines


def _build_human_checklist(
    plan: dict[str, Any],
    *,
    buy: dict[str, Any],
    sell: dict[str, Any],
) -> list[str]:
    """有底仓才展示：若做正T（人勾选）。系统只列条件，不下令。"""
    if not _has_position(plan):
        return []

    lines = ["📋 若做正T（人勾选）"]
    sell_obs = numeric_or_none(sell.get("observation_price"))
    buy_obs = numeric_or_none(buy.get("observation_price"))
    current = numeric_or_none(plan.get("current_price"))
    stop = numeric_or_none(buy.get("invalid_price"))

    if sell_obs is not None and not _is_fake_zone_price(sell_obs, current):
        lines.append(f"  · 先确认卖点关注区（参考 {sell_obs:.2f} 一带/冲高乏力）")
    else:
        lines.append("  · 先确认卖点关注区（上方/冲高乏力；当前暂无有效卖点参考）")

    worth = (plan.get("t0_account") or {}).get("worth_t") or {}
    if buy_obs is not None and sell_obs is not None and sell_obs > buy_obs:
        edge = "费后够门槛" if worth.get("worth") else ("费后不够门槛" if worth else "费后未计")
        lines.append(
            f"  · 买回区低于卖点（买回参考 {buy_obs:.2f} < 卖 {sell_obs:.2f}），且{edge}（纪律提醒）"
        )
    else:
        lines.append("  · 买回区低于卖点，且费后空间盖住门槛（当前区间未齐，慎动）")

    if stop is not None:
        broken = current is not None and current < stop
        lines.append(
            f"  · 未破看法失效价 {stop:.2f}"
            + ("（现价已低于参考，今日宜停）" if broken else "")
        )
    else:
        lines.append("  · 未破看法失效价")

    space_state = str(plan.get("space_state") or "")
    if space_state == "too_small":
        lines.append("  · 非破位日 / 非空间不足日（今日空间偏小，宜不做）")
    else:
        lines.append("  · 非破位日 / 非空间不足日")

    acct = plan.get("t0_account") or {}
    if acct.get("allow_reverse_t"):
        lines.append("  · 倒T：仅自担风险（已声明有现金且非深套）；默认仍不鼓励")
    else:
        lines.append("  · 倒T：默认不鼓励")

    lines.append("  · 是否动手由人决定，不构成执行指令")
    return lines


def _build_failure_conditions(plan: dict[str, Any], buy: dict, sell: dict,
                               stop_price: str, buy_state: str, sell_state: str) -> str:
    """生成失效条件：什么时候放弃当前计划。"""
    parts = []
    parts.append(f"跌破{stop_price}")

    resonance = plan.get("resonance") or {}
    lights = resonance.get("lights", {})

    # 价格行为反转
    ab_info = lights.get("ab", {})
    if ab_info.get("buy"):
        parts.append("价格行为转卖")
    elif ab_info.get("sell"):
        parts.append("价格行为转买")

    # 威科夫反转
    wyck_info = lights.get("wyckoff", {})
    if wyck_info.get("buy"):
        parts.append("威科夫转卖")
    elif wyck_info.get("sell"):
        parts.append("威科夫转买")

    # VWAP
    vwap = plan.get("vwap")
    current = numeric_or_none(plan.get("current_price"))
    if vwap and current:
        if current < vwap:
            parts.append("跌破VWAP")
        else:
            parts.append("跌回VWAP")

    return " / ".join(parts) if parts else "无"


def _build_account_section(plan: dict[str, Any]) -> list[str]:
    """持仓纪律段（v2）。无底仓不展示，避免「做 T 召唤」。"""
    if not _has_position(plan):
        return []
    acct = plan.get("t0_account")
    if not acct:
        return []
    mode = acct.get("mode", "")
    if mode == "none":
        return []

    lines = ["📉 持仓纪律"]
    mode_label = {
        "cost_cut": "先卖后买（降本参考）",
        "grid": "网格参考",
        "reduce": "边做 T 边减仓（参考）",
    }.get(mode, mode)
    lines.append(f"  纪律：{mode_label} · 是否动手由人决定")

    avg_cost = acct.get("avg_cost", 0)
    new_cost = acct.get("new_cost_estimate")
    if avg_cost > 0 and new_cost and new_cost < avg_cost:
        lines.append(f"  成本 {avg_cost:.2f} → 预估 T 后 {new_cost:.2f}")

    worth = acct.get("worth_t") or {}
    if worth:
        net_pct = worth.get("net_pct", 0)
        min_edge = worth.get("min_edge_pct", 0.8)
        worth_text = "够门槛（纪律提醒）" if worth.get("worth") else "不够门槛（慎动）"
        lines.append(f"  费后空间：约 {net_pct:.1f}%（门槛 {min_edge}%）→ {worth_text}")

    if not acct.get("allow_reverse_t", True):
        lines.append("  倒 T：否（浮亏过深或无现金）")

    float_pnl = acct.get("float_pnl_pct", 0)
    if float_pnl < 0:
        lines.append(f"  浮亏：{float_pnl:.1f}%")

    return lines


def _build_theory_diagnostics(plan: dict[str, Any]) -> str:
    """各理论检测摘要：威科夫 Spring/UT 检测 + 动量 RSI。"""
    model = plan.get("model") or {}
    zones = model.get("zones") or {}
    cur = plan.get("current_price") or 0
    from t0_config import VOLUME_SHRINK_RATIO, VOLUME_EXPAND_RATIO

    vol_ratio = model.get("volume_ratio") or 0
    buy_support = (zones.get("buy_zone") or {}).get("main_support") or 0
    sell_res = (zones.get("sell_zone") or {}).get("main_resistance") or 0

    # 威科夫
    w = ["威科夫"]
    if buy_support and cur:
        w.append(f"Spring(支{buy_support:.2f})")
    if sell_res and cur:
        w.append(f"UT(压{sell_res:.2f})")
    if vol_ratio:
        lbl = "缩" if vol_ratio < VOLUME_SHRINK_RATIO else ("放" if vol_ratio > VOLUME_EXPAND_RATIO else "平")
        w.append(f"量比{vol_ratio:.1f}({lbl})")
    parts = [" ".join(w)]

    # 动量
    m = ["动量"]
    if cur:
        m.append(f"现价{cur:.2f}")
    parts.append(" ".join(m))

    return f"  {' | '.join(parts)}"


def _format_theory_price_line(name: str, status: str, info: dict, reason: str) -> str:
    """格式化单个理论的价格行：状态 + 原因 + 入场/出场价。"""
    buy_price = info.get("buy_price")
    sell_price = info.get("sell_price")
    exit_price = info.get("exit_price")

    # 构建价格信息
    price_parts = []
    if buy_price and buy_price > 0:
        price_parts.append(f"入场{buy_price:.2f}")
    if sell_price and sell_price > 0:
        price_parts.append(f"入场{sell_price:.2f}")
    if exit_price and exit_price > 0:
        price_parts.append(f"出场{exit_price:.2f}")

    price_str = f" {'｜'.join(price_parts)}" if price_parts else ""
    return f"  {name} {status}（{reason}{price_str}）"


def _format_score_light(label: str, info: dict[str, Any]) -> str:
    """五条件灯：多✓ / 空✓ / 未达 —— 禁止「卖=下单」误读。"""
    reason = str(info.get("reason") or "").strip()
    # 原因过长时截断，避免刷屏
    if len(reason) > 28:
        reason = reason[:26] + "…"
    if info.get("buy"):
        mark = "多✓"
    elif info.get("sell"):
        mark = "空✓"
    else:
        mark = "未达"
    return f"{label}{mark}" + (f"({reason})" if reason else "")


def _build_resonance_section(plan: dict[str, Any]) -> list[str]:
    """结构/评分参考段（v2）：只展示，不映射为可执行指令。"""
    resonance = plan.get("resonance")
    if not resonance:
        return []

    lights = resonance.get("lights") or {}
    lines: list[str] = []
    score = resonance.get("score")
    if score is not None:
        if score >= 60:
            band = "偏强"
        elif score >= 40:
            band = "中性偏上"
        else:
            band = "偏弱"
        lines.append(
            f"  结构分 {score}/100（{band}）· EMA/VWAP/箱体/量/ATR 各20 · 仅供结构参考，不构成执行指令"
        )

    # 五条件评分灯（生产 check_resonance）
    score_keys = [
        ("ema", "EMA"),
        ("vwap", "VWAP"),
        ("box", "箱体"),
        ("volume", "量能"),
        ("atr", "ATR"),
    ]
    if any(k in lights for k, _ in score_keys):
        parts = []
        for key, label in score_keys:
            info = lights.get(key) or {}
            if not info:
                continue
            parts.append(_format_score_light(label, info))
        if parts:
            # 两行更易扫：前三项位置类 / 后两项确认类
            lines.append("  " + " ｜ ".join(parts[:3]))
            if len(parts) > 3:
                lines.append("  " + " ｜ ".join(parts[3:]))
        lines.append("  读法：多✓=偏多条件成立 空✓=偏空检查成立 未达=本项没亮 · 非买卖指令")
    else:
        # 兼容旧 ab/威科夫/动量灯：降级为参考文案
        ab_info = lights.get("ab", {})
        ab_result = plan.get("ab_result") or {}
        if ab_info or ab_result:
            if ab_info.get("buy"):
                ab_status = "偏多"
            elif ab_info.get("sell"):
                ab_status = "偏空"
            elif ab_info and not ab_info.get("ok"):
                ab_status = "无数据"
            else:
                ab_status = "中性"
            ab_detail = ab_info.get("reason") or "—"
            ai = ab_result.get("always_in", "neutral")
            if ai == "bull":
                ab_detail = "Always-In多 · " + str(ab_detail)
            elif ai == "bear":
                ab_detail = "Always-In空 · " + str(ab_detail)
            lines.append(f"  价格行为 {ab_status}（{ab_detail}）")

        wyck_info = lights.get("wyckoff", {})
        if wyck_info:
            if wyck_info.get("buy"):
                wyck_status = "偏多"
            elif wyck_info.get("sell"):
                wyck_status = "偏空"
            else:
                wyck_status = "中性"
            lines.append(f"  威科夫 {wyck_status}（{wyck_info.get('reason') or '—'}）")

        mom_info = lights.get("momentum", {})
        if mom_info:
            if mom_info.get("buy"):
                mom_status = "偏多"
            elif mom_info.get("sell"):
                mom_status = "偏空"
            elif not mom_info.get("ok"):
                mom_status = "无数据"
            else:
                mom_status = "中性"
            lines.append(f"  动量 {mom_status}（{mom_info.get('reason') or '—'}）")

    if not any("不构成执行" in ln for ln in lines):
        lines.append("  仅供结构参考，不构成执行指令")
    return lines


def side_signal_type(side: str, side_state: str) -> str:
    if is_zone_hit(side_state):
        return "low_buy_triggered" if side == "buy" else "high_sell_triggered"
    if side_state == "已错过":
        return "trigger_expired"
    if side_state == "被阻断":
        return "blocked"
    return "low_buy_watch" if side == "buy" else "high_sell_watch"


def side_action(side: str, side_state: str) -> str:
    if is_zone_hit(side_state):
        return "low_buy" if side == "buy" else "high_sell"
    if side_state == "被阻断":
        return "stop_low_buy" if side == "buy" else "stop_high_sell"
    return "observe"


def side_trigger_price(model: dict[str, Any], side_state: str) -> Any:
    if is_zone_hit(side_state):
        return model.get("execution_price")
    return model.get("observation_price")


def side_summary(model: dict[str, Any], side: str, trigger_price: Any) -> str:
    side_state = side_status(model)
    if side == "buy":
        if is_zone_hit(side_state):
            return f"低吸到价关注，参考 {price(trigger_price)}，超过可接受价不追；是否动手由人决定。"
        return f"低吸未到价，只盯 {price(trigger_price)} 以下是否 5m 止跌。"
    if is_zone_hit(side_state):
        return f"高抛到价关注，参考 {price(trigger_price)}，低于可接受价不砸；是否动手由人决定。"
    return f"高抛未到价，只盯 {price(trigger_price)} 附近是否冲高失败。"


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
        return "degraded"
    if value in {"complete", "full"}:
        return "full"
    if value in {"fresh", "insufficient", "non_trading", "partial", "degraded"}:
        return value
    return "partial"
