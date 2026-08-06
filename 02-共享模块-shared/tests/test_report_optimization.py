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
    """方案 C：撑/压/主峰；不写套牢面；无警报不写底部。"""
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
    assert "撑 50.00" in line or "下方难撑" in line
    assert "压 58.00" in line
    assert "多数套牢" not in line
    assert "多数获利" not in line
    assert "套牢中等" not in line
    assert "底部" not in line  # 无警报不写
    assert "｜" not in line


def test_format_chip_position_light_nanwang_like():
    """跌穿成本区：下方难撑 · 压位（不写套牢面）。"""
    line = format_chip_position_light(
        41.63,
        [
            {"price": 44.4, "share_of_total": 5},
            {"price": 50.4, "share_of_total": 15},
        ],
        {"has_history": True, "warning_level": "none", "migration_pct": 0},
        profit_pct=9.0,
    )
    assert "下方难撑" in line
    assert "压 44.40" in line
    assert "多数套牢" not in line
    assert "成本较" not in line  # 普通峰不是 15/85 分位，不写集中度


def test_format_chip_position_light_main_peak_where_cost_sits():
    """主筹码峰：标出主峰在哪（相对现价）。"""
    # 上方大峰
    above = format_chip_position_light(
        43.2,
        [
            {"price": 41.75, "share_of_total": 8, "volume": 50},
            {"price": 44.95, "share_of_total": 35, "volume": 200},
            {"price": 49.36, "share_of_total": 10, "volume": 60},
        ],
        None,
        profit_pct=8.0,
    )
    assert "主峰在 44.95 上方" in above

    # 下方大峰
    below = format_chip_position_light(
        46.0,
        [
            {"price": 41.75, "share_of_total": 30, "volume": 180},
            {"price": 44.95, "share_of_total": 12, "volume": 70},
            {"price": 49.36, "share_of_total": 9, "volume": 40},
        ],
        None,
        profit_pct=60.0,
    )
    assert "主峰在 41.75 下方" in below

    # 附近
    near = format_chip_position_light(
        45.0,
        [
            {"price": 44.80, "share_of_total": 28, "volume": 150},
            {"price": 50.00, "share_of_total": 10, "volume": 40},
        ],
        None,
        profit_pct=50.0,
    )
    assert "主峰在 44.80 附近" in near

    # 仅 15/85 分位时不把分位当主峰
    only_pct = format_chip_position_light(
        50.0,
        [
            {"price": 48.5, "share_of_total": 15},
            {"price": 51.0, "share_of_total": 85},
        ],
        None,
        profit_pct=55.0,
    )
    assert "主峰在" not in only_pct
    assert "成本较齐" in only_pct

    # 国电南瑞类：95 分位 30.00 绝不能盖过真实主峰 22.50
    gdnr_like = format_chip_position_light(
        24.54,
        [
            {"price": 22.50, "share_of_total": 9.59, "volume": 0},
            {"price": 22.80, "share_of_total": 7.48, "volume": 0},
            {"price": 24.00, "share_of_total": 6.35, "volume": 0},
            {"price": 24.60, "share_of_total": 5.22, "volume": 0},
            {"price": 21.60, "share_of_total": 5, "kind": "percentile", "percentile": 5},
            {"price": 22.50, "share_of_total": 15, "kind": "percentile", "percentile": 15},
            {"price": 24.00, "share_of_total": 50, "kind": "percentile", "percentile": 50},
            {"price": 26.40, "share_of_total": 85, "kind": "percentile", "percentile": 85},
            {"price": 30.00, "share_of_total": 95, "kind": "percentile", "percentile": 95},
        ],
        None,
        profit_pct=56.7,
    )
    assert "主峰在 22.50 下方" in gdnr_like
    assert "主峰在 30.00" not in gdnr_like


def test_format_chip_position_light_concentration_from_cyq_percentiles():
    """仅 cyq 15/85 分位可写偏集中/偏发散。"""
    tight = format_chip_position_light(
        50.0,
        [
            {"price": 48.5, "share_of_total": 15},
            {"price": 51.0, "share_of_total": 85},
        ],
        None,
        profit_pct=55.0,
    )
    assert "成本较齐" in tight

    wide = format_chip_position_light(
        50.0,
        [
            {"price": 40.0, "share_of_total": 15},
            {"price": 60.0, "share_of_total": 85},
        ],
        None,
        profit_pct=55.0,
    )
    assert "成本较散" in wide


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


