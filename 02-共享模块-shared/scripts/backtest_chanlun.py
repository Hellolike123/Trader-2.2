#!/usr/bin/env python3
"""缠论买卖点专项回测

对指定股票的历史数据，逐日滑动窗口检测缠论买卖点，然后前向验证信号准确率。

用法:
    python3 scripts/backtest_chanlun.py --target 南网科技 --days 300
    python3 scripts/backtest_chanlun.py --target 南网科技 中国铝业 宁德时代 --days 300
    python3 scripts/backtest_chanlun.py --pool --days 300    # 回测选股池全部票

输出:
    每个信号类型的触发次数、胜率、平均收益、最大回撤。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import trader_shared
from trader_shared.chan_core import chanlun_analysis, _calc_macd
from trader_shared.data_provider import get_provider
from trader_shared.light_data import to_float

# ── 回测参数 ──
LOOKBACK = 300       # 滑动窗口大小（根日线）
MIN_BARS = 60        # 最少需要多少根 bar 才开始检测
FORWARD_DAYS = 10    # 信号后前向验证天数
WIN_THRESHOLD = 0.02 # 涨幅超过 2% 算赢
STOP_THRESHOLD = -0.03  # 跌幅超过 3% 算止损


def _load_pool() -> list[str]:
    """从 ~/.trader/pool.json 读取选股池代码列表。"""
    pool_file = Path.home() / ".trader" / "pool.json"
    if not pool_file.exists():
        return []
    try:
        data = json.loads(pool_file.read_text())
        targets = data.get("targets") or data.get("stocks") or []
        return [t.get("code") or t.get("symbol") or "" for t in targets if isinstance(t, dict)]
    except Exception:
        return []


def _forward_return(bars: list[dict], signal_idx: int, forward: int) -> float | None:
    """计算信号发生后 forward 天的收益率。"""
    if signal_idx + forward >= len(bars):
        return None
    entry = to_float(bars[signal_idx].get("close"))
    exit_ = to_float(bars[signal_idx + forward].get("close"))
    if entry is None or exit_ is None or entry <= 0:
        return None
    return (exit_ / entry - 1.0) * 100


def _max_drawdown_after(bars: list[dict], signal_idx: int, forward: int) -> float | None:
    """信号后 forward 天内的最大回撤。"""
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


def backtest_stock(target: str, days: int = 300, forward: int = FORWARD_DAYS) -> dict[str, Any]:
    """对单只股票运行缠论买卖点回测。"""
    provider = get_provider()
    sec = provider.resolve_security(target)
    bars = provider.fetch_qfq_daily(sec, days=days)
    if len(bars) < MIN_BARS:
        return {"target": target, "error": f"数据不足: {len(bars)} 根"}

    bars = _calc_macd(bars)

    signals: list[dict[str, Any]] = []

    for i in range(MIN_BARS, len(bars)):
        window = bars[:i + 1]
        current = to_float(window[-1].get("close"))
        if current is None or current <= 0:
            continue

        macd_curr = to_float(window[-1].get("macd_histogram"))
        macd_prev = to_float(window[-2].get("macd_histogram")) if len(window) >= 2 else None

        result = chanlun_analysis(window, current, macd_curr, macd_prev)
        if not result:
            continue

        date_str = str(window[-1].get("date", ""))

        for bp in result.get("buy_points", []):
            fwd = _forward_return(bars, i, forward)
            mdd = _max_drawdown_after(bars, i, forward)
            if fwd is not None:
                signals.append({
                    "date": date_str,
                    "type": bp["type"],
                    "price": bp["price"],
                    "confidence": bp.get("confidence", 0),
                    "forward_return_pct": round(fwd, 2),
                    "max_drawdown_pct": round(mdd, 2) if mdd is not None else None,
                    "win": fwd >= WIN_THRESHOLD * 100,
                    "stop_hit": mdd is not None and mdd <= STOP_THRESHOLD * 100,
                })

        for sp in result.get("sell_points", []):
            fwd = _forward_return(bars, i, forward)
            mdd = _max_drawdown_after(bars, i, forward)
            if fwd is not None:
                # 卖点：价格下跌算赢
                signals.append({
                    "date": date_str,
                    "type": sp["type"],
                    "price": sp["price"],
                    "confidence": sp.get("confidence", 0),
                    "forward_return_pct": round(-fwd, 2),  # 反转：跌为正
                    "max_drawdown_pct": round(-mdd, 2) if mdd is not None else None,
                    "win": fwd <= -WIN_THRESHOLD * 100,
                    "stop_hit": mdd is not None and mdd >= WIN_THRESHOLD * 100,
                })

    return _aggregate(signals, target)


def _aggregate(signals: list[dict], target: str) -> dict[str, Any]:
    """按信号类型聚合统计。"""
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
        }

    return result


def _print_result(result: dict) -> None:
    """格式化输出回测结果。"""
    target = result.get("target", "?")
    total = result.get("total_signals", 0)
    error = result.get("error")
    if error:
        print(f"  {target}: {error}")
        return

    print(f"\n{'='*50}")
    print(f"  {target}  |  总信号: {total}")
    print(f"{'='*50}")

    by_type = result.get("by_type", {})
    if not by_type:
        print("  无信号")
        return

    for stype in sorted(by_type.keys()):
        s = by_type[stype]
        icon = "🟢" if s["win_rate"] >= 60 else "🟡" if s["win_rate"] >= 45 else "🔴"
        print(f"  {icon} {stype}: {s['count']}次  胜率{s['win_rate']}%  "
              f"均收益{s['avg_return_pct']:+.1f}%  "
              f"最差{s['min_return_pct']:+.1f}%  止损率{s['stop_rate']}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="缠论买卖点专项回测")
    parser.add_argument("--target", nargs="*", help="股票代码或名称")
    parser.add_argument("--pool", action="store_true", help="回测选股池全部票")
    parser.add_argument("--days", type=int, default=300, help="回测天数 (默认 300)")
    parser.add_argument("--forward", type=int, default=FORWARD_DAYS, help="前向验证天数 (默认 10)")
    args = parser.parse_args()

    targets = args.target or []
    if args.pool:
        targets = _load_pool()
        if not targets:
            print("选股池为空，请先用 final_pool.py add 添加股票")
            return

    if not targets:
        print("用法: python3 scripts/backtest_chanlun.py --target 南网科技 --days 300")
        return

    print(f"缠论买卖点回测  |  回测天数: {args.days}  |  前向验证: {args.forward}天")
    print(f"{'='*50}")

    all_results = []
    for t in targets:
        result = backtest_stock(t, days=args.days, forward=args.forward)
        _print_result(result)
        all_results.append(result)

    # 汇总
    if len(all_results) > 1:
        print(f"\n{'='*50}")
        print("  汇总")
        print(f"{'='*50}")
        type_stats: dict[str, dict] = {}
        for r in all_results:
            for stype, s in r.get("by_type", {}).items():
                if stype not in type_stats:
                    type_stats[stype] = {"count": 0, "wins": 0, "returns": []}
                type_stats[stype]["count"] += s["count"]
                type_stats[stype]["wins"] += int(s["count"] * s["win_rate"] / 100)
                type_stats[stype]["returns"].append(s["avg_return_pct"])

        for stype in sorted(type_stats.keys()):
            ts = type_stats[stype]
            wr = round(ts["wins"] / ts["count"] * 100, 1) if ts["count"] > 0 else 0
            avg_r = round(sum(ts["returns"]) / len(ts["returns"]), 2) if ts["returns"] else 0
            icon = "🟢" if wr >= 60 else "🟡" if wr >= 45 else "🔴"
            print(f"  {icon} {stype}: {ts['count']}次  胜率{wr}%  均收益{avg_r:+.1f}%")


if __name__ == "__main__":
    main()
