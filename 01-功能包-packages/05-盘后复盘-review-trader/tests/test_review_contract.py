from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARED_MARKET = ROOT.parents[1] / "02-共享模块-shared" / "01-行情数据-market-data"
SHARED_ROOT = ROOT.parents[1] / "02-共享模块-shared"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(SHARED_MARKET) not in sys.path:
    sys.path.insert(0, str(SHARED_MARKET))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))
for name in ("contract_utils", "light_data", "review_model", "review_render", "review_compare", "review_store", "validate_output", "models"):
    sys.modules.pop(name, None)

import review_compare
import review_store
from review_compare import render_compare
from review_model import analyze_intraday, dense_price_zone, sum_volume, theory_verdicts
from review_render import render_single
from review_store import recent_reviews, save_review
from validate_output import validate


def sample_review(cost: float | None = 57.60) -> dict:
    return {
        "contract": "review_trader_v1",
        "mode": "single",
        "session": "close",
        "name": "南网科技",
        "symbol": "688248.SH",
        "date": "2026-04-29",
        "target": "南网科技",
        "quote": {
            "open": 55.12,
            "high": 56.98,
            "low": 54.18,
            "close": 56.44,
            "pre_close": 54.71,
            "change_pct": 3.16,
            "volume": 3906000,
            "amount": None,
            "turnover_rate": None,
        },
        "cost": cost,
        "pnl_pct": -2.01 if cost else None,
        "intraday": {
            "data_state": "full",
            "volume_lines": [
                "上午 265.0万手，占全天 68%",
                "午后 126.0万手，占全天 32%",
                "09:35 最大量柱 35.7万股，约为开盘段均量 4.5倍",
            ],
            "lines": [
                "09:35-10:00｜开盘急杀：55.12→54.18，区间 54.18-55.12。",
                "09:35 放出最大量柱 35.7万股。",
                "10:00-11:30｜早盘反弹",
                "10:25 17.9万股；11:10 17.8万股，推动早盘修复。",
            ],
            "morning_ratio": 0.68,
        },
        "levels": {
            "support": [
                {"price": 56.44, "label": "今日收盘价，守住偏强"},
                {"price": 55.50, "label": "回撤第一防线"},
                {"price": 54.18, "label": "今日低点，跌破则止跌失败"},
            ],
            "pressure": [
                {"price": 56.98, "label": "今日高点，明日第一关"},
                {"price": 57.50, "label": "成本区前压力"},
                {"price": 57.60, "label": "你的成本，最关键"},
            ],
            "key_support": 54.18,
            "first_support": 55.50,
            "key_pressure": 57.60,
        },
        "theory": {
            "chanlun": "短线修复段，尚未完成向上离开。",
            "wyckoff": "接近 Spring 类修复，但午后缩量确认不足。",
            "chip": "57.60 是你的成本压力区；轻量估算不等同真实筹码分布。",
            "fund": "有吸筹/洗盘嫌疑，但证据不足以确认。",
            "momentum": "早盘改善，午后未延续。",
            "supports": [
                "结构：两次接近位置止跌",
                "量价：开盘放量下杀后收回，不是一路放量下跌",
                "威科夫：有 Spring 类修复特征",
            ],
            "blocks": [
                "缠论：还没突破 56.98-57.60，结构没有向上离开",
                "量价：午后明显缩量，买盘没有持续放大",
                "筹码：57.60 是你的成本，附近可能有解套压力",
            ],
            "scores": {"structure": 75, "volume": 65, "chip": 45, "momentum": 55, "total": 62},
            "state": "短线止跌修复",
            "double_low": True,
            "afternoon_shrink": True,
        },
        "summary": {
            "state": "短线止跌修复",
            "score": 62,
            "key_pressure": 57.60,
            "key_support": 54.18,
            "first_support": 55.50,
            "action": "放量站稳关键压力才考虑加仓；否则继续观察。",
        },
    }


def test_single_review_wechat_panel_contract() -> None:
    markdown = render_single(sample_review())

    assert "收盘 56.44" in markdown
    assert "结论 " in markdown
    assert "📊 关键价位 " in markdown
    assert "下方支撑：" in markdown
    assert "上方压力：" in markdown
    assert "⚠️ 最大风险 " in markdown
    assert "🔎 分时走势 " in markdown
    assert "📈 五层打分 " in markdown
    assert "🎯 信号判断 " in markdown
    assert "👉 一句话 " in markdown
    assert "缠论：" in markdown
    assert "威科夫：" in markdown
    assert "筹码：" in markdown
    assert "资金行为：" in markdown
    assert "|---|" not in markdown
    assert validate(markdown) == []


def test_single_review_without_cost_omits_personal_position_line() -> None:
    markdown = render_single(sample_review(cost=None))

    assert "未输入持仓成本" in markdown
    assert "浮盈亏约" not in markdown
    assert validate(markdown) == []


