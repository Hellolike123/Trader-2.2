"""report_core 渲染优化测试（Task 1-9）。

基于三花智控 002050 的 2026-07-12 真实数据构造 mock。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trader_shared.report_core import render_short_midline  # noqa: E402
from trader_shared.wyckoff_core import (  # noqa: E402
    format_wyckoff_event_light,
    format_wyckoff_midline_light,
)
from trader_shared.chan_core import format_chanlun_short_light  # noqa: E402
from trader_shared.chip_core import format_chip_position_light  # noqa: E402


def test_format_chip_position_light_basic():
    """方案 C：支撑 · 阻力 · 套牢面；无警报不写底部。"""
    line = format_chip_position_light(
        55.0,
        [
            {"price": 50.0, "share_of_total": 12},
            {"price": 58.0, "share_of_total": 20},
        ],
        {"has_history": True, "warning_level": "none", "migration_pct": 0},
        profit_pct=10.0,
    )
    assert line.startswith("筹码：")
    assert "支撑 50.00" in line or "支撑弱" in line
    assert "阻力 58.00" in line
    assert "套牢面大" in line
    assert "底部" not in line  # 无警报不写
    assert "｜" not in line


def test_format_chip_position_light_nanwang_like():
    """跌穿成本区：支撑弱 · 阻力 · 套牢面大。"""
    line = format_chip_position_light(
        41.63,
        [
            {"price": 44.4, "share_of_total": 5},
            {"price": 50.4, "share_of_total": 15},
        ],
        {"has_history": True, "warning_level": "none", "migration_pct": 0},
        profit_pct=9.0,
    )
    assert "支撑弱" in line
    assert "阻力 44.40" in line
    assert "套牢面大" in line


def _daily_bars() -> list[dict]:
    """20 根日线，最高在 19 天前。"""
    bars = []
    for i in range(20):
        if i == 0:
            h = 49.36
        else:
            h = 43.0 + i * 0.1
        bars.append({
            "date": f"2026-06-{i + 10:02d}",
            "high": h, "low": 42.0, "close": 43.0 + i * 0.05,
        })
    return bars


def _report() -> dict:
    """三花智控 002050 mock（基于 2026-07-12 真实数据）。"""
    return {
        "name": "三花智控", "symbol": "002050.SZ",
        "current": 43.20, "change_pct": 0.82,
        "short_term_momentum": "转弱",
        "market_env": {"level": "偏弱"},
        "ma_raw": {"ma5": 43.14, "ma10": 43.50, "ma20": 44.65, "ma250": 42.75},
        "volume_ratio": 1.0, "turnover_rate": 3.0,
        "atr14": 1.85, "atr_adjust": "none",
        "major_stage": "蓄势",
        "conclusion": {
            "midline": "盘整偏空 · 暂缓跟踪",
            "stage_line": "蓄势",
            "execution": "现价不买 · 不追",
            "reason": "亏1.4/赚1.0，不划算",
            "this_week": "不追现价；回买点再谈",
            "conflict": "周线偏空，短线也不追",
            "wave_label": "回调见底 · 关注一类买｜底背驰",
            "wave_label_mid": "笔数不足 · 先观望",
        },
        "discipline": {
            "suggested_pct_cap": 0,
            "invalidation": "收盘有效跌破MA20(44.65)且反抽站不回；或跌破止损 41.85",
        },
        "fusion": {
            "signals_detail": {
                "chan": {"reason": "一类买 (底背驰)", "direction": 1},
                "momentum": {"reason": "动量中性", "direction": 0},
                "vpf": {"reason": "平量（量比1.1，近3日-1.4%）", "direction": 0, "volume_ratio": 1.05},
            },
            "fund_flow_outflow_veto_msg": None,
        },
        "key_prices": {
            "stop_sell": 41.00,
            "buy_zone_low": 41.93, "buy_zone_high": 42.98, "buy_ref": 42.46,
            "short_sell_low": 43.63, "short_sell_high": 44.19,
            "swing_sell": 46.0, "far_sell": 60.03,
            "risk": 0.61, "reward_near": 1.73,
            "risk_chase": 1.35, "reward_chase": 0.99,
        },
        "mid_key_prices": {
            "line_life": "41.14 生命线（跌破则减仓）",
            "line_pullback": "41.14-46.69 回踩区（到了分批低吸）",
            "line_resist": "56.00 压力位（靠近分批减仓）",
            "line_target": "68.82 目标位（到了分批止盈）",
            "life_line": 41.14, "resist": 56.00,
        },
        "chip_current_pct": 8.3,
        "chip_peaks": [
            {"price": 41.75, "volume": 551950, "support_level": "弱支撑"},
            {"price": 44.95, "volume": 2751987, "support_level": "强阻力"},
            {"price": 49.36, "volume": 576185, "support_level": "弱阻力"},
        ],
        "support_source": "MA5", "resistance_source": "MA10",
        "support": 42.46, "confirm": 43.63,
        "take": 44.19,
        "extend_sector": {},
        "daily_bars": _daily_bars(),
    }


def _between(text: str, start: str, end: str | None = None) -> str:
    block = text.split(start, 1)[1]
    if end and end in block:
        block = block.split(end, 1)[0]
    return block


def _short_theory_block(text: str) -> str:
    theory = _between(text, "📐 理论分析", "🎯 支撑阻力")
    return _between(theory, "\n  短线")


def _decision_block(text: str) -> str:
    return _between(text, "✅ 出手", "✅ 亮点")


# ── Task 1: 盈亏比 ✓/✗ 判定 + 卖点区目标百分比 ──

def test_risk_reward_ratio_with_verdict():
    """短线关键价低吸区带盈亏比 ✓（现版：回踩买 · 盈亏比 x:1）。"""
    out = render_short_midline(_report())
    assert "回踩买" in out
    assert "盈亏比 2.4:1 ✓" in out
    # 现价不宜追：动作区「不划算」
    assert "不划算" in out


def test_sell_zone_with_target_pct():
    """止盈区行带目标百分比。"""
    out = render_short_midline(_report())
    assert "止盈区" in out
    assert "目标+" in out


# ── Task 2: 价格阶梯来源标注 ──

def test_price_source_annotation():
    """买点区/卖点区带来源标注。"""
    out = render_short_midline(_report())
    assert "← MA5支撑" in out
    assert "← MA10压力" in out


def test_price_source_unknown_no_annotation():
    """来源为空时不加标注。"""
    r = _report()
    r["support_source"] = None
    r["resistance_source"] = None
    out = render_short_midline(r)
    assert "← MA5支撑" not in out
    assert "← MA10压力" not in out


# ── Task 3: 删除「说明」行 ──

def test_no_conflict_line():
    """删除「说明：{conflict}」行。"""
    r = _report()
    r["conclusion"]["conflict"] = "周线偏空，短线也不追"
    out = render_short_midline(r)
    assert "说明：周线偏空" not in out


# ── 短线威科夫事件灯（英文灯 + 中文括号，只展示）──

def test_format_wyckoff_event_light_spring():
    line = format_wyckoff_event_light({
        "spring_signal": True,
        "spring_vol_class": "low_vol_confirm",
        "timeframe": "daily",
    })
    assert line.startswith("状态：Spring（弹簧）")
    assert "低位假跌破后收回" in line
    assert "偏多" in line


def test_format_wyckoff_midline_light_ar():
    """中线人话：阶段白话 · 灯（中文括号）· 防误读短句。"""
    line = format_wyckoff_midline_light({
        "ar_signal": True,
        "phase_label": "积累期 B（辅助：AR无BC）",
        "timeframe": "weekly",
    })
    assert line.startswith("威科夫：")
    assert "还在吸筹中" in line
    assert "AR（自动反弹）" in line
    assert "不能当已经转强" in line
    assert "高潮后快速反弹" not in line
    assert not line.endswith("偏多")


def test_format_wyckoff_midline_light_shows_box():
    """中线与短线同款：仅 L2/L3（真 ST）写成熟箱体上下沿。"""
    line = format_wyckoff_midline_light({
        "ar_signal": True,
        "phase": "accumulation_b",
        "phase_label": "积累期 B",
        "phase_a_status": "established",
        "sc_low": 40.3,
        "ar_high": 43.0,
        "secondary_test_sc_signal": True,
        "tr_maturity": "L2",
        "box_display_mode": "box",
        "timeframe": "weekly",
    })
    assert "箱体 40.30-43.00" in line
    assert "AR（自动反弹）" in line


def test_format_wyckoff_midline_light_forming_lower():
    line = format_wyckoff_midline_light({
        "sc_signal": True,
        "phase": "accumulation_a",
        "phase_label": "积累期 A（卖力高潮：SC，箱体未成形）",
        "phase_a_status": "forming",
        "sc_low": 38.14,
        "tr_maturity": "L1",
        "box_display_mode": "proto",
        "timeframe": "weekly",
    })
    assert "雏形" in line
    assert "下沿 38.14（上沿未出）" in line
    assert "箱体 38" not in line


def test_format_wyckoff_midline_light_gated_no_tr_suppresses_box():
    """中线与短线同构：no_tr 门控时不写 forming 箱体。"""
    line = format_wyckoff_midline_light({
        "sc_signal": True,
        "phase": "none",
        "phase_label": "",
        "phase_a_status": "forming",
        "phase_tr_gated": True,
        "phase_tr_gate_reason": "no_tr",
        "sc_low": 38.14,
        "timeframe": "weekly",
        "wyckoff_summary": "中线",
    })
    assert "箱体" not in line
    assert "下沿" not in line
    assert "SC（卖力高潮）" in line  # 事件灯可保留；只禁箱体


def test_phase_a_box_bounds_prefers_seed_over_tr():
    from trader_shared.wyckoff_core import _phase_a_box_bounds, _phase_a_box_phrase

    lo, hi = _phase_a_box_bounds({
        "tr_lower": 9.0,
        "tr_upper": 15.0,
        "phase_a_range": {"sc_low": 10.5, "ar_high": 12.5, "status": "established"},
        "phase_a_status": "established",
    })
    assert (lo, hi) == (10.5, 12.5)
    assert _phase_a_box_phrase({
        "phase_a_status": "established",
        "sc_low": 12.0,
        "ar_high": 10.0,
    }) == ""


def test_format_wyckoff_midline_light_event_without_phase():
    """有事件、无阶段时阶段位为「无」；事件 Code（中文）+ 短防误读。"""
    line = format_wyckoff_midline_light({
        "bullish_volume_divergence": True,
        "timeframe": "weekly",
        "wyckoff_summary": "中线",
    })
    assert line == "威科夫：无 · BullDiv（看多背离） · 不能当反转"


def test_format_wyckoff_event_light_none():
    line = format_wyckoff_event_light({"timeframe": "daily", "wyckoff_summary": "无"})
    assert "状态：—" in line
    assert "暂无事件" in line


def test_short_section_shows_event_light():
    """理论分析·短线含事件行；读 wyckoff_daily，不进评分。"""
    r = _report()
    r["wyckoff_daily"] = {
        "spring_signal": True,
        "spring_vol_class": "normal",
        "timeframe": "daily",
    }
    r["wyckoff_midline"] = {
        "timeframe": "weekly",
        "phase_label": "积累期 C",
        "spring_signal": False,
        "wyckoff_summary": "中线",
    }
    out = render_short_midline(r)
    assert "📐 理论分析" in out
    assert "\n  短线" in out
    assert "事件：Spring（弹簧）" in out
    # 中线 + 短线均有「威科夫：」点名行
    assert out.count("威科夫：") >= 2


def test_short_section_omits_empty_status_and_compacts_structure():
    """无威科夫事件不占事件行；缠论过长压缩；资金去掉「未取到」。"""
    r = _report()
    r["wyckoff_daily"] = {"timeframe": "daily", "wyckoff_summary": "无"}
    r["conclusion"]["wave_label"] = "回调段 · 盘整 · 回调一笔中 · 线段偏少"
    r["fusion"]["signals_detail"]["chan"] = {
        "direction": -1,
        "reason": "暂无买卖点 · 回调段 · 盘整 · 看跌",
    }
    r["fusion"]["signals_detail"]["vpf"] = {
        "direction": 0,
        "reason": "平量（量比1.3）（资金未取到）",
    }
    out = render_short_midline(r)
    short = _short_theory_block(out)
    head = short
    assert "事件：" not in head
    assert "状态：" not in head
    assert "缠论：" in short
    struct = [ln for ln in short.splitlines() if "缠论：" in ln][0]
    assert struct.count("·") <= 3 or "（暂无买卖点）" in struct
    assert "资金未取到" not in short
    assert "仪表：" not in short
    assert "决策：不推荐" not in short


def test_format_chanlun_short_light_buy1():
    line = format_chanlun_short_light({
        "chanlun": {
            "buy_points": [{"type": "一类买", "price": 10.0}],
            "sell_points": [],
            "divergence": {"bottom_divergence": True},
            "trend_label": "上涨",
        }
    })
    assert line.startswith("一买")
    assert "底背驰" in line
    assert "看涨" in line
    assert "（本周期）" in line  # 本周期信号标记（非区间套确认）


def test_format_chanlun_short_light_from_fusion_reason():
    """仅有 fusion reason 时也能解析出一买句式。"""
    line = format_chanlun_short_light(
        {},
        fusion_chan={"reason": "缠论一类买 (底背驰)", "direction": 1},
    )
    assert "一买" in line
    assert "看涨" in line


def test_short_section_chan_type_first():
    """理论分析·短线结构：类型优先（一买…）而非 reason 原文堆叠。"""
    r = _report()
    r["chanlun"] = {
        "chanlun": {
            "buy_points": [{"type": "一类买", "price": 42.0}],
            "sell_points": [],
            "divergence": {"bottom_divergence": True},
            "trend_label": "上涨",
        }
    }
    r["fusion"]["signals_detail"]["chan"] = {
        "reason": "缠论一类买 (底背驰)",
        "direction": 1,
    }
    out = render_short_midline(r)
    short = _short_theory_block(out)
    decision = _decision_block(out)
    assert "缠论：一买" in short
    assert "看涨" in short
    # 新骨架：缠论在理论区，动作在出手区；仍不用旧「出手：」行
    assert "动作：" in decision
    assert "出手：" not in short
    pos_struct = out.find("缠论：")
    pos_action = out.find("动作：")
    assert 0 <= pos_struct < pos_action


def test_r01_strategy_gates_omitted_from_report():
    """R-01: 人读报告省略 📐 策略（决策/动作已覆盖；闸口仍在 strategy_match）。"""
    r = _report()
    r["has_position"] = False
    r["discipline"] = {
        "suggested_pct_cap": 0,
        "allow_new_entry": False,
        "invalidation": "破止损作废",
        "action": "不新开",
    }
    r["chanlun"] = {
        "chanlun": {
            "buy_points": [{"type": "一类买", "price": 42.0}],
            "sell_points": [],
            "divergence": {},
            "trend_label": "上涨",
        }
    }
    out = render_short_midline(r)
    short = _decision_block(out)
    assert "📐 策略" not in short
    assert "选股：" not in short
    assert "动作：" in short or "决策：" in short or "新开：" in short


def test_r02_no_position_not_manage_active_tone():
    """R-02: 人读报告无 📐；若残留「持：」行不得写成已触发执行。"""
    r = _report()
    r["has_position"] = False
    r["cost"] = 0
    r["discipline"] = {"allow_new_entry": False, "action": "不新开", "suggested_pct_cap": 0}
    out = render_short_midline(r)
    short = _decision_block(out)
    assert "📐 策略" not in short
    if "持：" in short:
        hold_line = [ln for ln in short.splitlines() if "持：" in ln][0]
        assert "执行" not in hold_line or "预案" in hold_line


def test_r03_strategy_block_no_md_table():
    """R-03: 短线区无 markdown 表格/粗体（含省略 📐 后仍成立）。"""
    out = render_short_midline(_report())
    short = _short_theory_block(out)
    assert "**" not in short
    assert "|---|" not in short

# ── Task 4: ✅/⚠️ 具体化 ──

def test_highlight_specific():
    """亮点用具体数据，不用模板空话。"""
    out = render_short_midline(_report())
    assert "先看关键价与出手" not in out


def test_highlight_excludes_bearish_chan_and_weak_stage():
    """类二卖/看跌与转弱不得进 ✅ 亮点，应落在风险。"""
    r = _report()
    r["conclusion"]["stage_line"] = "转弱"
    r["fusion"]["signals_detail"]["chan"] = {
        "reason": "类二卖 · 反抽偏弱 · 看跌",
        "direction": -1,
    }
    out = render_short_midline(r)
    hl = next(ln for ln in out.splitlines() if "✅ 亮点" in ln)
    assert "类二卖" not in hl
    assert "看跌" not in hl
    assert "转弱" not in hl
    risk = next(ln for ln in out.splitlines() if "⚠️ 风险" in ln or ln.startswith("风险：") or "风险：" in ln)
    assert "类二卖" in risk or "看跌" in risk
    assert "转弱" in risk


def test_highlight_excludes_bearish_midline_stage_tag():
    """面板阶段带「偏空」或 midline_bias=bear 时，不得进 ✅ 亮点。"""
    r = _report()
    r["conclusion"]["stage_line"] = "主升初期"
    r["conclusion"]["midline"] = "盘整偏空 · 暂缓跟踪"
    r["midline_bias"] = "bear"
    r["fusion"]["signals_detail"]["chan"] = {
        "reason": "暂无买卖点 · 回调段 · 看跌",
        "direction": -1,
    }
    out = render_short_midline(r)
    hl = next(ln for ln in out.splitlines() if "✅ 亮点" in ln)
    assert "主升初期" not in hl
    assert "偏空" not in hl
    risk = next(ln for ln in out.splitlines() if "⚠️ 风险" in ln)
    assert "偏空" in risk or "主升初期" in risk


def test_short_section_has_daily_phase_line():
    """短线区必有「威科夫：」只读行（与中线点名同构）；禁止「日线阶段：」。"""
    r = _report()
    r["wyckoff_daily"] = {
        "timeframe": "daily",
        "phase": "none",
        "phase_a_status": "none",
        "phase_tr_gated": True,
        "phase_tr_gate_reason": "no_tr",
    }
    out = render_short_midline(r)
    short = _short_theory_block(out)
    assert "缠论：" in short
    assert "威科夫：" in short
    assert "日线阶段：" not in short
    assert "暂定不出" in short or "仅对照" in short
    assert "暂不出阶段" not in short
    # 仍在短线块内，且在缠论之后
    lines = [ln.strip() for ln in short.splitlines() if ln.strip()]
    struct_i = next(i for i, ln in enumerate(lines) if ln.startswith("缠论："))
    phase_i = next(i for i, ln in enumerate(lines) if ln.startswith("威科夫："))
    assert phase_i > struct_i


def test_wyckoff_l2_omits_measure_lines():
    """R-R5：L0-L2 沉默省略量度行，不写未达 L3 解释。"""
    r = _report()
    r["wyckoff_midline"] = {
        "timeframe": "weekly",
        "phase": "accumulation",
        "phase_label": "吸筹B",
        "tr_maturity": "L2",
        "measure_allowed": False,
        "tr_lower": 10.0,
        "tr_upper": 12.0,
        "cause_effect_up_target": 14.0,
        "cause_effect_down_target": 8.0,
    }
    out = render_short_midline(r)
    theory = _between(out, "📐 理论分析", "🎯 支撑阻力")
    assert "量度目标：" not in theory
    assert "下沿 10.00｜上沿 12.00（L3）" not in theory
    assert "未达 L3" not in out


def test_wyckoff_l3_measure_stays_under_theory():
    """R-R4/R-R5：L3 下沿/上沿 + 量度目标留在理论分析·威科夫下。"""
    r = _report()
    r["wyckoff_midline"] = {
        "timeframe": "weekly",
        "phase": "accumulation",
        "phase_label": "吸筹C",
        "tr_maturity": "L3",
        "measure_allowed": True,
        "tr_lower": 10.0,
        "tr_upper": 12.0,
        "cause_effect_up_target": 14.0,
        "cause_effect_down_target": 8.0,
        "pnf_method": "height_1to1_fallback",
    }
    r["wyckoff_daily"] = {
        "timeframe": "daily",
        "phase": "accumulation",
        "phase_label": "吸筹C",
        "tr_maturity": "L3",
        "measure_allowed": True,
        "tr_lower": 40.0,
        "tr_upper": 44.0,
        "cause_effect_up_target": 48.0,
        "cause_effect_down_target": 36.0,
    }
    out = render_short_midline(r)
    theory = _between(out, "📐 理论分析", "🎯 支撑阻力")
    support = _between(out, "🎯 支撑阻力", "✅ 出手")
    assert "下沿 10.00｜上沿 12.00（L3）" in theory
    assert "量度目标：上 14.00｜下 8.00（高度1:1，非出手）" in theory
    assert "下沿 40.00｜上沿 44.00（L3）" in theory
    assert "量度目标：上 48.00｜下 36.00（P&F，非出手）" in theory
    assert "量度目标：" not in support
    assert "（L3）" not in support


def test_risk_uses_short_resist():
    """风险行用短线 MA20 压力，不用中线远压力。"""
    out = render_short_midline(_report())
    assert "41.85" in out
    assert "44.65" in out


# ── Task 5: 中线筹码状态行 ──

def test_midline_chip_status():
    """中线区筹码方案 C：支撑 · 阻力 · 套牢面。"""
    out = render_short_midline(_report())
    assert "筹码：" in out
    assert "阻力 44.95" in out or "阻力 44.9" in out
    assert "套牢面大" in out  # profit 8.3%


def test_midline_chip_no_above_peak_graceful():
    """无上方峰时写阻力弱，不出现旧「套牢峰」文案。"""
    r = _report()
    r["chip_peaks"] = [{"price": 40.0, "volume": 100, "support_level": "弱支撑"}]
    r["chip_current_pct"] = 95.0
    out = render_short_midline(r)
    assert "套牢峰" not in out
    assert "阻力弱" in out
    assert "套牢面小" in out  # 获利盘 95%


def test_midline_chip_missing_graceful():
    """筹码数据缺失时不显示筹码行。"""
    r = _report()
    r["chip_peaks"] = []
    r["chip_current_pct"] = None
    out = render_short_midline(r)
    assert "筹码：" not in out


# ── Task 6: 动能行展示 reason 原文 ──

def test_momentum_reason_full():
    """动能行展示 reason 原文不截断。"""
    r = _report()
    r["fusion"]["signals_detail"]["momentum"]["reason"] = "MACD柱缩短（多头衰减）"
    out = render_short_midline(r)
    assert "动能：MACD柱缩短（多头衰减）" in out


def test_momentum_short_reason():
    """短 reason 保持原样。"""
    r = _report()
    r["fusion"]["signals_detail"]["momentum"]["reason"] = "动量中性"
    out = render_short_midline(r)
    assert "动能：动量中性" in out


# ── Task 7: 价量资金展示 vpf.reason 原文 ──

def test_vpf_reason_full():
    """价量资金行展示 vpf.reason 原文。"""
    out = render_short_midline(_report())
    assert "资金：平量（量比1.1，近3日-1.4%）" in out


def test_vpf_no_veto_no_append():
    """无 veto 时不追加资金流向。"""
    r = _report()
    r["fusion"]["fund_flow_outflow_veto_msg"] = None
    out = render_short_midline(r)
    fund_line = [l for l in out.split("\n") if "资金：" in l]
    if fund_line:
        assert "主力连续" not in fund_line[0]


def test_vpf_with_veto_appends():
    """有 veto 时追加到资金行（短标注）。"""
    r = _report()
    r["fusion"]["fund_flow_outflow_veto_msg"] = "连续 3 日主力净流出超阈值"
    out = render_short_midline(r)
    assert "连3日流出" in out or "主力连续3日净流出" in out or "连续 3 日主力净流出" in out


# ── Task 8: 调整天数 + 相对强弱降级 ──

def test_adjust_days():
    """meta 量价行并入调整天数（现版：调整N天）。"""
    out = render_short_midline(_report())
    assert "调整19天" in out


def test_atr_merged_into_volume_line():
    """ATR14（含复权口径）并入量比/换手/调整同行，禁止独立成行。"""
    out = render_short_midline(_report())
    assert "ATR14 1.85（未复权）" in out
    vol_line = next(
        ln for ln in out.splitlines()
        if "量比" in ln and "ATR14" in ln
    )
    assert "调整19天" in vol_line
    assert "换手3.0%" in vol_line
    # 不得再有仅含 ATR 的独立缩进行
    atr_only = [
        ln for ln in out.splitlines()
        if ln.strip().startswith("ATR14") or ln.strip().startswith("ATR口径")
    ]
    assert atr_only == []


def test_atr_adjust_label_only_when_atr_missing():
    """有复权口径但无有效 atr14 时写 ATR口径，仍并入量价行。"""
    r = _report()
    r["atr14"] = 0
    out = render_short_midline(r)
    assert "ATR口径 未复权" in out
    assert any("量比" in ln and "ATR口径" in ln for ln in out.splitlines())


def test_adjust_days_new_high():
    """创新高时显示「创新高」。"""
    r = _report()
    r["daily_bars"][-1]["high"] = 50.0
    out = render_short_midline(r)
    assert "创新高" in out


def test_meta_pure_d_board_without_sector():
    """无行业时 meta 仍标板块指数涨跌 + 个股；不写大盘/正常偏弱/跑赢。"""
    r = _report()
    r["symbol"] = "002050.SZ"
    r["extend_sector"] = {}
    r["market_env"] = {
        "level": "偏弱",
        "change_pct": 1.25,
        "index_label": "深成",
        "index_code": "399001.SZ",
    }
    out = render_short_midline(r)
    head = out.split("📐 理论分析")[0]
    assert "综合动能 转弱 ｜ 深成 +1.25% ｜ 个股 +0.82%" in out
    assert "大盘" not in head
    assert " 偏弱" not in head and "正常" not in head
    assert "相对强弱" not in out
    assert "行业：" not in out
    assert "跑赢" not in head


def test_meta_pure_d_with_sector():
    """有行业时并入 meta 短名；不单独行业行、不写跑赢。"""
    r = _report()
    r["symbol"] = "688248.SH"
    r["market_env"] = {
        "level": "正常",
        "change_pct": 2.99,
        "index_label": "科创",
        "index_code": "000688.SH",
    }
    r["extend_sector"] = {
        "status": "正常",
        "sector_name": "电气设备",
        "sector_change_pct": -3.44,
        "stock_vs_sector": "跑赢 +4.28%",
    }
    r["change_pct"] = 0.84
    out = render_short_midline(r)
    assert "综合动能 转弱 ｜ 科创 +2.99% ｜ 电气 -3.44% ｜ 个股 +0.84%" in out
    assert "行业：" not in out
    assert "跑赢" not in out.split("📐 理论分析")[0]


# ── Task 9: 中线关键价格式统一 ──

def test_mid_key_price_format():
    """中线关键价格式：价格前置 + 动作统一。"""
    out = render_short_midline(_report())
    assert "41.14 生命线" in out
    assert "41.14-46.69 回踩区" in out
    assert "56.00 压力位" in out or "56.00 压力" in out
    assert "68.82 目标位" in out or "68.82 目标" in out
