"""统一报告渲染模块

提供 3 个公共渲染函数，输出严格遵守微信端格式红线：
- 禁用 # 标题、--- 水平线、** 粗体、| 表格、> 块引用、* / - 列表符
- 首行必须以固定 emoji + 标题开头
- 分节用 emoji + 文本，不用 Markdown 语法

短中线模板（默认）：render_short_midline
旧模板回退：SHORT_MIDLINE_REPORT=0/false → render_single_legacy
生产入口：final_report.py → render_single
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any


def _short_midline_enabled() -> bool:
    # 优先读 env，其次 config 常量
    env = os.environ.get("SHORT_MIDLINE_REPORT")
    if env is not None:
        return env.lower() in ("true", "1", "yes")
    try:
        from trader_shared.config import SHORT_MIDLINE_REPORT
        return bool(SHORT_MIDLINE_REPORT)
    except Exception:
        return True


def render_single(r: dict[str, Any]) -> str:
    """渲染单票分析报告（生产入口）。

    默认短中线模板；SHORT_MIDLINE_REPORT=false 回退旧模板。
    """
    if _short_midline_enabled():
        return render_short_midline(r)
    return render_single_legacy(r)


def render_short_midline(r: dict[str, Any]) -> str:
    """短中线报告模板（顺序冻结，见 docs/short-midline-report-and-gate-plan.md §1.1）。

    分析报告 — 名（码）｜短中线
    现价 + 阶段动能大盘 + MA
    🎯 结论
    🗳️ 日线三专家 + 日线裁定
    📍 关键价 + 两句亏赚
    🗺 空间参考
    ✅⚠️📌 T0 池
    """
    name = r.get("name", "")
    code = str(r.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
    current = float(r.get("current") or 0)
    change_pct = float(r.get("change_pct") or 0)
    # 优先 ma_raw（数值）；ma 可能是展示用字符串 dict
    ma_raw = r.get("ma_raw") if isinstance(r.get("ma_raw"), dict) else None
    if not ma_raw:
        ma_raw = r.get("ma") if isinstance(r.get("ma"), dict) else {}
    ma_raw = ma_raw or {}

    def _ma_float(key: str) -> float | None:
        v = ma_raw.get(key)
        if v is None or v == "" or v == "--":
            return None
        try:
            f = float(v)
            return f if f > 0 else None
        except (TypeError, ValueError):
            return None

    major_stage = str(r.get("major_stage") or "")
    momentum = str(r.get("short_term_momentum") or "")
    market_env = r.get("market_env") or {}
    regime = ""
    if isinstance(market_env, dict):
        regime = str(market_env.get("level") or "")
    if not regime:
        fusion = r.get("fusion") or {}
        regime = str(fusion.get("regime") or "")

    conclusion = r.get("conclusion") or {}
    key_prices = r.get("key_prices") or {}
    fusion = r.get("fusion") or {}
    fusion_signals = fusion.get("signals_detail") or {}
    daily_ruling = str(
        conclusion.get("daily_ruling")
        or r.get("daily_ruling")
        or "中性，观望"
    )

    lines: list[str] = [
        f"分析报告 — {name}（{code}）｜短中线",
        "",
        f"现价 {current:.2f}（{change_pct:+.2f}%）",
    ]

    # 阶段｜动能｜大盘
    meta_parts = []
    if major_stage and major_stage != "None":
        meta_parts.append(f"阶段 {major_stage}")
    if momentum:
        meta_parts.append(f"动能 {momentum}")
    if regime:
        meta_parts.append(f"大盘 {regime}")
    if meta_parts:
        lines.append(f"  {' ｜ '.join(meta_parts)}")

    # MA：契约要求同一行含 MA20 与 MA250（无值时用 --）
    ma_parts = []
    for k, label in (("ma5", "MA5"), ("ma20", "MA20"), ("ma250", "MA250")):
        fv = _ma_float(k)
        if fv is not None:
            ma_parts.append(f"{label}：{fv:.2f}")
        elif k in ("ma20", "ma250"):
            ma_parts.append(f"{label}：--")
    joined_ma = " ｜ ".join(ma_parts) if ma_parts else "MA20：-- ｜ MA250：--"
    if "MA20" not in joined_ma:
        joined_ma = "MA20：-- ｜ " + joined_ma
    if "MA250" not in joined_ma:
        joined_ma = joined_ma + " ｜ MA250：--"
    lines.append(f"  {joined_ma}")

    # 可选量比
    volume_ratio_val = float(r.get("volume_ratio") or 0)
    turnover_val = float(r.get("turnover_rate") or 0)
    vol_parts = []
    if volume_ratio_val > 0:
        vol_label = "放量" if volume_ratio_val >= 1.5 else ("缩量" if volume_ratio_val <= 0.7 else "平量")
        vol_parts.append(f"量比{volume_ratio_val:.1f}（{vol_label}）")
    if turnover_val > 0:
        vol_parts.append(f"换手{turnover_val:.1f}%")
    if vol_parts:
        lines.append(f"  {' ｜ '.join(vol_parts)}")

    ma250_val = _ma_float("ma250")
    if current > 0 and ma250_val is not None and current < ma250_val:
        lines.append(f"  ⚠️ 股价在年线（{ma250_val:.2f}）下方运行，注意风险")

    # ── 🎯 结论：主中线(四阶段) + 理论(威科夫/缠论旁证) + 短线/出手 ──
    lines.append("")
    lines.append("🎯 结论")
    mid = conclusion.get("midline") or "观察"
    short = conclusion.get("shortline") or "观察"
    execution = conclusion.get("execution") or "现价不买 · 不追"
    reason = conclusion.get("reason") or ""
    this_week = conclusion.get("this_week") or ""
    conflict = conclusion.get("conflict") or ""

    # 主中线：四阶段 + 看法（驱动不变）
    _stage_txt = major_stage if major_stage and major_stage != "None" else "未知"
    lines.append(f"  中线：{_stage_txt} · {mid}")

    # 理论旁证一行并排（不覆盖四阶段；中线缠/威各自独立周K结果）
    try:
        from trader_shared.wyckoff_core import format_wyckoff_oneline
        _wyk_raw = r.get("wyckoff_midline") or r.get("wyckoff")
        if isinstance(_wyk_raw, dict) and "wyckoff" in _wyk_raw:
            _wyk_raw = _wyk_raw.get("wyckoff")
        if not isinstance(_wyk_raw, dict):
            _wyk_raw = {}
        _wyk_line = format_wyckoff_oneline(_wyk_raw, direction=None)
    except Exception:
        _wyk_line = "威科夫：暂无明确信号 · 中性"
    _wyk_body = _wyk_line.replace("威科夫：", "").replace("威科夫:", "").strip()
    _wyk_compact = _wyk_body.replace(" · ", "·").replace(" ·", "·").replace("· ", "·")

    try:
        from trader_shared.chan_core import format_chanlun_theory_line
        # 严格用中线缠结果，禁止回退到日线 fusion 顶背驰冒充中线
        _chan_mid = r.get("chanlun_midline")
        if _chan_mid is None:
            _chan_compact = "数据不足·中性"
        else:
            _chan_compact = format_chanlun_theory_line(_chan_mid)
    except Exception:
        _chan_compact = "数据不足·中性"
    lines.append(f"  理论：威科夫 {_wyk_compact} ｜ 缠论 {_chan_compact}")

    lines.append(f"  短线：{short}")
    # 出手 + 原因并一行，避免两行说同一件事
    if reason and reason not in execution:
        lines.append(f"  出手：{execution}（{reason}）")
    else:
        lines.append(f"  出手：{execution}")
    if conflict:
        lines.append(f"  说明：{conflict}")

    # ── 🗳️ 短线专家（日线缠信号 + 动能；理论区已有结构/威科夫）──
    lines.append("")
    lines.append("🗳️ 短线专家")
    # 短线缠论：事件信号（与理论区结构行区分）
    _csig2 = fusion_signals.get("chan") if isinstance(fusion_signals.get("chan"), dict) else {}
    if _csig2:
        _st2 = str(_csig2.get("reason") or "").replace("缠论", "").strip().lstrip(":：").strip() or "无信号"
        _cd2 = _csig2.get("direction", 0)
        _dl2 = "看涨" if _cd2 and int(_cd2) > 0 else ("看跌" if _cd2 and int(_cd2) < 0 else "中性")
        lines.append(f"  缠论：{_st2} · {_dl2}")
    else:
        lines.append("  缠论：暂无信号 · 中性")
    _msig = fusion_signals.get("momentum") if isinstance(fusion_signals.get("momentum"), dict) else {}
    if _msig:
        _mst = str(_msig.get("reason") or "").replace("动量", "").replace("动能", "").strip().lstrip(":：").strip() or "无信号"
        _md = _msig.get("direction", 0)
        _mdl = "看涨" if _md and int(_md) > 0 else ("看跌" if _md and int(_md) < 0 else "中性")
        lines.append(f"  动能：{_mst} · {_mdl}")
    else:
        lines.append("  动能：暂无信号 · 中性")
    lines.append(f"  短线裁定：{daily_ruling}")

    # ── 📍 关键价（买卖点始终输出）──
    stop_sell = key_prices.get("stop_sell") or r.get("stop")
    buy_low = key_prices.get("buy_zone_low")
    buy_high = key_prices.get("buy_zone_high")
    buy_ref = key_prices.get("buy_ref")
    short_low = key_prices.get("short_sell_low")
    short_high = key_prices.get("short_sell_high")
    swing_sell = key_prices.get("swing_sell")
    far_sell = key_prices.get("far_sell")

    # 回退：无 key_prices 时从 report 原始字段拼
    if not buy_ref:
        support = float(r.get("support") or 0)
        if support > 0:
            buy_ref = support
            buy_low = buy_low or support
            buy_high = buy_high or round(support * 1.005, 2)
    if not stop_sell:
        stop_sell = float(r.get("stop") or 0) or None
    if not short_high and not short_low:
        confirm = float(r.get("confirm") or 0)
        if confirm > 0:
            short_low = short_high = confirm
    if not swing_sell:
        swing_sell = float(r.get("resistance") or 0) or None

    lines.append("")
    lines.append("📍 关键价")
    if stop_sell:
        lines.append(f"  止损卖点 {float(stop_sell):.2f}")
    else:
        lines.append("  止损卖点 未定义")
    if buy_low and buy_high:
        lines.append(f"  买点区 {float(buy_low):.2f}-{float(buy_high):.2f}")
    elif buy_ref:
        lines.append(f"  买点区 {float(buy_ref):.2f}")
    else:
        lines.append("  买点区 数据不足")
    if current > 0:
        lines.append(f"  🌟 现价 {current:.2f}")
    if short_low and short_high:
        if float(short_low) == float(short_high):
            lines.append(f"  短线卖点区 {float(short_low):.2f}")
        else:
            lines.append(f"  短线卖点区 {float(short_low):.2f}-{float(short_high):.2f}")
    if swing_sell:
        lines.append(f"  波段卖点区 {float(swing_sell):.2f}")

    lines.append("")
    line_buy = key_prices.get("line_buy") or ""
    line_chase = key_prices.get("line_chase") or ""
    if line_buy:
        lines.append(f"  {line_buy}")
    elif buy_ref and stop_sell:
        # 最低限度两句，保证含「买」
        risk = max(0.0, float(buy_ref) - float(stop_sell))
        tgt = float(short_high or short_low or swing_sell or buy_ref)
        rew = max(0.0, tgt - float(buy_ref))
        lines.append(f"  {float(buy_ref):.2f} 买：亏约 {risk:.1f} / 赚约 {rew:.1f}（远看 {rew:.1f}）")
    if line_chase:
        lines.append(f"  {line_chase}")
    elif current > 0 and stop_sell:
        risk2 = max(0.0, current - float(stop_sell))
        tgt = float(short_high or short_low or swing_sell or current)
        rew2 = max(0.0, tgt - current)
        lines.append(f"  {current:.2f} 追：亏约 {risk2:.1f} / 赚约 {rew2:.1f} → 不追")

    # ── 🗺 空间参考：10/60/120 支撑地图，不用卖点冒充 ──
    lines.append("")
    lines.append("🗺 空间参考（不指挥下单）")
    key_levels = r.get("key_levels") or {}
    near = key_prices.get("space_near") or key_levels.get("short_support") or r.get("support")
    mid_p = key_prices.get("space_mid") or key_levels.get("mid_support")
    far = key_prices.get("space_far") or key_levels.get("long_support")
    space_parts = []
    if near and float(near) > 0:
        space_parts.append(f"近端支撑 {float(near):.2f}")
    if mid_p and float(mid_p) > 0:
        space_parts.append(f"波段支撑 {float(mid_p):.2f}")
    if far and float(far) > 0:
        space_parts.append(f"远端支撑 {float(far):.2f}")
    if space_parts:
        lines.append(f"  {' ｜ '.join(space_parts)}")
    else:
        lines.append("  数据不足")

    # ── 亮点 / 风险：对齐短中线叙事 ──
    support = float(r.get("support") or 0)
    confirm = float(r.get("confirm") or 0)
    _short_resist = float(
        key_prices.get("swing_sell")
        or key_levels.get("short_resist")
        or 0
    )
    stop_v = float(stop_sell or 0)

    lines.append("")
    if major_stage and any(k in major_stage for k in ("蓄势", "主升")) and "派发" not in major_stage and "衰退" not in major_stage:
        lines.append(f"✅ 亮点：阶段 {major_stage}，中线故事未到派发/衰退")
    elif support > 0 and current > support * 1.005:
        lines.append(f"✅ 亮点：现价仍在支撑 {support:.2f} 上方")
    else:
        lines.append("✅ 亮点：先看关键价与出手，不单看远支撑")

    if "不追" in execution or "不买" in execution:
        if stop_v > 0 and _short_resist > current > 0:
            lines.append(f"⚠️ 风险：现价不宜追；止损看 {stop_v:.2f}，上方压力约 {_short_resist:.2f}")
        else:
            lines.append("⚠️ 风险：现价不宜追，等回买点")
    elif major_stage and "派发" in major_stage:
        lines.append(f"⚠️ 风险：派发期注意破位" + (f"，跌破 {stop_v:.2f} 需离场" if stop_v else ""))
    elif major_stage and "衰退" in major_stage:
        lines.append("⚠️ 风险：趋势向下，不宜介入")
    elif _short_resist > current > 0:
        _dist_res = (_short_resist - current) / current * 100
        lines.append(f"⚠️ 风险：上方压力 {_short_resist:.2f} 距现价约 {_dist_res:.0f}%")
    else:
        lines.append("⚠️ 风险：未站稳前不提前加仓")

    # ── 本周只做（唯一）+ T0 ──
    if this_week:
        lines.append(f"📌 本周只做：{this_week}")

    has_position = bool(r.get("has_position"))
    no_new = any(k in execution for k in ("不买", "不追", "不新开", "观望"))
    if not has_position and no_new:
        lines.append("T0：无底仓，不启用（与出手一致，不新开）")
    else:
        t0_ref = r.get("t0_ref") or {}
        t0_buy = float(t0_ref.get("low_buy") or buy_low or support or 0)
        t0_sell = float(t0_ref.get("high_sell") or swing_sell or short_high or confirm or 0)
        # 有仓才给高低点；无仓但允许挂单时给买点参考
        t0_parts = []
        if has_position:
            if t0_buy > 0:
                t0_parts.append(f"低吸参考 {t0_buy:.2f}")
            if t0_sell > 0:
                t0_parts.append(f"高抛参考 {t0_sell:.2f}")
            lines.append(f"T0：{' ｜ '.join(t0_parts)}" if t0_parts else "T0：有底仓，按关键价做短线")
        elif t0_buy > 0:
            lines.append(f"T0：仅观察；计划买点约 {t0_buy:.2f}（未放行不下手）")
        else:
            lines.append("T0：观察关键价即可")

    pool_count = r.get("pool_count")
    pool_cap = r.get("pool_cap")
    if pool_count is not None and pool_cap is not None:
        lines.append(f"当前池 {pool_count}/{pool_cap}，回复 1 入池")

    return "\n".join(lines)


def render_single_legacy(r: dict[str, Any]) -> str:
    """旧版单票分析报告（SHORT_MIDLINE_REPORT=false 时回退）。"""
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
    for _key, _label in (("chan", "缠论"), ("momentum", "动量")):
        if _key not in fusion_signals:
            continue
        _sig = fusion_signals[_key]
        if not isinstance(_sig, dict):
            continue
        _state = str(_sig.get("reason", "") or "").replace(_label, "").strip().lstrip(":").strip()
        _dir = _sig.get("direction", 0)
        _dir_label = "看涨" if _dir > 0 else ("看跌" if _dir < 0 else "中性")
        if not _state or _state == "无明确信号":
            _state = "无信号"
        lines.append(f"  {_label}:{_state}·{_dir_label}")

    if "wyckoff" in fusion_signals or r.get("wyckoff"):
        try:
            from trader_shared.wyckoff_core import format_wyckoff_oneline
            _w_sig = fusion_signals.get("wyckoff") if isinstance(fusion_signals.get("wyckoff"), dict) else {}
            _w_dir = _w_sig.get("direction") if _w_sig else None
            _wyk_raw = r.get("wyckoff")
            if isinstance(_wyk_raw, dict) and "wyckoff" in _wyk_raw:
                _wyk_raw = _wyk_raw.get("wyckoff")
            lines.append(f"  {format_wyckoff_oneline(_wyk_raw if isinstance(_wyk_raw, dict) else {}, direction=_w_dir)}")
        except Exception:
            _sig = fusion_signals.get("wyckoff") if isinstance(fusion_signals.get("wyckoff"), dict) else {}
            _dir = _sig.get("direction", 0) if _sig else 0
            _dl = "偏多" if _dir > 0 else ("偏空" if _dir < 0 else "中性")
            lines.append(f"  威科夫：暂无明确信号 · {_dl}")

    disagreement = int(fusion.get("disagreement", 0))
    if disagreement > 0 and fusion_signals:
        _bull = sum(1 for v in fusion_signals.values() if isinstance(v, dict) and v.get("direction", 0) > 0)
        _bear = sum(1 for v in fusion_signals.values() if isinstance(v, dict) and v.get("direction", 0) < 0)
        lines.append(f"  {_bull}方看多 vs {_bear}方看空")

    bs = str(r.get("base_status") or "")
    ts = str(r.get("theory_status") or "")
    if bs and ts and bs != ts:
        lines.extend(["", f"  基础状态：{bs} ｜ 体系结论：{ts}"])
    elif bs:
        lines.extend(["", f"  {bs}"])

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

    all_price_lines: list[tuple[float, str]] = []
    if stop > 0:
        all_price_lines.append((stop, f"  {stop:.2f} 止损（跌破支撑，趋势破坏）"))
    if low_price > 0:
        all_price_lines.append((low_price, f"  {low_price:.2f} ← 试探买"))
    if current > 0:
        all_price_lines.append((current, f"  🌟 {current:.2f} 当前位置"))

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

    all_price_lines.sort(key=lambda x: x[0])
    for val, line in all_price_lines:
        lines.append(line)

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

    win_rate_data = r.get("win_rate_data")
    if win_rate_data:
        lines.extend(["", "📊 股性与历史回测"])
        buy = win_rate_data.get("buy")
        if buy:
            avg_pnl = buy.get("avg_pnl")
            avg_pnl_str = f"{avg_pnl:+.1f}%" if isinstance(avg_pnl, (int, float)) else str(avg_pnl)
            lines.append(f"  买入信号 {buy['count']}次 ｜ {buy['wins']}胜{buy['count'] - buy['wins']}负 ｜ 胜率 {buy['win_rate']}% ｜ 平均 {avg_pnl_str}")

    _mid_support = float(key_levels.get("mid_support") or 0)
    _short_resist = float(key_levels.get("short_resist") or 0)
    if _mid_support > 0 and _mid_support < current:
        _dist_sup = (current - _mid_support) / current * 100
        lines.append(f"\n✅ 亮点：中线支撑 {_mid_support:.2f} 距当前价 {_dist_sup:.0f}%，下跌空间有限")
    elif current > low_price * 1.005:
        lines.append(f"\n✅ 亮点：{current:.2f} 仍站在防守位 {low_price:.2f} 上方")
    else:
        lines.append(f"\n⚠️ 亮点：暂无亮点，价格已跌破防守位 {low_price:.2f}")

    if _short_resist > 0 and _short_resist > current:
        _dist_res = (_short_resist - current) / current * 100
        lines.append(f"⚠️ 风险：短线压力 {_short_resist:.2f} 距当前价仅 {_dist_res:.0f}%，追高风险大")
    elif major_stage == "衰退":
        lines.append("⚠️ 风险：趋势向下，不宜介入")
    else:
        lines.append(f"⚠️ 风险：等信号确认，{confirm:.2f} 未站稳前不宜提前介入")

    pool_count = r.get("pool_count")
    pool_cap = r.get("pool_cap")
    if pool_count is not None and pool_cap is not None:
        lines.append(f"\n当前池 {pool_count}/{pool_cap}，回复 1 入池")

    return "\n".join(lines)


def render_pool_summary(pool_data: dict[str, Any]) -> str:
    """渲染选股池汇总/排序报告。"""
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