def test_midday_review_panel_contract() -> None:
    review = sample_review()
    review["session"] = "midday"
    markdown = render_single(review)

    assert markdown.startswith("📌 南网科技｜2026-04-29午间复盘")
    assert "午间现价，守住偏强" in markdown
    assert "上午低点，跌破则止跌失败" in markdown
    assert "上午高点，午后第一关" in markdown
    assert "午间有修复" in markdown
    assert "注意午间复盘以数据时间快照为准" in markdown
    assert validate(markdown) == []


def test_weak_review_does_not_render_as_structure_improved() -> None:
    review = sample_review()
    review["theory"]["state"] = "弱修复观察"
    review["theory"]["scores"]["total"] = 50

    markdown = render_single(review)

    assert "弱修复观察，还不能按反转处理。" in markdown
    assert "只有弱修复迹象" in markdown
    assert "结构和量价有改善" not in markdown


def test_compare_contract() -> None:
    items = [
        {
            "name": "南网科技",
            "date": "2026-04-29",
            "state": "短线止跌修复",
            "score": 68,
            "structure_score": 75,
            "volume_score": 70,
            "chip_score": 48,
            "momentum_score": 65,
            "key_pressure": 57.60,
            "key_support": 54.18,
            "action": "放量站稳关键压力才考虑加仓；否则继续观察。",
            "blocks": ["筹码：成本区压力仍在"],
        },
        {
            "name": "中国铝业",
            "date": "2026-04-29",
            "state": "震荡偏强",
            "score": 61,
            "structure_score": 65,
            "volume_score": 58,
            "chip_score": 60,
            "momentum_score": 55,
            "key_pressure": 11.85,
            "key_support": 11.42,
            "action": "持有观察，不追高。",
            "blocks": ["动能：仍需重新放量确认"],
        },
    ]
    markdown = render_compare(items)

    assert markdown.startswith("📌 多股复盘比较｜2026-04-29")
    assert "结论：" in markdown
    assert "排序：" in markdown
    assert "主盯：" in markdown
    assert "副盯：" in markdown
    assert "只观察 / 先防守：" in markdown
    assert "明日动作：" in markdown
    assert validate(markdown) == []


def test_compare_json_output_returns_structured_payload(monkeypatch) -> None:
    first = sample_review()
    second = copy.deepcopy(sample_review())
    second["name"] = "中国铝业"
    second["symbol"] = "601600.SH"

    reviews = [first, second]
    monkeypatch.setattr(review_compare, "build_review", lambda *args, **kwargs: reviews.pop(0))
    monkeypatch.setattr(review_compare, "save_review", lambda review: None)

    payload = json.loads(review_compare.run_compare(["南网科技", "中国铝业"], output="json"))

    assert payload["contract"] == "review_trader_compare_v1"
    assert len(payload["items"]) == 2
    assert payload["markdown"].startswith("📌 多股复盘比较｜2026-04-29")


