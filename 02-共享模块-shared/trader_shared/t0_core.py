"""T0 信号与卡片核心（自 t0/scripts/t0_core 迁入）。"""
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

    from trader_shared.t0_config import TREND_FILTER_EXTREME_ONLY  # noqa: F401 — keep import side for config loaders

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

    # ── 组装：微信短卡（无 #/**/表格/列表符；短行优先） ──
    # 标题缩码：688248.SH → 688248，省宽度
    symbol = str(plan.get("symbol") or "")
    code = symbol.split(".")[0] if symbol else ""
    title_code = code or symbol
    lines = [
        f"🎯 {plan.get('name','')}（{title_code}）{current_text}（{pct_text(numeric_or_none(plan.get('current_change_pct')))}）",
    ]

    conclusion = _build_conclusion(plan, buy_state, sell_state)
    lines.append(f"→ {conclusion}")

    lines.append("")
    lines.extend(structure_lines)

    if checklist_lines:
        lines.append("")
        lines.extend(checklist_lines)

    # ⑤ 边界：失效 + 参考分（与买卖价四类分开）
    stop_num = numeric_or_none(buy.get("invalid_price"))
    fail_bits: list[str] = []
    if stop_num is not None:
        fail_bits.append(f"跌破止损{stop_num:.2f}")
    vwap = numeric_or_none(plan.get("vwap"))
    if vwap and current_price and current_price < vwap:
        fail_bits.append("跌破VWAP")
    if fail_bits:
        lines.append(f"看法失效：{' / '.join(fail_bits)}")

    resonance = plan.get("resonance") or {}
    score = resonance.get("score")
    if score is not None and int(score) > 0 and not _data_thin(plan):
        lines.append(f"参考分 {int(score)} · 仅供结构对照，非下单指令")

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
        from trader_shared.t0_config import VOLUME_EXPAND_RATIO, VOLUME_SHRINK_RATIO
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
    """微信短结论：位置优先，控制在约一行手机宽度。"""
    parts: list[str] = []
    thin = _data_thin(plan)

    if thin and not _vwap_rel_text(plan) and _box_position_text(plan) is None:
        parts.append("数据不足")
    else:
        vwap_txt = _vwap_rel_text(plan)
        if vwap_txt:
            # 微信短写：价在VWAP上 → VWAP上
            parts.append(vwap_txt.replace("价在", "").replace("价近", "近"))
        box_txt = _box_position_text(plan)
        if box_txt:
            parts.append(
                box_txt.replace("靠近今日高区", "近高区")
                .replace("靠近今日低区", "近低区")
                .replace("靠近今日中轴", "中轴")
            )
        vol_txt = _volume_label(plan)
        if "放量" in vol_txt:
            parts.append("放量")
        elif "缩量" in vol_txt:
            parts.append("缩量")

    if is_zone_hit(buy_state):
        parts.append("近买区")
    if is_zone_hit(sell_state):
        parts.append("近卖区")
    if not _has_position(plan):
        parts.append("无底仓")
    parts.append("人决策")
    return " · ".join(parts)


# 单回合费用粗估（佣金+印花+滑点），用于 RR/空间是否盖住费用
_ROUND_TRIP_COST_PCT = 0.0035


def _first_exit_above(plan: dict[str, Any], floor: float | None) -> float | None:
    exit_plan = plan.get("exit_plan") or {}
    items = exit_plan.get("exit_plan") or []
    cands = []
    for item in items:
        p = numeric_or_none(item.get("price"))
        if p is not None and (floor is None or p > floor):
            cands.append(p)
    return min(cands) if cands else None


def _resolve_buy_px(buy: dict[str, Any], plan: dict[str, Any]) -> float | None:
    """买入参考价：到价用执行价，否则观察价/价区支撑。"""
    if is_zone_hit(side_status(buy)):
        px = numeric_or_none(buy.get("execution_price"))
        if px is not None:
            return px
    px = numeric_or_none(buy.get("observation_price"))
    if px is not None:
        return px
    zones = (plan.get("model") or {}).get("zones") or {}
    return numeric_or_none((zones.get("buy_zone") or {}).get("main_support") or (zones.get("buy_zone") or {}).get("upper"))