# ── Task 1: 盈亏比 ✓/✗ 判定 + 卖点区目标百分比 ──

def _open_ladder_report() -> dict:
    """放行态 mock：共振齐 + 策略亮 + 纪律允许，短线才铺低吸/止盈阶梯。"""
    r = _report()
    r["discipline"] = {
        **(r.get("discipline") or {}),
        "allow_new_entry": True,
        "action": "试探",
        "suggested_pct_cap": 10,
        "entry_checklist": {"all_green": True},
    }
    r["conclusion"] = {
        **(r.get("conclusion") or {}),
        "execution": "试探 · 仓 10%",
        "midline": "趋势未坏 · 可跟踪",
        "reason": "",
    }
    r["resonance"] = {"grade": "aligned", "aligned": True}
    r["strategy_match"] = {
        "gates": {
            "entry": {
                "executable": True,
                "mode": "active",
                "primary": {"id": "pullback", "name": "回踩"},
            }
        }
    }
    r["decision_view"] = {
        "allow_new_recommend": True,
        "discipline_allow": True,
        "resonance_ok": True,
        "strategy_entry_lit": True,
        "summary_line": "可试探",
    }
    r["suggested_pct"] = 10
    return r


def test_risk_reward_ratio_with_verdict():
    """放行态：短线低吸区带盈亏比 ✓。"""
    out = render_short_midline(_open_ladder_report())
    assert "回踩买" in out
    assert "盈亏比 2.4:1 ✓" in out


def test_sell_zone_with_target_pct():
    """放行态：止盈区行带目标百分比。"""
    out = render_short_midline(_open_ladder_report())
    assert "止盈区" in out
    assert "目标+" in out


# ── Task 2: 价格阶梯来源标注 ──

def test_price_source_annotation():
    """放行态：买点区/卖点区带来源标注。"""
    out = render_short_midline(_open_ladder_report())
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


def test_w_diff1_forming_no_ar_high_rejects_tr_upper():
    """W-DIFF-1 / M-R1：forming 无 ar_high 时禁止分位 tr_upper 冒充上沿。"""
    from trader_shared.wyckoff_core import _phase_a_box_bounds, _phase_a_box_phrase

    wyk = {
        "phase_a_status": "forming",
        "box_display_mode": "proto",
        "tr_maturity": "L1",
        "tr_upper": 92.9,
        "tr_lower": 80.0,
        "sc_low": 82.0,
        "ar_high": None,
        "phase_a_range": {
            "status": "forming",
            "sc_low": 82.0,
            "ar_high": None,
        },
    }
    lo, hi = _phase_a_box_bounds(wyk)
    assert lo == 82.0
    assert hi is None
    phrase = _phase_a_box_phrase(wyk)
    assert "上沿未出" in phrase
    assert "92.9" not in phrase
    assert "雏形 82.00-92.90" not in phrase
    assert "（待 ST）" not in phrase


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
    """⚡ 短线威科夫并入事件；读 wyckoff_daily，不进评分；无独立事件行。"""
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
    assert "⚡ 短线" in out
    short = out.split("⚡ 短线", 1)[-1]
    assert "事件：" not in short
    wyk = next(ln for ln in short.splitlines() if ln.strip().startswith("威科夫："))
    assert "Spring" in wyk
    assert "不作买点" in wyk
    # 中线 + 短线均有「威科夫：」点名行
    assert out.count("威科夫：") >= 2


def test_cd2b_midline_daily_fallback_survives_wave_label_rendering():
    """C-D2b：wave_label_mid 覆盖 compact 行时仍须标明日线 fallback。"""
    r = _report()
    r["chanlun_midline"] = {
        "chanlun": {
            "timeframe": "daily_fallback",
            "structure_type": "上涨趋势",
            "structure_confidence": "high",
            "trend_label": "拉升段",
            "strokes": [
                {"direction": "up"},
                {"direction": "down"},
                {"direction": "up"},
            ],
            "segments": [{"direction": "up"}],
            "buy_points": [],
            "sell_points": [],
            "divergence": {},
        }
    }
    # 生产缺口：该字段会盖掉 format_chanlun_theory_line 的「（日线）」。
    r["conclusion"]["wave_label_mid"] = "拉升趋势中 · 线段偏少"

    out = render_short_midline(r)
    midline = out.split("🧭 中线", 1)[-1].split("⚡ 短线", 1)[0]
    chan_line = next(line for line in midline.splitlines() if "缠论：" in line)

    assert "日线" in chan_line


