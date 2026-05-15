from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CONTRACTS = ROOT.parents[1] / "02-共享模块-shared" / "03-输出校验-contracts"
SHARED = ROOT.parents[1] / "02-共享模块-shared"
SHARED_CANDIDATE = ROOT.parents[1] / "02-共享模块-shared" / "02-候选逻辑-candidate"
SHARED_MARKET = ROOT.parents[1] / "02-共享模块-shared" / "01-行情数据-market-data"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))
if str(SHARED_CANDIDATE) not in sys.path:
    sys.path.insert(0, str(SHARED_CANDIDATE))
if str(SHARED_MARKET) not in sys.path:
    sys.path.insert(0, str(SHARED_MARKET))
for name in ("config", "light_data", "contract_utils", "candidate_core", "candidate_model", "validate_output", "models"):
    sys.modules.pop(name, None)

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from candidate_core import build_candidate_levels
from run_analysis import build_signal, render_markdown, volume_observation
from signal_contract import validate_signal
from validate_output import validate


def sample_report() -> dict:
    return {
        "name": "南网科技",
        "symbol": "688248.SH",
        "analysis_time": "2026-04-25 15:00",
        "current": 56.4,
        "change_pct": -5.39,
        "weekly_close": 56.4,
        "monthly_close": 57.93,
        "support": 55.87,
        "resistance": 60.55,
        "confirm": 60.55,
        "stop": 54.75,
        "take": 64.18,
        "stage": "修复",
        "scene": "防守观察",
        "low_zone": "55.87-56.43元",
        "replay": "04/01-04/07 回踩窗口（-1.00%）",
        "volume_text": "分时量能正常。",
        "upward_momentum": "价格还没贴近确认区，结论：动能仍是弱修复，暂不按启动处理。",
        "range_low": 54.6,
        "range_high": 65.0,
        "ma": {"ma5": "57.96", "ma10": "--", "ma20": "--", "ma30": "--"},
    }


def test_render_contract() -> None:
    markdown = render_markdown(sample_report())

    assert markdown.startswith("分析报告 — ") or markdown.startswith("📍")
    assert "MA5" in markdown
    assert "📍 决策" in markdown
    assert "❗ 关键价位" in markdown
    assert "🧭 简要分析" in markdown
    assert "✨ 亮点" in markdown
    assert "⚠️ 风险" in markdown
    assert "止损" in markdown
    assert "试探买" in markdown
    assert "止损" in markdown
    assert "执行价" not in markdown
    assert "t0-trader" not in markdown
    assert validate(markdown) == []


def test_build_signal_contract_from_sample_report() -> None:
    signal = build_signal(sample_report())

    assert signal["contract"] == "trader_signal_v1"
    assert signal["source_skill"] == "trader"
    assert signal["symbol"] == "688248.SH"
    assert signal["name"] == "南网科技"
    assert signal["signal_type"] == "wait_for_confirmation"
    assert signal["direction"] == "bullish_lean"
    assert signal["action"] == "observe"
    assert signal["trigger"]["price"] == 60.55
    assert signal["invalidation"]["price"] == 54.75
    assert signal["position"]["max_total_pct"] == 30
    assert validate_signal(signal) == []


def make_bars() -> list[dict]:
    closes = [
        10.00,
        10.20,
        10.10,
        10.40,
        10.30,
        10.50,
        10.70,
        10.60,
        10.80,
        10.90,
        10.70,
        10.50,
        10.30,
        10.20,
        10.10,
        10.00,
        9.90,
        10.00,
        10.10,
        10.20,
        10.30,
        10.40,
        10.50,
        10.60,
        10.70,
        10.80,
        10.90,
        11.00,
        11.10,
        11.20,
    ]
    bars = []
    for index, close in enumerate(closes, start=1):
        bars.append(
            {
                "date": f"2026-04-{index:02d}",
                "open": close - 0.05,
                "high": close + 0.20,
                "low": close - 0.20,
                "close": close,
                "volume": 1000 + index,
            }
        )
    return bars


