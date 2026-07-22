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
        "confidence": "high" if side_state == "可执行" else "medium",
        "data_status": normalize_t0_data_status(str(plan.get("data_status") or "partial")),
        "trigger": {
            "type": "completed_5m_confirm" if side_state == "可执行" else "watch_price",
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

    # 场景D：双触发同时存在
    if buy_state == "可执行" and sell_state == "可执行":
        lines.append("🚨 应急：低吸高抛同时可执行，先低吸后高抛，T+0锁仓套利")

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
    buy_state = str(plan.get("buy_display_status") or side_display(buy))
    sell_state = str(plan.get("sell_display_status") or side_display(sell))
    buy_obs = str(plan.get("buy_display_obs") or observation_value(buy, "以下"))
    sell_obs = str(plan.get("sell_display_obs") or observation_value(sell, "附近"))

    current_price = numeric_or_none(plan.get('current_price'))
    current_text = "无" if current_price is None else f"{current_price:.2f}"
    big_order = None
    has_tick_data = False
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
        has_tick_data = len(tick_data) > 0
        big_order = analyze_big_orders(bars, tick_data=tick_data, focus_prices=focus_prices, trade_date=trade_date, order_book=(plan.get("data") or {}).get("order_book"))

    from t0_config import TREND_FILTER_EXTREME_ONLY

    current_action = '低吸' if buy_state == '可执行' else '高抛' if sell_state == '可执行' else '不动'

    stop_price = price(numeric_or_none(buy.get('invalid_price')))

    # ── 距触发价距离计算 ──
    distance_lines: list[str] = []
    if current_price is not None:
        buy_obs_price = numeric_or_none(buy.get("observation_price"))
        sell_obs_price = numeric_or_none(sell.get("observation_price"))
        if buy_obs_price is not None and buy_state not in ("可执行", "数据不足", ""):
            gap_pct = (current_price - buy_obs_price) / buy_obs_price
            # 估算5分钟K线数量（假设每根约0.3%振幅）
            est_bars = int(gap_pct / 0.003) if gap_pct > 0 else 0
            if gap_pct > 0.005:
                distance_lines.append(f"低吸还差 {gap_pct*100:.1f}%（约{est_bars}根5m线）")
            elif gap_pct > 0:
                distance_lines.append(f"低吸接近关注价，差 {gap_pct*100:.1f}%")
        if sell_obs_price is not None and sell_state not in ("可执行", "数据不足", ""):
            gap_pct = (sell_obs_price - current_price) / current_price
            est_bars = int(gap_pct / 0.003) if gap_pct > 0 else 0
            if gap_pct > 0.005:
                distance_lines.append(f"高抛还差 {gap_pct*100:.1f}%（约{est_bars}根5m线）")
            elif gap_pct > 0:
                distance_lines.append(f"高抛接近关注价，差 {gap_pct*100:.1f}%")

    # ── 段1: 触发价（多理论参考价位） ──
    trigger_lines = [
        "📌 触发价",
        f"当前：{current_action} ｜ 止损：{stop_price}",
    ]
    _mzones = (plan.get("model") or {}).get("zones") or {}
    _res = plan.get("resonance") or {}

    # 低吸价位
    _cur = numeric_or_none(plan.get("current_price")) or 0
    _zone_buy = _mzones.get("buy_zone", {}).get("main_support")
    _ab_bp_raw = (_res.get("lights") or {}).get("ab", {}).get("buy_price")
    _ab_bp = None
    if _ab_bp_raw and _cur and abs(_ab_bp_raw - _cur) / _cur <= 0.2:
        _ab_bp = _ab_bp_raw
    _wyck_bp = (_res.get("lights") or {}).get("wyckoff", {}).get("buy_price")
    if buy_state == "可执行":
        _exec = numeric_or_none(buy.get("execution_price"))
        _acc = numeric_or_none(buy.get("acceptable_price"))
        if _exec and _acc:
            trigger_lines.append(f"低吸：可执行 {_exec:.2f}～{_acc:.2f}")
        else:
            trigger_lines.append(f"低吸：{buy_state}，{buy_obs}")
    else:
        _parts = []
        if _zone_buy:
            _parts.append(f"价区{_zone_buy:.2f}")
        if _ab_bp:
            _parts.append(f"价格行为{_ab_bp:.2f}")
        if _wyck_bp:
            _parts.append(f"威科夫{_wyck_bp:.2f}")
        _ref_str = "｜".join(_parts) if _parts else "暂无"
        trigger_lines.append(f"低吸：{_ref_str}")

    # 高抛价位
    _zone_sell = _mzones.get("sell_zone", {}).get("main_resistance")
    _ab_sp_raw = (_res.get("lights") or {}).get("ab", {}).get("sell_price")
    _ab_sp = None
    if _ab_sp_raw and _cur and abs(_ab_sp_raw - _cur) / _cur <= 0.2:
        _ab_sp = _ab_sp_raw
    _wyck_sp = (_res.get("lights") or {}).get("wyckoff", {}).get("sell_price")
    if sell_state == "可执行":
        _exec = numeric_or_none(sell.get("execution_price"))
        _acc = numeric_or_none(sell.get("acceptable_price"))
        if _exec and _acc:
            trigger_lines.append(f"高抛：可执行 {_exec:.2f}～{_acc:.2f}")
        else:
            trigger_lines.append(f"高抛：{sell_state}，{sell_obs}")
    else:
        _parts = []
        if _zone_sell:
            _parts.append(f"价区{_zone_sell:.2f}")
        if _ab_sp:
            _parts.append(f"价格行为{_ab_sp:.2f}")
        if _wyck_sp:
            _parts.append(f"威科夫{_wyck_sp:.2f}")
        _ref_str = "｜".join(_parts) if _parts else "暂无"
        trigger_lines.append(f"高抛：{_ref_str}")

    # 止盈价：拆分低吸止盈（高于现价）和高抛止盈（低于现价）
    exit_plan = plan.get("exit_plan") or {}
    exit_items = exit_plan.get("exit_plan") or []
    if exit_items and exit_plan.get("risk_r", 0) > 0 and _cur:
        buy_tp = []  # 低吸止盈（高于现价）
        sell_tp = []  # 高抛止盈（低于现价）
        for item in exit_items:
            p = item.get("price")
            if p is not None:
                if p > _cur:
                    buy_tp.append(f"{p:.2f}")
                else:
                    sell_tp.append(f"{p:.2f}")
        if buy_tp:
            trigger_lines.append(f"低吸止盈：{'｜'.join(buy_tp)}")
        if sell_tp:
            trigger_lines.append(f"高抛止盈：{'｜'.join(sell_tp)}")

    atr_info = plan.get("atr_info") or {}
    level_advice = atr_info.get("level_advice")
    if level_advice:
        trigger_lines.append(f"波动：{level_advice}")
    if distance_lines:
        trigger_lines.extend(distance_lines)

    # ── 段2: 大单异动 ──
    capital_lines = []
    if big_order and big_order.get("events"):
        title = "💰 大单异动" if has_tick_data else "💰 分时估算"
        by_side = big_order.get("by_side") or {}
        buy_info = by_side.get("主动买入") or {}
        sell_info = by_side.get("主动卖出") or {}
        buy_events = [e for e in big_order["events"] if "买入" in str(e.get("side",""))]
        sell_events = [e for e in big_order["events"] if "卖出" in str(e.get("side",""))]
        buy_total = round(buy_info.get("amount_wan") or 0)
        sell_total = round(sell_info.get("amount_wan") or 0)

        if buy_events and sell_events:
            capital_lines.append(f"{title}\n买入 {len(buy_events)}笔 {buy_total}万 ｜ 卖出 {len(sell_events)}笔 {sell_total}万")
        elif buy_events:
            capital_lines.append(f"{title}\n全部买入 {len(buy_events)}笔 +{buy_total}万")
        elif sell_events:
            capital_lines.append(f"{title}\n全部卖出 {len(sell_events)}笔 -{sell_total}万")

        sorted_events = sorted(big_order["events"], key=lambda e: str(e.get("time","")))
        # 只显示 TOP3 最大金额异动，不逐笔罗列
        top_events = sorted(big_order["events"], key=lambda e: abs(e.get("amount_wan") or 0), reverse=True)[:3]
        top_lines = []
        for e in top_events:
            t = str(e.get("time",""))
            amt = e.get("amount_wan") or 0
            side = str(e.get("side",""))
            sign = "+" if "买入" in side else "-"
            top_lines.append(f"  {t} {sign}{amt:.0f}万")
        capital_lines.extend(top_lines)

        net = buy_total - sell_total
        capital_lines.append(f"净流入 {'+' if net >= 0 else ''}{net}万{'，主力偏多' if net > 0 else '，主力偏空' if net < 0 else ''}")
        if not has_tick_data:
            capital_lines.append("（5m分时估算，非真实Tick数据）")

    # ── 段3: 操作建议（盘中动态 + 实时信号） ──
    advice_lines = []
    if order_book_analyze and plan.get("order_book"):
        ob = order_book_analyze(plan["order_book"])
        advice_lines.append(ob["line"])
    # Al Brooks 价格行为摘要
    ab_res = plan.get("ab_result") or {}
    if ab_res:
        _ab_parts = ["价格行为"]
        _ai = ab_res.get("always_in", "neutral")
        if _ai != "neutral":
            _ab_parts.append(f"Always-In{'多' if _ai == 'bull' else '空'}")
        _q = ab_res.get("signal_bar_quality", "none")
        if _q != "none":
            _ab_parts.append(f"信号棒{_q}")
        _hl = (ab_res.get("hl_count") or {}).get("type", "none")
        if _hl != "none":
            _ab_parts.append(_hl)
        if ab_res.get("breakout_mode"):
            _ab_parts.append("突破模式")
        advice_lines.append("  ".join(_ab_parts))
    history_lines = review_lines(plan.get("history"))
    if history_lines and history_lines != ["暂无关键事件。"]:
        advice_lines.extend(history_lines)
    signal_lines = _build_realtime_signal_section(plan)
    if signal_lines:
        # 跳过段内标题行（🔔 实时信号），并入统一「操作建议」段
        advice_lines.extend(signal_lines[1:])

    # ── 段4: 风控提醒 ──
    risk_lines = [
        f"👀 跌破 {stop_price} 止损退出" if buy_state == "可执行" else f"👀 跌破 {stop_price} 后不再低吸"
    ]
    ds = str(plan.get("data_status") or "")
    if ds == "partial":
        risk_lines.append("⚠️ 数据不完整，盘中判断可能不准")
    elif ds == "degraded":
        risk_lines.append("⚠️ 数据不足，盘中判断可能不准")

    # ── 段5: 应急指引 ──
    emergency_lines = _build_emergency_guide(plan, buy, sell, current_price)

    # ── 段5.5: 三重共振状态 ──
    resonance_lines = _build_resonance_section(plan)

    # ── 段6: 降本模式（仅 cost_cut 时显示） ──
    account_lines = _build_account_section(plan)

    # ── 组装输出：执行卡风格 ──
    lines = [
        f"🎯 {plan.get('name','')}（{plan.get('symbol','')}）{current_text}（{pct_text(numeric_or_none(plan.get('current_change_pct')))}）",
    ]

    # 结论：一句话告诉用户做什么
    conclusion = _build_conclusion(plan, buy_state, sell_state)
    lines.append(f"  → {conclusion}")

    # 执行价
    lines.append("")
    lines.append("📌 执行")
    lines.extend(trigger_lines[1:])  # 跳过 "📌 触发价" 标题

    # VWAP（只在距现价±20%内显示）
    vwap = plan.get("vwap")
    if vwap and current_price and abs(vwap - current_price) / current_price <= 0.2:
        lines.append(f"VWAP {vwap:.2f}")

    # 信号状态（一行）
    lines.append("")
    lines.append("🔗 信号")
    resonance_lines_short = _build_resonance_section(plan)
    if resonance_lines_short:
        lines.extend(resonance_lines_short)

    # 失效条件
    failure = _build_failure_conditions(plan, buy, sell, stop_price, buy_state, sell_state)
    if failure:
        lines.append(f"  失效：{failure}")

    # 资金（一行）
    if capital_lines:
        # 只取净流入那行
        for cl in capital_lines:
            if "净流入" in cl:
                lines.append(f"💰 {cl}")
                break

    # 降本模式
    if account_lines:
        lines.extend(account_lines)

    return "\n".join(lines)


def _build_conclusion(plan: dict[str, Any], buy_state: str, sell_state: str) -> str:
    """一句话结论：告诉用户现在该干什么。"""
    resonance = plan.get("resonance") or {}
    buy_green = resonance.get("buy_green", False)
    sell_red = resonance.get("sell_red", False)

    if buy_state == "可执行" and buy_green:
        return "三重共振买 → 可低吸"
    if sell_state == "可执行" and sell_red:
        return "三重共振卖 → 可高抛"
    if buy_state == "可执行" and not buy_green:
        return "触发但未共振 → 等确认再操作"
    if sell_state == "可执行" and not sell_red:
        return "触发但未共振 → 等确认再操作"

    # 未触发
    lights = resonance.get("lights", {})
    buy_count = sum(1 for v in lights.values() if v.get("buy"))
    sell_count = sum(1 for v in lights.values() if v.get("sell"))
    if buy_count >= 2:
        return "部分共振（买）→ 关注，等第三盏灯"
    if sell_count >= 2:
        return "部分共振（卖）→ 关注，等第三盏灯"

    return "暂不操作"


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
    """构建降本模式输出段。无持仓信息时不显示。"""
    acct = plan.get("t0_account")
    if not acct:
        return []
    mode = acct.get("mode", "")
    if mode == "none":
        return []

    lines = ["📉 降本模式"]
    mode_label = {"cost_cut": "cost_cut（先卖后买）", "grid": "grid（标准网格）", "reduce": "reduce（减仓）"}.get(mode, mode)
    lines.append(f"  模式：{mode_label}")

    avg_cost = acct.get("avg_cost", 0)
    new_cost = acct.get("new_cost_estimate")
    if avg_cost > 0 and new_cost and new_cost < avg_cost:
        lines.append(f"  成本 {avg_cost:.2f} → 预估 T 后 {new_cost:.2f}")

    worth = acct.get("worth_t") or {}
    if worth:
        net_pct = worth.get("net_pct", 0)
        min_edge = worth.get("min_edge_pct", 0.8)
        worth_text = "可做" if worth.get("worth") else "不可做"
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


def _build_resonance_section(plan: dict[str, Any]) -> list[str]:
    """构建三重共振状态输出段（红黄绿灯风格）。"""
    resonance = plan.get("resonance")
    if not resonance:
        return []

    lights = resonance.get("lights", {})
    buy_green = resonance.get("buy_green", False)
    sell_red = resonance.get("sell_red", False)

    # 统计亮灯数
    buy_count = sum(1 for v in lights.values() if v.get("buy"))
    sell_count = sum(1 for v in lights.values() if v.get("sell"))
    max_count = max(buy_count, sell_count)

    # ── Al Brooks 价格行为详情 ──
    ab_info = lights.get("ab", {})
    ab_result = plan.get("ab_result") or {}
    if ab_info.get("buy"):
        ab_status = "✅ 买"
    elif ab_info.get("sell"):
        ab_status = "✅ 卖"
    elif not ab_info.get("ok"):
        ab_status = "❓ 无数据"
    else:
        ab_status = "❌ 未亮"
    ab_detail = ab_info.get("reason") or "无信号"

    lines = []
    # Al Brooks 简化详情
    ai = ab_result.get("always_in", "neutral")
    quality = ab_result.get("signal_bar_quality", "none")
    hl = ab_result.get("hl_count") or {}
    hl_type = hl.get("type", "none")

    # 简化文案：只保留方向 + 关键信号
    ab_detail_text = ab_detail
    if ai != "neutral":
        ai_label = "多" if ai == "bull" else "空"
        if quality != "none":
            ab_detail_text = f"{ai_label}头·{quality}信号棒"
        else:
            ab_detail_text = f"{ai_label}头趋势"
    elif quality != "none":
        ab_detail_text = f"{quality}信号棒"

    # Al Brooks 价格行
    ab_price_line = _format_theory_price_line("价格行为", ab_status, ab_info, ab_detail_text)
    lines.append(ab_price_line)

    # ── 威科夫详情 ──
    wyck_info = lights.get("wyckoff", {})
    if wyck_info.get("buy"):
        wyck_status = "✅ 买"
    elif wyck_info.get("sell"):
        wyck_status = "✅ 卖"
    else:
        wyck_status = "❌ 未亮"
    wyck_reason = wyck_info.get("reason") or "无信号"
    wyck_price_line = _format_theory_price_line("威科夫", wyck_status, wyck_info, wyck_reason)
    lines.append(wyck_price_line)

    # ── 动量详情 ──
    mom_info = lights.get("momentum", {})
    if mom_info.get("buy"):
        mom_status = "✅ 买"
    elif mom_info.get("sell"):
        mom_status = "✅ 卖"
    elif not mom_info.get("ok"):
        mom_status = "❓ 无数据"
    else:
        mom_status = "❌ 未亮"
    mom_reason = mom_info.get("reason", "")
    mom_price_line = _format_theory_price_line("动量", mom_status, mom_info, mom_reason)
    lines.append(mom_price_line)

    # ── 各理论检测项诊断 ──
    diag = _build_theory_diagnostics(plan)
    if diag:
        lines.append(diag)

    if buy_green or sell_red:
        lines.append("  🟢 三重共振 → 可执行")
    elif max_count >= 2:
        # 找出没亮的那盏灯
        off = []
        for key, label in [("ab", "价格行为"), ("wyckoff", "威科夫"), ("momentum", "动量")]:
            info = lights.get(key, {})
            if not info.get("buy") and not info.get("sell"):
                off.append(label)
        hint = "等" + "+".join(off) + "确认" if off else "等第三盏灯"
        lines.append(f"  🟡 部分共振 → {hint}")
    else:
        lines.append("  🔴 未共振 → 暂不操作")

    return lines


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


def side_summary(model: dict[str, Any], side: str, trigger_price: Any) -> str:
    raw_status = str(model.get("status") or "")
    side_state = side_status(model)
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
        return "degraded"
    if value in {"complete", "full"}:
        return "full"
    if value in {"fresh", "insufficient", "non_trading", "partial", "degraded"}:
        return value
    return "partial"