def test_cd1a_daily_insufficient_reaches_final_shortline_panel():
    """C-D1a：生产报告的 chanlun_daily 不足原因不能被旧 fusion 槽盖掉。"""
    r = _report()
    r["chanlun_daily"] = {
        "chanlun": {
            "timeframe": "insufficient",
            "data_ok": False,
            "data_note": "日线不足：仅8根，至少需要20根",
            "data_bars_daily": 8,
            "data_bars_weekly": 0,
            "adjust_mode": "unknown",
            "buy_points": [],
            "sell_points": [],
            "divergence": {},
        }
    }
    r["fusion"]["signals_detail"]["chan"] = {
        "direction": 0,
        "reason": "暂无买卖点 · 中性",
    }

    out = render_short_midline(r)
    shortline = out.split("⚡ 短线", 1)[-1]
    chan_line = next(line for line in shortline.splitlines() if "缠论：" in line)

    assert "日线不足" in chan_line
    assert "暂无买卖点 · 中性" not in chan_line


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
    short = out.split("⚡ 短线", 1)[-1]
    head = short.split("关键价", 1)[0]
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
    assert "（观察）" not in line


def test_format_chanlun_short_light_observe_tier_like2():
    """O-T 可选：类二买短名旁标观察；不改 type_raw / fusion 计分。"""
    from trader_shared.chan_core import resolve_chanlun_primary

    chan = {
        "chanlun": {
            "buy_points": [{"type": "类二买", "price": 346.16, "confidence": 1}],
            "sell_points": [],
            "divergence": {},
            "trend_label": "回调段",
        }
    }
    info = resolve_chanlun_primary(chan)
    assert info["type_raw"] == "类二买"
    assert info["type_short"] == "类二买"  # resolve 不变，仅 light 展示加观察
    line = format_chanlun_short_light(chan)
    assert line.startswith("类二买（观察）")
    assert "回踩偏弱" in line
    assert "看涨" in line


def test_format_chanlun_short_light_does_not_infer_point_from_fusion_reason():
    """C-D3b/c/d：引擎无点时，fusion 文案不得补出买点或下单叙事。"""
    line = format_chanlun_short_light(
        {
            "chanlun": {
                "buy_points": [],
                "sell_points": [],
                "divergence": {},
                "trend_label": "回调段",
            }
        },
        fusion_chan={"reason": "缠论一类买 (底背驰)", "direction": 1},
        wave_label="接近一买 · 可低吸 · 回调见底",
    )
    assert line.startswith("暂无买卖点")
    assert "回调段" in line
    assert "回调见底" in line
    assert "一买" not in line
    assert "一类买" not in line
    assert not any(word in line for word in ("宜买", "可执行", "可低吸", "该买了"))


def test_short_midline_chan_exception_fallback_fail_closed(monkeypatch):
    """C-D3c/d：format 抛错时不得把 fusion reason/下单词灌进面板。"""
    import trader_shared.chan_core as chan_core

    def _boom(*_a, **_k):
        raise RuntimeError("forced")

    monkeypatch.setattr(chan_core, "format_chanlun_short_light", _boom)
    r = _report()
    r["fusion"]["signals_detail"]["chan"] = {
        "reason": "缠论一类买 · 可低吸",
        "direction": 1,
    }
    out = render_short_midline(r)
    short = out.split("⚡ 短线", 1)[-1].split("关键价", 1)[0]
    assert "缠论：暂无信号 · 中性" in short
    assert "一买" not in short
    assert "可低吸" not in short


