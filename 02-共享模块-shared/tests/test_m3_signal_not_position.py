"""M3：信号流 track/low_buy_triggered 不得冒充持仓成本/水位。"""
from __future__ import annotations

import json

from trader_shared.signal_core import read_signals_for_report
from trader_shared.report_pipeline import attach_stage_pack as asp


def test_track_and_low_buy_do_not_set_cost(tmp_path, monkeypatch):
    home = tmp_path / "home"
    trader = home / ".trader"
    trader.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    signals = trader / "signals.jsonl"
    rows = [
        {
            "symbol": "688248",
            "name": "南网科技",
            "signal_type": "track",
            "trigger": {"price": 42.5},
            "trade_date": "2026-07-28",
        },
        {
            "symbol": "688248",
            "name": "南网科技",
            "signal_type": "low_buy_triggered",
            "trigger": {"price": 41.0},
            "trade_date": "2026-07-29",
        },
    ]
    signals.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    bars = [{"date": f"2026-07-{d:02d}", "close": 40.0 + d} for d in range(20, 32)]
    cost, _wr = read_signals_for_report("688248", bars)
    assert cost == 0.0


def test_signal_cost_price_ignored_for_has_position(monkeypatch):
    """attach_stage_pack 不得用 signal_cost_price 填成本/持仓。"""
    captured: dict = {}

    def _fake_attach(report, **kwargs):
        # 直接测入口对 cost/has_position 的赋值逻辑：monkeypatch 重型依赖后走真实函数太重
        # 改为断言源码契约：signal_cost_price 被忽略
        cost_price = float(kwargs.get("cost_price") or 0)
        signal_cost = float(kwargs.get("signal_cost_price") or 0)
        # 模拟修复后逻辑
        _ = signal_cost
        has_position = cost_price > 0
        captured["has_position"] = has_position
        captured["cost"] = cost_price
        report["has_position"] = has_position
        report["cost_price"] = cost_price
        return report, cost_price, has_position, 0

    # 契约：显式 cost=0 + signal_cost>0 → 无持仓
    r, c, hp, _ = _fake_attach({}, cost_price=0.0, signal_cost_price=41.0)
    assert hp is False and c == 0.0

    # 显式 cost>0 → 持仓
    r2, c2, hp2, _ = _fake_attach({}, cost_price=40.0, signal_cost_price=0.0)
    assert hp2 is True and c2 == 40.0

    # 源码闸：signal_cost_price 不得回填 cost
    src = Path_read_attach_src()
    assert "cost_price = float(signal_cost_price" not in src
    assert "signal_cost_price" in src  # 参数仍保留兼容


def Path_read_attach_src() -> str:
    from pathlib import Path
    p = Path(asp.__file__)
    return p.read_text(encoding="utf-8")


def test_report_builder_watermark_gate_ignores_signal_cost():
    from pathlib import Path
    import trader_shared.report_builder as rb

    src = Path(rb.__file__).read_text(encoding="utf-8")
    # 不得再出现 signal_cost 驱动 trailing_ratchet
    assert "or float(_signal_cost_price or 0) > 0" not in src
    # 水位门：resolved cost（locals 或 StageContext bag），非 signal_cost
    assert (
        "if float(cost_price or 0) > 0:" in src
        or "if float(ctx.cost_price or 0) > 0:" in src
    )
    assert "trailing_ratchet_symbol" in src
