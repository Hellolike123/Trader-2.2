"""选股池 compare 渲染辅助。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pool_cmds.verify import *  # noqa: F403

def review_result(item: dict[str, Any], report: dict[str, Any]) -> tuple[str, str, str]:
    high_or_current = to_float(report.get("current")) or 0.0
    trigger = to_float(item.get("trigger")) or 0.0
    defense = to_float(item.get("defense")) or 0.0
    if high_or_current <= defense:
        return "失效", f"现价{price(high_or_current)}，跌破防守{price(defense)}", "防守失效，转淘汰观察。"
    if high_or_current >= trigger:
        return "命中", f"现价{price(high_or_current)}，达到触发{price(trigger)}", "触发有效，继续按防守位管理。"
    return "未触发", f"现价{price(high_or_current)}，未到触发{price(trigger)}", "不买是正确的，继续观察。"


def _latest_signal_summary(report: dict[str, Any], store_path: Path | None = None) -> str:
    symbol = str(report.get("symbol") or "")
    if not symbol:
        return ""
    try:
        from trader_shared.signal_store import load_recent_signals
        signals = load_recent_signals(symbol, limit=3, path=store_path)
    except Exception:
        return ""
    recent = [s for s in signals if isinstance(s, dict)]
    if not recent:
        return ""
    latest = recent[-1]
    sig_type = str(latest.get("signal_type") or "")
    action = str(latest.get("action") or "")
    source = str(latest.get("source_skill") or "")
    if sig_type in ("low_buy_triggered", "low_buy_watch", "low_buy"):
        return f"🟢T0低吸{action if source == 't0' else ''}"
    if sig_type in ("high_sell_triggered", "high_sell_watch", "high_sell"):
        return f"🔴T0高抛" if source == "t0" else f"🔴高抛{action}"
    if sig_type == "risk_stop":
        return "⚠️止损"
    if sig_type == "reduce":
        return f"📉减仓({action})"
    if sig_type == "track":
        return f"👁跟踪"
    return ""


def render_compare(reports: list[dict[str, Any]]) -> str:
    from trader_shared.candidate_core import atr_volatility_level

    # ── 评分辅助函数 ──
    def _scores(r: dict[str, Any]) -> dict[str, int]:
        try:
            return score_report(r)
        except Exception:
            return {"total_score": 0, "chanlun_score": 0, "wyckoff_score": 0,
                    "chip_score": 0, "fusion_score": 0, "momentum_score": 0, "momentum_tag": ""}

    def _sort_key(r: dict[str, Any]):
        try:
            sc = score_report(r)
            return (-sc.get("total_score", 0),)
        except Exception:
            return (0,)

    sorted_reports = sorted(reports, key=_sort_key)

    # ── 大盘 ──
    market_level = get_market_level()
    lines = [f"对比 — {' vs '.join(r.get('name','?') for r in sorted_reports)}", ""]
    if market_level:
        lines.append(f"🌍 大盘{market_level} | {get_market_note()}")
        lines.append("")

    # ── 逐票详情 ──
    for i, r in enumerate(sorted_reports, 1):
        name = r.get("name", "?")
        code = str(r.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
        scene = str(r.get("scene") or "?")
        current = to_float(r.get("current")) or 0.0
        stop_val = to_float(r.get("stop")) or 0.0
        support_val = to_float(r.get("support")) or 0.0
        resistance_val = to_float(r.get("resistance")) or 0.0
        confirm_val = to_float(r.get("confirm")) or 0.0
        take_val = to_float(r.get("take")) or 0.0

        atr14 = to_float(r.get("atr14")) or 0.0
        atr_ratio = to_float(r.get("atr_ratio")) or 0.0
        atr_level, atr_cap = atr_volatility_level(atr_ratio)
        atr_pct = atr_ratio * 100

        if atr_ratio >= 0.03:
            atr_text = f"波幅偏高({atr_pct:.0f}%)"
        elif atr_ratio >= 0.02:
            atr_text = f"波动偏大({atr_pct:.0f}%)"
        elif atr14 > 0:
            atr_text = f"波动正常({atr_pct:.0f}%)"
        else:
            atr_text = "数据不足"

        # 阶段 + 动能
        major_stage = str(r.get("major_stage") or "")
        momentum = str(r.get("short_term_momentum") or "")

        # 评分
        scores = _scores(r)
        total = scores.get("total_score", 0)
        chan = scores.get("chanlun_score", 0)
        wyck = scores.get("wyckoff_score", 0)
        chip = scores.get("chip_score", 0)
        fus = scores.get("fusion_score", 0)
        mom = scores.get("momentum_score", 0)
        chan_max = 45
        wyck_max = 30
        chip_max = 25
        fus_max = 20
        mom_max = 20

        # 融合详情
        fusion = r.get("fusion") or {}
        fusion_action = fusion.get("action", "")
        fusion_conf = fusion.get("confidence", 0)
        fusion_ws = fusion.get("weighted_score", 0)

        # 主力评分
        mf = r.get("main_force_score") or {}
        mf_total = mf.get("total_score", 0) if isinstance(mf, dict) else 0

        lines.append(f"{i}. {name}（{code}）  {scene}  {current:.2f}元  {atr_text}")
        lines.append(f"   阶段：{major_stage} ｜ 动能：{momentum} ｜ 综合评分：{total}")

        # 五层打分
        lines.append(f"   五层打分：缠{chan}/{chan_max} 威{wyck}/{wyck_max} 筹{chip}/{chip_max} 融{fus}/{fus_max} 动{mom}/{mom_max}")

        # 融合 + 主力
        if fusion_action:
            lines.append(f"   融合：{fusion_action}（得分 {fusion_ws:+.2f}，置信度 {fusion_conf:.0%}）")
        if mf_total > 0:
            lines.append(f"   主力评分：{mf_total}分（{mf.get('label', '')}）")

        # 关键价位
        lines.append(f"   关键位：止损 {stop_val:.2f} 支撑 {support_val:.2f} 现价 {current:.2f} 压力 {resistance_val:.2f} 确认 {confirm_val:.2f}")

        # EXPMA 趋势
        expma = r.get("expma_status") or {}
        expma_label = expma.get("trend_label", "") if isinstance(expma, dict) else ""
        if expma_label:
            lines.append(f"   EXPMA：{expma_label}")

        # 筹码峰
        chip_peaks = r.get("chip_peaks") or []
        if chip_peaks:
            support_peaks = sorted(
                [p for p in chip_peaks if float(p.get("price", 0)) < current],
                key=lambda p: float(p.get("share_of_total", 0)), reverse=True
            )
            resist_peaks = sorted(
                [p for p in chip_peaks if float(p.get("price", 0)) > current],
                key=lambda p: float(p.get("share_of_total", 0)), reverse=True
            )
            if support_peaks:
                top_s = support_peaks[0]
                lines.append(f"   筹码支撑：{float(top_s.get('price',0)):.2f}元（占比{float(top_s.get('share_of_total',0))*100:.0f}%）")
            if resist_peaks:
                top_r = resist_peaks[0]
                lines.append(f"   筹码压力：{float(top_r.get('price',0)):.2f}元（占比{float(top_r.get('share_of_total',0))*100:.0f}%）")

        # 多周期共振
        resonance = r.get("resonance") or {}
        if isinstance(resonance, dict) and resonance.get("total_score", 0) > 0:
            _format_resonance_score(resonance.get("total_score", 0), lines)

        # 信号摘要
        signal_summary = _latest_signal_summary(r)
        if signal_summary:
            lines.append(f"   信号：{signal_summary}")

        lines.append("")

    # ── 量化排序结论 ──
    ranking = _render_ranking_conclusion(sorted_reports, _scores, market_level)
    lines.extend(ranking)

    return "\n".join(lines)


def _render_ranking_conclusion(sorted_reports: list[dict[str, Any]],
                                get_scores,
                                market_level: str) -> list[str]:
    """生成量化排序结论，解释为什么这样排。"""
    if len(sorted_reports) < 2:
        return []

    scores_list = [get_scores(r) for r in sorted_reports]

    # 多维度打分对比
    dim_labels = {
        "total_score": "综合",
        "chanlun_score": "缠论",
        "wyckoff_score": "威科夫",
        "chip_score": "筹码",
        "fusion_score": "融合",
        "momentum_score": "动能",
    }

    result: list[str] = ["", "📊 多维度对比"]

    # 表头
    headers = ["标的"] + [dim_labels.get(d, d) for d in dim_labels if d != "total_score"] + ["总分"]
    result.append("  " + "  ".join(f"{h:>6s}" for h in headers))

    # 数据行（与表头顺序一致：标的 缠论 威科夫 筹码 融合 动能 总分）
    max_name_len = max((len(str(r.get("name", "?"))[:8]) for r in sorted_reports), default=4)
    for i, (r, sc) in enumerate(zip(sorted_reports, scores_list)):
        name = str(r.get("name", "?"))[:8]
        vals = [f"{name:<{max_name_len}s}"]
        for d in dim_labels:
            if d == "total_score":
                continue  # total_score 放到最后
            vals.append(f"{sc.get(d, 0):>6d}")
        vals.append(f"{sc.get('total_score', 0):>6d}")
        result.append("  " + "  ".join(vals))

    result.append("")

    # 排序理由
    winner = sorted_reports[0]
    winner_scores = scores_list[0]
    winner_name = winner.get("name", "?")
    winner_total = winner_scores.get("total_score", 0)

    reasons = []
    for j in range(1, len(sorted_reports)):
        other = sorted_reports[j]
        other_scores = scores_list[j]
        other_total = other_scores.get("total_score", 0)
        delta = winner_total - other_total
        if delta <= 0:
            continue

        # 找出赢在哪几个维度
        wins = []
        for d in ("chanlun_score", "wyckoff_score", "chip_score", "fusion_score", "momentum_score"):
            wd = winner_scores.get(d, 0) - other_scores.get(d, 0)
            if wd > 0:
                dim_name = dim_labels.get(d, d)
                wins.append(f"{dim_name}+{wd}")

        reason = f"{winner_name} 领先 {delta} 分"
        if wins:
            reason += f"（优势：{', '.join(wins[:3])}）"
        reasons.append(reason)

    # ATR 补充提示
    atr_info = []
    for r in sorted_reports:
        atr_pct = to_float(r.get("atr_ratio")) or 0.0
        atr_pct *= 100
        atr_info.append((r.get("name", "?"), atr_pct))
    min_atr_name = min(atr_info, key=lambda x: x[1])[0]
    if len(atr_info) >= 2:
        reasons.append(f"波动率最低：{min_atr_name}（{min(atr_info, key=lambda x: x[1])[1]:.0f}%）")

    if reasons:
        result.append("💡 排序理由：")
        for reason in reasons:
            result.append(f"  • {reason}")

    # 大盘提示 + 明确推荐
    if market_level == "很差":
        result.append("")
        result.append("👉 大盘很差，所有标的先观察，不急着买")
    elif market_level == "偏弱":
        result.append("")
        result.append("👉 大盘偏弱，优先选波动小、信号靠谱的")
    elif len(sorted_reports) >= 2:
        result.append("")
        w_name = winner_name
        w_score = winner_total
        s_name = sorted_reports[1].get("name", "?")
        s_score = scores_list[1].get("total_score", 0)
        if w_score > s_score:
            gap = w_score - s_score
            if gap >= 10:
                result.append(f"👉 综合评分差距明显（{gap}分），优先选择 {w_name}")
            elif gap >= 5:
                result.append(f"👉 {w_name} 综合略优（领先{gap}分），建议优先关注")
            else:
                result.append(f"👉 {w_name} 与 {s_name} 分差不大（{gap}分），结合当前持仓综合判断")
        else:
            result.append(f"👉 同等条件下，优先选波动小的（{min_atr_name} 波动最低）")

    return result


def _format_resonance_score(score: int, lines: list[str]) -> None:
    """格式化共振评分（微信可读版）。"""
    parts = []
    if score >= 8:
        parts.append("多时间窗共振强")
    elif score >= 6:
        parts.append("部分时间窗共振")
    elif score >= 4:
        parts.append("低分，信号未共振")
    lines.append(f"   共振评分：{score}分（{'；'.join(parts)}）")

__all__ = [
    "render_compare",
    "review_result",
    "_format_resonance_score",
    "_latest_signal_summary",
    "_render_ranking_conclusion",
]