def test_short_section_chan_type_first():
    """⚡ 短线结构：类型优先（一买…）而非 reason 原文堆叠。"""
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
    short = out.split("⚡ 短线", 1)[-1].split("关键价", 1)[0]
    assert "缠论：一买" in short
    assert "看涨" in short
    # A 版读序：缠论在动作前，且用「动作」不用「出手」
    assert "动作：" in short
    assert "出手：" not in short
    pos_struct = short.find("缠论：")
    pos_action = short.find("动作：")
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
    short = out.split("⚡ 短线", 1)[-1]
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
    short = out.split("⚡ 短线", 1)[-1].split("关键价", 1)[0]
    assert "📐 策略" not in short
    if "持：" in short:
        hold_line = [ln for ln in short.splitlines() if "持：" in ln][0]
        assert "执行" not in hold_line or "预案" in hold_line


def test_r03_strategy_block_no_md_table():
    """R-03: 短线区无 markdown 表格/粗体（含省略 📐 后仍成立）。"""
    out = render_short_midline(_report())
    short = out.split("⚡ 短线", 1)[-1] if "⚡ 短线" in out else out
    assert "**" not in short
    assert "|---|" not in short

# ── Task 4: ✅/⚠️ 具体化 ──

def test_highlight_specific():
    """亮点用具体数据，不用模板空话。"""
    out = render_short_midline(_report())
    assert "先看关键价与出手" not in out


def test_highlight_excludes_bearish_chan_and_weak_stage():
    """类二卖/看跌与转弱不得进 ✅ 亮点，应落在风险（引擎卖点，非 fusion 手补）。"""
    r = _report()
    r["conclusion"]["stage_line"] = "转弱"
    r["chanlun"] = {
        "chanlun": {
            "buy_points": [],
            "sell_points": [{"type": "类二卖", "price": 45.0}],
            "divergence": {},
            "trend_label": "回调段",
        }
    }
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
    assert "类二卖" in risk or "二卖" in risk
    assert "转弱" in risk


def test_highlight_excludes_bearish_midline_stage_tag():
    """面板阶段带「偏空」或 midline_bias=bear 时，不得进 ✅ 亮点。"""
    r = _report()
    r["conclusion"]["stage_line"] = "主升初期"
    r["conclusion"]["midline"] = "盘整偏空 · 暂缓跟踪"
    r["midline_bias"] = "bear"
    r["chanlun"] = {
        "chanlun": {
            "buy_points": [],
            "sell_points": [],
            "divergence": {},
            "trend_label": "回调段",
        }
    }
    r["fusion"]["signals_detail"]["chan"] = {
        "reason": "暂无买卖点 · 回调段 · 看跌",
        "direction": -1,
    }
    out = render_short_midline(r)
    hl = next(ln for ln in out.splitlines() if "✅ 亮点" in ln)
    assert "主升初期" not in hl
    assert "偏空" not in hl
    # 面板无定论行；D-R7 关闭态风险优先现价不宜追，不复读整段「中线偏空」
    assert not any(ln.lstrip().startswith("定论：") for ln in out.splitlines())
    risk = next(ln for ln in out.splitlines() if "⚠️ 风险" in ln)
    assert "现价不宜追" in risk or "偏空" in risk or "主升初期" in risk


def test_cd3_panel_no_fusion_buy_without_engine_point():
    """C-D3b/c/d：中线浪型与亮点不得从 fusion/污染 wave 露出买点、背驰或下单词。"""
    r = _report()
    r["chanlun"] = {
        "chanlun": {
            "buy_points": [],
            "sell_points": [],
            "divergence": {},
            "trend_label": "回调段",
            "timeframe": "daily",
        }
    }
    r["chanlun_midline"] = {
        "chanlun": {
            "buy_points": [],
            "sell_points": [],
            "divergence": {},
            "trend_label": "拉升段",
            "timeframe": "weekly",
            "strokes": [
                {"direction": "up", "end_price": 40.0},
                {"direction": "down", "end_price": 38.0},
                {"direction": "up", "end_price": 43.0},
            ],
        }
    }
    r["conclusion"]["wave_label_mid"] = "拉升趋势中 · 关注一类买｜底背驰"
    r["fusion"]["signals_detail"]["chan"] = {
        "reason": "缠论一类买 · 可低吸",
        "direction": 1,
    }
    out = render_short_midline(r)
    mid = out.split("🧭 中线", 1)[-1].split("⚡ 短线", 1)[0]
    hl = next(ln for ln in out.splitlines() if "✅ 亮点" in ln)
    chan_line = next(ln for ln in mid.splitlines() if "缠论：" in ln)
    for forbidden in (
        "一类买", "一买", "关注一类", "接近一买", "可低吸", "宜买", "该买了",
        "底背驰", "顶背驰",
    ):
        assert forbidden not in chan_line
        assert forbidden not in hl
    assert "拉升趋势中" in chan_line