def test_candidate_confirm_uses_real_resistance_not_current_multiplier() -> None:
    bars = make_bars()
    levels = build_candidate_levels(10.50, bars, quote={"high": 10.72, "low": 10.32})
    resistance_prices = {item["price"] for item in levels["resistance_levels"]}

    # confirm_price = nearest resistance * (1 + MIN_CONFIRM_SPACE_PCT)
    # not current_price * arbitrary multiplier
    confirm = levels["confirm_price"]
    assert confirm not in resistance_prices  # intentional: it's resistance + buffer
    # Should be close to some resistance * 1.008 (MIN_CONFIRM_SPACE_PCT = 0.008)
    from trader_shared.config import MIN_CONFIRM_SPACE_PCT
    assert any(
        abs(confirm - round(r * (1 + MIN_CONFIRM_SPACE_PCT), 2)) < 0.02
        for r in resistance_prices
    ), f"{confirm} should derive from resistance * 1.008"
    # Must NOT be current * 1.02
    assert confirm != round(10.50 * 1.02, 2)


def test_dynamic_low_zone_and_stop_use_volatility_buffer() -> None:
    bars = make_bars()
    levels = build_candidate_levels(10.50, bars, quote={"high": 10.72, "low": 10.32})

    assert 0.005 <= levels["zone_width_pct"] <= 0.012
    assert 0.008 <= levels["stop_buffer_pct"] <= 0.025
    assert levels["low_zone_upper"] == round(levels["main_support"] * (1 + levels["zone_width_pct"]), 2)
    assert levels["hard_stop"] == round(levels["main_support"] * (1 - levels["stop_buffer_pct"]), 2)
    assert levels["hard_stop"] != round(levels["main_support"] * 0.98, 2)


def test_moving_averages_join_support_and_resistance_candidates() -> None:
    bars = make_bars()
    levels = build_candidate_levels(10.50, bars, quote={"high": 10.72, "low": 10.32})
    all_names = {item["name"] for item in levels["support_levels"] + levels["resistance_levels"]}

    assert {"MA5", "MA10", "MA20", "MA30"} & all_names


def test_volume_observation_ignores_dirty_intraday_volume() -> None:
    daily = [{"date": "2026-04-01", "open": 10, "close": 10.2, "volume": "bad"}]
    bars_5m = [{"volume": 1000} for _ in range(12)] + [{"volume": "bad"} for _ in range(6)]

    text = volume_observation(daily, bars_5m)

    assert "量能" in text


def test_validate_rejects_agent_reformatted_output() -> None:
    markdown = """## 南网科技（688248.SH）| 日线 | 2026-04-26

### 📍 状态
现价 56.40元，当前按**修复**处理。

### 🎯 关键价位
| 类型 | 价位 |
|------|------|
| 波段防守位 | **55.87元** |

### ⏱️ T0 计划
- **今日做法**：先买后卖
- **T0买入价**：55.87元

> ⚠️ 以上为技术分析，仅供参考，不构成投资建议。
"""
    errors = validate(markdown)
    joined = "\n".join(errors)
    assert "markdown heading syntax is not allowed" in joined
    assert "markdown bullet lists are not allowed" in joined
    assert "T0买入价" in joined or "执行价" in joined or "heading must appear exactly once" in joined


def test_build_signal_for_scene_转弱() -> None:
    report = sample_report()
    report.update({"stage": "转弱", "scene": "防守观察"})

    signal = build_signal(report)

    assert signal["signal_type"] == "defensive"
    assert signal["direction"] == "bearish_lean"
    assert signal["action"] == "wait"
    assert signal["confidence"] == "low"
    assert signal["position"]["max_total_pct"] == 0


def test_build_signal_for_scene_冲高减仓() -> None:
    report = sample_report()
    report.update({"stage": "走强", "scene": "冲高减仓"})

    signal = build_signal(report)

    assert signal["signal_type"] == "reduce"
    assert signal["direction"] == "neutral"
    assert signal["action"] == "reduce"
    assert signal["confidence"] == "medium"


def test_build_signal_for_scene_突破确认() -> None:
    report = sample_report()
    report.update({"stage": "走强", "scene": "突破确认"})

    signal = build_signal(report)

    assert signal["signal_type"] == "track"
    assert signal["direction"] == "bullish"
    assert signal["action"] == "track"
    assert signal["confidence"] == "medium"
    assert signal["position"]["max_total_pct"] == 30


