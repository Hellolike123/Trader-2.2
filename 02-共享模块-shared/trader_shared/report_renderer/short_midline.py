"""短中线双轨报告渲染（实现本体）。"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from trader_shared.report_renderer._helpers import _reformat_mid_line, _short_midline_enabled

# 行业短名：电气设备→电气；其余去常见后缀 / 别名
_INDUSTRY_SHORT_ALIAS: dict[str, str] = {
    "电气设备": "电气",
    "股份制银行": "银行",
    "国有大行": "大行",
    "城商行": "城商",
}
_INDUSTRY_SUFFIXES = ("设备", "制造", "制品", "材料", "工程", "服务", "产业", "股份")


def _short_industry_name(name: str) -> str:
    s = str(name or "").replace("(A股)", "").replace("(A)", "").strip()
    if not s:
        return s
    if s in _INDUSTRY_SHORT_ALIAS:
        return _INDUSTRY_SHORT_ALIAS[s]
    for suf in _INDUSTRY_SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf) + 1:
            return s[: -len(suf)]
    return s


# 引擎无买卖点时，浪型/fusion 不得夹带买点与下单词（C-D3）
_CHAN_POINT_CLAIM_RE = re.compile(
    r"(?:关注|接近|潜在)?"
    r"(?:类)?[一二三](?:类)?[买卖]"
    r"|可低吸|宜买|可执行|该买了|三重共振买"
)
def _sanitize_chan_display_text(
    text: str,
    *,
    allow_bottom_div: bool = False,
    allow_top_div: bool = False,
) -> str:
    """洗掉买/卖点宣称与下单词；背驰词仅按引擎实际方向放行。"""
    raw = str(text or "").strip()
    if not raw:
        return raw
    ban_parts = [_CHAN_POINT_CLAIM_RE.pattern]
    if not allow_bottom_div:
        ban_parts.append(r"底背驰")
    if not allow_top_div:
        ban_parts.append(r"顶背驰")
    claim_re = re.compile("|".join(ban_parts))
    chunks: list[str] = []
    for part in re.split(r"\s*[·｜|]\s*", raw):
        piece = part.strip()
        if not piece:
            continue
        cleaned = claim_re.sub("", piece).strip(" ·｜|，,")
        if cleaned and not claim_re.search(cleaned):
            if cleaned in ("关注", "接近", "潜在", "注意"):
                continue
            chunks.append(cleaned)
        elif cleaned:
            chunks.append(cleaned)
    return " · ".join(chunks)


def _compact_short_structure_line(line: str) -> str:
    """短线结构行压缩：最多保留「主信号 · 注 · 方向」三段，避免浪型堆叠难扫读。"""
    raw = str(line or "").strip()
    if not raw:
        return raw

    tag = ""
    for t in ("（同级）", "（本周期）"):
        if raw.endswith(t):
            tag = t
            raw = raw[: -len(t)].rstrip()
            break
    parts = [p.strip() for p in raw.split("·") if p.strip()]
    if len(parts) <= 3:
        body = " · ".join(parts)
        if tag and tag not in body:
            body = f"{body}{tag}"
        return body

    _dirs = {"看涨", "看跌", "中性"}
    _nop = {"暂无买卖点", "暂无信号"}
    dirs = [p for p in parts if p in _dirs]
    nops = [p for p in parts if p in _nop]
    nest = [
        p
        for p in parts
        if p.endswith("✓") or p.endswith("✗") or p == "未确认" or re.match(r"^\d+m", p)
    ]
    rest = [p for p in parts if p not in _dirs and p not in _nop and p not in nest]

    # 同类「回调*」只留一条
    deduped: list[str] = []
    saw_pull = False
    for p in rest:
        if "回调" in p:
            if saw_pull:
                continue
            saw_pull = True
        deduped.append(p)
    # 有背驰/买卖点主词时优先它，丢掉浪型旁枝（拉升趋势中等）
    _sig_keys = ("背驰", "一买", "二买", "三买", "一卖", "二卖", "三卖", "类一", "类二")
    _has_sig = any(any(k in p for k in _sig_keys) for p in deduped)
    if _has_sig:
        rest = [p for p in deduped if any(k in p for k in _sig_keys) or p in ("抛压减轻", "上攻乏力", "低点抬高", "突破中枢", "高点降低", "柱弱确认", "回踩偏弱")][:2]
    else:
        _prio = ("盘整", "线段", "背驰", "拉升", "下跌", "中枢", "趋势")
        ranked = sorted(
            enumerate(deduped),
            key=lambda iv: (0 if any(k in iv[1] for k in _prio) else 1, iv[0]),
        )
        rest = [p for _, p in ranked[:2]]

    out: list[str] = []
    out.extend(rest)
    if dirs:
        out.append(dirs[0])
    out.extend(nest[:1])  # 区间套最多留一个
    body = " · ".join(out) if out else (nops[0] if nops else raw)
    if nops and nops[0] not in body:
        body = f"{body}（{nops[0]}）" if body else nops[0]
    if tag and tag not in body:
        body = f"{body}{tag}"
    return body


def _short_fund_display(vsig: dict[str, Any]) -> str:
    """资金行短文案：取主句、压「近5日主力累计*」前缀，避免截成「价量近…」。"""
    reason = str(vsig.get("reason") or vsig.get("vp_reason") or "").strip() or "中性"
    reason = re.sub(r"（资金未取到）", "", reason)
    reason = re.sub(r"资金未取到", "", reason)
    primary = reason.split("；")[0].strip()
    primary = re.sub(r"近5日主力累计流出", "主力5日流出", primary)
    primary = re.sub(r"近5日主力累计流入", "主力5日流入", primary)
    primary = re.sub(r"\s{2,}", " ", primary).strip(" ·｜|")
    if len(primary) > 28:
        primary = re.sub(r"（占比[^）]*）", "", primary).strip()
    if len(primary) > 28:
        primary = primary[:26] + "…"
    return primary or "中性"


def render_short_midline(r: dict[str, Any]) -> str:
    """短中线报告模板（docs/mid-short-dual-track-plan.md §0.1）。

    meta → 🧭 中线 → ⚡ 短线 → 说明 → 📌/T0/池
    B3C 阶段+看法并列；B2A 无 🗺、🌟 仅短线。
    """
    name = r.get("name", "")
    code = str(r.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
    current = float(r.get("current") or 0)
    change_pct = float(r.get("change_pct") or 0)
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

    # major_stage 不进面板「阶段：」（日线四阶段仅门控/池）；阶段行见 conclusion.stage_line
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
    mid_key_prices = r.get("mid_key_prices") or {}
    fusion = r.get("fusion") or {}
    fusion_signals = fusion.get("signals_detail") or {}
    daily_ruling = str(
        conclusion.get("daily_ruling")
        or r.get("daily_ruling")
        or "中性，观望"
    )

    ma20_v = _ma_float("ma20")
    ma250_v = _ma_float("ma250")
    _ma20_text = f"{ma20_v:.2f}" if ma20_v else "--"
    _ma250_text = f"{ma250_v:.2f}" if ma250_v else "--"
    _ma250_warn = " ⚠️下方" if (current > 0 and ma250_v and current < ma250_v) else ""

    lines: list[str] = [
        f"分析报告 — {name}（{code}）｜短中线",
        "",
    ]

    # GATE 1 / 防幻觉：非 full 必须在标题后立刻标数据完备度
    _ds = str(r.get("data_status") or "").lower()
    if _ds in ("partial", "degraded", "failed"):
        _miss = r.get("missing_sources") or []
        if isinstance(_miss, (list, tuple)) and _miss:
            _miss_txt = "、".join(str(x) for x in _miss if x)
            lines.append(f"⚠️ 数据不完整（缺：{_miss_txt}），建议仅供参考")
        elif _ds == "partial":
            lines.append("⚠️ 数据不完整，建议仅供参考")
        else:
            lines.append(f"⚠️ 数据不完整（{_ds}），仅基础行情参考")
        lines.append("")

    lines.append(
        f"现价 {current:.2f}（{change_pct:+.2f}%）｜MA20 {_ma20_text}｜MA250 {_ma250_text}{_ma250_warn}"
    )

    # 盘中诚实标注：实时价已锚定，但策略判定基于截至该日收盘的真实日线
    # （合成 bar 不再掺入 bars，避免 volume=0 等假数据污染策略计算）
    _intraday_as_of = r.get("intraday_as_of")
    if _intraday_as_of:
        lines.append(f"  ⏱ 盘中：实时价已锚定 · 策略判定基于截至 {_intraday_as_of} 收盘")

    # meta 纯 D：动能｜板块指数涨跌｜行业短名涨跌｜个股（不写正常/偏弱、不写跑赢）
    # 阶段主展示在 🧭；环境档仍跟板块指数算，仅内部逻辑用，meta 不露
    meta_parts = []
    if momentum:
        meta_parts.append(f"综合动能 {momentum}")

    _market_env_data = r.get("market_env") if isinstance(r.get("market_env"), dict) else {}
    _mkt_chg = _market_env_data.get("change_pct")
    _bars_mkt = _market_env_data.get("bars") or []
    _last_date = str(_bars_mkt[-1].get("date") if _bars_mkt else "").strip()
    _bars_stale = bool(_market_env_data.get("bars_stale"))
    _idx_label = str(_market_env_data.get("index_label") or "").strip()
    if not _idx_label:
        try:
            from trader_shared.market_env import resolve_board_index

            _sym = str(r.get("symbol") or code or "")
            _idx_label = resolve_board_index(_sym)[1]
        except Exception:
            _idx_label = "指数"
    if _bars_stale and _last_date:
        meta_parts.append(f"{_idx_label} ⚠️暂停于{_last_date[-5:]}")
    elif _mkt_chg is not None:
        try:
            meta_parts.append(f"{_idx_label} {float(_mkt_chg):+.2f}%")
        except (TypeError, ValueError):
            meta_parts.append(_idx_label)
    elif regime or _idx_label:
        # 无涨跌幅时仍标板块名（离线 mock）；不写正常/偏弱
        meta_parts.append(_idx_label)

    _ext_sec = r.get("extend_sector") or {}
    if isinstance(_ext_sec, dict) and _ext_sec.get("status") == "正常":
        _sec_name = str(_ext_sec.get("sector_name") or _ext_sec.get("industry") or "").strip()
        _sec_chg = _ext_sec.get("sector_change_pct")
        if _sec_name:
            _short_ind = _short_industry_name(_sec_name)
            if isinstance(_sec_chg, (int, float)):
                meta_parts.append(f"{_short_ind} {float(_sec_chg):+.2f}%")
            else:
                meta_parts.append(_short_ind)
    if change_pct is not None:
        try:
            meta_parts.append(f"个股 {float(change_pct):+.2f}%")
        except (TypeError, ValueError):
            pass

    if meta_parts:
        lines.append(f"  {' ｜ '.join(meta_parts)}")

    volume_ratio_val = float(r.get("volume_ratio") or 0)
    turnover_val = float(r.get("turnover_rate") or 0)
    vol_parts = []
    if volume_ratio_val > 0:
        vol_label = "放量" if volume_ratio_val >= 1.5 else ("缩量" if volume_ratio_val <= 0.7 else "平量")
        vol_parts.append(f"量比{volume_ratio_val:.1f}（{vol_label}）")
    if turnover_val > 0:
        vol_parts.append(f"换手{turnover_val:.1f}%")
    # 调整天数并入量价行
    _bars = r.get("daily_bars") or []
    if len(_bars) >= 20 and current > 0:
        _recent = _bars[-20:]
        _high20 = max((float(b.get("high") or 0)) for b in _recent)
        if _high20 > 0:
            _days_from_high = 0
            for _b in reversed(_recent):
                if (float(_b.get("high") or 0)) >= _high20 - 0.001:
                    break
                _days_from_high += 1
            if _days_from_high == 0:
                vol_parts.append("创新高")
            else:
                vol_parts.append(f"调整{_days_from_high}天")

    # ATR 复权口径并入量价行（日线 ATR 依赖 OHLC 尺度，前复权/未复权不可混读）
    _atr_adj = str(r.get("atr_adjust") or "").strip().lower()
    _atr_adj_label = {
        "qfq": "前复权",
        "hfq": "后复权",
        "none": "未复权",
    }.get(_atr_adj)
    if _atr_adj_label:
        _atr14 = r.get("atr14")
        try:
            _atr14_f = float(_atr14) if _atr14 is not None else None
        except (TypeError, ValueError):
            _atr14_f = None
        if _atr14_f is not None and _atr14_f > 0:
            vol_parts.append(f"ATR14 {_atr14_f:.2f}（{_atr_adj_label}）")
        else:
            vol_parts.append(f"ATR口径 {_atr_adj_label}")

    if vol_parts:
        lines.append(f"  {' ｜ '.join(vol_parts)}")

    # 行业/个股已并入上方 meta（纯 D）；不再单独「行业：…｜跑赢…」行

    # 概念题材
    _ext_concept = r.get("extend_concept") or {}
    if isinstance(_ext_concept, dict) and (_ext_concept.get("status") == "正常" or _ext_concept.get("concept_list")):
        _c_list = _ext_concept.get("concept_list") or []
        _c_chgs = _ext_concept.get("concept_change_pct") or []
        _concept_parts = []
        for _c_name, _c_chg in zip(_c_list, _c_chgs):
            _c_chg_str = f"{_c_chg:+.2f}%" if isinstance(_c_chg, (int, float)) else "--"
            _concept_parts.append(f"{_c_name}（涨幅 {_c_chg_str}）")
        if _concept_parts:
            lines.append(f"  概念题材：{' ｜ '.join(_concept_parts[:4])}")

    # 资金面
    _ext_north = r.get("extend_northbound") or {}
    _ext_margin = r.get("extend_margin") or {}
    _has_north = isinstance(_ext_north, dict) and _ext_north.get("status") == "正常"
    _has_margin = isinstance(_ext_margin, dict) and _ext_margin.get("status") == "正常"
    if _has_north or _has_margin:
        _north_part = ""
        if _has_north:
            _net = _ext_north.get("north_net_flow_wan")
            _5d = _ext_north.get("north_flow_5d_wan")
            def _fmt_flow(val):
                if val is None: return "--"
                if abs(val) >= 10000: return f"{val/10000:.2f}亿"
                return f"{val:.2f}万"
            _north_part = f"北向净流入 {_fmt_flow(_net)}（近5日 {_fmt_flow(_5d)}）"
        _margin_part = ""
        if _has_margin:
            _bal = _ext_margin.get("margin_balance_wan")
            _buy = _ext_margin.get("margin_buy_wan") or 0.0
            _sell = _ext_margin.get("margin_sell_wan") or 0.0
            _net_buy = _buy - _sell
            def _fmt_flow(val):
                if val is None: return "--"
                if abs(val) >= 10000: return f"{val/10000:.2f}亿"
                return f"{val:.2f}万"
            _margin_part = f"融资余额 {_fmt_flow(_bal)}（本日净买入 {_fmt_flow(_net_buy)}）"
        _cap_parts = []
        if _north_part:
            _cap_parts.append(_north_part)
        if _margin_part:
            _cap_parts.append(_margin_part)
        if _cap_parts:
            lines.append(f"  资金面：{' ｜ '.join(_cap_parts)}")

    mid = conclusion.get("midline") or "中线观察"
    short = conclusion.get("shortline") or "观察"
    execution = conclusion.get("execution") or "现价不买 · 不追"
    # 阶段 4：主叙事听 decision_view（不推荐则压偏买出手）
    try:
        from trader_shared.decision_view import apply_decision_to_execution

        execution = apply_decision_to_execution(execution, r)
    except Exception:
        pass
    reason = conclusion.get("reason") or ""
    this_week = conclusion.get("this_week") or ""
    conflict = conclusion.get("conflict") or ""
    # M1：阶段行只听中线定论 stage_line；禁日线 major_stage 冒充
    stage_line = str(conclusion.get("stage_line") or "").strip()
    if stage_line == "None":
        stage_line = ""

    # ── 🧭 中线（B3C）──
    lines.append("")
    lines.append("🧭 中线")

    # 阶段 + 中线偏多/偏空标签（合并"看法"行）
    _stage_line = str(stage_line or '未知')
    _mid = str(conclusion.get("midline") or "").strip()
    if _mid and _mid != "中线观察":
        # 提取方向标签（偏多/偏空）和短因
        _tag = ""
        if any(k in _mid for k in ("可跟踪", "趋势未坏", "结构偏多", "看涨")):
            _tag = "偏多"
        elif any(k in _mid for k in ("慎跟", "偏空", "暂缓", "信号打架", "破坏")):
            _tag = "偏空"
        # 提取短因（去掉标点，取前8字）
        _short = _mid.replace("·", "").replace("，", "").replace("。", "").split("（")[0].strip()[:10]
        if _tag:
            _stage_line = f"{_stage_line} · {_tag}（{_short}）"
    lines.append(f"  阶段：{_stage_line}")

    # 定论：威科夫中线 + 缠论中线 合成注记（各自独立输出已在下方威科夫/缠论段渲染）
    _midline_note = str(
        conclusion.get("midline_verdict_note")
        or (r.get("midline_verdict") or {}).get("note")
        or ""
    ).strip()
    if _midline_note:
        lines.append(f"  定论：{_midline_note}")

    # 仓位衔接：结构看好但仓位为0时，加桥接说明
    _suggested_pct = r.get("suggested_pct")
    try:
        _sp = int(_suggested_pct) if _suggested_pct is not None else None
    except (TypeError, ValueError):
        _sp = None

    # 威科夫中线：报告边界只经 wyckoff_view（周线独占，禁止回退日线）
    try:
        from trader_shared.wyckoff_view import format_midline_display
        _wyk_raw = r.get("wyckoff_midline")
        if isinstance(_wyk_raw, dict) and "wyckoff" in _wyk_raw:
            _wyk_raw = _wyk_raw.get("wyckoff")
        if not isinstance(_wyk_raw, dict):
            _wyk_raw = {}
        _wyk_line = format_midline_display(
            _wyk_raw,
            symbol=str(r.get("ts_code") or r.get("code") or ""),
            direction=None,
        )
    except Exception:
        _wyk_line = "威科夫：数据不足 · 中性"
    # 已是「威科夫：…」完整行
    if not str(_wyk_line).startswith("威科夫"):
        _wyk_line = f"威科夫：{_wyk_line}"
    lines.append(f"  {_wyk_line}")
    # 中线量度目标：周线 P&F（与短线日线分开算）
    try:
        from trader_shared.wyckoff_view import format_cause_effect_display
        _src_m = r.get("wyckoff_midline")
        if isinstance(_src_m, dict) and isinstance(_src_m.get("wyckoff"), dict):
            _src_m = _src_m["wyckoff"]
        _ce_mid = format_cause_effect_display(_src_m if isinstance(_src_m, dict) else {})
        if _ce_mid:
            lines.append(f"  {_ce_mid}")
    except Exception:
        pass

    try:
        from trader_shared.chan_core import format_chanlun_theory_line
        from trader_shared.chan_discipline import needs_same_level_tag, append_same_level_tag
        _chan_mid = r.get("chanlun_midline")
        if _chan_mid is None:
            _chan_compact = "数据不足·中性"
        else:
            _chan_compact = format_chanlun_theory_line(_chan_mid)
        _chan_compact = append_same_level_tag(
            _chan_compact, needs_same_level_tag(_chan_mid, text=_chan_compact)
        )
    except Exception:
        _chan_compact = "数据不足·中性"

    # 缠论行：合并浪型（状态+信号）+ 方向
    _wave_mid = str(conclusion.get("wave_label_mid") or "").strip()
    # 结构不足以支撑方向判断时，禁止从 trend_label 强叠看涨/看跌
    # （历史曾产出「笔数不足 · 看跌 · 无法判断」式矛盾）。
    _insufficient_struct = any(
        k in _wave_mid
        for k in (
            "无法判断", "笔数不足", "无明确结构", "数据不足",
            "先观望", "中枢未成型", "线段不足", "结构待确认",
        )
    )

    # 方向/点类型与 resolve_chanlun_primary 同源（禁再手写一套卖买优先级）
    _chan_dir_mid = ""
    _chan_point_type = ""  # 买卖点类型名，如"一类买""类二买"等
    _allow_bottom_div = False
    _allow_top_div = False
    _mid_strokes: list = []
    try:
        from trader_shared.chan_core import unwrap_chan

        _mid_chan = unwrap_chan(r.get("chanlun_midline")) or {}
        _mid_strokes = [
            s for s in (_mid_chan.get("strokes") or []) if isinstance(s, dict)
        ]
        _mid_div = (
            _mid_chan.get("divergence")
            if isinstance(_mid_chan.get("divergence"), dict)
            else {}
        )
        _allow_bottom_div = bool(_mid_div.get("bottom_divergence"))
        _allow_top_div = bool(_mid_div.get("top_divergence"))
    except Exception:
        _mid_strokes = []
    if not _insufficient_struct:
        try:
            from trader_shared.chan_core import resolve_chanlun_primary

            _prim = resolve_chanlun_primary(r.get("chanlun_midline"))
            _pd = int(_prim.get("direction") or 0)
            if _pd < 0:
                _chan_dir_mid = "看跌"
            elif _pd > 0:
                _chan_dir_mid = "看涨"
            if _prim.get("status") == "point":
                _chan_point_type = str(
                    _prim.get("type_raw") or _prim.get("type_short") or ""
                ).strip()
            # primary 背驰类型再校准放行方向（防 divergence 字典缺失）
            if _prim.get("status") == "divergence":
                _tr = str(_prim.get("type_raw") or "")
                if "底" in _tr:
                    _allow_bottom_div = True
                if "顶" in _tr:
                    _allow_top_div = True
        except Exception:
            pass

    # C-D3：浪型文案始终洗掉买/卖点宣称与下单词（引擎点改由 _chan_point_type 注入）；
    # 背驰词按引擎实际方向放行（有顶背驰不得残留底背驰，反之亦然）。
    if _wave_mid:
        _wave_mid = _sanitize_chan_display_text(
            _wave_mid,
            allow_bottom_div=_allow_bottom_div,
            allow_top_div=_allow_top_div,
        )

    # C-D4e：中线浪型路径也须接笔尖离价闸（与 conclusion_block / Skill 同源）
    try:
        from trader_shared.conclusion_block import _stroke_tip_left_against

        _tip_mid = _stroke_tip_left_against(_mid_strokes, float(current or 0))
        if _tip_mid == "up_left":
            _wave_mid = "高点已离开·向下未成笔"
            _chan_dir_mid = ""
            _chan_point_type = ""
            _insufficient_struct = False
        elif _tip_mid == "down_left":
            _wave_mid = "低点已离开·向上未成笔"
            _chan_dir_mid = ""
            _chan_point_type = ""
            _insufficient_struct = False
    except Exception:
        pass

    if _wave_mid:
        if _chan_dir_mid:
            # 拆分浪型：状态 · 信号 → 状态 · [买卖点] · 方向 · 信号
            _wave_parts = _wave_mid.split(" · ", 1)
            _wave_state = _wave_parts[0]
            _wave_sig = _wave_parts[1] if len(_wave_parts) > 1 else ""
            # 去矛盾：顶/底背驰同框时只保留与已解析方向一致者；卖点行不挂底背驰
            if "顶背驰" in _wave_sig and "底背驰" in _wave_sig:
                if _chan_dir_mid == "看跌":
                    _wave_sig = "顶背驰"
                elif _chan_dir_mid == "看涨":
                    _wave_sig = "底背驰"
                else:
                    _wave_sig = ""
            if _chan_dir_mid == "看跌" and "底背驰" in _wave_sig:
                _wave_sig = (
                    _wave_sig.replace("｜底背驰", "")
                    .replace("底背驰｜", "")
                    .replace("底背驰", "")
                    .strip("｜ ·")
                )
            if _chan_dir_mid == "看涨" and "顶背驰" in _wave_sig:
                _wave_sig = (
                    _wave_sig.replace("｜顶背驰", "")
                    .replace("顶背驰｜", "")
                    .replace("顶背驰", "")
                    .strip("｜ ·")
                )
            _point_part = f" · {_chan_point_type}" if _chan_point_type else ""
            if _wave_sig:
                _chan_display = f"{_wave_state}{_point_part} · {_chan_dir_mid} · {_wave_sig}"
            else:
                _chan_display = f"{_wave_state}{_point_part} · {_chan_dir_mid}"
        else:
            # 结构不足且无方向：浪型里已有「先观望/中性」则原样；否则补「先观望」（可执行立场）
            if _insufficient_struct:
                if any(k in _wave_mid for k in ("观望", "中性")):
                    _chan_display = _wave_mid
                else:
                    _chan_display = f"{_wave_mid} · 先观望"
            else:
                _chan_display = _wave_mid
    else:
        _chan_display = _chan_compact
    _chan_mid_inner = _chan_mid
    if isinstance(_chan_mid_inner, dict) and isinstance(_chan_mid_inner.get("chanlun"), dict):
        _chan_mid_inner = _chan_mid_inner["chanlun"]
    _chan_mid_tf = (
        str(_chan_mid_inner.get("timeframe") or "").strip()
        if isinstance(_chan_mid_inner, dict)
        else ""
    )
    if _chan_mid_tf == "daily_fallback" and "日线" not in _chan_display:
        _chan_display = f"{_chan_display}（日线）"
    lines.append(f"  缠论：{_chan_display}")

    # 位置灯（筹码峰：下方成本 / 上方套牢 / 搬家）— 只展示，不进 fusion
    _pos_mid = ""
    try:
        from trader_shared.chip_core import format_chip_position_light
        _pos_mid = format_chip_position_light(
            current,
            r.get("chip_peaks") or [],
            r.get("chip_migration") if isinstance(r.get("chip_migration"), dict) else None,
            r.get("chip_current_pct") if isinstance(r.get("chip_current_pct"), (int, float)) else None,
        )
        if _pos_mid:
            lines.append(f"  {_pos_mid}")
    except Exception:
        _pos_mid = ""

    # 附：股东（背景，不抢位置灯）
    _ext_fund = r.get("extend_fundamental") or {}
    _sh = _ext_fund.get("shareholder") or {}
    if isinstance(_sh, dict) and _sh.get("status") and _sh.get("status") != "数据不足":
        _sh_chg = _sh.get("change_pct") or 0.0
        _sh_status = _sh.get("status")
        lines.append(f"  附：股东户数较上期 {_sh_chg:+.2f}%（{_sh_status}）")

    # 业绩预期
    _eps_data = _ext_fund.get("consensus_eps") or {}
    _eps_rows = _eps_data.get("rows") or []
    if isinstance(_eps_rows, list) and _eps_rows:
        _eps_26 = None
        _eps_27 = None
        _count_26 = "--"
        _count_27 = "--"
        for _row in _eps_rows:
            _year = str(_row.get("year", ""))
            _avg = str(_row.get("avg_eps", ""))
            _cnt = str(_row.get("count", ""))
            if "2026" in _year or "26" in _year:
                _eps_26 = _avg
                _count_26 = _cnt
            elif "2027" in _year or "27" in _year:
                _eps_27 = _avg
                _count_27 = _cnt
        if _eps_26 or _eps_27:
            _eps_parts = []
            if _eps_26:
                _eps_parts.append(f"26年均值{_eps_26}元")
            if _eps_27:
                _eps_parts.append(f"27年均值{_eps_27}元")
            _cnt_val = _count_27 if _count_27 != "--" else _count_26
            _cnt_str = f"（{_cnt_val}家机构预测）" if _cnt_val != "--" else ""
            lines.append(f"  业绩预期：{' ｜ '.join(_eps_parts)}{_cnt_str}")

    # 中线关键价（按价格升序排列）
    lines.append("")
    lines.append("  关键价（中线）")

    # 收集中线价位，按价格排序
    _mid_items: list[tuple[float, str]] = []
    _mid_fields = [
        ("line_life", "生命线"), ("line_pullback", "回踩区"),
        ("line_golden_buy", "黄金买点"), ("line_resist", "压力位"),
        ("line_target", "目标位"),
    ]
    for _key, _name in _mid_fields:
        _line = _reformat_mid_line(mid_key_prices.get(_key) or "")
        if not _line:
            continue
        _m = re.match(r"([\d.]+)", _line)
        if _m:
            _mid_items.append((float(_m.group(1)), _line))

    # 添加 MA 参考位（年线优先，其次 MA20）
    _ma250_v = _ma_float("ma250")
    _ma20_v = _ma_float("ma20")
    if _ma250_v and _ma250_v > 0:
        _lbl = "年线支撑" if current > _ma250_v else "年线压力"
        _mid_items.append((_ma250_v, f"{_ma250_v:.2f} MA250（{_lbl}）"))
    if _ma20_v and _ma20_v > 0 and abs(_ma20_v - (_ma250_v or 0)) > 0.5:
        _lbl = "中线压力" if current < _ma20_v else "中线支撑"
        _mid_items.append((_ma20_v, f"{_ma20_v:.2f} MA20（{_lbl}）"))

    # 按价格排序
    _mid_items.sort(key=lambda x: x[0])

    # 中线关键价插入现价锚点（无 🌟；🌟 仅短线关键价）
    if current > 0:
        _ins = False
        for _i, (p, _) in enumerate(_mid_items):
            if p > current:
                _mid_items.insert(_i, (current, f"现价 {current:.2f}"))
                _ins = True
                break
        if not _ins:
            _mid_items.append((current, f"现价 {current:.2f}"))

    # 输出带 % 距离标注
    for _p, _text in _mid_items:
        if "现价" in _text:
            lines.append(f"    {_text}")
        else:
            _dist_pct = (_p - current) / current * 100 if current > 0 else 0.0
            _dist_str = f"{_dist_pct:+.0f}%" if abs(_dist_pct) >= 1 else f"{_dist_pct:+.1f}%"
            # 如果是区间（如 61.18-72.60），计算上下界的 %
            _range_m = re.match(r"([\d.]+)-([\d.]+)\s", _text)
            if _range_m:
                _hi = float(_range_m.group(2))
                _hi_pct = (_hi - current) / current * 100 if current > 0 else 0.0
                _hi_str = f"{_hi_pct:+.0f}%" if abs(_hi_pct) >= 1 else f"{_hi_pct:+.1f}%"
                _dist_str = f"{_dist_str}~{_hi_str}"
            # 在首个（前插入 % 距离
            _insert_at = _text.find("（")
            if _insert_at > 0:
                _text = _text[:_insert_at] + f"（{_dist_str} · " + _text[_insert_at + 1:]
            else:
                _text = f"{_text}（{_dist_str}）"
            lines.append(f"    {_text}")
    if not _mid_items:
        lines.append("    数据不足")

    # ── ⚡ 短线 A 版：结构 → 状态 → 动能｜资金 → 动作 → 失效 ──
    lines.append("")
    lines.append("⚡ 短线")

    _disc = r.get("discipline") if isinstance(r.get("discipline"), dict) else {}
    _cap_t = _disc.get("suggested_pct_cap")
    # 全绿才保留试探类；否则强制观察语义
    _all_green = False
    _cl2 = _disc.get("entry_checklist") if isinstance(_disc.get("entry_checklist"), dict) else {}
    if _cl2:
        _all_green = bool(_cl2.get("all_green"))
    if not _all_green and any(k in execution for k in ("试探", "买点挂", "可按买")):
        execution = "现价不买 · 不追"
        if reason and "清单" not in reason:
            reason = (reason + "，清单未全绿") if reason else "清单未全绿，不新开"
    # 精简 reason：多个原因时只取前 2 个，总长限 30 字
    if reason:
        _parts = [p.strip() for p in re.split(r"[，,；;]", reason) if p.strip()]
        if len(_parts) > 2:
            reason = "，".join(_parts[:2])
        if len(reason) > 30:
            reason = reason[:28] + "…"

    # 1) 结构：缠论类型优先
    _csig2 = fusion_signals.get("chan") if isinstance(fusion_signals.get("chan"), dict) else {}
    _wave = str(conclusion.get("wave_label") or "").strip()
    try:
        from trader_shared.chan_core import format_chanlun_short_light
        _chan_src = r.get("chanlun") or r.get("chan")
        _chan_daily = r.get("chanlun_daily")
        _chan_daily_inner = _chan_daily
        if isinstance(_chan_daily_inner, dict) and isinstance(
            _chan_daily_inner.get("chanlun"), dict
        ):
            _chan_daily_inner = _chan_daily_inner["chanlun"]
        if isinstance(_chan_daily_inner, dict) and (
            _chan_daily_inner.get("data_ok") is False
            or _chan_daily_inner.get("timeframe") == "insufficient"
        ):
            # 不足/失败必须越过旧 fusion-only 兼容槽，原样进入最终面板。
            _chan_src = _chan_daily
        _chan_line = format_chanlun_short_light(
            _chan_src,
            fusion_chan=_csig2 or None,
            wave_label=_wave,
        )
    except Exception:
        # C-D3c/d：异常兜底 fail-closed，禁止把 fusion reason/下单词灌进面板
        _chan_line = "暂无信号 · 中性"
    # 与中线同构：学说点名「缠论：」「威科夫：」
    lines.append(f"  缠论：{_compact_short_structure_line(_chan_line)}")

    # 1b) 买点生命周期（L1 展示；挂在缠论下）
    _life = r.get("buy_point_lifecycle") if isinstance(r.get("buy_point_lifecycle"), dict) else {}
    _life_line = str(_life.get("display_line") or "").strip()
    if _life_line:
        lines.append(f"  {_life_line}")

    def _unwrap_wyk_daily(raw: object) -> dict:
        if not isinstance(raw, dict):
            return {}
        if "wyckoff" in raw and isinstance(raw.get("wyckoff"), dict):
            return raw["wyckoff"]  # type: ignore[index]
        return raw

    _wyk_daily_u: dict = {}
    _src_d = r.get("wyckoff_daily")
    _wyk_daily_u = _unwrap_wyk_daily(_src_d)
    if not _wyk_daily_u:
        _fb_d = _unwrap_wyk_daily(r.get("wyckoff"))
        if _fb_d.get("timeframe") != "weekly":
            _wyk_daily_u = _fb_d

    # 1c) 威科夫：日线只对照（标签固定「威科夫：」，禁止「日线阶段：」；不进背景岗/出手）
    try:
        from trader_shared.wyckoff_view import format_daily_phase_display

        _phase_d = format_daily_phase_display(
            _wyk_daily_u or None,
            symbol=str(r.get("ts_code") or r.get("code") or ""),
        )
        _phase_body = str(_phase_d).strip()
        # 兼容旧前缀；面板只出「威科夫：」
        for _pfx in ("日线阶段：", "威科夫："):
            if _phase_body.startswith(_pfx):
                _phase_body = _phase_body[len(_pfx):].strip()
                break
        lines.append(f"  威科夫：{_phase_body or '数据不足 · 仅对照'}")
    except Exception:
        lines.append("  威科夫：数据不足 · 仅对照")
    # 短线量度目标：日线 P&F（与中线周线分开算）
    try:
        from trader_shared.wyckoff_view import format_cause_effect_display
        _ce_d = format_cause_effect_display(_wyk_daily_u)
        if _ce_d:
            lines.append(f"  {_ce_d}")
    except Exception:
        pass

    # 2) 事件：日线威科夫事件灯（仅有真实事件时输出；暂无事件省略）
    try:
        from trader_shared.wyckoff_view import format_event_display

        if _wyk_daily_u:
            _ev = format_event_display(
                _wyk_daily_u, symbol=str(r.get("ts_code") or r.get("code") or "")
            )
            # 统一标签「事件：」（format 内可能仍是「状态：/事件：」）
            if _ev.startswith("状态："):
                _ev = "事件：" + _ev[len("状态："):]
            elif _ev.startswith("事件："):
                pass
            else:
                _ev = f"事件：{_ev}"
            # 去掉「主句（复述注）」长括号，保留灯码 + 主句 + 方向
            _ev = re.sub(r"(· [^·（]{2,16})（[^）]{6,}）", r"\1", _ev)
            _ev = re.sub(r"\s*·\s*", " · ", _ev)
            _ev = re.sub(r"\s{2,}", " ", _ev).strip()
            # 空事件不占行
            if "暂无事件" not in _ev and "数据不足" not in _ev:
                lines.append(f"  {_ev}")
    except Exception:
        pass

    # 2b) 位置灯（筹码峰）— 与中线相同则省略，避免双抄
    try:
        from trader_shared.chip_core import format_chip_position_light
        _pos_s = format_chip_position_light(
            current,
            r.get("chip_peaks") or [],
            r.get("chip_migration") if isinstance(r.get("chip_migration"), dict) else None,
            r.get("chip_current_pct") if isinstance(r.get("chip_current_pct"), (int, float)) else None,
        )
        if _pos_s and _pos_s != _pos_mid:
            lines.append(f"  {_pos_s}")
    except Exception:
        pass

    # 3) 动能 / 资金分行（微信窄屏一长行会糊成一团）
    _msig = fusion_signals.get("momentum") if isinstance(fusion_signals.get("momentum"), dict) else {}
    if _msig:
        _mst = str(_msig.get("reason") or "").strip().lstrip(":：").strip() or "无信号"
        if len(_mst) > 28:
            _mst = _mst[:26] + "…"
    else:
        _mst = "暂无信号"

    _vsig = fusion_signals.get("vpf") if isinstance(fusion_signals.get("vpf"), dict) else {}
    if _vsig:
        _vst = _short_fund_display(_vsig)
        _veto = str(fusion.get("fund_flow_outflow_veto_msg") or "").strip()
        if _veto:
            _days_m = re.search(r"连续\s*(\d+)\s*日", _veto)
            if _days_m:
                _vst = f"{_vst} · 连{_days_m.group(1)}日流出"
            elif len(_veto) <= 16:
                _vst = f"{_vst} · {_veto}"
    else:
        _vst = "暂无信号"
    lines.append(f"  动能：{_mst}")
    lines.append(f"  资金：{_vst}")

    # 信号分歧：结构 vs 动能
    _chan_dir2 = int(_csig2.get("direction", 0)) if _csig2 else 0
    _mom_dir2 = int(_msig.get("direction", 0)) if _msig else 0
    if _chan_dir2 * _mom_dir2 < 0:
        _c_label = "看多" if _chan_dir2 > 0 else "看空"
        _m_label = "看多" if _mom_dir2 > 0 else "看空"
        lines.append(f"  ⚠️ 信号分歧：结构{_c_label} vs 动能{_m_label} → 以不新开为主")

    # 阶段 4：决策块（空行分隔，扫读：看盘 ↑ / 能不能做 ↓）
    lines.append("")
    try:
        from trader_shared.decision_view import format_decision_narrative_lines

        for _nl in format_decision_narrative_lines(r):
            if _nl and _nl not in lines:
                lines.append(_nl)
    except Exception:
        pass

    # 4) 动作：主计划一行；原因过长则另起「原因：」避免动作行糊死
    _confirm_v = float(r.get("confirm") or 0)
    _wait_bits: list[str] = []
    _is_hold_off = any(k in execution for k in ("不买", "观望", "不追", "不新开", "空仓"))
    if _is_hold_off:
        _action_main = "不新开"
        if _confirm_v > 0 and _confirm_v > current:
            _wait_bits.append(f"等站稳 {_confirm_v:.2f}")
        elif "不追" in execution:
            _wait_bits.append("不追现价")
    elif any(k in execution for k in ("试探", "买点挂", "可按买", "半仓", "增持")):
        _action_main = execution.replace(" · ", " · ").strip() or "可试探"
        if len(_action_main) > 22:
            _action_main = _action_main[:20] + "…"
    else:
        _action_main = execution.strip() or "观察"
        if len(_action_main) > 22:
            _action_main = _action_main[:20] + "…"

    _action_parts = [_action_main]
    _action_parts.extend(_wait_bits)
    if _cap_t is not None:
        _action_parts.append(f"仓 {_cap_t}%")
    # 亏赚/不划算类原因一律另起，动作行只留「做什么」
    _reason_line = ""
    if reason and reason not in _action_main and not any(reason in p for p in _action_parts):
        if any(k in reason for k in ("亏", "赚", "不划算", "偏冲高", "置信")) or len(
            " · ".join(_action_parts + [reason])
        ) > 28:
            _reason_line = reason
        else:
            _action_parts.append(reason)
    lines.append(f"  动作：{' · '.join(_action_parts)}")
    if _reason_line:
        lines.append(f"  原因：{_reason_line}")

    # 5) 破位线（有仓/盯盘看；无仓=计划作废线，不是今天必卖指令）
    _gate = r.get("mistery_gate") if isinstance(r.get("mistery_gate"), dict) else {}
    _inv = str(_disc.get("invalidation") or _gate.get("invalidation") or "").strip()
    if _inv:
        _inv = _inv.replace("收盘有效跌破", "跌破").replace("且反抽站不回", "站不回")
        _inv = _inv.replace("或跌破止损", "或破止损")
        if len(_inv) > 52:
            _inv = _inv[:49] + "…"
        lines.append(f"  破位看：{_inv}")

    # 策略闸口仍由 pipeline 写入 strategy_match（供 decision_view）；
    # 人读报告省略 📐——日常以 决策/动作/新开/失效 为准。

    stop_sell = key_prices.get("stop_sell") or r.get("effective_stop") or r.get("stop")
    try:
        _trail_v = float(r.get("trailing_stop") or 0)
        _hard_v = float(stop_sell or r.get("stop") or 0)
        if _trail_v > 0:
            stop_sell = max(_hard_v, _trail_v)
    except (TypeError, ValueError):
        pass
    buy_low = key_prices.get("buy_zone_low")
    buy_high = key_prices.get("buy_zone_high")
    buy_ref = key_prices.get("buy_ref")
    short_low = key_prices.get("short_sell_low")
    short_high = key_prices.get("short_sell_high")
    swing_sell = key_prices.get("swing_sell")
    far_sell = key_prices.get("far_sell")

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

    # 提前计算 RR 值（供防线标注使用）
    _target_rr = float(r.get("take") or 0)
    _risk_buy = max(0.0, float(buy_low or 0) - float(stop_sell or 0)) if buy_low and stop_sell else 0.0
    _rew_buy = max(0.0, _target_rr - float(buy_low or 0)) if buy_low and _target_rr > 0 else 0.0
    _risk_chase = max(0.0, current - float(stop_sell or 0)) if current > 0 and stop_sell else 0.0
    _rew_chase = max(0.0, _target_rr - current) if current > 0 and _target_rr > 0 else 0.0
    _ratio_buy = _rew_buy / _risk_buy if _risk_buy > 0 else 0.0
    _ratio_chase = _rew_chase / _risk_chase if _risk_chase > 0 else 0.0
    _rr_buy_verdict = "✓" if _ratio_buy >= 2.0 else ("✗" if _ratio_buy < 1.0 else "△")
    _rr_chase_verdict = "✓" if _ratio_chase >= 2.0 else ("✗" if _ratio_chase < 1.0 else "△")

    lines.append("")
    lines.append("  关键价（短线）")

    # 按价格从低到高排列，每个价位一行
    _price_items: list[tuple[float, str, str]] = []  # (price, label, action)

    # 来源标注映射（MA 类区分支撑/压力后缀）
    _sup_src = str(r.get("support_source") or "").strip()
    _res_src = str(r.get("resistance_source") or "").strip()
    _SRC_BASE = {
        "low_5d": "近5日低点", "low_20d": "近20日低点",
        "ma5": "MA5", "ma10": "MA10", "ma20": "MA20",
        "chip_support": "筹码密集区", "chip_resistance": "筹码密集区",
        "high_5d": "近5日高点", "high_20d": "近20日高点",
        "pivot_61.8": "黄金分割位",
    }
    _MA_KEYS = {"ma5", "ma10", "ma20"}
    _sup_base = _SRC_BASE.get(_sup_src.lower(), "")
    _res_base = _SRC_BASE.get(_res_src.lower(), "")
    
    if _sup_src.lower() == "chip_support" and "chip_support_lower" in r and "chip_support_upper" in r:
        _sup_lower = r.get("chip_support_lower")
        _sup_upper = r.get("chip_support_upper")
        if _sup_lower is not None and _sup_upper is not None:
            _sup_label = f"筹码支撑带 {_sup_lower:.2f}-{_sup_upper:.2f}"
        else:
            _sup_label = f"{_sup_base}支撑" if _sup_src.lower() in _MA_KEYS and _sup_base else _sup_base
    else:
        _sup_label = f"{_sup_base}支撑" if _sup_src.lower() in _MA_KEYS and _sup_base else _sup_base

    if _res_src.lower() == "chip_resistance" and "chip_resistance_lower" in r and "chip_resistance_upper" in r:
        _res_lower = r.get("chip_resistance_lower")
        _res_upper = r.get("chip_resistance_upper")
        if _res_lower is not None and _res_upper is not None:
            _res_label = f"筹码阻力带 {_res_lower:.2f}-{_res_upper:.2f}"
        else:
            _res_label = f"{_res_base}压力" if _res_src.lower() in _MA_KEYS and _res_base else _res_base
    else:
        _res_label = f"{_res_base}压力" if _res_src.lower() in _MA_KEYS and _res_base else _res_base

    # 卖点区目标百分比
    _sell_tgt_pct = ""
    if current > 0 and short_high and float(short_high) > current:
        _sell_tgt_pct = f"，目标+{(float(short_high) - current) / current * 100:.1f}%"

    if stop_sell:
        _stop_annotation = "破就走"
        if _risk_chase > 0:
            _stop_annotation = f"跌破亏 {_risk_chase:.1f}"
        _price_items.append((float(stop_sell), "止损", _stop_annotation))

    if buy_low and buy_high:
        _src_suffix = f" ← {_sup_label}" if _sup_label else ""
        _allow_entry = bool(_disc.get("allow_new_entry", True))
        if not _allow_entry:
            _buy_annotation = "等确认"
        else:
            _buy_annotation = "回踩买"
            if _risk_buy > 0 and _rew_buy > 0:
                _buy_annotation += f"，亏{_risk_buy:.1f} 赚{_rew_buy:.1f} → 盈亏比 {_ratio_buy:.1f}:1 {_rr_buy_verdict}"
        _price_items.append((float(buy_low) - 0.001, f"低吸区 {float(buy_low):.2f}-{float(buy_high):.2f}", f"{_buy_annotation}{_src_suffix}"))
    elif buy_ref:
        _src_suffix = f" ← {_sup_label}" if _sup_label else ""
        _price_items.append((float(buy_ref), "买点区", f"分批建仓{_src_suffix}"))

    # MA5 支撑（如果在止损和现价之间）
    _ma5 = _ma_float("ma5")
    if _ma5 and stop_sell and _ma5 > float(stop_sell) and _ma5 < current:
        _price_items.append((_ma5, "MA5 支撑", "加仓试探"))

    if current > 0:
        _price_items.append((current, "现价", "持有，不追"))

    # VWAP 支撑/压力
    _vwap = r.get("vwap")
    _vwap_lvl = r.get("vwap_level")
    try:
        _vwap_f = float(_vwap) if _vwap is not None else None
    except (TypeError, ValueError):
        _vwap_f = None
    if _vwap_f is not None:
        _vwap_act = "日内均线支撑" if current >= _vwap_f else "日内均线压力"
        _price_items.append((_vwap_f, f"VWAP（{_vwap_lvl or '--'}）", _vwap_act))

    # MA20 压力（如果在现价和卖点区之间）
    _ma20 = _ma_float("ma20")
    if _ma20 and _ma20 > current:
        _price_items.append((_ma20, "MA20 压力", "靠近只减不加"))

    if short_low and short_high:
        _res_suffix = f" ← {_res_label}" if _res_label else ""
        _allow_entry = bool(_disc.get("allow_new_entry", True))
        if not _allow_entry:
            _sell_annotation = "等确认"
        else:
            _sell_annotation = "分批出"
            if _rew_chase > 0:
                _sell_annotation += f"，赚 {_rew_chase:.1f}"
            if _sell_tgt_pct:
                _sell_annotation += _sell_tgt_pct
        if float(short_low) == float(short_high):
            _price_items.append((float(short_low), "止盈区", f"{_sell_annotation}{_res_suffix}"))
        else:
            _price_items.append((float(short_low) - 0.001, f"止盈区 {float(short_low):.2f}-{float(short_high):.2f}", f"{_sell_annotation}{_res_suffix}"))

    # 止盈（如果和卖点区不同）
    _take = r.get("take")
    try:
        _take_f = float(_take) if _take is not None else None
    except (TypeError, ValueError):
        _take_f = None
    if _take_f and short_high and abs(_take_f - float(short_high)) / max(float(short_high), 1) > 0.01:
        _price_items.append((_take_f, "前高/止盈", "全部止盈"))

    # 按价格排序输出
    _price_items.sort(key=lambda x: x[0])
    for price, label, action in _price_items:
        if "现价" in label:
            lines.append(f"    🌟 {current:.2f} 现价（{action}）")
        else:
            lines.append(f"    {price:.2f} {label}（{action}）")

    lines.append("")

    # ── T0（日内算法：低吸到高抛的日内差价 + 盈亏比）──
    _t0_has_pos = bool(r.get("has_position"))
    _t0_no_new = any(k in execution for k in ("不买", "不追", "不新开", "观望"))
    if not _t0_has_pos and _t0_no_new:
        _bl = float(buy_low or 0)
        _bh = float(buy_high or 0)
        _sl = float(short_low or 0)
        if _bl > 0 and _sl > 0:
            _tm = round((_bh + _sl) / 2, 2)
            _tr = max(0.0, _bl - float(stop_sell or 0))
            _tw = max(0.0, _sl - _bl)
            _tr_ratio = _tw / _tr if _tr > 0 else 0
            _tv = "✓" if _tr_ratio >= 2.0 else ("✗" if _tr_ratio < 1.0 else "△")
            lines.append(f"  日内 T0：{_bl:.2f} 低吸 ｜ {_tm:.2f} 观察 ｜ {_sl:.2f} 高抛（差价{_tw:.2f}元，盈亏比{_tr_ratio:.1f}:1 {_tv}）")
        else:
            lines.append("  T0：无底仓，不启用（与出手一致，不新开）")
    else:
        t0_ref = r.get("t0_ref") or {}
        _t0_buy = float(t0_ref.get("low_buy") or buy_low or r.get("support") or 0)
        _t0_sell = float(t0_ref.get("high_sell") or swing_sell or short_high or confirm or 0)
        if _t0_buy > 0 and _t0_sell > 0:
            _tm = round((_t0_buy + _t0_sell) / 2, 2)
            _tr = max(0.0, _t0_buy - float(stop_sell or 0))
            _tw = max(0.0, _t0_sell - _t0_buy)
            _tr_ratio = _tw / _tr if _tr > 0 else 0
            _tv = "✓" if _tr_ratio >= 2.0 else ("✗" if _tr_ratio < 1.0 else "△")
            lines.append(f"  日内 T0：{_t0_buy:.2f} 低吸 ｜ {_tm:.2f} 观察 ｜ {_t0_sell:.2f} 高抛（差价{_tw:.2f}元，盈亏比{_tr_ratio:.1f}:1 {_tv}）")
        elif _t0_has_pos:
            _tp = []
            if _t0_buy > 0:
                _tp.append(f"低吸参考 {_t0_buy:.2f}")
            if _t0_sell > 0:
                _tp.append(f"高抛参考 {_t0_sell:.2f}")
            lines.append(f"  T0：{' ｜ '.join(_tp)}" if _tp else "T0：有底仓，按关键价做短线")
        elif _t0_buy > 0:
            lines.append(f"  T0：仅观察；计划买点约 {_t0_buy:.2f}（未放行不下手）")
        else:
            lines.append("  T0：观察关键价即可")

    # ── 🎯 组合策略共振（combo）已暂停渲染：箱体先做独立模块，暂不进报告 ──

    # 「说明」行已删除（与出手行语义重复）

    # ── 亮点 / 风险（禁止「阶段…中线故事」挂羊头）──
    support = float(r.get("support") or 0)
    confirm = float(r.get("confirm") or 0)
    key_levels = r.get("key_levels") or {}
    _mid_resist = float(
        mid_key_prices.get("resist")
        or key_prices.get("swing_sell")
        or key_levels.get("mid_resist")
        or 0
    )
    stop_v = float(stop_sell or 0)
    life_v = float(mid_key_prices.get("life_line") or 0)

    lines.append("")
    # ── 亮点 / 风险（具体数据驱动，禁模板空话）──
    _ma20_v = _ma_float("ma20")
    _ma5_v = _ma_float("ma5")

    # 亮点/风险缠论：只认引擎买卖点（resolve_chanlun_primary）；禁 fusion.reason 手补（C-D3）
    _hl_parts = []
    _chan_bear_hl = False
    _chan_hl_label = ""
    _chan_risk_label = ""
    try:
        from trader_shared.chan_core import resolve_chanlun_primary

        _prim_hl = resolve_chanlun_primary(r.get("chanlun") or r.get("chanlun_daily"))
        _chan_dir_hl = int(_prim_hl.get("direction") or 0)
        _chan_type_hl = str(
            _prim_hl.get("type_short") or _prim_hl.get("type_raw") or ""
        ).strip()
        _chan_bear_hl = _chan_dir_hl < 0 or any(
            k in _chan_type_hl for k in ("卖", "看跌", "顶背驰", "偏空", "减仓")
        )
        if _prim_hl.get("status") == "point" and _chan_type_hl:
            if _chan_bear_hl:
                _chan_risk_label = _chan_type_hl
            else:
                _chan_hl_label = _chan_type_hl
    except Exception:
        _chan_hl_label = ""
        _chan_risk_label = ""
    if _chan_hl_label:
        _hl_parts.append(f"缠论{_chan_hl_label}")
    # 亮点阶段：看面板「阶段：」行（含偏空标签）+ midline_bias，勿把偏空主升当亮点
    _stage_disp_hl = str(_stage_line or stage_line or "").strip()
    _mid_bias_hl = str(r.get("midline_bias") or "").strip().lower()
    _stage_bear_hl = bool(
        _mid_bias_hl == "bear"
        or any(k in _stage_disp_hl for k in ("转弱", "派发", "衰退", "偏空", "慎跟", "暂缓"))
    )
    _stage_bull_hl = bool(
        _stage_disp_hl
        and any(k in _stage_disp_hl for k in ("蓄势", "主升"))
        and not _stage_bear_hl
    )
    if _stage_bull_hl:
        _hl_parts.append(f"中线阶段{stage_line or _stage_disp_hl}")
    if _ma5_v and current > 0 and current > _ma5_v and not _chan_bear_hl and not _stage_bear_hl:
        _hl_parts.append("现价在MA5上方")

    _ext_sent = r.get("extend_sentiment") or {}
    _theme = _ext_sent.get("theme_harden") or {}
    if isinstance(_theme, dict) and _theme.get("reason") and not _stage_bear_hl:
        _hl_parts.append(f"题材催化：{_theme.get('reason')}")

    if _hl_parts:
        lines.append(f"✅ 亮点：{'；'.join(_hl_parts)}")
    elif ("可跟踪" in mid or "未坏" in mid) and not _chan_bear_hl and _stage_bull_hl:
        if _sp is not None and _sp <= 0:
            lines.append(f"✅ 亮点：中线结构可跟踪，等纪律放行；阶段 {stage_line}")
        else:
            lines.append(f"✅ 亮点：中线看法仍可跟踪；阶段 {stage_line}")
    elif _stage_bull_hl:
        lines.append(f"✅ 亮点：阶段 {stage_line}，等短线信号")
    else:
        lines.append("✅ 亮点：暂无，先看纪律与风险")

    # 风险：止损价 + 短线 MA20 压力（不用中线远压力） + 未来待解禁
    _risk_parts = []
    if _chan_bear_hl and _chan_risk_label:
        _risk_parts.append(f"缠论{_chan_risk_label}")
    if _stage_bear_hl and (_stage_disp_hl or stage_line):
        _risk_parts.append(f"中线阶段{_stage_disp_hl or stage_line}")
    elif stage_line and any(k in stage_line for k in ("转弱", "派发", "衰退")):
        _risk_parts.append(f"中线阶段{stage_line}")
    if "不追" in execution or "不买" in execution:
        _risk_parts.append("现价不宜追")
        if stop_v > 0:
            _risk_parts.append(f"止损看 {stop_v:.2f}")
        if _ma20_v and _ma20_v > current > 0:
            _risk_parts.append(f"上方MA20({_ma20_v:.2f})压力")
    elif stage_line and "派发" in stage_line and f"中线阶段{stage_line}" not in _risk_parts:
        _risk_parts.append("派发阶段注意破位" + (f"，跌破 {stop_v:.2f} 需离场" if stop_v else ""))
    elif stage_line and "衰退" in stage_line and f"中线阶段{stage_line}" not in _risk_parts:
        _risk_parts.append("衰退阶段，不宜介入")
    elif life_v > 0 and current > 0 and current < life_v * 1.02:
        _risk_parts.append(f"靠近/跌破中线生命线 {life_v:.2f}")
    elif not _risk_parts:
        _risk_parts.append("未站稳前不提前加仓")

    _unlocks = _ext_sent.get("unlocks") or []
    if isinstance(_unlocks, list) and _unlocks:
        _unlock_parts = []
        for _u in _unlocks:
            _u_date = _u.get("date", "")
            _u_ratio = _u.get("ratio", 0.0)
            _u_amt = _u.get("amount_wan", 0.0)
            _unlock_parts.append(f"{_u_date}解禁{_u_ratio:.2f}%（{_u_amt:.2f}万股）")
        if _unlock_parts:
            _risk_parts.append(f"待解禁：{' ｜ '.join(_unlock_parts[:3])}")

    lines.append(f"⚠️ 风险：{'；'.join(_risk_parts)}")

    # ── 📌 明日策略（替代"本周只做"）──
    _buy_lo_val = float(buy_low or 0)
    _buy_hi_val = float(buy_high or 0)
    _sell_lo_val = float(short_low or 0)
    _sell_hi_val = float(short_high or 0)
    if _sell_lo_val > 0 and _buy_lo_val > 0:
        _strategy_parts = []
        if _sell_hi_val > 0:
            _strategy_parts.append(f"若高开到 {_sell_lo_val:.2f} 附近减仓")
        if _buy_lo_val > 0:
            _strategy_parts.append(f"若低开到 {_buy_lo_val:.2f} 附近观察承接")
        if _strategy_parts:
            lines.append(f"📌 明日策略：{'；'.join(_strategy_parts)}")
    elif this_week:
        lines.append(f"📌 本周只做：{this_week}")

    pool_count = r.get("pool_count")
    pool_cap = r.get("pool_cap")
    if pool_count is not None and pool_cap is not None:
        lines.append(f"当前池 {pool_count}/{pool_cap}，回复 1 入池")

    return "\n".join(lines)


