"""缠论专项结构卡渲染（微信安全；只读引擎薄 view）。

法源：
- B·中剪：docs/plans/chanlun-skill-slim-b-handoff.md
- 旧薄卡：docs/plans/done/chanlun-cd-followup-handoff.md §2.3 / §3
禁止在此模块重算笔或从其他文案补出买卖点；禁止抄威科夫箱体/量度语义。
"""
from __future__ import annotations

from typing import Any


_DIRECTION_LABEL = {
    "up": "向上笔",
    "down": "向下笔",
}
_DIRECTION_ARROW = {
    "up": "↑",
    "down": "↓",
}
_ADJUST_LABEL = {
    "qfq": "前复权",
    "hfq": "后复权",
    "none": "未复权",
    "mixed": "混合",
    "unknown": "未知",
    "mixed/unknown": "混合／未知",
}

# 正式六灯（B 卡满灯竖排）；类一/类二另作观察追加
_FORMAL_LAMPS = ("一类买", "二类买", "三类买", "一类卖", "二类卖", "三类卖")
_FORMAL_BUY = ("一类买", "二类买", "三类买")
_FORMAL_SELL = ("一类卖", "二类卖", "三类卖")
_FORBIDDEN_BUY_WORDS = (
    "可执行",
    "宜买",
    "去买",
    "可低吸",
    "三重共振买",
    "该买了",
    "接近一买",
    "潜在三买",
)


def _fmt_price(value: Any) -> str | None:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return None


# 类一/类二 = 观察档（deep-card §2.3）；正式一类/二类/三类不加。
# 用 startswith「类一」「类二」：一类买/二类买 不会误命中。
_OBSERVE_TYPE_PREFIXES = ("类一", "类二")


def _display_point_type(point_type: str) -> str:
    """展示分层：类一/类二可见面标（观察）；正式一/二/三类原样。"""
    if point_type.startswith(_OBSERVE_TYPE_PREFIXES) and "（观察）" not in point_type:
        return f"{point_type}（观察）"
    return point_type


def _fmt_points(points: Any) -> str:
    """仅展示引擎给出的 type/price；空数组不得推断或手补。"""
    if not isinstance(points, list):
        return "未形成"
    rendered: list[str] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        point_type = str(point.get("type") or "").strip()
        if not point_type:
            continue
        label = _display_point_type(point_type)
        price = _fmt_price(point.get("price"))
        rendered.append(f"{label} {price}" if price else label)
    return "、".join(rendered) if rendered else "未形成"


def _tip_leave_label(view: dict[str, Any]) -> str:
    """C-D4e：笔尖离价降级文案（与 conclusion_block 同源语义）。"""
    tip = str(view.get("tip_leave") or "")
    if tip == "up_left":
        return "高点已离开·向下未成笔"
    if tip == "down_left":
        return "低点已离开·向上未成笔"
    return ""


def _fmt_current_direction(view: dict[str, Any]) -> str:
    demoted = _tip_leave_label(view)
    if demoted:
        return demoted
    direction = str(view.get("current_stroke_direction") or "")
    return _DIRECTION_LABEL.get(direction, "未形成")


def _fmt_recent_directions(view: dict[str, Any]) -> str:
    directions = view.get("recent_stroke_directions")
    if not isinstance(directions, list):
        return "—"
    arrows = [
        _DIRECTION_ARROW[str(direction)]
        for direction in directions
        if str(direction) in _DIRECTION_ARROW
    ]
    return "".join(arrows) if arrows else "—"


def _fmt_structure(view: dict[str, Any]) -> str:
    if not view.get("data_ok") or view.get("timeframe") == "insufficient":
        return "数据不足"
    structure = str(view.get("structure_type") or "").strip()
    return structure if structure and structure != "无结构" else "中枢未成型"


def _fmt_trend(view: dict[str, Any]) -> str:
    if not view.get("data_ok") or view.get("timeframe") == "insufficient":
        return "数据不足"
    demoted = _tip_leave_label(view)
    if demoted:
        return demoted
    return str(view.get("trend_label") or "暂无明确走势")