def test_build_signal_for_scene_低吸观察() -> None:
    report = sample_report()
    report.update({"stage": "修复", "scene": "低吸观察"})

    signal = build_signal(report)

    assert signal["signal_type"] == "wait_for_confirmation"
    assert signal["direction"] == "bullish_lean"
    assert signal["action"] == "observe"
    assert validate_signal(signal) == []


def test_build_signal_risk_flags_structure_weak() -> None:
    report = sample_report()
    report.update({"stage": "转弱", "scene": "低吸观察"})

    signal = build_signal(report)

    assert "structure_weak" in signal["risk_flags"]


def test_build_signal_risk_flags_limited_upside_space() -> None:
    report = sample_report()
    report.update({"stage": "走强", "scene": "空间不足"})

    signal = build_signal(report)

    assert "limited_upside_space" in signal["risk_flags"]


def test_build_signal_risk_flags_volume_confirmation_missing() -> None:
    report = sample_report()
    report.update({"volume_text": "量能材料不足，先按关键价位执行。"})

    signal = build_signal(report)

    assert "volume_confirmation_missing" in signal["risk_flags"]


def test_build_signal_includes_data_status() -> None:
    report = sample_report()
    report.update({"data_status": "degraded"})

    signal = build_signal(report)

    assert signal["data_status"] == "degraded"


def test_build_signal_summary_not_empty() -> None:
    signal = build_signal(sample_report())

    assert signal["summary"]
    assert len(signal["summary"]) > 5


def test_build_signal_trigger_price_from_confirm() -> None:
    report = sample_report()
    report["confirm"] = 65.0

    signal = build_signal(report)

    assert signal["trigger"]["price"] == 65.0


def test_build_signal_invalidation_price_from_stop() -> None:
    report = sample_report()
    report["stop"] = 52.0

    signal = build_signal(report)

    assert signal["invalidation"]["price"] == 52.0


def test_build_signal_all_allowed_values() -> None:
    report = sample_report()
    signal = build_signal(report)

    from signal_contract import (
        ALLOWED_ACTIONS,
        ALLOWED_CONFIDENCE,
        ALLOWED_DATA_STATUS,
        ALLOWED_DIRECTIONS,
        ALLOWED_SIGNAL_TYPES,
        CONTRACT_VERSION,
    )

    assert signal["contract"] == CONTRACT_VERSION
    assert signal["signal_type"] in ALLOWED_SIGNAL_TYPES
    assert signal["direction"] in ALLOWED_DIRECTIONS
    assert signal["action"] in ALLOWED_ACTIONS
    assert signal["confidence"] in ALLOWED_CONFIDENCE
    assert signal["data_status"] in ALLOWED_DATA_STATUS


def test_build_signal_position_sanity() -> None:
    report = sample_report()

    for stage in ("走强", "修复", "震荡", "转弱"):
        for scene in ("低吸观察", "防守观察", "冲高减仓", "突破确认", "等转强", "空间不足"):
            report["stage"] = stage
            report["scene"] = scene
            signal = build_signal(report)
            total = signal["position"]["max_total_pct"]
            single = signal["position"]["max_single_move_pct"]
            assert 0 <= total <= 100
            assert 0 <= single <= 100
            assert total >= single


def test_markdown_unchanged_by_signal_build() -> None:
    before = render_markdown(sample_report())

    build_signal(sample_report())

    after = render_markdown(sample_report())
    assert before == after


# ---- generate_alert tests ----


def _alert_report(**overrides: float) -> dict:
    """Base alert-ready report with ATR and key levels."""
    base: dict = {
        "name": "测试科技",
        "current": 50.0,
        "support": 48.00,
        "resistance": 55.00,
        "confirm": 53.00,
        "stop": 47.00,
        "low_zone": "48.00-48.50元",
        "scene": "低吸观察",
        "atr14": 2.0,
    }
    base.update(overrides)
    report: dict = {}
    for k in ("name", "current", "support", "resistance", "confirm", "stop", "low_zone", "scene", "atr14"):
        report[k] = base[k]
    return report


def test_alert_no_trigger_when_far() -> None:
    from run_analysis import generate_alert

    # threshold=max(2.0*0.4, 50*0.008)=0.8
    # 50 距离所有关键位都远（support=48, stop=47, confirm=53, resistance=55）
    report = _alert_report(current=50.0)
    assert generate_alert(report) is None


