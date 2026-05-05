"""Calibrator — Simplified strategy backtest engine.

WARNING: This is a SIMPLIFIED backtest simulator, NOT a formal backtesting engine.
It uses daily OHLC prices with fixed entry/exit rules, but does NOT simulate:
  - Order book / slippage / partial fills
  - Transaction costs
  - Real-time market dynamics
Results are directional only — use for parameter tuning, not for performance claims.

Usage:
    python3 scripts/calibrator.py 南网科技 --days 365
    python3 scripts/calibrator.py 南网科技 中国铝业 --compare-env
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Optional pandas for faster aggregation (graceful fallback)
try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

SHARED_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = SHARED_ROOT / "scripts"
MARKET_DATA = SHARED_ROOT / "01-行情数据-market-data"
CANDIDATE = SHARED_ROOT / "02-候选逻辑-candidate"
SHARE_PY = SHARED_ROOT / "trader_shared"
for _p in (_SCRIPTS_DIR, MARKET_DATA, CANDIDATE, SHARE_PY):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from candidate_core import build_candidate_levels, pct_change, to_float
from trader_shared.data_provider import get_provider
from trader_shared import assess as _assess_market

MAX_HOLD_DAYS = 20

# Signal type config
DEFAULT_SIGNAL_TYPES = ("低吸观察", "等转强")
BUY_SIGNAL_TYPES = ("低吸观察", "等转强", "防守观察", "空间不足")
ALL_SIGNAL_TYPES = ("低吸观察", "等转强", "防守观察", "冲高减仓", "空间不足", "暂不碰")


def _by_signal_trades(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group trades by signal type and return detailed stats."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        st = t.get("signal_type") or ""
        groups.setdefault(st, []).append(t)
    result: dict[str, dict[str, Any]] = {}
    for st, group in groups.items():
        wins = [t for t in group if t["pnl_pct"] > 0]
        losses = [t for t in group if t["pnl_pct"] <= 0]
        avg_gain = round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0.0
        avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0.0
        avg_days = round(sum(t["days_held"] for t in group) / len(group)) if group else 0
        max_dd = max((t.get("pnl_pct", 0) for t in group), key=lambda x: abs(x)) if group else 0.0
        result[st] = {
            "count": len(group),
            "win_rate": round(len(wins) / len(group), 2) if group else 0.0,
            "avg_gain_pct": avg_gain,
            "avg_loss_pct": avg_loss,
            "avg_days_held": avg_days,
            "best_pnl_pct": round(max(t["pnl_pct"] for t in group), 2) if group else 0.0,
            "worst_pnl_pct": round(min(t["pnl_pct"] for t in group), 2) if group else 0.0,
        }
    return result


def _by_month(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group trades by year-month and return aggregate stats."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        exit_dt = t.get("exit_date", "")
        if len(exit_dt) >= 7:
            ym = exit_dt[:7]
            groups.setdefault(ym, []).append(t)
    result: dict[str, dict[str, Any]] = {}
    for ym, g in groups.items():
        wins = [t for t in g if t["pnl_pct"] > 0]
        losses = [t for t in g if t["pnl_pct"] <= 0]
        total_ret = round(sum(t["pnl_pct"] for t in g), 2)
        avg_ret = round(total_ret / len(g), 2) if g else 0.0
        avg_days = round(sum(t["days_held"] for t in g) / len(g)) if g else 0
        result[ym] = {
            "count": len(g),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(g), 2) if g else 0.0,
            "total_return_pct": total_ret,
            "avg_pnl_pct": avg_ret,
            "avg_days_held": avg_days,
        }
    return dict(sorted(result.items()))


def run(target: str, days: int = 365, signal_types: tuple[str, ...] | None = None, env_filter: bool = False) -> dict[str, Any]:
    provider = get_provider()
    sec = provider.resolve_security(target)
    bars = provider.fetch_qfq_daily(sec, days=days)
    if len(bars) < 60:
        return {"error": f"数据不足，仅{len(bars)}根K线", "trades": [], "stats": {}}

    trades = []
    holding = False
    entry_price = 0.0
    entry_date = ""
    entry_signal = ""
    hold_days = 0

    for i in range(60, len(bars)):
        day_bars = bars[: i + 1]
        current = float(day_bars[-1].get("close") or 0)
        if current <= 0:
            continue

        try:
            levels = build_candidate_levels(current, day_bars)
        except Exception:
            continue

        status = levels.get("status", "")
        hard_stop = float(levels.get("hard_stop") or 0)
        take = float(levels.get("take") or 0)
        low = float(day_bars[-1].get("low") or current)

        if not holding:
            if status in (signal_types or DEFAULT_SIGNAL_TYPES):
                if env_filter:
                    try:
                        env = _assess_market()
                        market_level = env.get("level", "未知")
                        if market_level == "很差":
                            continue
                    except Exception:
                        pass
                holding = True
                entry_price = current
                entry_date = str(day_bars[-1].get("date") or "")
                entry_signal = status
                hold_days = 0
        else:
            hold_days += 1
            exit_reason = ""
            if hard_stop > 0 and low <= hard_stop:
                pnl = round((hard_stop - entry_price) / entry_price * 100, 2)
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": str(day_bars[-1].get("date") or ""),
                    "signal_type": entry_signal,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(hard_stop, 2),
                    "pnl_pct": pnl,
                    "days_held": hold_days,
                    "stopped_out": True,
                })
                holding = False
            elif take > 0 and current >= take:
                pnl = round((take - entry_price) / entry_price * 100, 2)
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": str(day_bars[-1].get("date") or ""),
                    "signal_type": entry_signal,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(take, 2),
                    "pnl_pct": pnl,
                    "days_held": hold_days,
                    "stopped_out": False,
                })
                holding = False
            elif hold_days >= MAX_HOLD_DAYS:
                pnl = round((current - entry_price) / entry_price * 100, 2)
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": str(day_bars[-1].get("date") or ""),
                    "signal_type": entry_signal,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(current, 2),
                    "pnl_pct": pnl,
                    "days_held": hold_days,
                    "stopped_out": False,
                })
                holding = False
            elif status == "暂不碰":
                pnl = round((current - entry_price) / entry_price * 100, 2)
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": str(day_bars[-1].get("date") or ""),
                    "signal_type": entry_signal,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(current, 2),
                    "pnl_pct": pnl,
                    "days_held": hold_days,
                    "stopped_out": False,
                })
                holding = False

    if holding and trades:
        last_close = float(bars[-1].get("close") or 0)
        pnl = round((last_close - entry_price) / entry_price * 100, 2)
        trades.append({
            "entry_date": entry_date,
            "exit_date": str(bars[-1].get("date") or ""),
            "signal_type": entry_signal,
            "entry_price": round(entry_price, 2),
            "exit_price": round(last_close, 2),
            "pnl_pct": pnl,
            "days_held": hold_days,
            "stopped_out": False,
        })

    stats_data = _compute_stats(trades)
    by_signal = _by_signal_type(trades)
    by_month = _by_month(trades)
    suggestions = generate_suggestions(stats_data, by_signal, by_month)

    return {
        "target": target,
        "total_trades": len(trades),
        "trades": trades,
        "stats": stats_data,
        "by_signal_type": by_signal,
        "by_month": by_month,
        "suggestions": suggestions,
    }


def _compute_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {"total_trades": 0, "win_rate": 0, "avg_gain": 0, "avg_loss": 0, "profit_factor": 0, "max_drawdown": 0, "total_return": 0}

    if _HAS_PANDAS:
        try:
            df = pd.DataFrame(trades)
            pnl = df["pnl_pct"]
            wins = pnl > 0
            total_trades = len(df)
            win_rate = round(wins.mean(), 2)
            avg_gain = round(pnl[wins].mean(), 2) if wins.any() else 0
            avg_loss = round(pnl[~wins].mean(), 2) if (~wins).any() else 0
            pf_losses = abs(avg_loss) * (~wins).sum()
            profit_factor = (
                round(abs(avg_gain * wins.sum() / pf_losses), 2) if pf_losses > 0 else 999
            )
            cum = pnl.cumsum()
            max_dd = round((cum - cum.expanding().max()).fillna(0).abs().max(), 2)
            return {
                "total_trades": total_trades,
                "win_rate": win_rate,
                "avg_gain": avg_gain,
                "avg_loss": avg_loss,
                "profit_factor": profit_factor,
                "max_drawdown": max_dd,
                "total_return": round(pnl.sum(), 2),
                "by_signal_type": _by_signal_type(trades),
            }
        except Exception:
            pass

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    win_rate = round(len(wins) / len(trades), 2)
    avg_gain = round(sum(t["pnl_pct"] for t in wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0
    profit_factor = round(abs(avg_gain * len(wins) / (abs(avg_loss) * len(losses))), 2) if losses and avg_loss else 999

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cumulative += t["pnl_pct"]
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)

    return {
        "total_trades": len(trades),
        "win_rate": win_rate,
        "avg_gain": avg_gain,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "max_drawdown": round(max_dd, 2),
        "total_return": round(cumulative, 2),
        "by_signal_type": _by_signal_type(trades),
    }


def _by_signal_type(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if _HAS_PANDAS and trades:
        try:
            df = pd.DataFrame(trades)
            grouped = df.groupby("signal_type", sort=False)
            result: dict[str, dict[str, Any]] = {}
            for st, g in grouped:
                pnl = g["pnl_pct"]
                w = pnl > 0
                result[str(st)] = {
                    "count": len(g),
                    "win_rate": round(w.mean(), 2),
                    "avg_gain": round(pnl[w].mean(), 2) if w.any() else 0.0,
                    "avg_loss": round(pnl[~w].mean(), 2) if (~w).any() else 0.0,
                    "avg_days_held": round(g["days_held"].mean()),
                    "best_pnl": round(pnl.max(), 2),
                    "worst_pnl": round(pnl.min(), 2),
                }
            return result
        except Exception:
            pass

    groups: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        st = str(t.get("signal_type") or "")
        groups.setdefault(st, []).append(t)
    result: dict[str, dict[str, Any]] = {}
    for st, group in groups.items():
        w = [t for t in group if t["pnl_pct"] > 0]
        losses = [t for t in group if t["pnl_pct"] <= 0]
        result[st] = {
            "count": len(group),
            "win_rate": round(len(w) / len(group), 2),
            "avg_gain": round(sum(t["pnl_pct"] for t in w) / len(w), 2) if w else 0.0,
            "avg_loss": round(sum(t["pnl_pct"] for t in losses) / len(losses), 2) if losses else 0.0,
            "avg_days_held": round(sum(t.get("days_held", 0) for t in group) / len(group)),
            "best_pnl": round(max(t["pnl_pct"] for t in group), 2),
            "worst_pnl": round(min(t["pnl_pct"] for t in group), 2),
        }
    return result


def _by_month(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if _HAS_PANDAS and trades:
        try:
            df = pd.DataFrame(trades)
            df["_ym"] = df["exit_date"].astype(str).str[:7]
            valid = df["_ym"].str.len() == 7
            df = df[valid].copy()
            result: dict[str, dict[str, Any]] = {}
            for ym, g in df.groupby("_ym", sort=True):
                pnl = g["pnl_pct"]
                w = pnl > 0
                result[ym] = {
                    "count": len(g),
                    "wins": int(w.sum()),
                    "losses": int((~w).sum()),
                    "win_rate": round(w.mean(), 2),
                    "total_return_pct": round(pnl.sum(), 2),
                    "avg_pnl_pct": round(pnl.mean(), 2),
                }
            return dict(sorted(result.items()))
        except Exception:
            pass

    groups: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        exit_dt = t.get("exit_date", "")
        if len(exit_dt) >= 7:
            ym = exit_dt[:7]
            groups.setdefault(ym, []).append(t)
    result: dict[str, dict[str, Any]] = {}
    for ym, g in groups.items():
        wins = [t for t in g if t["pnl_pct"] > 0]
        total_ret = round(sum(t["pnl_pct"] for t in g), 2)
        avg_ret = round(total_ret / len(g), 2) if g else 0.0
        result[ym] = {
            "count": len(g),
            "wins": len(wins),
            "losses": len(g) - len(wins),
            "win_rate": round(len(wins) / len(g), 2) if g else 0.0,
            "total_return_pct": total_ret,
            "avg_pnl_pct": avg_ret,
        }
    return dict(sorted(result.items()))


def generate_suggestions(stats: dict[str, Any], by_signal: dict[str, dict[str, Any]], by_month: dict[str, dict[str, Any]]) -> list[str]:
    suggestions: list[str] = []
    if stats["total_trades"] < 5:
        suggestions.append("交易次数不足（<5次），统计结论仅供参考")
        return suggestions

    wr = stats["win_rate"]
    if wr >= 0.60:
        suggestions.append(f"策略整体胜率 {wr*100:.0f}%，策略有效")
    elif wr >= 0.45:
        suggestions.append(f"策略胜率 {wr*100:.0f}%，勉强及格，建议观察更长时间")
    else:
        suggestions.append(f"策略胜率仅 {wr*100:.0f}%，建议审视入场条件或暂不使用")

    dd = stats["max_drawdown"]
    if dd > 15:
        suggestions.append(f"最大回撤 {dd:.0f}% 偏大，建议降低单票仓位或设更紧止损")

    pf = stats["profit_factor"]
    if pf >= 1.5:
        suggestions.append(f"盈利因子 {pf:.1f} 良好")
    elif pf >= 1.0:
        suggestions.append(f"盈利因子 {pf:.1f} 接近 1，建议优化入场条件")
    else:
        suggestions.append(f"盈利因子 {pf:.1f} 偏低，亏损大于盈利")

    # Per-signal-type analysis
    for st, sd in by_signal.items():
        sample_flag = " (样本不足)" if sd["count"] < 5 else ""
        if sd["count"] >= 3:
            if sd["win_rate"] >= 0.65:
                suggestions.append(f"{st} 胜率 {sd['win_rate']*100:.0f}%（{sd['count']}次）{sample_flag}，建议优先跟这个信号")
            elif sd["win_rate"] < 0.40:
                suggestions.append(f"{st} 胜率仅 {sd['win_rate']*100:.0f}%（{sd['count']}次）{sample_flag}，建议少跟或不跟")
        else:
            suggestions.append(f"{st} 仅 {sd['count']} 次，样本不足，暂不下结论")

    # Monthly trend
    months = list(by_month.keys())
    if len(months) >= 2:
        first = by_month.get(months[0], {})
        last = by_month.get(months[-1], {})
        if first.get("win_rate", 0) > 0 and last.get("win_rate", 0) > 0:
            if last["win_rate"] > first["win_rate"] + 0.10:
                suggestions.append(f"胜率从 {int(first['win_rate']*100)}% 改善至 {int(last['win_rate']*100)}%，趋势向好")
            elif first["win_rate"] > last["win_rate"] + 0.10:
                suggestions.append(f"胜率从 {int(first['win_rate']*100)}% 下滑至 {int(last['win_rate']*100)}%，注意近期变化")

    return suggestions


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Trader signal calibrator.")
    parser.add_argument("targets", nargs="+", help="Stock names to calibrate")
    parser.add_argument("--days", type=int, default=365, help="Lookback days")
    parser.add_argument("--env-filter", action="store_true", help="Filter entries when market is '很差'")
    parser.add_argument("--compare-env", action="store_true", help="Compare multiple targets side-by-side")
    args = parser.parse_args()

    results = []
    for target in args.targets:
        r = run(target, days=args.days, env_filter=args.env_filter)
        results.append(r)

    if args.compare_env and len(results) >= 2:
        print(f"对比 — {' vs '.join(r['target'] for r in results)}")
        print("")
        header = f"{'票':<10} {'交易次数':>6} {'胜率':>6} {'收益%':>8} {'回撤%':>8} {'盈利因子':>8}"
        print(header)
        for r in results:
            s = r["stats"]
            print(f"{r['target']:<10} {s['total_trades']:>6} {s['win_rate']*100:>5.0f}% {s['total_return']:>7.1f}% {s['max_drawdown']:>7.1f}% {s['profit_factor']:>8.1f}")
        print("")
        print("各信号类型：")
        for r in results:
            print(f"\n{r['target']}:")
            for st, data in r["stats"].get("by_signal_type", {}).items():
                print(f"  {st}: {data['count']}次, 胜率{data['win_rate']*100:.0f}%")
    else:
        for r in results:
            print(f"\n=== {r['target']} ===")
            print(f"总交易: {r['total_trades']}")
            print(f"胜率: {r['stats']['win_rate']}")
            print(f"总收益: {r['stats']['total_return']}%")
            print(f"最大回撤: {r['stats']['max_drawdown']}%")
            if r["stats"].get("by_signal_type"):
                print("各信号类型:")
                for st, data in r["stats"]["by_signal_type"].items():
                    print(f"  {st}: {data['count']}次, 胜率{data['win_rate']*100:.0f}%")
            print("建议:", r["suggestions"])