def test_cd4e_trader_midline_wave_label_demoted():
    """C-D4e：Trader 中线 wave 路径也须笔尖离价降级，禁拉升趋势中·看涨。"""
    r = _report()
    r["current"] = 95.0
    r["chanlun_midline"] = {
        "chanlun": {
            "buy_points": [],
            "sell_points": [],
            "divergence": {},
            "trend_label": "拉升段",
            "timeframe": "weekly",
            "strokes": [
                {"direction": "up", "end_price": 120.0},
                {"direction": "down", "end_price": 110.0},
                {"direction": "up", "end_price": 187.0},
            ],
        }
    }
    r["conclusion"]["wave_label_mid"] = "拉升趋势中 · 线段偏少"
    out = render_short_midline(r)
    mid = out.split("🧭 中线", 1)[-1].split("⚡ 短线", 1)[0]
    chan_line = next(ln for ln in mid.splitlines() if "缠论：" in ln)
    assert "高点已离开·向下未成笔" in chan_line
    assert "拉升趋势中" not in chan_line
    assert "看涨" not in chan_line


def test_cd3_midline_wave_sanitized_even_with_engine_sell():
    """C-D3：有引擎卖点时，污染浪型里的买点宣称/下单词仍须剔除。"""
    r = _report()
    r["chanlun_midline"] = {
        "chanlun": {
            "buy_points": [],
            "sell_points": [{"type": "一类卖", "price": 50.0}],
            "divergence": {},
            "trend_label": "拉升段",
            "timeframe": "weekly",
            "strokes": [
                {"direction": "up", "end_price": 40.0},
                {"direction": "down", "end_price": 38.0},
                {"direction": "up", "end_price": 43.0},
            ],
        }
    }
    r["conclusion"]["wave_label_mid"] = "拉升趋势中 · 关注一类买｜可低吸"
    out = render_short_midline(r)
    mid = out.split("🧭 中线", 1)[-1].split("⚡ 短线", 1)[0]
    chan_line = next(ln for ln in mid.splitlines() if "缠论：" in ln)
    assert "一类卖" in chan_line or "一卖" in chan_line
    for forbidden in ("关注一类买", "一类买", "一买", "可低吸", "宜买", "该买了"):
        assert forbidden not in chan_line


def test_cd3_midline_opposite_divergence_stripped_from_wave_state():
    """C-D3：单侧引擎背驰时，浪型状态段不得残留相反背驰。"""
    r = _report()
    base_strokes = [
        {"direction": "up", "end_price": 40.0},
        {"direction": "down", "end_price": 38.0},
        {"direction": "up", "end_price": 43.0},
    ]

    r_top = dict(r)
    r_top["chanlun_midline"] = {
        "chanlun": {
            "buy_points": [],
            "sell_points": [],
            "divergence": {"top_divergence": True, "bottom_divergence": False},
            "trend_label": "拉升段",
            "timeframe": "weekly",
            "strokes": list(base_strokes),
        }
    }
    r_top["conclusion"] = dict(r["conclusion"])
    r_top["conclusion"]["wave_label_mid"] = "底背驰 · 拉升趋势中"
    out_top = render_short_midline(r_top)
    mid_top = out_top.split("🧭 中线", 1)[-1].split("⚡ 短线", 1)[0]
    chan_top = next(ln for ln in mid_top.splitlines() if "缠论：" in ln)
    assert "底背驰" not in chan_top
    assert "顶背驰" in chan_top or "看跌" in chan_top

    r_bot = dict(r)
    r_bot["chanlun_midline"] = {
        "chanlun": {
            "buy_points": [],
            "sell_points": [],
            "divergence": {"top_divergence": False, "bottom_divergence": True},
            "trend_label": "回调段",
            "timeframe": "weekly",
            "strokes": list(base_strokes),
        }
    }
    r_bot["conclusion"] = dict(r["conclusion"])
    r_bot["conclusion"]["wave_label_mid"] = "顶背驰 · 回调见底"
    out_bot = render_short_midline(r_bot)
    mid_bot = out_bot.split("🧭 中线", 1)[-1].split("⚡ 短线", 1)[0]
    chan_bot = next(ln for ln in mid_bot.splitlines() if "缠论：" in ln)
    assert "顶背驰" not in chan_bot
    assert "底背驰" in chan_bot or "看涨" in chan_bot


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
    short = out.split("⚡ 短线", 1)[-1]
    assert "缠论：" in short
    assert "威科夫：" in short
    assert "日线阶段：" not in short
    assert "暂定不出" in short or "不作买点" in short or "仅对照" in short
    assert "不作买点" in short
    assert "暂不出阶段" not in short
    # 仍在短线块内，且在缠论之后
    lines = [ln.strip() for ln in short.splitlines() if ln.strip()]
    struct_i = next(i for i, ln in enumerate(lines) if ln.startswith("缠论："))
    phase_i = next(i for i, ln in enumerate(lines) if ln.startswith("威科夫："))
    assert phase_i > struct_i