def _midline_heading(view: dict[str, Any]) -> str:
    timeframe = str(view.get("timeframe") or "insufficient")
    if timeframe == "weekly":
        return "⏱ 中线副读（周）"
    if timeframe == "daily_fallback":
        return "⏱ 中线副读（日线 fallback）"
    return "⏱ 中线副读（数据不足）"


def _view_lines(view: dict[str, Any]) -> list[str]:
    """微信可读：买卖点前置，字段分行；并列仅保留短字段用｜。"""
    stroke_n = int(view.get("stroke_count") or 0)
    # G-K3：中枢=合并后 pivot；窗=引擎 raw zones_count
    pivot_n = int(view.get("pivot_count") if view.get("pivot_count") is not None else (view.get("zones_count") or 0))
    raw_n = int(view.get("zones_count") or 0)
    segs_n = int(view.get("segments_count") or 0)
    return [
        f"  买点：{_fmt_points(view.get('buy_points'))}",
        f"  卖点：{_fmt_points(view.get('sell_points'))}",
        f"  结构：{_fmt_structure(view)}",
        f"  走势：{_fmt_trend(view)}",
        f"  笔：{stroke_n}",
        f"  当前笔：{_fmt_current_direction(view)}",
        f"  近笔：{_fmt_recent_directions(view)}",
        f"  中枢：{pivot_n}｜窗{raw_n}｜段：{segs_n}",
    ]


def _wechat_safe(text: str) -> str:
    """兜底清理外部名称/错误串可能带入的 Markdown 控制符。"""
    return (
        text.replace("**", "")
        .replace("---", "—")
        .replace("|", "｜")
        .replace("#", "＃")
        .replace("*", "＊")
        .replace(">", "＞")
    )


def render_chanlun_card(plan: dict[str, Any]) -> str:
    """渲染日线短线 + 周线中线副读结构卡。"""
    name = str(plan.get("name") or plan.get("target") or "未知")
    code = str(plan.get("code") or "")
    title = f"缠论 — {name}" + (f"（{code}）" if code else "") + "｜短中线结构卡"
    daily_count = int(plan.get("data_bars_daily") or 0)
    weekly_count = int(plan.get("data_bars_weekly") or 0)
    adjust_mode = str(plan.get("adjust_mode") or "unknown").lower()
    adjust_label = _ADJUST_LABEL.get(adjust_mode, adjust_mode or "未知")
    data_note = str(plan.get("data_note") or "日周数据齐")
    short_view = plan.get("short_view") if isinstance(plan.get("short_view"), dict) else {}
    midline_view = (
        plan.get("midline_view") if isinstance(plan.get("midline_view"), dict) else {}
    )

    lines = [title, ""]
    price = _fmt_price(plan.get("price"))
    lines.append("📊 现况")
    if price is not None:
        lines.append(f"  现价：{price}")
    lines.append(f"  取数：日{daily_count}根｜周{weekly_count}根")
    lines.append(f"  复权：{adjust_label}")
    lines.append(f"  说明：{data_note}")
    lines.extend(["", "⚡ 短线（日）"])
    lines.extend(_view_lines(short_view))
    lines.extend(["", _midline_heading(midline_view)])
    lines.extend(_view_lines(midline_view))
    lines.extend(
        [
            "",
            "💬 说明",
            "  本卡只复述缠论引擎结构与买卖点",
            "  中线阶段仍由周线威科夫负责",
        ]
    )
    return _wechat_safe("\n".join(lines))