def _resolve_sell_px(sell: dict[str, Any], plan: dict[str, Any], buy_px: float | None) -> float | None:
    """卖出参考价：必须高于买价才有效；否则用止盈计划/压力位兜底。"""
    current = numeric_or_none(plan.get("current_price"))
    floor = buy_px if buy_px is not None else current

    def _ok(px: float | None) -> float | None:
        if px is None:
            return None
        if floor is not None and px <= floor + 1e-6:
            return None
        return px

    if is_zone_hit(side_status(sell)):
        hit = _ok(numeric_or_none(sell.get("execution_price")))
        if hit is not None:
            return hit
    obs = _ok(numeric_or_none(sell.get("observation_price")))
    if obs is not None:
        return obs
    zones = (plan.get("model") or {}).get("zones") or {}
    zone_sell = _ok(
        numeric_or_none(
            (zones.get("sell_zone") or {}).get("main_resistance")
            or (zones.get("sell_zone") or {}).get("lower")
        )
    )
    if zone_sell is not None:
        return zone_sell
    # 止盈计划兜底（操盘要看见上方目标）
    return _first_exit_above(plan, floor)


def _rr_verdict(rr: float | None, net_space_pct: float | None) -> str:
    """盈亏比白话判定（不用 RR 缩写）。"""
    if rr is None:
        return "算不出"
    if net_space_pct is not None and net_space_pct < 0:
        return "盖不住费用"
    if rr >= 2.0:
        return "够用"
    if rr >= 1.0:
        return "一般"
    return "偏弱"


def _atr_pair_txt(risk: float, reward: float, atr: float | None) -> str:
    """亏/赚相对 ATR 的短注，如（0.1/0.4倍ATR）。"""
    if atr is None or atr <= 0:
        return ""
    return f"（{risk / atr:.1f}/{reward / atr:.1f}倍ATR）"


def _ledger_one_line(
    *,
    title: str,
    risk: float,
    reward: float,
    atr: float | None,
    rr: float,
    net_space: float | None = None,
    verdict: str | None = None,
) -> str:
    """一本账压成一行：亏｜赚｜盈亏比｜费后。"""
    judge = verdict if verdict is not None else _rr_verdict(rr, net_space)
    bits = [
        f"{title}：亏约{risk:.2f}｜赚约{reward:.2f}{_atr_pair_txt(risk, reward, atr)}",
        f"1比{rr:.1f} · {judge}",
    ]
    if net_space is not None:
        fee_txt = "盖得住" if net_space >= 0 else "盖不住费"
        bits.append(f"费后{net_space * 100:.1f}%{fee_txt}")
    return "｜".join(bits)