def test_risk_uses_short_resist():
    """风险行用短线 MA20 压力，不用中线远压力。"""
    out = render_short_midline(_report())
    assert "41.85" in out
    assert "44.65" in out


# ── Task 5: 中线筹码状态行 ──

def test_midline_chip_status():
    """中线区筹码方案 C：撑/压/主峰。"""
    out = render_short_midline(_report())
    assert "筹码：" in out
    assert "压 44.95" in out or "压 44.9" in out
    assert "多数套牢" not in out


def test_midline_chip_no_above_peak_graceful():
    """无上方峰时写上方阻力弱，不出现旧「套牢峰」文案。"""
    r = _report()
    r["chip_peaks"] = [{"price": 40.0, "volume": 100, "support_level": "弱支撑"}]
    r["chip_current_pct"] = 95.0
    out = render_short_midline(r)
    assert "套牢峰" not in out
    assert "上方阻力弱" in out
    assert "多数获利" not in out


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


def test_fund_line_appends_main_force_and_relation():
    """资金行可附加主力评分 / 价资关系 / 大单短标签。"""
    r = _report()
    r["fund_flow_features"] = {
        "cum_flow_5d_wan": -1800,
        "consecutive_outflow_days": 3,
        "flow_price_relation": "价涨资出",
    }
    r["main_force_score"] = {"total_score": 4, "label": "偏弱"}
    r["big_order_direction"] = "偏卖"
    out = render_short_midline(r)
    fund_line = next(l for l in out.split("\n") if "资金：" in l)
    assert "连3日流出" in fund_line
    assert "价涨资出" in fund_line
    assert "主力4/15" in fund_line
    assert "大单偏卖" in fund_line


def test_fund_line_marks_estimate_and_stale_source():
    """资金估 / 资金偏旧 短标注。"""
    from datetime import date, timedelta

    r = _report()
    old = (date.today() - timedelta(days=5)).strftime("%Y%m%d")
    r["fund_flow_features"] = {
        "cum_flow_5d_wan": -50,
        "consecutive_outflow_days": 0,
        "flow_price_relation": "无数据",
        "data_source": "bars_estimate",
        "latest_fund_date": old,
    }
    r["main_force_score"] = {}
    r["big_order_direction"] = None
    out = render_short_midline(r)
    fund_line = next(l for l in out.split("\n") if "资金：" in l)
    assert "资金估" in fund_line
    assert "资金偏旧" in fund_line


def test_risk_flags_prefix_hard_flags():
    """ST/停牌/新股硬旗前置到风险行。"""
    r = _report()
    r["risk_flags"] = ["ST", "新股"]
    out = render_short_midline(r)
    risk_line = next(l for l in out.split("\n") if l.startswith("⚠️ 风险："))
    assert risk_line.index("ST") < risk_line.index("现价不宜追")
    assert "新股" in risk_line


# ── Task 8: 调整天数 + 相对强弱降级 ──

