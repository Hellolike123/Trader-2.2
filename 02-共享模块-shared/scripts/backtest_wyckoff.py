#!/usr/bin/env python3
"""威科夫买卖点专项回测（信号体检，非完整账户撮合）

逐日滑动窗口调用 wyckoff_analysis（use_persisted_phase=False），
在事件「新亮灯」日记录一次，再看之后 N 日涨跌。

口径对齐 backtest_chanlun.py：信号日收盘进场、固定前向窗口、无费用/T+1。
适合回答「这类事件出现后短窗有没有边」，不回答「按它满仓能不能赚钱」。

用法:
    python3 scripts/backtest_wyckoff.py --target 南网科技 --days 300
    python3 scripts/backtest_wyckoff.py --target 南网科技 三花智控 华熙生物 --days 300
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_ROOT = SCRIPT_DIR.parent
for _p in (SHARED_ROOT, SCRIPT_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import trader_shared  # noqa: F401
from trader_shared.data_provider import get_provider
from trader_shared.light_data import to_float
from trader_shared.wyckoff_core import wyckoff_analysis

MIN_BARS = 60
FORWARD_DAYS = 10
WIN_THRESHOLD = 0.02
STOP_THRESHOLD = -0.03

# 偏多事件 → 买侧；偏空事件 → 卖侧（经典「出手点」，不含 SC/AR 等阶段标记）
_BUY_EVENTS = (
    ("Spring", "spring_signal", "spring_price"),
    ("SOS", "sos_signal", "sos_price"),
    ("LPS", "lps_signal", "lps_price"),
    ("BU", "bu_signal", "bu_price"),
)
_SELL_EVENTS = (
    ("Upthrust", "upthrust_signal", "upthrust_price"),
    ("SOW", "sow_signal", "sow_price"),
    ("LPSY", "lpsy_signal", "lpsy_price"),
    ("UTAD", "utad_signal", "utad_price"),
    ("BC", "bc_signal", "bc_price"),
    ("ARE", "are_signal", "are_price"),
    ("TrendRally", "trend_rally_signal", "trend_rally_price"),
)


def _forward_return(bars: list[dict], signal_idx: int, forward: int) -> float | None:
    if signal_idx + forward >= len(bars):
        return None
    entry = to_float(bars[signal_idx].get("close"))
    exit_ = to_float(bars[signal_idx + forward].get("close"))
    if entry is None or exit_ is None or entry <= 0:
        return None
    return (exit_ / entry - 1.0) * 100


def _max_drawdown_after(bars: list[dict], signal_idx: int, forward: int) -> float | None:
    entry = to_float(bars[signal_idx].get("close"))
    if entry is None or entry <= 0:
        return None
    max_dd = 0.0
    for i in range(signal_idx + 1, min(signal_idx + forward + 1, len(bars))):
        low = to_float(bars[i].get("low"))
        if low is not None and low > 0:
            dd = (low / entry - 1.0) * 100
            if dd < max_dd:
                max_dd = dd
    return max_dd


def _load_bars(target: str, days: int) -> tuple[list[dict] | None, str | None, str]:
    provider = get_provider()
    try:
        sec = provider.resolve_security(target)
        bars = provider.fetch_qfq_daily(sec, days=days)
        code = getattr(sec, "code", "") or target
    except Exception as e:
        return None, f"拉数失败: {e}", target
    if len(bars) < MIN_BARS:
        return None, f"数据不足: {len(bars)} 根", target
    return bars, None, code


def _event_ok(result: dict, signal_key: str) -> bool:
    if not result.get(signal_key):
        return False
    # 过滤过早/失败弹簧与过早/失败上冲——买卖对称，对齐生产 bias
    if signal_key == "spring_signal":
        if result.get("spring_premature"):
            return False
        if result.get("spring_strength") == "failure":
            return False
    if signal_key == "upthrust_signal":
        if result.get("upthrust_premature"):
            return False
        if result.get("upthrust_strength") == "failure":
            return False
    return True


def _collect_signals(bars: list[dict], forward: int, symbol: str) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    prev_on: dict[str, bool] = {}

    for i in range(MIN_BARS, len(bars)):
        window = bars[: i + 1]
        result = wyckoff_analysis(
            window, symbol=symbol, timeframe="daily", use_persisted_phase=False
        )
        if not result or result.get("timeframe") == "insufficient":
            continue

        date_str = str(window[-1].get("date", ""))
        close = to_float(window[-1].get("close"))

        for name, sk, pk in _BUY_EVENTS:
            on = _event_ok(result, sk)
            edged = on and not prev_on.get(sk, False)
            prev_on[sk] = bool(result.get(sk))
            if not edged:
                continue
            fwd = _forward_return(bars, i, forward)
            mdd = _max_drawdown_after(bars, i, forward)
            if fwd is None:
                continue
            price = to_float(result.get(pk)) or close
            signals.append({
                "date": date_str,
                "type": name,
                "price": price,
                "forward_return_pct": round(fwd, 2),
                "max_drawdown_pct": round(mdd, 2) if mdd is not None else None,
                "win": fwd >= WIN_THRESHOLD * 100,
                "stop_hit": mdd is not None and mdd <= STOP_THRESHOLD * 100,
                "side": "buy",
                "idx": i,
            })

        for name, sk, pk in _SELL_EVENTS:
            on = _event_ok(result, sk)
            edged = on and not prev_on.get(sk, False)
            prev_on[sk] = bool(result.get(sk))
            if not edged:
                continue
            fwd = _forward_return(bars, i, forward)
            mdd = _max_drawdown_after(bars, i, forward)
            if fwd is None:
                continue
            price = to_float(result.get(pk)) or close
            signals.append({
                "date": date_str,
                "type": name,
                "price": price,
                "forward_return_pct": round(-fwd, 2),
                "max_drawdown_pct": round(-mdd, 2) if mdd is not None else None,
                "win": fwd <= -WIN_THRESHOLD * 100,
                "stop_hit": False,  # 卖侧 adverse 用上涨不利；此处不做假止损率
                "side": "sell",
                "idx": i,
            })

    return signals


def _aggregate(signals: list[dict], target: str) -> dict[str, Any]:
    if not signals:
        return {"target": target, "total_signals": 0, "by_type": {}}

    by_type: dict[str, list[dict]] = {}
    for s in signals:
        by_type.setdefault(s["type"], []).append(s)

    result: dict[str, Any] = {
        "target": target,
        "total_signals": len(signals),
        "by_type": {},
    }
    for stype, group in by_type.items():
        wins = sum(1 for s in group if s["win"])
        stops = sum(1 for s in group if s["stop_hit"])
        returns = [s["forward_return_pct"] for s in group]
        result["by_type"][stype] = {
            "count": len(group),
            "win_rate": round(wins / len(group) * 100, 1) if group else 0,
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0,
            "max_return_pct": round(max(returns), 2) if returns else 0,
            "min_return_pct": round(min(returns), 2) if returns else 0,
            "stop_rate": round(stops / len(group) * 100, 1) if group else 0,
            "side": group[0].get("side"),
        }
    return result


def backtest_stock(target: str, days: int = 300, forward: int = FORWARD_DAYS) -> dict[str, Any]:
    bars, err, code = _load_bars(target, days)
    if err:
        return {"target": target, "error": err}
    assert bars is not None
    signals = _collect_signals(bars, forward, symbol=code)
    out = _aggregate(signals, target)
    out["code"] = code
    return out


def _print_result(result: dict) -> None:
    target = result.get("target", "?")
    if result.get("error"):
        print(f"  {target}: {result['error']}")
        return
    total = result.get("total_signals", 0)
    print(f"\n{'='*50}")
    print(f"  {target}  |  威科夫事件  |  总信号: {total}")
    print(f"{'='*50}")
    by_type = result.get("by_type", {})
    if not by_type:
        print("  无信号（这段里没出现可统计的新亮灯事件）")
        return
    for stype in sorted(by_type.keys()):
        s = by_type[stype]
        icon = "🟢" if s["win_rate"] >= 60 else "🟡" if s["win_rate"] >= 45 else "🔴"
        side = s.get("side") or "?"
        print(
            f"  {icon} {stype}({side}): {s['count']}次  胜率{s['win_rate']}%  "
            f"均收益{s['avg_return_pct']:+.1f}%  "
            f"最差{s['min_return_pct']:+.1f}%  止损率{s['stop_rate']}%"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="威科夫买卖点专项回测")
    parser.add_argument("--target", nargs="*", help="股票代码或名称")
    parser.add_argument("--days", type=int, default=300)
    parser.add_argument("--forward", type=int, default=FORWARD_DAYS)
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()

    targets = args.target or []
    if not targets:
        print("用法: python3 scripts/backtest_wyckoff.py --target 南网科技 --days 300")
        return

    print(
        f"威科夫买卖点回测  |  回测天数: {args.days}  |  "
        f"前向验证: {args.forward}天  |  新亮灯才计数"
    )
    print("买侧: Spring/SOS/LPS/BU  |  卖侧: Upthrust/SOW/LPSY/UTAD/BC/ARE/TrendRally")
    print(f"{'='*56}")

    all_results = []
    for t in targets:
        result = backtest_stock(t, days=args.days, forward=args.forward)
        _print_result(result)
        all_results.append(result)

    if args.out:
        out_path = Path(args.out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "days": args.days,
            "forward": args.forward,
            "targets": targets,
            "results": all_results,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {out_path}")


if __name__ == "__main__":
    main()
