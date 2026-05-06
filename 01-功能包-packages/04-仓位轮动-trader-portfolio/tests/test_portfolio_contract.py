from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHARED = ROOT.parents[1] / "02-共享模块-shared" / "02-候选逻辑-candidate"
CONTRACTS = ROOT.parents[1] / "02-共享模块-shared" / "03-输出校验-contracts"
SHARED_MARKET = ROOT.parents[1] / "02-共享模块-shared" / "01-行情数据-market-data"
SHARED_ROOT = ROOT.parents[1] / "02-共享模块-shared"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))
if str(SHARED_MARKET) not in sys.path:
    sys.path.insert(0, str(SHARED_MARKET))
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))
for name in ("config", "light_data", "contract_utils", "candidate_core", "candidate_model", "validate_output", "signal_contract", "models"):
    sys.modules.pop(name, None)

from portfolio_run import build_signal_summaries, render_markdown, render_snapshot_markdown, build_roles
from portfolio_core import sort_candidates
from signal_contract import validate_signal
from validate_output import validate


def test_portfolio_markdown_contract() -> None:
    items = [
        {
            "ok": True,
            "name": "中国铝业",
            "status": "低吸观察",
            "current": 12.07,
            "change_pct": 1.43,
            "defense": 11.76,
            "stop": 11.52,
            "buy_low": 11.76,
            "buy_high": 11.88,
            "confirm": 12.60,
            "take": 13.36,
            "score": 420,
            "atr14": 1.2,
            "atr_ratio": 0.015,
            "atr_level": "波动正常",
            "atr_cap": 10,
            "livermore_score": 420,
            "t0_action": "等待高抛触发",
        },
        {
            "ok": True,
            "name": "南网科技",
            "status": "防守观察",
            "current": 56.40,
            "change_pct": -5.39,
            "defense": 55.87,
            "stop": 54.75,
            "buy_low": 55.87,
            "buy_high": 56.43,
            "confirm": 60.55,
            "take": 64.18,
            "score": 230,
            "atr14": 1.5,
            "atr_ratio": 0.018,
            "atr_level": "波动正常",
            "atr_cap": 10,
            "livermore_score": 230,
            "t0_action": "等待低吸触发",
        },
        {
            "ok": True,
            "name": "三安光电",
            "status": "等确认",
            "current": 15.11,
            "change_pct": -2.58,
            "defense": 14.50,
            "stop": 14.21,
            "buy_low": 14.50,
            "buy_high": 14.64,
            "confirm": 15.50,
            "take": 16.43,
            "score": 180,
            "atr14": 0.8,
            "atr_ratio": 0.012,
            "atr_level": "波动正常",
            "atr_cap": 10,
            "livermore_score": 180,
            "t0_action": "不做",
        },
    ]
    sorted_items = sort_candidates(items)
    plan = build_roles(sorted_items, max_total=70, main_cap=40)
    markdown = render_markdown(items, plan, sorted_items, market_level="", market_note="")

    assert "轮动仓位 —" in markdown
    assert "📌 组合" in markdown
    assert "中国铝业" in markdown
    assert "主仓  中国铝业" in markdown
    assert "副仓  南网科技" in markdown
    assert "观察  三安光电" in markdown
    assert "现金  75%" in markdown
    assert "加仓" in markdown
    assert validate(markdown) == []


def test_validate_rejects_reformatted_portfolio_output() -> None:
    markdown = """### 🧺 轮动仓位计划

### 📌 当前组合结论
- **主仓**：中国铝业
- **副仓**：南网科技

### 📊 仓位分配
| 标的 | 仓位 |
|------|------|
| 中国铝业 | 50% |

### ⚠️ 风险控制
> 仅供参考，不构成投资建议。
"""
    errors = validate(markdown)
    joined = "\n".join(errors)
    assert "report must start with" in joined
    assert "missing content" in joined


def snapshot_item(
    name: str,
    status: str,
    current: float,
    *,
    confirm: float,
    defense: float,
    stop: float,
    take: float,
    weight_pct: float | None = None,
    cost: float | None = None,
) -> dict:
    return {
        "ok": True,
        "name": name,
        "target": name,
        "status": status,
        "current": current,
        "change_pct": 1.0,
        "defense": defense,
        "stop": stop,
        "buy_low": defense,
        "buy_high": round(defense * 1.01, 2),
        "confirm": confirm,
        "take": take,
        "score": 300,
        "t0_action": "不做",
        "holding_weight_pct": weight_pct,
        "cost": cost,
    }