def _build_trade_price_rr_block(
    plan: dict[str, Any],
    *,
    buy: dict[str, Any],
    sell: dict[str, Any],
) -> list[str]:
    """买卖价四行：价位｜波动｜计划账｜现价账（参考，非指令）。"""
    current = numeric_or_none(plan.get("current_price"))
    buy_px = _resolve_buy_px(buy, plan)
    sell_px = _resolve_sell_px(sell, plan, buy_px)
    stop = numeric_or_none(buy.get("invalid_price"))
    atr_info = plan.get("atr_info") or {}
    atr = numeric_or_none(atr_info.get("atr14"))
    atr_ratio = numeric_or_none(atr_info.get("atr_ratio"))

    lines = ["📌 买卖价"]

    buy_txt = f"{buy_px:.2f}" if buy_px is not None else "—"
    sell_txt = f"{sell_px:.2f}" if sell_px is not None else "—"
    stop_txt = f"{stop:.2f}" if stop is not None else "—"
    if is_zone_hit(side_status(buy)) and buy.get("acceptable_price") is not None:
        buy_txt = f"{buy_px:.2f}～{float(buy['acceptable_price']):.2f}"
    if is_zone_hit(side_status(sell)) and sell.get("acceptable_price") is not None and sell_px is not None:
        acc = numeric_or_none(sell.get("acceptable_price"))
        if acc is not None:
            lo, hi = sorted([sell_px, acc])
            sell_txt = f"{lo:.2f}～{hi:.2f}"

    # ① 价位一行
    lines.append(f"低吸买入：{buy_txt}｜止损：{stop_txt}｜高抛卖出：{sell_txt}")

    # ② 波动一行
    if atr is not None and atr > 0:
        atr_pct = (atr_ratio * 100) if atr_ratio is not None and atr_ratio < 1 else atr_ratio
        if atr_pct is None and current:
            atr_pct = atr / current * 100
        atr_bits = [f"波动：ATR {atr:.2f}元"]
        if atr_pct is not None:
            atr_bits.append(f"占现价{atr_pct:.1f}%")
        level = str(atr_info.get("level") or "").strip()
        if level:
            atr_bits.append(level)
        lines.append("｜".join(atr_bits))
    else:
        lines.append("波动：ATR暂无")

    # ③ 计划账一行
    if buy_px is not None and sell_px is not None and stop is not None and buy_px > stop:
        risk = buy_px - stop
        reward = sell_px - buy_px
        if risk > 0 and reward > 0:
            plan_rr = reward / risk
            net_space = (sell_px - buy_px) / buy_px - _ROUND_TRIP_COST_PCT
            lines.append(
                _ledger_one_line(
                    title="计划账",
                    risk=risk,
                    reward=reward,
                    atr=atr,
                    rr=plan_rr,
                    net_space=net_space,
                )
            )
        elif reward <= 0:
            lines.append("计划账：高低未拉开，盈亏比无效")
        else:
            lines.append("计划账：止损无效，盈亏比不算")
    else:
        lines.append("计划账：价位未齐，盈亏比暂无")

    # ④ 现价账一行
    if current is not None and sell_px is not None and stop is not None and current > stop:
        risk_c = current - stop
        reward_c = sell_px - current
        if risk_c > 0 and reward_c > 0:
            rr_c = reward_c / risk_c
            net_c = (sell_px - current) / current - _ROUND_TRIP_COST_PCT
            chase = "偏弱" if rr_c < 1.0 or net_c < 0 else "可看"
            lines.append(
                _ledger_one_line(
                    title="现价账",
                    risk=risk_c,
                    reward=reward_c,
                    atr=atr,
                    rr=rr_c,
                    net_space=net_c,
                    verdict=chase,
                )
            )
        elif reward_c <= 0:
            lines.append("现价账：已近/超过卖点，不宜追")
    else:
        lines.append("现价账：相对止损无效，暂不算")

    return lines


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
    """微信排版：盘面一行 + 买卖价短块；不刷距离/不足。"""
    has_pos = _has_position(plan)
    lines = ["📌 盘面"]

    bits: list[str] = []
    high, low = _quote_day_range(plan)
    if high is not None and low is not None and high >= low:
        bits.append(f"今日{low:.2f}-{high:.2f}")
    amp_pct = _amplitude_pct_display(plan)
    if amp_pct is not None:
        bits.append(f"振幅{amp_pct:.1f}%")
    vol = _volume_label(plan)
    if "放量" in vol:
        bits.append("放量")
    elif "缩量" in vol:
        bits.append("缩量")
    elif "平量" in vol:
        bits.append("平量")
    vwap = numeric_or_none(plan.get("vwap"))
    if vwap is not None and _vwap_rel_text(plan):
        bits.append(f"VWAP{vwap:.2f}")
    if bits:
        lines.append("｜".join(bits))

    if not has_pos:
        lines.append("无底仓 · 不做T召唤")

    lines.append("")
    lines.extend(_build_trade_price_rr_block(plan, buy=buy, sell=sell))
    # 微信不展示「还差x%约N根5m」距离噪音
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
    from trader_shared.t0_config import VOLUME_SHRINK_RATIO, VOLUME_EXPAND_RATIO

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
    """结构/评分参考段（v2）：只展示，不映射为可执行指令。操盘卡里降权。"""
    resonance = plan.get("resonance")
    if not resonance:
        return []

    lights = resonance.get("lights") or {}
    lines: list[str] = []
    score = resonance.get("score")
    # 数据全未达时一行带过，不刷屏
    score_keys = ("ema", "vwap", "box", "volume", "atr")
    all_miss = bool(lights) and all(
        not (lights.get(k) or {}).get("buy") and not (lights.get(k) or {}).get("sell")
        for k in score_keys
        if k in lights
    )
    if score is not None and (score == 0 or all_miss) and _data_thin(plan):
        return ["  评分暂无（分钟线未齐）· 仅供参考，不构成执行指令"]
    if score is not None:
        if score >= 60:
            band = "偏强"
        elif score >= 40:
            band = "中性偏上"
        else:
            band = "偏弱"
        lines.append(
            f"  结构分 {score}/100（{band}）· 仅供结构参考，不构成执行指令"
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