def test_alert_stop_broken() -> None:
    from run_analysis import generate_alert

    # current=46.5 < stop=47 → 跌破止损
    report = _alert_report(current=46.5)
    alert = generate_alert(report)
    assert alert is not None
    assert "⚠️" in alert
    assert "跌破止损" in alert
    assert "测试科技" in alert
    assert "46.50" in alert


def test_alert_stop_approaching() -> None:
    from run_analysis import generate_alert

    # current=47.5, stop=47, threshold=0.8, 47 <= 47.5 <= 47.8 → 接近止损
    report = _alert_report(current=47.5)
    alert = generate_alert(report)
    assert alert is not None
    assert "接近止损" in alert


def test_alert_support_zone() -> None:
    from run_analysis import generate_alert

    # thresh=0.8. current=48.5, |48.5-48|=0.5<=0.8; 48.5>47+0.8(47.8) → 不触发止损
    report = _alert_report(current=48.5)
    alert = generate_alert(report)
    assert alert is not None
    assert "📍" in alert
    assert "接近支撑" in alert


def test_alert_support_broken() -> None:
    from run_analysis import generate_alert

    # thresh=0.8. current=47.9, |47.9-48|=0.1<=0.8; 47.9>47.8 → 不触发止损
    report = _alert_report(current=47.9)
    alert = generate_alert(report)
    assert alert is not None
    assert "📍" in alert
    assert "进入支撑区" in alert


def test_alert_confirm_zone() -> None:
    from run_analysis import generate_alert

    # current=52.8, confirm=53, threshold=0.8, |52.8-53|=0.2 <= 0.8
    report = _alert_report(current=52.8)
    alert = generate_alert(report)
    assert alert is not None
    assert "📈" in alert
    assert "触及确认区" in alert


def test_alert_confirm_broken() -> None:
    from run_analysis import generate_alert

    # current=53.2, confirm=53, threshold=0.8, |53.2-53|=0.2 <= 0.8
    report = _alert_report(current=53.2)
    alert = generate_alert(report)
    assert alert is not None
    assert "📈" in alert
    assert "已越过确认价" in alert


def test_alert_resistance_zone() -> None:
    from run_analysis import generate_alert

    # atr14=3.0 → thresh=max(3.0*0.35, current*0.006)=max(1.05, 0.317)=1.05
    # current=54.2, resistance=55, |54.2-55|=0.8 <= 1.05 → 触发减仓位
    # |54.2-53|=1.2 > 1.05 → confirm 不触发，让 resistance 有执行机会
    report = _alert_report(current=54.2, atr14=3.0)
    alert = generate_alert(report)
    assert alert is not None
    assert "📉" in alert
    assert "触及减仓位" in alert


def test_alert_resistance_broken() -> None:
    from run_analysis import generate_alert

    # current=55.2, resistance=55, threshold=0.8, |55.2-55|=0.2 <= 0.8
    report = _alert_report(current=55.2)
    alert = generate_alert(report)
    assert alert is not None
    assert "📉" in alert
    assert "已突破减仓位" in alert


def test_alert_stop_priority_over_support() -> None:
    """When current is between support and stop, should prefer stop alert."""
    from run_analysis import generate_alert

    # current=47.5, stop=47, support=48 → stop 优先
    report = _alert_report(current=47.5)
    alert = generate_alert(report)
    assert alert is not None
    assert "接近止损" in alert
    assert "支撑区" not in alert and "接近支撑" not in alert


def test_alert_no_trigger_when_scene_冲高减仓() -> None:
    """When scene is 冲高减仓, confirm and resistance alerts should be suppressed."""
    from run_analysis import generate_alert

    # current=52.8, confirm=53, threshold=0.8 → 但 scene=冲高减仓 被跳过
    report = _alert_report(current=52.8, scene="冲高减仓")
    assert generate_alert(report) is None


def test_alert_no_trigger_when_0_atr() -> None:
    """Without ATR, threshold uses 1% of price."""
    from run_analysis import generate_alert

    report = _alert_report(atr14=0, current=50.0)
    threshold = 50.0 * 0.01  # 0.5
    # 50 距离所有关键位 > 0.5
    assert generate_alert(report) is None

