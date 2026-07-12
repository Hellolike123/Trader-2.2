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
        "major_stage": "蓄势",
        "conclusion": {
            "midline": "盘整偏空 · 暂缓跟踪",
            "stage_line": "蓄势",
            "execution": "现价不买 · 不追",
            "reason": "亏1.4/赚1.0，不划算",
            "this_week": "不追现价；回买点再谈",
            "conflict": "周线偏空，短线也不追",
            "wave_label": "回调见底 · 关注一类买｜底背驰",
            "wave_label_mid": "笔数不足 · 无法判断",
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


# ── Task 1: 盈亏比 ✓/✗ 判定 + 卖点区目标百分比 ──

def test_risk_reward_ratio_with_verdict():
    """盈亏比行带 ✓/✗ 判定符号（新标签：回踩低吸 / 现价跟进）。"""
    out = render_short_midline(_report())
    assert "回踩低吸：亏约" in out
    assert "现价跟进：亏约" in out
    assert "盈亏比 2.4:1 ✓ 值得关注" in out
    assert "盈亏比 0.4:1 ✗ 不划算" in out


def test_sell_zone_with_target_pct():
    """卖点区行带目标百分比。"""
    out = render_short_midline(_report())
    assert "目标+2.3%" in out


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


# ── Task 4: ✅/⚠️ 具体化 ──

def test_highlight_specific():
    """亮点用具体数据，不用模板空话。"""
    out = render_short_midline(_report())
    assert "先看关键价与出手" not in out


def test_risk_uses_short_resist():
    """风险行用短线 MA20 压力，不用中线远压力。"""
    out = render_short_midline(_report())
    assert "41.85" in out
    assert "44.65" in out


# ── Task 5: 中线筹码状态行 ──

def test_midline_chip_status():
    """中线区有筹码状态行。"""
    out = render_short_midline(_report())
    assert "筹码：获利盘 8.3%" in out
    assert "套牢峰 44.95" in out


def test_midline_chip_no_above_peak_graceful():
    """无上方峰时不显示套牢。"""
    r = _report()
    r["chip_peaks"] = [{"price": 40.0, "volume": 100, "support_level": "弱支撑"}]
    r["chip_current_pct"] = 95.0
    out = render_short_midline(r)
    assert "套牢峰" not in out


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
    assert "价量资金：平量（量比1.1，近3日-1.4%）" in out


def test_vpf_no_veto_no_append():
    """无 veto 时不追加资金流向。"""
    r = _report()
    r["fusion"]["fund_flow_outflow_veto_msg"] = None
    out = render_short_midline(r)
    vpf_line = [l for l in out.split("\n") if "价量资金" in l]
    if vpf_line:
        assert "主力连续" not in vpf_line[0]


def test_vpf_with_veto_appends():
    """有 veto 时追加到价量资金行。"""
    r = _report()
    r["fusion"]["fund_flow_outflow_veto_msg"] = "连续 3 日主力净流出超阈值"
    out = render_short_midline(r)
    assert "主力连续3日净流出" in out or "连续 3 日主力净流出" in out


# ── Task 8: 调整天数 + 相对强弱降级 ──

def test_adjust_days():
    """meta 区显示调整天数。"""
    out = render_short_midline(_report())
    assert "调整：第19天" in out


def test_adjust_days_new_high():
    """创新高时显示「创新高」。"""
    r = _report()
    r["daily_bars"][-1]["high"] = 50.0
    out = render_short_midline(r)
    assert "创新高" in out


def test_relative_strength_fallback_when_sector_empty():
    """extend_sector 为空但 market_env 有时 fallback 显示相对强弱。"""
    r = _report()
    r["extend_sector"] = {}
    out = render_short_midline(r)
    assert "相对强弱：跑赢大盘" in out


def test_relative_strength_when_present():
    """extend_sector 有数据时显示相对强弱。"""
    r = _report()
    r["extend_sector"] = {"status": "正常", "stock_vs_sector": "跑赢 +1.50%"}
    out = render_short_midline(r)
    assert "相对强弱：跑赢 +1.50%" in out


# ── Task 9: 中线关键价格式统一 ──

def test_mid_key_price_format():
    """中线关键价格式：价格前置 + 动作统一。"""
    out = render_short_midline(_report())
    assert "41.14 生命线" in out
    assert "41.14-46.69 回踩区" in out
    assert "56.00 压力位" in out or "56.00 压力" in out
    assert "68.82 目标位" in out or "68.82 目标" in out