def test_snapshot_rotation_transfers_from_a_to_confirmed_b() -> None:
    markdown = render_snapshot_markdown(
        [
            snapshot_item("中国铝业", "冲高减仓", 13.30, confirm=12.60, defense=11.76, stop=11.52, take=13.36, weight_pct=30, cost=11.50),
            snapshot_item("南网科技", "等转强", 60.80, confirm=60.55, defense=55.87, stop=54.75, take=64.18, weight_pct=0),
        ],
        {
            "account": {"total_position_pct": 70, "cash_pct": 30, "max_move_pct": 10},
            "holdings": [{"target": "中国铝业", "weight_pct": 30, "cost": 11.50}],
            "candidates": [{"target": "南网科技"}],
        },
    )

    assert "🧺 高切低轮动面板" in markdown
    assert "今日动作：触发强轮动" in markdown
    assert "从中国铝业减当前仓位的1/3，释放约10%总仓。" in markdown
    assert "南网科技承接10%总仓，剩余0%留现金。" in markdown
    assert "卖完条件" in markdown
    assert "后续复盘" in markdown
    assert validate(markdown) == []


def test_snapshot_rotation_moves_to_cash_when_candidate_unconfirmed() -> None:
    markdown = render_snapshot_markdown(
        [
            snapshot_item("中国铝业", "冲高减仓", 13.30, confirm=12.60, defense=11.76, stop=11.52, take=13.36, weight_pct=30),
            snapshot_item("南网科技", "防守观察", 56.40, confirm=60.55, defense=55.87, stop=54.75, take=64.18, weight_pct=0),
        ],
        {
            "account": {"total_position_pct": 70, "cash_pct": 30, "max_move_pct": 10},
            "holdings": [{"target": "中国铝业", "weight_pct": 30}],
            "candidates": [{"target": "南网科技"}],
        },
    )

    assert "今日动作：触发轻轮动" in markdown
    assert "从中国铝业减当前仓位的1/6，释放约5%总仓。" in markdown
    assert "没有合格接力，释放仓位先留现金。" in markdown
    assert validate(markdown) == []


def test_snapshot_no_rotation_when_no_trigger() -> None:
    markdown = render_snapshot_markdown(
        [
            snapshot_item("中国铝业", "低吸观察", 12.07, confirm=12.60, defense=11.76, stop=11.52, take=13.36, weight_pct=30),
            snapshot_item("南网科技", "防守观察", 56.40, confirm=60.55, defense=55.87, stop=54.75, take=64.18, weight_pct=0),
        ],
        {
            "account": {"total_position_pct": 70, "cash_pct": 30, "max_move_pct": 10},
            "holdings": [{"target": "中国铝业", "weight_pct": 30}],
            "candidates": [{"target": "南网科技"}],
        },
    )

    assert "今日动作：不轮动" in markdown
    assert "A 未钝化，B 未确认。" in markdown
    assert validate(markdown) == []


def test_snapshot_risk_exit_outputs_sell_out_condition() -> None:
    markdown = render_snapshot_markdown(
        [
            snapshot_item("中国铝业", "暂不碰", 11.40, confirm=12.60, defense=11.76, stop=11.52, take=13.36, weight_pct=30),
            snapshot_item("南网科技", "等转强", 60.80, confirm=60.55, defense=55.87, stop=54.75, take=64.18, weight_pct=0),
        ],
        {
            "account": {"total_position_pct": 70, "cash_pct": 30, "max_move_pct": 10},
            "holdings": [{"target": "中国铝业", "weight_pct": 30}],
            "candidates": [{"target": "南网科技"}],
        },
    )

    assert "今日动作：触发风控退出" in markdown
    assert "从中国铝业减当前仓位的1/2，释放约15%总仓。" in markdown
    assert "中国铝业：跌破11.52元，或跌破后反抽站不回，卖完。" in markdown
    assert validate(markdown) == []


def test_portfolio_signal_summaries_validate_for_json_consumers() -> None:
    signals = build_signal_summaries(
        [
            snapshot_item("中国铝业", "冲高减仓", 13.30, confirm=12.60, defense=11.76, stop=11.52, take=13.36, weight_pct=30),
            snapshot_item("南网科技", "等转强", 60.80, confirm=60.55, defense=55.87, stop=54.75, take=64.18, weight_pct=0),
            snapshot_item("三安光电", "暂不碰", 14.00, confirm=15.50, defense=14.50, stop=14.21, take=16.43, weight_pct=0),
        ],
        max_total=80,
        max_single_move=10,
    )

    assert len(signals) == 3
    assert all(signal["contract"] == "trader_signal_v1" for signal in signals)
    assert all(signal["source_skill"] == "trader-portfolio" for signal in signals)
    assert [signal["signal_type"] for signal in signals] == ["reduce", "track", "defensive"]
    assert [signal["action"] for signal in signals] == ["reduce", "track", "wait"]
    assert all(validate_signal(signal) == [] for signal in signals)
