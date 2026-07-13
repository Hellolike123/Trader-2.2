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
import re
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


def _reformat_mid_line(line: str) -> str:
    """中线关键价行格式转换：价格前置 + 动作统一。

    旧格式「生命线 41.14（破则中线转弱）」→ 新格式「41.14 生命线（跌破则减仓）」。
    已是新格式时原样返回。
    """
    if not line:
        return line
    # 生命线
    m = re.match(r"^生命线\s+([\d.]+)（.+）$", line)
    if m:
        return f"{m.group(1)} 生命线（跌破则减仓）"
    # 回踩区（含区间或单价）
    m = re.match(r"^回踩区\s+([\d.-]+)（(.+)）$", line)
    if m:
        _tag = m.group(2).replace("到了才谈低吸", "到了分批低吸")
        return f"{m.group(1)} 回踩区（{_tag}）"
    # 压力/目标（合并）
    m = re.match(r"^压力/目标\s+([\d.]+)（(.+)）$", line)
    if m:
        _tag = m.group(2).replace("靠近只减不加", "靠近分批减仓").replace("波段上看", "到了分批止盈")
        return f"{m.group(1)} 压力/目标位（{_tag}）"
    # 压力
    m = re.match(r"^压力\s+([\d.]+)（(.+)）$", line)
    if m:
        _tag = m.group(2).replace("靠近只减不加", "靠近分批减仓")
        return f"{m.group(1)} 压力位（{_tag}）"
    # 目标
    m = re.match(r"^目标\s+([\d.]+)（(.+)）$", line)
    if m:
        return f"{m.group(1)} 目标位（到了分批止盈）"
    # 黄金买点
    m = re.match(r"^黄金买点\s+([\d.]+)（(.+)）$", line)
    if m:
        return f"{m.group(1)} 黄金买点（{m.group(2)}）"
    return line


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

    major_stage = str(r.get("major_stage") or "")
    if major_stage == "None":
        major_stage = ""
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

    lines: list[str] = [
        f"分析报告 — {name}（{code}）｜短中线",
        "",
        f"现价 {current:.2f}（{change_pct:+.2f}%）",
    ]

    # meta：动能｜大盘（阶段主展示在 🧭，meta 不重复以免与中线打架）
    meta_parts = []
    if momentum:
        meta_parts.append(f"综合动能 {momentum}")
    if regime:
        meta_parts.append(f"大盘 {regime}")
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

    if vol_parts:
        lines.append(f"  {' ｜ '.join(vol_parts)}")

    # 相对强弱与行业板块（优先 extend_sector；fallback 用个股涨跌 vs 大盘环境）
    _ext_sec = r.get("extend_sector") or {}
    if isinstance(_ext_sec, dict) and _ext_sec.get("status") == "正常":
        _sec_name = _ext_sec.get("sector_name") or ""
        _sec_chg = _ext_sec.get("sector_change_pct")
        _sec_rank = _ext_sec.get("sector_rank") or 0
        _sec_tot = _ext_sec.get("sector_total") or 0
        _vs = str(_ext_sec.get("stock_vs_sector") or "").strip()
        
        _sec_chg_str = f"{_sec_chg:+.2f}%" if isinstance(_sec_chg, (int, float)) else "--"
        _rank_str = f"排名 {_sec_rank}/{_sec_tot}" if _sec_rank > 0 else ""
        
        _sector_parts = []
        if _sec_name:
            _short_name = _sec_name.replace("(A股)", "").replace("(A)", "").strip()
            _sector_parts.append(f"{_short_name} {_sec_chg_str}")
        # 个股涨跌幅
        if change_pct is not None:
            _sector_parts.append(f"个股 {change_pct:+.2f}%")
        if _vs:
            _sector_parts.append(_vs.replace("板块", "").strip())
        if _sector_parts:
            lines.append(f"  行业：{' ｜ '.join(_sector_parts)}")
    elif change_pct != 0 and regime:
        # 简易对比：个股涨跌 vs 大盘环境词
        _regime_map = {"偏强": 0.5, "正常": 0, "偏弱": -0.5, "很差": -1.0}
        _regime_score = _regime_map.get(regime, 0)
        _vs_simple = change_pct - _regime_score
        if _vs_simple > 0.5:
            lines.append(f"  相对强弱：跑赢大盘 +{_vs_simple:.1f}%")
        elif _vs_simple < -0.5:
            lines.append(f"  相对强弱：跑弱 {_vs_simple:.1f}%")
        else:
            lines.append(f"  相对强弱：与大盘持平")

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

    ma250_val = _ma_float("ma250")
    if current > 0 and ma250_val is not None and current < ma250_val:
        lines.append(f"  ⚠️ 股价在年线（{ma250_val:.2f}）下方运行，注意风险")

    mid = conclusion.get("midline") or "中线观察"
    short = conclusion.get("shortline") or "观察"
    execution = conclusion.get("execution") or "现价不买 · 不追"
    reason = conclusion.get("reason") or ""
    this_week = conclusion.get("this_week") or ""
    conflict = conclusion.get("conflict") or ""
    stage_line = str(conclusion.get("stage_line") or major_stage or "").strip()
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

    # 仓位衔接：结构看好但仓位为0时，加桥接说明
    _suggested_pct = r.get("suggested_pct")
    try:
        _sp = int(_suggested_pct) if _suggested_pct is not None else None
    except (TypeError, ValueError):
        _sp = None

    # 威科夫/缠论：严格 mid 字段，禁止回退日线
    try:
        from trader_shared.wyckoff_core import format_wyckoff_oneline
        _wyk_raw = r.get("wyckoff_midline")
        if isinstance(_wyk_raw, dict) and "wyckoff" in _wyk_raw:
            _wyk_raw = _wyk_raw.get("wyckoff")
        if not isinstance(_wyk_raw, dict):
            _wyk_raw = {}
        _wyk_line = format_wyckoff_oneline(_wyk_raw, direction=None, show_phase=True)
    except Exception:
        _wyk_line = "威科夫：数据不足 · 中性"
    _wyk_body = _wyk_line.replace("威科夫：", "").replace("威科夫:", "").strip()
    _wyk_compact = _wyk_body.replace(" · ", "·").replace(" ·", "·").replace("· ", "·")
    lines.append(f"  威科夫：{_wyk_compact}")

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
    # 从缠论结果提取方向词
    _chan_dir_mid = ""
    try:
        _chan_mid_raw = r.get("chanlun_midline")
        if isinstance(_chan_mid_raw, dict):
            _chan_inner = _chan_mid_raw.get("chanlun", _chan_mid_raw)
            if isinstance(_chan_inner, dict):
                _bps = _chan_inner.get("buy_points") or []
                _sps = _chan_inner.get("sell_points") or []
                _div = _chan_inner.get("divergence") or {}
                if any(isinstance(p, dict) and "买" in str(p.get("type", "")) for p in _bps):
                    _chan_dir_mid = "看涨"
                elif any(isinstance(p, dict) and "卖" in str(p.get("type", "")) for p in _sps):
                    _chan_dir_mid = "看跌"
                elif _div.get("top_divergence"):
                    _chan_dir_mid = "看跌"
                elif _div.get("bottom_divergence"):
                    _chan_dir_mid = "看涨"
                else:
                    _tl = str(_chan_inner.get("trend_label") or "")
                    if "拉升" in _tl:
                        _chan_dir_mid = "看涨"
                    elif "回调" in _tl:
                        _chan_dir_mid = "看跌"
    except Exception:
        pass

    if _wave_mid:
        # 浪型已含状态+信号，方向插在中间
        if _chan_dir_mid:
            # 拆分浪型：状态 · 信号 → 状态 · 方向 · 信号
            _wave_parts = _wave_mid.split(" · ", 1)
            _wave_state = _wave_parts[0]
            _wave_sig = _wave_parts[1] if len(_wave_parts) > 1 else ""
            _chan_display = f"{_wave_state} · {_chan_dir_mid} · {_wave_sig}" if _wave_sig else f"{_wave_state} · {_chan_dir_mid}"
        else:
            _chan_display = _wave_mid
    else:
        _chan_display = _chan_compact
    lines.append(f"  缠论：{_chan_display}")

    # 筹码状态行（获利盘 + 上方套牢峰 + 股东变动）
    _chip_pct = r.get("chip_current_pct")
    _chip_peaks = r.get("chip_peaks") or []
    _above_peaks = [p for p in _chip_peaks if isinstance(p, dict) and float(p.get("price") or 0) > current] if current > 0 else []
    _chip_parts = []
    if _chip_pct is not None and isinstance(_chip_pct, (int, float)):
        _chip_parts.append(f"获利盘 {_chip_pct:.1f}%")
    if _above_peaks:
        _above_peaks.sort(key=lambda x: float(x.get("price") or 0))
        _nearest = _above_peaks[0]
        _peak_price = float(_nearest.get("price") or 0)
        _tag = "上方压力重" if _peak_price < current * 1.10 else "上方有压力"
        _lower = _nearest.get("price_lower")
        _upper = _nearest.get("price_upper")
        if _lower is not None and _upper is not None:
            _chip_parts.append(f"套牢峰 {_peak_price:.2f}（阻力区 {_lower:.2f}-{_upper:.2f}，{_tag}）")
        else:
            _chip_parts.append(f"套牢峰 {_peak_price:.2f}（{_tag}）")
    
    _ext_fund = r.get("extend_fundamental") or {}
    _sh = _ext_fund.get("shareholder") or {}
    if isinstance(_sh, dict) and _sh.get("status") and _sh.get("status") != "数据不足":
        _sh_chg = _sh.get("change_pct") or 0.0
        _sh_status = _sh.get("status")
        _chip_parts.append(f"股东户数较上期 {_sh_chg:+.2f}%（{_sh_status}）")
        
    if _chip_parts:
        lines.append(f"  筹码：{' ｜ '.join(_chip_parts)}")

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

    # 插入现价（🌟 标记）
    if current > 0:
        _ins = False
        for _i, (p, _) in enumerate(_mid_items):
            if p > current:
                _mid_items.insert(_i, (current, f"🌟 现价 {current:.2f}"))
                _ins = True
                break
        if not _ins:
            _mid_items.append((current, f"🌟 现价 {current:.2f}"))

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

    # ── ⚡ 短线（简化：出手→缠论+浪型→动能→失效）──
    lines.append("")
    lines.append("⚡ 短线")

    # 出手（合并裁定+新开+分仓，放第一行）
    _disc = r.get("discipline") if isinstance(r.get("discipline"), dict) else {}
    _cap_t = _disc.get("suggested_pct_cap")
    _cap_str = f" · 分仓{_cap_t}%" if _cap_t is not None else ""
    # 全绿才保留试探类出手；否则强制观察语义
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
    if reason and reason not in execution:
        # 出手带触发价：如果观望且 confirm 存在，追加触发条件
        _confirm_v = float(r.get("confirm") or 0)
        if "不买" in execution or "观望" in execution:
            if _confirm_v > 0 and _confirm_v > current:
                execution = f"观望 · 等价格回到 {_confirm_v:.2f}（确认位）以上"
        lines.append(f"  出手：{execution}（{reason}）{_cap_str}")
    else:
        lines.append(f"  出手：{execution}{_cap_str}")

    # 缠论 + 浪型（合并为一行）
    _csig2 = fusion_signals.get("chan") if isinstance(fusion_signals.get("chan"), dict) else {}
    _wave = str(conclusion.get("wave_label") or "").strip()
    if _csig2:
        _st2 = str(_csig2.get("reason") or "").replace("缠论", "").strip().lstrip(":：").strip() or "无信号"
        _cd2 = _csig2.get("direction", 0)
        _dl2 = "看涨" if _cd2 and int(_cd2) > 0 else ("看跌" if _cd2 and int(_cd2) < 0 else "中性")
        _chan_part = f"{_st2} · {_dl2}"
        try:
            from trader_shared.chan_discipline import needs_same_level_tag, append_same_level_tag
            _bps = r.get("chan_buy_point_types") or []
            _need_sl = needs_same_level_tag(
                r.get("chanlun") or r.get("chan"),
                text=_chan_part,
                buy_point_types=_bps if isinstance(_bps, list) else [],
            )
            _chan_part = append_same_level_tag(_chan_part, _need_sl)
        except Exception:
            pass
        if _wave:
            # 去重：浪型中的信号词如果已出现在缠论reason里，不重复
            _wave_parts = [w.strip() for w in _wave.split(" · ")]
            _chan_lower = _chan_part.lower()
            # 检查信号类型重叠（一类卖/二类卖/一类买/二类买/顶背驰/底背驰）
            _sig_keywords = {"一类卖", "二类卖", "三类卖", "一类买", "二类买", "三类买", "顶背驰", "底背驰"}
            _wave_deduped = []
            for w in _wave_parts:
                w_lower = w.lower()
                # 完全子串匹配
                if w_lower in _chan_lower or w in _chan_part:
                    continue
                # 信号类型关键词匹配
                if any(kw in w for kw in _sig_keywords if kw in _chan_part):
                    continue
                _wave_deduped.append(w)
            if _wave_deduped:
                lines.append(f"  缠论：{_chan_part} · {' · '.join(_wave_deduped)}")
            else:
                lines.append(f"  缠论：{_chan_part}")
        else:
            lines.append(f"  缠论：{_chan_part}")
    else:
        _chan_line = "暂无信号 · 中性"
        if _wave:
            _chan_line += f" · {_wave}"
        lines.append(f"  缠论：{_chan_line}")

    # 信号分歧一行：缠论 vs 动量方向相反时提醒
    _chan_dir2 = int(_csig2.get("direction", 0)) if _csig2 else 0
    _mom_dir2 = int(_msig.get("direction", 0)) if 'msig' in dir() and isinstance(_msig, dict) else 0
    if _chan_dir2 * _mom_dir2 < 0:
        _c_label = "看多" if _chan_dir2 > 0 else "看空"
        _m_label = "看多" if _mom_dir2 > 0 else "看空"
        lines.append(f"  ⚠️ 信号分歧：缠论{_c_label} vs 动能{_m_label} → 观望为主")

    # 动能（展示 reason 原文，不删括号不编造分项）
    _msig = fusion_signals.get("momentum") if isinstance(fusion_signals.get("momentum"), dict) else {}
    if _msig:
        _mst = str(_msig.get("reason") or "").strip().lstrip(":：").strip() or "无信号"
        if len(_mst) > 40:
            _mst = _mst[:38] + "…"
        lines.append(f"  动能：{_mst}")
    else:
        lines.append("  动能：暂无信号")

    # 价量资金（展示 reason 原文 + 资金否决追加）
    _vsig = fusion_signals.get("vpf") if isinstance(fusion_signals.get("vpf"), dict) else {}
    if _vsig:
        _vst = str(_vsig.get("reason") or _vsig.get("vp_reason") or "").strip() or "中性"
        if len(_vst) > 40:
            _vst = _vst[:38] + "…"
        # 有资金否决时追加（veto_msg 格式："连续 N 日主力净流出超阈值"）
        _veto = str(fusion.get("fund_flow_outflow_veto_msg") or "").strip()
        if _veto:
            _days_m = re.search(r"连续\s*(\d+)\s*日", _veto)
            if _days_m:
                _vst = f"{_vst} ｜ 主力连续{_days_m.group(1)}日净流出"
            else:
                _vst = f"{_vst} ｜ {_veto}"
        lines.append(f"  价量资金：{_vst}")
    else:
        lines.append("  价量资金：暂无信号")

    # 失效（保留）
    _gate = r.get("mistery_gate") if isinstance(r.get("mistery_gate"), dict) else {}
    _inv = str(_disc.get("invalidation") or _gate.get("invalidation") or "").strip()
    if _inv:
        if len(_inv) > 60:
            _inv = _inv[:57] + "…"
        lines.append(f"  失效：{_inv}")

    stop_sell = key_prices.get("stop_sell") or r.get("stop")
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
        _buy_annotation = f"回踩买"
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
        _sell_annotation = "分批出"
        if _rew_chase > 0:
            _sell_annotation += f"，赚 {_rew_chase:.1f}"
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
    _chan_sig = str((fusion_signals.get("chan") or {}).get("reason") or "")
    _ma20_v = _ma_float("ma20")
    _ma5_v = _ma_float("ma5")

    # 亮点：缠论信号 + 阶段 + MA5 上方 + 题材催化
    _hl_parts = []
    if _chan_sig and _chan_sig != "无信号":
        _chan_clean = _chan_sig.replace("缠论", "").strip() or _chan_sig
        _hl_parts.append(f"缠论{_chan_clean}")
    if stage_line and any(k in stage_line for k in ("蓄势", "主升")):
        _hl_parts.append(f"中线阶段{stage_line}")
    if _ma5_v and current > 0 and current > _ma5_v:
        _hl_parts.append("现价在MA5上方")
    
    _ext_sent = r.get("extend_sentiment") or {}
    _theme = _ext_sent.get("theme_harden") or {}
    if isinstance(_theme, dict) and _theme.get("reason"):
        _hl_parts.append(f"题材催化：{_theme.get('reason')}")

    if _hl_parts:
        lines.append(f"✅ 亮点：{'；'.join(_hl_parts)}")
    elif "可跟踪" in mid or "未坏" in mid:
        if _sp is not None and _sp <= 0:
            lines.append(f"✅ 亮点：中线结构可跟踪，等纪律放行" + (f"；阶段 {stage_line}" if stage_line else ""))
        else:
            lines.append(f"✅ 亮点：中线看法仍可跟踪" + (f"；阶段 {stage_line}" if stage_line else ""))
    else:
        lines.append(f"✅ 亮点：阶段 {stage_line or '未知'}，等短线信号" if stage_line else "✅ 亮点：等短线买点确认")

    # 风险：止损价 + 短线 MA20 压力（不用中线远压力） + 未来待解禁
    _risk_parts = []
    if "不追" in execution or "不买" in execution:
        _risk_parts.append("现价不宜追")
        if stop_v > 0:
            _risk_parts.append(f"止损看 {stop_v:.2f}")
        if _ma20_v and _ma20_v > current > 0:
            _risk_parts.append(f"上方MA20({_ma20_v:.2f})压力")
    elif stage_line and "派发" in stage_line:
        _risk_parts.append("派发阶段注意破位" + (f"，跌破 {stop_v:.2f} 需离场" if stop_v else ""))
    elif stage_line and "衰退" in stage_line:
        _risk_parts.append("衰退阶段，不宜介入")
    elif life_v > 0 and current > 0 and current < life_v * 1.02:
        _risk_parts.append(f"靠近/跌破中线生命线 {life_v:.2f}")
    else:
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
            lines.append(f"  {format_wyckoff_oneline(_wyk_raw if isinstance(_wyk_raw, dict) else {}, direction=_w_dir, show_phase=True)}")
        except Exception:
            _sig = fusion_signals.get("wyckoff") if isinstance(fusion_signals.get("wyckoff"), dict) else {}
            _dir = _sig.get("direction", 0) if _sig else 0
            _dl = "偏多" if _dir > 0 else ("偏空" if _dir < 0 else "中性")
            lines.append(f"  威科夫：暂无事件 · {_dl}")

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