def test_adjust_days():
    """meta 量价行并入调整天数（现版：调整N天）。"""
    out = render_short_midline(_report())
    assert "调整19天" in out


def test_atr_merged_into_volume_line():
    """顶栏 A：量能行含量比/换手/调整；ATR 默认不进顶栏、无独立 ATR 行。"""
    out = render_short_midline(_report())
    vol_line = next(ln for ln in out.splitlines() if ln.lstrip().startswith("量能："))
    assert "量比" in vol_line and "调整19天" in vol_line
    assert "换手3.0%" in vol_line
    assert "ATR14" not in vol_line
    assert "ATR14" not in out.split("🧭", 1)[0]
    atr_only = [
        ln for ln in out.splitlines()
        if ln.strip().startswith("ATR14") or ln.strip().startswith("ATR口径")
    ]
    assert atr_only == []


def test_atr_adjust_label_only_when_atr_missing():
    """顶栏 A：无有效 atr14 时也不在顶栏写 ATR口径。"""
    r = _report()
    r["atr14"] = 0
    out = render_short_midline(r)
    head = out.split("🧭", 1)[0]
    assert "ATR口径" not in head
    assert "ATR14" not in head


def test_adjust_days_new_high():
    """创新高时显示「创新高」。"""
    r = _report()
    r["daily_bars"][-1]["high"] = 50.0
    out = render_short_midline(r)
    assert "创新高" in out


def test_meta_pure_d_board_without_sector():
    """无行业时环境行：指数 + 动能；无个股%、无大盘/正常偏弱/跑赢。"""
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
    head = out.split("🧭")[0]
    assert "环境：深成 +1.25% ｜ 动能 转弱" in out
    assert "个股 +" not in head
    assert "大盘" not in head
    assert " 偏弱" not in head and "正常" not in head
    assert "相对强弱" not in out
    assert "行业：" not in out
    assert "跑赢" not in head
    assert "量能：" in head


def test_meta_pure_d_with_sector():
    """有行业时并入环境行短名；无个股%、不单独行业行、不写跑赢。"""
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
    head = out.split("🧭")[0]
    assert "环境：科创 +2.99% ｜ 电气 -3.44% ｜ 动能 转弱" in out
    assert "个股 +" not in head
    assert "行业：" not in out
    assert "跑赢" not in head


# ── Task 9: 中线关键价格式统一 ──

def test_mid_key_price_format():
    """中线关键价阶梯：价格升序；>+30% 目标/压力不进阶梯。"""
    out = render_short_midline(_report())
    mid = out.split("⚡ 短线", 1)[0]
    assert "41.14 生命线" in mid
    assert "MA20" in mid or "MA250" in mid
    # 56 压力 +30% 边界可留；68 目标 +59% 必须去掉
    assert "68.82" not in mid
    # 严格升序（抓关键价块数字行）
    block = []
    grab = False
    for ln in mid.splitlines():
        if "关键价（中线）" in ln:
            grab = True
            continue
        if grab:
            if not ln.strip():
                break
            if ln.strip().startswith("现价") or any(ch.isdigit() for ch in ln):
                block.append(ln)
    prices = []
    for ln in block:
        m = __import__('re').search(r"(\d+\.\d+)", ln.replace('🌟',''))
        if m:
            prices.append(float(m.group(1)))
    assert prices == sorted(prices), prices


# ── 面板减重 D-R1…D-R8（trader-panel-declutter-handoff）──

def _closed_declutter_report() -> dict:
    """关闭态样例：无仓 + 不新开 + 框破坏偏空。"""
    r = _report()
    r["has_position"] = False
    r["weekly_frame"] = "破坏"
    r["discipline"] = {
        "allow_new_entry": False,
        "action": "不新开",
        "suggested_pct_cap": 0,
        "invalidation": "破止损作废",
        "weekly_frame": "破坏",
    }
    r["conclusion"]["execution"] = "不新开 · 不追现价 · 仓 0%"
    r["conclusion"]["midline"] = "中线框破坏 · 战略减/清倾向"
    r["conclusion"]["midline_verdict_note"] = (
        "威科夫无阶段 × 缠论盘整 → 双源无明确方向"
    )
    r["conclusion"]["stage_line"] = "无阶段"
    r["mid_key_prices"] = {
        **r["mid_key_prices"],
        "line_pullback": "41.14-46.69 回踩区（到了分批低吸）",
        "line_golden_buy": "42.00 黄金买点（50%回撤·最佳低吸位）",
    }
    return r