def _as_view(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _collect_points(view: dict[str, Any]) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """正式 type→价；观察档 (label, price_s) 列表。只读引擎数组。"""
    formal: dict[str, str] = {}
    observe: list[tuple[str, str]] = []
    for key in ("buy_points", "sell_points"):
        points = view.get(key)
        if not isinstance(points, list):
            continue
        for point in points:
            if not isinstance(point, dict):
                continue
            point_type = str(point.get("type") or "").strip()
            if not point_type:
                continue
            price_s = _fmt_price(point.get("price")) or ""
            if point_type in _FORMAL_LAMPS:
                # 同类型多点：保留第一个有价的
                if point_type not in formal or (price_s and not formal[point_type]):
                    formal[point_type] = price_s
            elif point_type.startswith(_OBSERVE_TYPE_PREFIXES):
                label = _display_point_type(point_type)
                observe.append((label, price_s))
    return formal, observe


def _lit_types(view: dict[str, Any]) -> list[str]:
    """快照用：已亮正式 + 观察 type（引擎原文）。"""
    out: list[str] = []
    for key in ("buy_points", "sell_points"):
        points = view.get(key)
        if not isinstance(points, list):
            continue
        for point in points:
            if not isinstance(point, dict):
                continue
            point_type = str(point.get("type") or "").strip()
            if point_type:
                out.append(point_type)
    return out


def _format_lamp_lines(view: dict[str, Any]) -> list[str]:
    formal, observe = _collect_points(view)
    lines: list[str] = []
    for lamp in _FORMAL_LAMPS:
        if lamp in formal:
            price = formal[lamp]
            lines.append(f"● {lamp} {price}".rstrip())
        else:
            lines.append(f"○ {lamp}")
    for label, price in observe:
        lines.append(f"● {label} {price}".rstrip() if price else f"● {label}")
    return lines


def _has_formal(view: dict[str, Any], types: tuple[str, ...]) -> bool:
    formal, _ = _collect_points(view)
    return any(t in formal for t in types)


def _primary_formal_label(view: dict[str, Any]) -> str:
    formal, _ = _collect_points(view)
    for lamp in _FORMAL_LAMPS:
        if lamp in formal:
            price = formal[lamp]
            return f"{lamp} {price}".rstrip() if price else lamp
    return "暂无正式买卖点"


def _view_bias_cn(view: dict[str, Any]) -> str:
    """总览偏向：正式点优先；否则用「大结构内本波」人话，避免「偏空｜上涨趋势」拧句。"""
    if not view.get("data_ok") or view.get("timeframe") == "insufficient":
        return "中性"
    if _has_formal(view, _FORMAL_SELL) and not _has_formal(view, _FORMAL_BUY):
        return "偏空"
    if _has_formal(view, _FORMAL_BUY):
        return "偏多"
    structure = str(view.get("structure_type") or "").strip()
    trend = str(view.get("trend_label") or "").strip()
    direction = str(view.get("current_stroke_direction") or "")
    tip = _tip_leave_label(view)
    # tip / 回调 落在上涨框架里 → 回调偏空（勿裸写偏空｜上涨趋势）
    if tip.startswith("高点") or (
        structure == "上涨趋势" and (trend == "回调段" or direction == "down")
    ):
        return "回调偏空" if structure == "上涨趋势" or tip.startswith("高点") else "偏空"
    if tip.startswith("低点") or (
        structure == "下跌趋势" and (trend == "拉升段" or direction == "up")
    ):
        return "反弹偏多" if structure == "下跌趋势" or tip.startswith("低点") else "偏多"
    # 盘整内：笔向与本波标签冲突时，跟笔向但加「盘整」语境
    if structure == "盘整":
        if direction == "down" or trend == "回调段":
            return "盘整偏空"
        if direction == "up" or trend == "拉升段":
            return "盘整偏多"
    if direction == "up":
        return "偏多"
    if direction == "down":
        return "偏空"
    return "中性"


def _stance_tier(short: dict[str, Any], mid: dict[str, Any]) -> str:
    if not short.get("data_ok") or short.get("timeframe") == "insufficient":
        return "先别做"
    if _has_formal(short, _FORMAL_SELL) and not _has_formal(short, _FORMAL_BUY):
        return "先别做"
    if _has_formal(short, _FORMAL_BUY) and not _tip_leave_label(short):
        return "可盯"
    _ = mid  # 周线副读不抬姿态档，只参与入池
    return "慎做"


def _pool_advice(short: dict[str, Any], mid: dict[str, Any]) -> str:
    if not short.get("data_ok") or short.get("timeframe") == "insufficient":
        return "暂不建议入池（数据不足）"
    short_buy = _has_formal(short, _FORMAL_BUY)
    short_sell = _has_formal(short, _FORMAL_SELL)
    mid_sell_only = _has_formal(mid, _FORMAL_SELL) and not _has_formal(mid, _FORMAL_BUY)
    if short_sell and not short_buy:
        return "结构偏空，暂不建议入池"
    if mid_sell_only and not short_buy:
        return "结构偏空，暂不建议入池"
    formal, _ = _collect_points(short)
    if any(t in formal for t in ("二类买", "三类买")) and not mid_sell_only:
        return "建议入池"
    if "一类买" in formal and not mid_sell_only:
        return "建议入池（日线一类买，待确认）"
    return "暂不建议入池（无正式买点）"


def _wave_vs_stroke_phrase(view: dict[str, Any]) -> str:
    """本波标签与当前笔冲突时，用人话消歧（如拉升段+向下笔→拉升遇阻）。"""
    trend = str(view.get("trend_label") or "").strip()
    direction = str(view.get("current_stroke_direction") or "")
    tip = _tip_leave_label(view)
    if tip:
        return tip
    if trend == "拉升段" and direction == "down":
        return "拉升遇阻"
    if trend == "回调段" and direction == "up":
        return "回调后反弹"
    if trend in ("拉升段", "回调段"):
        return trend
    return trend or "暂无明确走势"


def _structure_wave_phrase(view: dict[str, Any]) -> str:
    """大结构 + 本波合一，避免「上涨趋势 · 回调段」读成两套结论。"""
    if not view.get("data_ok") or view.get("timeframe") == "insufficient":
        return "数据不足"
    structure = _fmt_structure(view)
    if structure == "数据不足":
        return structure
    tip = _tip_leave_label(view)
    trend = str(view.get("trend_label") or "").strip()
    direction = str(view.get("current_stroke_direction") or "")
    wave = _wave_vs_stroke_phrase(view)

    if tip:
        if structure == "上涨趋势":
            return f"上涨趋势内回撤（{tip}）"
        if structure == "下跌趋势":
            return f"下跌趋势内反弹（{tip}）"
        if structure == "盘整":
            return f"盘整·{tip}"
        return tip

    if structure == "上涨趋势" and (
        trend == "回调段" or direction == "down" or wave in ("回调段", "拉升遇阻")
    ):
        return "上涨趋势内回调"
    if structure == "下跌趋势" and (
        trend == "拉升段" or direction == "up" or wave in ("拉升段", "回调后反弹")
    ):
        return "下跌趋势内反弹"
    if structure == "盘整":
        if wave == "拉升遇阻":
            return "盘整·拉升遇阻"
        if wave == "回调后反弹":
            return "盘整·回调后反弹"
        if wave in ("回调段", "拉升段"):
            return f"盘整·{wave}"
        return "盘整"
    if wave and wave != structure:
        return f"{structure} · {wave}"
    return structure or wave or "暂无明确结构"


def _structure_short(view: dict[str, Any]) -> str:
    return _structure_wave_phrase(view)


def _sentence(view: dict[str, Any], *, fallback_tag: bool = False) -> str:
    if not view.get("data_ok") or view.get("timeframe") == "insufficient":
        return "数据不足，仅现价"
    phrase = _structure_wave_phrase(view)
    tip = _tip_leave_label(view)
    parts = [phrase]
    # tip 已写进 phrase 时勿再重复「当前{同一句 tip}」
    if not tip:
        parts.append(f"当前{_fmt_current_direction(view)}")
    else:
        direction = str(view.get("current_stroke_direction") or "")
        if direction in _DIRECTION_LABEL:
            parts.append(f"引擎末笔{_DIRECTION_LABEL[direction]}（仅对照）")
    parts.append(_primary_formal_label(view))
    line = " · ".join(p for p in parts if p)
    if fallback_tag or str(view.get("timeframe") or "") == "daily_fallback":
        if "（日线）" not in line:
            line = f"{line}（日线）"
    return line


def _wave_short(view: dict[str, Any]) -> str:
    """日线本波总览：与周线同构，禁止「拉升段 · 向下笔」拧句。"""
    if not view.get("data_ok") or view.get("timeframe") == "insufficient":
        return "数据不足"
    tip = _tip_leave_label(view)
    if tip:
        return tip
    primary = _primary_formal_label(view)
    wave = _wave_vs_stroke_phrase(view)
    direction = _fmt_current_direction(view)
    if primary != "暂无正式买卖点":
        return f"{primary} · {direction}"
    # 本波名已含方向语义时不再叠「·向下笔」
    if wave in ("拉升遇阻", "回调后反弹"):
        return wave
    return f"{wave} · {direction}"


def _stroke_facts(view: dict[str, Any]) -> str:
    stroke_n = int(view.get("stroke_count") or 0)
    return (
        f"笔：{stroke_n}｜当前笔：{_fmt_current_direction(view)}"
        f"｜近笔：{_fmt_recent_directions(view)}"
    )


def _pivot_facts(view: dict[str, Any]) -> str:
    pivot_n = int(
        view.get("pivot_count")
        if view.get("pivot_count") is not None
        else (view.get("zones_count") or 0)
    )
    raw_n = int(view.get("zones_count") or 0)
    segs_n = int(view.get("segments_count") or 0)
    return f"中枢：{pivot_n}｜窗{raw_n}｜段：{segs_n}"


def _next_formal_focus(view: dict[str, Any]) -> str:
    """下一关注：按一→二→三类买推进；已有买则看更高阶未形成者。"""
    formal, _ = _collect_points(view)
    buy_order = _FORMAL_BUY
    lit_idx = [i for i, lamp in enumerate(buy_order) if lamp in formal]
    if lit_idx:
        nxt = lit_idx[-1] + 1
        if nxt < len(buy_order):
            return f"下一关注：{buy_order[nxt]}未形成"
        return "正式买点已齐，盯笔破坏"
    if _has_formal(view, _FORMAL_SELL):
        return "下一关注：笔破坏或卖点消化"
    return "下一关注：一类买未形成"


def _story_lines(view: dict[str, Any], *, fallback_tag: bool = False) -> dict[str, str]:
    if not view.get("data_ok") or view.get("timeframe") == "insufficient":
        return {
            "now": "数据不足",
            "better": "补足数据后再评估",
            "worse": "数据不足时不引用买卖点",
            "watch": "先补数据",
        }
    now = _sentence(view, fallback_tag=fallback_tag)
    primary = _primary_formal_label(view)
    tip = _tip_leave_label(view)
    better = (
        f"笔结构延续且出现更高阶正式买；现 {primary}"
        if not _has_formal(view, _FORMAL_BUY)
        else f"正式买维持：{primary}；笔未反向破坏"
    )
    worse = (
        tip
        if tip
        else (
            "笔破坏或正式卖亮起"
            if not _has_formal(view, _FORMAL_SELL)
            else f"正式卖在场：{primary}"
        )
    )
    watch = _next_formal_focus(view)
    return {"now": now, "better": better, "worse": worse, "watch": watch}


def format_chanlun_light_change(
    prev: dict[str, Any] | None,
    curr: dict[str, Any],
) -> str:
    """🔔 变化文案。prev 为空 → 首次记录。"""
    if not prev:
        return "首次记录，暂无对比"

    def _codes(entry: dict[str, Any], key: str) -> set[str]:
        vals = entry.get(key) or []
        return {str(x) for x in vals if str(x).strip()}

    prev_d = _codes(prev, "daily_points")
    prev_w = _codes(prev, "weekly_points")
    curr_d = _codes(curr, "daily_points")
    curr_w = _codes(curr, "weekly_points")
    prev_all = prev_d | {f"W:{c}" for c in prev_w}
    curr_all = curr_d | {f"W:{c}" for c in curr_w}

    def _label(token: str) -> str:
        if token.startswith("W:"):
            return f"周{token[2:]}"
        return token

    new_lit = sorted(curr_all - prev_all)
    gone = sorted(prev_all - curr_all)
    parts: list[str] = []
    parts.append("新亮：" + ("、".join(_label(x) for x in new_lit) if new_lit else "无"))
    parts.append("熄灭：" + ("、".join(_label(x) for x in gone) if gone else "无"))
    return "；".join(parts)


def build_chanlun_light_snapshot_entry(plan: dict[str, Any]) -> dict[str, Any]:
    """从 plan 提取灯快照（不写盘）。"""
    from datetime import datetime, timezone

    short = _as_view(plan.get("short_view"))
    mid = _as_view(plan.get("midline_view"))
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "daily_points": _lit_types(short),
        "weekly_points": _lit_types(mid),
    }


