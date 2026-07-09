"""统一报告渲染模块

提供 3 个公共渲染函数，输出严格遵守微信端格式红线：
- 禁用 # 标题、--- 水平线、** 粗体、| 表格、> 块引用、* / - 列表符
- 首行必须以固定 emoji + 标题开头
- 分节用 emoji + 文本，不用 Markdown 语法
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def render_single(r: dict[str, Any]) -> str:
    """渲染单票分析报告（完整版）。

    输入为 build_report() 返回的 dict，包含价格、均线、融合层、决策区间、
    持仓、筹码、股性、亮点风险等全部字段。
    """
    name = r.get("name", "")
    code = str(r.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
    current = float(r.get("current") or 0)
    change_pct = float(r.get("change_pct") or 0)
    ma_raw = r.get("ma") or r.get("ma_raw") or {}
    low_price = float(r.get("support") or 0)
    stop = float(r.get("stop") or 0)
    confirm = float(r.get("confirm") or 0)
    resistance = float(r.get("resistance") or 0)
    has_position = r.get("has_position", False)
    cost_price = float(r.get("cost_price") or 0)

    lines: list[str] = [
        f"分析报告 — {name}（{code}）",
        "",
        f"现价 {current:.2f}（{change_pct:+.2f}%）",
    ]

    # ── 均线 ──
    ma_parts = []
    for k in ("ma5", "ma10", "ma20", "ma30", "ma250"):
        v = ma_raw.get(k)
        if v and isinstance(v, (int, float)) and v > 0:
            ma_parts.append(f"MA{int(k[2:])}：{v:.2f}")
    if ma_parts:
        lines.append(f"  {' ｜ '.join(ma_parts)}")

    # ── 量能 + 距高低 ──
    volume_ratio_val = float(r.get("volume_ratio") or 0)
    turnover_val = float(r.get("turnover_rate") or 0)
    bars_for_range = r.get("daily_bars") or []
    vol_parts = []
    if volume_ratio_val > 0:
        vol_label = "放量" if volume_ratio_val >= 1.5 else ("缩量" if volume_ratio_val <= 0.7 else "平量")
        vol_parts.append(f"量比{volume_ratio_val:.1f}（{vol_label}）")
    if turnover_val > 0:
        vol_parts.append(f"换手{turnover_val:.1f}%")
    if len(bars_for_range) >= 20 and current > 0:
        highs = [float(b.get("high") or 0) for b in bars_for_range[-20:] if float(b.get("high") or 0) > 0]
        lows = [float(b.get("low") or 0) for b in bars_for_range[-20:] if float(b.get("low") or 0) > 0]
        if highs:
            d = (current - max(highs)) / max(highs) * 100
            vol_parts.append(f"距高{d:+.1f}%" if d < 0 else f"高{d:+.1f}%")
        if lows:
            d = (current - min(lows)) / min(lows) * 100
            vol_parts.append(f"距低{d:+.1f}%" if d > 0 else f"低{d:+.1f}%")
    if vol_parts:
        lines.append(f"  {' ｜ '.join(vol_parts)}")

    # ── 年线警告 ──
    ma250_val = ma_raw.get("ma250")
    if current > 0 and ma250_val and isinstance(ma250_val, (int, float)) and current < ma250_val:
        lines.append(f"  ⚠️ 股价在年线（{ma250_val:.2f}）下方运行，注意风险")

    lines.append("")

    # ── 融合层：阶段 → 动作 ──
    fusion = r.get("fusion") or {}
    fusion_action = str(fusion.get("action") or r.get("fusion_action") or "未知")
    major_stage = str(r.get("major_stage") or "")
    veto = fusion.get("fund_flow_outflow_veto_msg") or ""
    veto_part = f"（{veto}）" if veto else ""

    stage_action_map = {"蓄势": "低吸高抛", "主升": "持股待涨", "派发": "逢高减仓", "衰退": "不碰"}
    _action_word = fusion_action.split("（")[0].split("(")[0].strip() if "（" in fusion_action or "(" in fusion_action else fusion_action
    _real_status = str(r.get("base_status") or "")
    if _real_status in ("暂不碰", "风险回避", "空仓规避"):
        _action_word = _real_status

    if major_stage and major_stage != "None":
        lines.append(f"🎯 {major_stage} → {_action_word}{veto_part}")
    else:
        lines.append(f"🎯 {_action_word}{veto_part}")

    # ── 理论信号行 ──
    fusion_signals = fusion.get("signals_detail") or {}
    _SIGNAL_LABELS = {"chan": "缠论", "momentum": "动量", "wyckoff": "威科夫"}
    _theory_parts = []
    for _key, _label in _SIGNAL_LABELS.items():
        if _key in fusion_signals:
            _sig = fusion_signals[_key]
            if isinstance(_sig, dict):
                _state = str(_sig.get("reason", "") or "").replace(_label, "").strip().lstrip(":").strip()
                _dir = _sig.get("direction", 0)
                _dir_label = "看涨" if _dir > 0 else ("看跌" if _dir < 0 else "中性")
                if not _state or _state == "无明确信号":
                    _state = "无信号"
                _theory_parts.append(f"{_label}:{_state}·{_dir_label}")
    for _tp in _theory_parts:
        lines.append(f"  {_tp}")

    # ── 冲突比 ──
    disagreement = int(fusion.get("disagreement", 0))
    if disagreement > 0 and fusion_signals:
        _bull = sum(1 for v in fusion_signals.values() if isinstance(v, dict) and v.get("direction", 0) > 0)
        _bear = sum(1 for v in fusion_signals.values() if isinstance(v, dict) and v.get("direction", 0) < 0)
        lines.append(f"  {_bull}方看多 vs {_bear}方看空")

    # ── 双状态行 ──
    bs = str(r.get("base_status") or "")
    ts = str(r.get("theory_status") or "")
    if bs and ts and bs != ts:
        lines.extend(["", f"  基础状态：{bs} ｜ 体系结论：{ts}"])
    elif bs:
        lines.extend(["", f"  {bs}"])

    # ── 趋势轨道 ──
    _st_dir = r.get("supertrend_direction")
    _data_partial = r.get("data_status") == "partial"
    if _st_dir:
        _st_emoji = "🟢" if _st_dir == "up" else ("🔴" if _st_dir == "down" else "⚪")
        _st_label = "多头" if _st_dir == "up" else ("空头" if _st_dir == "down" else "中性")
        _st_stop = r.get("supertrend_stop")
        _st_atr = float(r.get("supertrend_atr") or r.get("atr14") or 0)
        _st_vol = r.get("supertrend_vol_level") or ""
        lines.append("")
        lines.append("📊 趋势轨道（参考）")
        if _data_partial:
            lines.append("  ⚠️ 数据不完整，趋势带可能失准")
        if _st_atr and _st_atr > 0:
            lines.append(f"  ATR {_st_atr:.2f}元（{_st_vol}）")
        if _st_stop:
            _dist = (current - _st_stop) / _st_stop * 100 if _st_stop else 0
            lines.append(f"  轨道：{_st_emoji} {_st_label} {_st_stop:.2f}（距现价 {_dist:+.1f}%）— 仅趋势带参考，非止损")

    # ── VWAP ──
    _vwap = r.get("vwap")
    if _vwap:
        _vwap_dev = float(r.get("vwap_dev") or 0)
        _vwap_pos = r.get("vwap_position")
        _vwap_level = r.get("vwap_level") or ""
        _vwap_emoji = "🟢" if _vwap_pos == "above" else "🔴"
        _vwap_sign = "+" if _vwap_dev >= 0 else ""
        lines.append("")
        lines.append("📈 主力成本（VWAP·当日）")
        if _data_partial:
            lines.append("  ⚠️ 数据不完整，VWAP 可能失准")
        lines.append(f"  今日VWAP：{_vwap:.2f}元")
        pos_text = "之上" if _vwap_pos == "above" else "之下"
        lines.append(f"  价格 {_vwap_emoji} 在VWAP{pos_text}（当日{_vwap_level}，{_vwap_sign}{_vwap_dev * 100:.1f}%）")

    # ── 决策区间 ──
    _RESTRICTIVE = frozenset({"暂不碰", "风险回避", "空仓规避", "退场观察"})
    _pos_cap = int(r.get("position_cap") or 0)
    _lz_low = float(r.get("low_zone_lower") or 0)
    _lz_high = float(r.get("low_zone_upper") or 0)
    _take_val = float(r.get("take") or 0)

    lines.append("")
    lines.append("📍 决策")

    if not has_position and bs not in _RESTRICTIVE and _lz_low > 0 and _lz_high > 0:
        lines.append(f"  空仓：在 {_lz_low:.2f}-{_lz_high:.2f}元 试探买 {_pos_cap}%，止损 {stop:.2f}")
    elif has_position and _take_val > 0:
        lines.append(f"  有底仓：反弹 {_take_val:.2f} 冲不动减")

    # 价格阶梯（统一排序）
    all_price_lines: list[tuple[float, str]] = []
    if stop > 0:
        all_price_lines.append((stop, f"  {stop:.2f} 止损（跌破支撑，趋势破坏）"))

    # 试探买
    if low_price > 0:
        all_price_lines.append((low_price, f"  {low_price:.2f} ← 试探买"))

    # 当前价
    if current > 0:
        all_price_lines.append((current, f"  🌟 {current:.2f} 当前位置"))

    # 多周期支撑压力
    key_levels = r.get("key_levels") or {}
    if key_levels:
        _weighted_score = float(r.get("weighted_score") or 0)
        if _weighted_score >= 0.25:
            _lr_action = "持有关注 / 趋势强"
        elif _weighted_score >= 0.1:
            _lr_action = "减仓 20%"
        else:
            _lr_action = "减仓 50% / 趋势弱"

        for kl_key, label, pct in [
            ("long_support", "长线支撑", "加仓至 20%"),
            ("mid_support", "中线支撑", "首次建仓 10%"),
            ("short_support", "短线支撑", "试探买 5%"),
        ]:
            val = float(key_levels.get(kl_key) or 0)
            if val > 0 and val < current:
                all_price_lines.append((val, f"  {val:.2f} ← {label}（{pct}）"))

        for kl_key, label, pct in [
            ("short_resist", "短线压力", "卖 20%"),
            ("mid_resist", "中线压力", "减仓 30%"),
            ("long_resist", "长线压力", _lr_action),
        ]:
            val = float(key_levels.get(kl_key) or 0)
            if val > 0 and val > current:
                all_price_lines.append((val, f"  {val:.2f} → {label}（{pct}）"))

    # Fibonacci 扩展
    fib_ext_1382 = r.get("fib_ext_1382")
    fib_ext_1618 = r.get("fib_ext_1618")
    if fib_ext_1382 and fib_ext_1382 > resistance:
        all_price_lines.append((fib_ext_1382, f"  {fib_ext_1382:.2f} ← 黄金分割138.2%目标"))
    if fib_ext_1618 and fib_ext_1618 > resistance:
        all_price_lines.append((fib_ext_1618, f"  {fib_ext_1618:.2f} ← 黄金分割161.8%目标"))

    # 共振检测
    all_price_lines.sort(key=lambda x: x[0])
    resonance_map: dict[float, list[str]] = {}
    price_counts = {}
    for val, _ in all_price_lines:
        price_counts[val] = price_counts.get(val, 0) + 1
    for val, cnt in price_counts.items():
        if cnt >= 2:
            resonance_map[val] = []

    for val, line in all_price_lines:
        if val in resonance_map:
            suffix = "【双线共振】" if len(resonance_map) <= 5 else "【三线共振】"
            line = line + suffix
        lines.append(line)

    # ── 持仓盈亏 ──
    if has_position and cost_price > 0:
        pnl_pct = (current - cost_price) / cost_price * 100
        pnl_text = f"盈 {pnl_pct:+.1f}%" if pnl_pct >= 0 else f"亏 {abs(pnl_pct):.1f}%"
        fusion_reduce = fusion_action in ("减仓", "空仓/止损", "减1/3 (高位松动)")
        lines.extend(["", f"📌 如果你有持仓（成本 {cost_price:.2f}）"])
        if pnl_pct >= 0:
            if major_stage == "主升":
                lines.append(f"  现在：持有，让利润跑（{pnl_text}）" if not fusion_reduce else f"  现在：持有，但融合层提示{fusion_action}，注意风险（{pnl_text}）")
            elif major_stage == "派发":
                lines.append(f"  现在：减仓，锁定利润（{pnl_text}）")
            else:
                lines.append(f"  现在：融合层提示{fusion_action}，考虑减仓（{pnl_text}）" if fusion_reduce else f"  现在：部分止盈，留底仓等突破（{pnl_text}）")
        else:
            if major_stage == "衰退":
                lines.append(f"  现在：止损，认亏走人（{pnl_text}）")
            elif major_stage == "主升":
                lines.append(f"  现在：持有，主升期大概率会回来（{pnl_text}）")
            else:
                lines.append(f"  现在：持有，不加仓（{pnl_text}）")

    # ── 筹码 ──
    chip_peaks = r.get("chip_peaks") or []
    chip_migration = r.get("chip_migration") or {}
    if chip_peaks:
        sorted_peaks = sorted(chip_peaks, key=lambda x: x.get("price", 0))
        peak_strs = [f"{p.get('price', 0):.2f}" for p in sorted_peaks[:3] if p.get("price", 0) > 0]
        chip_parts = [f"筹码：{' · '.join(peak_strs)}"]
        current_pct = r.get("chip_current_pct")
        if current_pct is not None and current_pct > 50:
            chip_parts.append(f"获利{current_pct:.0f}%")
        warning_text = chip_migration.get("warning_text", "")
        if "搬家" in warning_text:
            chip_parts.append("搬家")
        lines.append(f"  {' ｜ '.join(chip_parts)}")
        if "搬家" in warning_text:
            lines.append(f"  ⚠️ 筹码搬家：{warning_text}")

    # ── 股性与历史回测 ──
    win_rate_data = r.get("win_rate_data")
    if win_rate_data:
        lines.extend(["", "📊 股性与历史回测"])
        buy = win_rate_data.get("buy")
        sell = win_rate_data.get("sell")
        if buy:
            avg_pnl = buy.get("avg_pnl")
            avg_pnl_str = f"{avg_pnl:+.1f}%" if isinstance(avg_pnl, (int, float)) else str(avg_pnl)
            lines.append(f"  买入信号 {buy['count']}次 ｜ {buy['wins']}胜{buy['count'] - buy['wins']}负 ｜ 胜率 {buy['win_rate']}% ｜ 平均 {avg_pnl_str}")
        if sell:
            avg_pnl_s = sell.get("avg_pnl")
            avg_pnl_s_str = f"{avg_pnl_s:+.1f}%" if isinstance(avg_pnl_s, (int, float)) else str(avg_pnl_s)
            lines.append(f"  卖出信号 {sell['count']}次 ｜ {sell['wins']}胜{sell['count'] - sell['wins']}负 ｜ 胜率 {sell['win_rate']}% ｜ 避坑 {avg_pnl_s_str}")
        if win_rate_data.get("sample_warning"):
            lines.append("  ⚠️ 样本不足，仅供参考")

    # ── 亮点 ──
    _mid_support = float(key_levels.get("mid_support") or 0)
    _short_resist = float(key_levels.get("short_resist") or 0)
    if _mid_support > 0 and _mid_support < current:
        _dist_sup = (current - _mid_support) / current * 100
        lines.append(f"\n✅ 亮点：中线支撑 {_mid_support:.2f} 距当前价 {_dist_sup:.0f}%，下跌空间有限")
    elif current > low_price * 1.005:
        lines.append(f"\n✅ 亮点：{current:.2f} 仍站在防守位 {low_price:.2f} 上方")
    elif current >= low_price:
        lines.append(f"\n⚠️ 现价逼近防守位 {low_price:.2f}，随时可能跌破")
    else:
        lines.append(f"\n⚠️ 亮点：暂无亮点，价格已跌破防守位 {low_price:.2f}")

    # ── 风险 ──
    if _short_resist > 0 and _short_resist > current:
        _dist_res = (_short_resist - current) / current * 100
        lines.append(f"⚠️ 风险：短线压力 {_short_resist:.2f} 距当前价仅 {_dist_res:.0f}%，追高风险大")
    elif "出货" in str(chip_migration.get("warning_text", "")):
        lines.append(f"⚠️ 风险：筹码在搬家，主力在出货，警惕继续下跌")
    elif major_stage == "主升":
        lines.append(f"⚠️ 风险：主升期主要风险是回踩 {low_price:.2f} 支撑未守住")
    elif major_stage == "蓄势":
        lines.append(f"⚠️ 风险：突破 {confirm:.2f} 失败将引发回踩，突破前不宜提前介入")
    elif major_stage == "派发":
        lines.append(f"⚠️ 风险：派发期注意破位，跌破 {stop:.2f} 需离场")
    elif major_stage == "衰退":
        lines.append(f"⚠️ 风险：趋势向下，不宜介入")
    else:
        lines.append(f"⚠️ 风险：等信号确认，{confirm:.2f} 未站稳前不宜提前介入")

    # ── 池子状态 ──
    pool_count = r.get("pool_count")
    pool_cap = r.get("pool_cap")
    if pool_count is not None and pool_cap is not None:
        lines.append(f"\n当前池 {pool_count}/{pool_cap}，回复 1 入池")

    return "\n".join(lines)


def render_pool_summary(pool_data: dict[str, Any]) -> str:
    """渲染选股池汇总/排序报告。

    Args:
        pool_data: 选股池数据 dict，需包含:
            - items: list[dict]，每项含 name, code, status, score, current
            - market_level: 大盘环境（可选）
            - updated_at: 更新时间（可选）
    """
    items = pool_data.get("items") or []
    market_level = pool_data.get("market_level") or "未知"
    updated = pool_data.get("updated_at") or datetime.now().strftime("%Y-%m-%d")

    lines = [
        f"选股池 ｜ 大盘{market_level}",
        f"容量 {len(items)}/10 ｜ {updated}",
        "",
    ]

    if not items:
        lines.append("池子为空")
        return "\n".join(lines)

    sorted_items = sorted(items, key=lambda x: float(x.get("score") or 0), reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    for i, item in enumerate(sorted_items):
        name = item.get("name", "")
        code = item.get("code", "")
        score = item.get("score", 0)
        status = item.get("status", "")
        current = item.get("current", 0)
        medal = medals[i] if i < 3 else f" {i + 1}."
        lines.append(f"{medal} {name}（{code}）｜ 评分：{score}")
        lines.append(f"    {status} 现价 {current}")

    return "\n".join(lines)


def render_backtest(results: list[dict[str, Any]] | dict[str, Any]) -> str:
    """渲染回测报告。支持单个 dict 或 list[dict] 输入。"""
    if isinstance(results, dict):
        results = [results]
    if not results:
        return "回测无数据"

    lines = [
        "缠论买卖点回测",
        f"回测日期: {datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]

    for r in results:
        target = r.get("target", "?")
        total = r.get("total_signals", 0)
        error = r.get("error")
        if error:
            lines.append(f"  {target}: {error}")
            continue
        by_type = r.get("by_type", {})
        if not by_type:
            lines.append(f"  {target}: 无信号")
            continue
        lines.append(f"{'─' * 30}")
        lines.append(f"  {target}  |  总信号: {total}")
        for stype in sorted(by_type.keys()):
            s = by_type[stype]
            wr = s.get("win_rate", 0)
            avg_r = s.get("avg_return_pct", 0)
            min_r = s.get("min_return_pct", 0)
            stop_r = s.get("stop_rate", 0)
            icon = "🟢" if wr >= 60 else "🟡" if wr >= 45 else "🔴"
            lines.append(f"  {icon} {stype}: {s['count']}次  胜率{wr}%  均收益{avg_r:+.1f}%  最差{min_r:+.1f}%  止损率{stop_r}%")

    if len(results) > 1:
        type_stats: dict[str, dict] = {}
        for r in results:
            for stype, s in r.get("by_type", {}).items():
                if stype not in type_stats:
                    type_stats[stype] = {"count": 0, "wins": 0, "returns": []}
                type_stats[stype]["count"] += s["count"]
                type_stats[stype]["wins"] += int(s["count"] * s["win_rate"] / 100)
                type_stats[stype]["returns"].append(s["avg_return_pct"])
        lines.extend(["", f"{'─' * 30}", "  汇总"])
        for stype in sorted(type_stats.keys()):
            ts = type_stats[stype]
            wr = round(ts["wins"] / ts["count"] * 100, 1) if ts["count"] > 0 else 0
            avg_r = round(sum(ts["returns"]) / len(ts["returns"]), 2) if ts["returns"] else 0
            icon = "🟢" if wr >= 60 else "🟡" if wr >= 45 else "🔴"
            lines.append(f"  {icon} {stype}: {ts['count']}次  胜率{wr}%  均收益{avg_r:+.1f}%")

    return "\n".join(lines)