def test_d_r1_verdict_no_stack_bias_on_no_direction():
    """D-R1：面板不再展示定论行；内部 rewrite 仍去硬叠（字段侧）。"""
    from trader_shared.report_renderer.short_midline import _rewrite_declutter_verdict_note

    r = _closed_declutter_report()
    out = render_short_midline(r)
    assert not any(ln.lstrip().startswith("定论：") for ln in out.splitlines())
    note = _rewrite_declutter_verdict_note(
        r["conclusion"]["midline_verdict_note"],
        bias_tag="偏空",
        bias_short="中线框破坏战略减清倾向",
        mid=r["conclusion"]["midline"],
        weekly_frame="破坏",
        stage_line=r["conclusion"].get("stage_line") or "",
    )
    assert "双源无明确方向" not in note
    assert "无方向 · 偏空" not in note
    assert "中线框破坏" in note and "偏空" in note and "战略减" in note
    assert "仅副读" in note


def test_d_r2_plan_buy_zone_when_not_allowed():
    """D-R2：关闭态短线阶梯不铺计划买区/低吸区；用站稳线。"""
    out = render_short_midline(_closed_declutter_report())
    short = out.split("⚡ 短线", 1)[1]
    assert "计划买区" not in short
    assert "低吸区" not in short
    assert "回踩买" not in short
    assert "站稳线" in short or "止损" in short


def test_d_r3_ma5_observe_when_closed():
    """D-R3：关闭态 MA5 为观察，无加仓试探。"""
    out = render_short_midline(_closed_declutter_report())
    assert "加仓试探" not in out
    assert "MA5 支撑（观察）" in out


def test_d_r4_spot_no_hold_when_flat():
    """D-R4：无仓现价注解为不追，无「持有」。"""
    out = render_short_midline(_closed_declutter_report())
    spot = next(ln for ln in out.splitlines() if "🌟" in ln and "现价" in ln)
    assert "不追" in spot
    assert "持有" not in spot


def test_d_r5_t0_disabled_when_flat_closed():
    """D-R5：无仓+不新开 → 仅无底仓不启用，无日内 T0/低吸。"""
    out = render_short_midline(_closed_declutter_report())
    assert "T0：无底仓，不启用（与出手一致，不新开）" in out
    assert "日内 T0：" not in out
    # 短线关键价区计划买区可有「未放行」，但 T0 行不得含低吸
    t0_lines = [ln for ln in out.splitlines() if "T0" in ln]
    assert t0_lines
    assert all("低吸" not in ln for ln in t0_lines)


def test_d_r6_mid_key_no_low_absorb_verbs_when_closed():
    """D-R6：关闭/偏空时中线关键价无低吸动词；重叠大回踩可省略。"""
    out = render_short_midline(_closed_declutter_report())
    mid = out.split("⚡ 短线", 1)[0]
    assert "低吸" not in mid
    assert "最佳低吸" not in mid
    # 黄金若在阶梯中，须是黄金位而非最佳低吸
    gold_lines = [ln for ln in mid.splitlines() if "黄金" in ln]
    for gl in gold_lines:
        assert "黄金位" in gl or "50%回撤" in gl
        assert "最佳低吸" not in gl


def test_d_r7_risk_no_repeat_bias_blob():
    """D-R7：风险不含整段中线偏空复读。"""
    out = render_short_midline(_closed_declutter_report())
    risk = next(ln for ln in out.splitlines() if "⚠️ 风险" in ln)
    assert "中线偏空" not in risk
    assert "现价不宜追" in risk


def test_d_r8_t0_intraday_ok_with_position():
    """D-R8：有仓时可打日内 T0 低吸/高抛（不误伤）。"""
    r = _closed_declutter_report()
    r["has_position"] = True
    r["cost"] = 40.0
    out = render_short_midline(r)
    assert "日内 T0：" in out
    assert "低吸" in out
    assert "无底仓，不启用" not in out