def _slim_change_line(change_line: Any) -> str | None:
    """有新亮或熄灭才展示；首次/无变化省略。"""
    text = str(change_line or "").strip()
    if not text or text.startswith("首次记录"):
        return None
    has_new = "新亮：无" not in text and "新亮：" in text
    has_gone = "熄灭：无" not in text and "熄灭：" in text
    if not has_new and not has_gone:
        return None
    # 压缩「仍亮」若存在
    return text


def render_chanlun_slim(plan: dict[str, Any]) -> str:
    """默认 B·中剪卡（--target）。"""
    name = str(plan.get("name") or plan.get("target") or "未知")
    code = str(plan.get("code") or "")
    price_s = _fmt_price(plan.get("price")) or "—"
    title = f"{name}（{code}）｜现价 {price_s}" if code else f"{name}｜现价 {price_s}"

    if plan.get("error") and not plan.get("data_ok", True):
        err = str(plan.get("error") or "数据不足")
        lines = [
            title,
            "周线副读：中性｜数据不足｜先别做",
            "日线本波：数据不足",
            "入池：暂不建议入池（数据不足）",
            "",
            "🔮 推演",
            "  现在",
            "    周线：数据不足",
            f"    日线：{err}",
            "",
            "  若变好",
            "    周线：补足数据后再评估",
            "    日线：补足数据后再评估",
            "",
            "  若变坏",
            "    周线：数据不足时不引用买卖点",
            "    日线：数据不足时不引用买卖点",
            "",
            "  ⭐ 盯",
            "    周线：先补数据",
            "    日线：先补数据",
            "    本卡不下单；出手/分道看 trader；中线阶段看威科夫",
        ]
        return _wechat_safe("\n".join(lines))

    short = _as_view(plan.get("short_view"))
    mid = _as_view(plan.get("midline_view"))
    mid_fallback = str(mid.get("timeframe") or "") == "daily_fallback"
    w_bias = _view_bias_cn(mid)
    stance = _stance_tier(short, mid)
    pool_line = _pool_advice(short, mid)
    w_story = _story_lines(mid, fallback_tag=mid_fallback)
    d_story = _story_lines(short)

    lines: list[str] = [
        title,
        f"周线副读：{w_bias}｜{_structure_short(mid)}｜{stance}",
        f"日线本波：{_wave_short(short)}",
        f"入池：{pool_line}",
        "",
        "🧭 周线 · 结构副读",
        f"  {_sentence(mid, fallback_tag=mid_fallback)}",
        "  灯",
    ]
    for lamp in _format_lamp_lines(mid):
        lines.append(f"  {lamp}")

    lines.extend(
        [
            "",
            "⚡ 日线 · 本波",
            f"  {_sentence(short)}",
            f"  {_stroke_facts(short)}",
            f"  {_pivot_facts(short)}",
            "  灯",
        ]
    )
    for lamp in _format_lamp_lines(short):
        lines.append(f"  {lamp}")

    change = _slim_change_line(plan.get("change_line"))
    if change:
        lines.extend(["", "🔔 变化", f"  {change}"])

    lines.extend(
        [
            "",
            "🔮 推演",
            "  现在",
            f"    周线：{w_story['now']}",
            f"    日线：{d_story['now']}",
            "",
            "  若变好",
            f"    周线：{w_story['better']}",
            f"    日线：{d_story['better']}",
            "",
            "  若变坏",
            f"    周线：{w_story['worse']}",
            f"    日线：{d_story['worse']}",
            "",
            "  ⭐ 盯",
            f"    周线：{w_story['watch']}",
            f"    日线：{d_story['watch']}",
            "    本卡不下单；出手/分道看 trader；中线阶段看威科夫",
        ]
    )

    text = "\n".join(lines)
    for bad in _FORBIDDEN_BUY_WORDS:
        if bad in text:
            text = text.replace(bad, "（结构参考）")
    return _wechat_safe(text)


__all__ = [
    "build_chanlun_light_snapshot_entry",
    "format_chanlun_light_change",
    "render_chanlun_card",
    "render_chanlun_slim",
]