def test_review_cache_keeps_midday_and_close_separate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(review_store, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(review_store, "CACHE_PATH", tmp_path / "state.json")
    close_review = sample_review()
    midday_review = copy.deepcopy(sample_review())
    midday_review["session"] = "midday"

    save_review(close_review)
    save_review(midday_review)
    reviews = recent_reviews()

    assert len(json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["reviews"]) == 2
    assert [item["session"] for item in reviews] == ["midday"]


def test_validator_rejects_tables_and_overconfident_terms() -> None:
    markdown = """📌 南网科技｜2026-04-29盘后复盘
| 类型 | 价位 |
|---|---|
主力吸筹，必涨。
"""
    errors = validate(markdown)
    joined = "\n".join(errors)

    assert "markdown tables are not allowed" in joined
    assert "review output contains banned term" in joined


def test_intraday_analysis_tolerates_dirty_volume_and_missing_prices() -> None:
    bars = []
    for index in range(10):
        minute = 30 + index * 5
        bars.append(
            {
                "time": f"2026-04-29 09:{minute:02d}" if minute < 60 else f"2026-04-29 10:{minute - 60:02d}",
                "open": 10.0 + index * 0.01,
                "close": 10.02 + index * 0.01,
                "high": "" if index == 2 else 10.08 + index * 0.01,
                "low": None if index == 3 else 9.95 + index * 0.01,
                "volume": "bad" if index == 4 else 1000 + index * 100,
            }
        )

    result = analyze_intraday(bars, "2026-04-29", session="midday")

    assert result["data_state"] == "full"
    assert result["total_volume"] == sum_volume(bars)
    assert "区间 0.00" not in "\n".join(result["lines"])


def test_close_intraday_marks_incomplete_tail_coverage() -> None:
    bars = []
    for index in range(10):
        minute = 30 + index * 5
        bars.append(
            {
                "time": f"2026-04-29 09:{minute:02d}" if minute < 60 else f"2026-04-29 10:{minute - 60:02d}",
                "open": 10.0,
                "close": 10.1,
                "high": 10.2,
                "low": 9.9,
                "volume": 1000,
            }
        )

    result = analyze_intraday(bars, "2026-04-29", session="close")

    assert result["data_state"] == "partial_close"
    assert result["coverage_complete"] is False
    assert result["tail_has_data"] is False


def test_tail_judgement_requires_tail_data() -> None:
    intraday = {
        "data_state": "partial_close",
        "morning_ratio": 0.8,
        "early_avg_volume": 1000,
        "recent_avg_volume": 500,
        "tail_has_data": False,
    }
    levels = {
        "today_low": 9.5,
        "previous_low": 9.4,
        "today_high": 10.5,
        "recent_high": 11.0,
        "key_pressure": 10.8,
    }
    quote = {"pre_close": 9.8}
    theory = theory_verdicts(10.0, quote, [{"close": 9.8}], intraday, levels, cost=None)

    assert any("尾盘数据不足" in item for item in theory["supports"])
    assert not any("尾盘无明显砸盘" in item for item in theory["supports"])


def test_dense_price_zone_uses_consistent_volume_weighting() -> None:
    daily = [
        {"high": 10.2, "low": 9.8, "close": 10.0, "volume": 1000},
        {"high": 20.2, "low": 19.8, "close": 20.0, "volume": 0},
    ]

    low, high = dense_price_zone(daily)

    assert low is not None and high is not None
    assert low < 10.0 < high
    assert high < 13.0


def test_run_compare_recent_raises_with_insufficient_reviews(tmp_path):
    review_store.CACHE_PATH = tmp_path / "state.json"
    review_store.CACHE_DIR = tmp_path
    from review_compare import run_compare_recent
    try:
        run_compare_recent()
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "少于2只" in str(e)


def test_run_compare_recent_succeeds_with_enough_reviews(tmp_path):
    review_store.CACHE_PATH = tmp_path / "state.json"
    review_store.CACHE_DIR = tmp_path
    review_store.save_review({
        "name": "测试票A",
        "quote": {"close": 10.0, "change_pct": 1.0},
        "theory": {"scores": {"structure": 70, "volume": 65, "chip": 60, "momentum": 55}, "supports": [], "blocks": []},
        "levels": {"key_pressure": 10.5, "key_support": 9.5, "first_support": 9.0},
        "summary": {"state": "短线止跌修复", "score": 65, "action": "观察"},
        "symbol": "000001.SZ",
        "date": "2026-05-01",
        "session": "close",
    })
    review_store.save_review({
        "name": "测试票B",
        "quote": {"close": 20.0, "change_pct": -0.5},
        "theory": {"scores": {"structure": 50, "volume": 45, "chip": 55, "momentum": 40}, "supports": [], "blocks": []},
        "levels": {"key_pressure": 20.5, "key_support": 19.5, "first_support": 19.0},
        "summary": {"state": "弱修复观察", "score": 45, "action": "先防守"},
        "symbol": "000002.SZ",
        "date": "2026-05-01",
        "session": "close",
    })
    from review_compare import run_compare_recent
    result = run_compare_recent()
    assert "多股复盘比较" in result
    assert "测试票A" in result
    assert "测试票B" in result


def test_run_compare_recent_json_output(tmp_path):
    review_store.CACHE_PATH = tmp_path / "state.json"
    review_store.CACHE_DIR = tmp_path
    review_store.save_review({
        "name": "票A",
        "quote": {"close": 10.0, "change_pct": 1.0},
        "theory": {"scores": {"structure": 70, "volume": 65, "chip": 60, "momentum": 55}, "supports": [], "blocks": []},
        "levels": {"key_pressure": 10.5, "key_support": 9.5, "first_support": 9.0},
        "summary": {"state": "短线止跌修复", "score": 65, "action": "观察"},
        "symbol": "000001.SZ",
        "date": "2026-05-01",
        "session": "close",
    })
    review_store.save_review({
        "name": "票B",
        "quote": {"close": 20.0, "change_pct": -0.5},
        "theory": {"scores": {"structure": 50, "volume": 45, "chip": 55, "momentum": 40}, "supports": [], "blocks": []},
        "levels": {"key_pressure": 20.5, "key_support": 19.5, "first_support": 19.0},
        "summary": {"state": "弱修复观察", "score": 45, "action": "先防守"},
        "symbol": "000002.SZ",
        "date": "2026-05-01",
        "session": "close",
    })
    import json
    from review_compare import run_compare_recent
    result = run_compare_recent(output="json")
    data = json.loads(result)
    assert data["contract"] == "review_trader_compare_v1"
    assert "items" in data
    assert "markdown" in data
