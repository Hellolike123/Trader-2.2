#!/usr/bin/env python3
"""缠论买卖点专项回测

对指定股票的历史数据，逐日滑动窗口检测缠论买卖点，然后前向验证信号准确率。

用法:
    python3 scripts/backtest_chanlun.py --target 南网科技 --days 300
    python3 scripts/backtest_chanlun.py --target 南网科技 --mode strict --days 300
    python3 scripts/backtest_chanlun.py --target 南网科技 中国铝业 --mode compare --days 300
    python3 scripts/backtest_chanlun.py --pool --mode compare --days 300 --out ~/.trader/chan_div_bc_compare.json

--mode:
    legacy  — CHAN_DIVERGENCE_BC=legacy（默认生产口径）
    strict  — 最后中枢 b vs c
    compare — 同数据双跑，输出差分汇总（供决定是否切默认）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SHARED_ROOT = SCRIPT_DIR.parent  # 02-共享模块-shared
for _p in (SHARED_ROOT, SCRIPT_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import trader_shared  # noqa: F401
from trader_shared.chan_core import chanlun_analysis, _calc_macd
from trader_shared.data_provider import get_provider
from trader_shared.light_data import to_float

# ── 回测参数 ──
LOOKBACK = 300
MIN_BARS = 60
FORWARD_DAYS = 10
WIN_THRESHOLD = 0.02
STOP_THRESHOLD = -0.03

# 对照时重点看的类型
_FOCUS_TYPES = ("一类买", "类一买", "二类买", "类二买", "一类卖", "类一卖", "二类卖", "类二卖")


def _load_pool() -> list[str]:
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


def _load_bars(target: str, days: int) -> tuple[list[dict] | None, str | None]:
    provider = get_provider()
    try:
        sec = provider.resolve_security(target)
        bars = provider.fetch_qfq_daily(sec, days=days)
    except Exception as e:
        return None, f"拉数失败: {e}"
    if len(bars) < MIN_BARS:
        return None, f"数据不足: {len(bars)} 根"
    return _calc_macd(bars), None


def _collect_signals(
    bars: list[dict],
    forward: int,
    divergence_bc: str,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for i in range(MIN_BARS, len(bars)):
        window = bars[: i + 1]
        current = to_float(window[-1].get("close"))
        if current is None or current <= 0:
            continue

        macd_curr = to_float(window[-1].get("macd_histogram"))
        macd_prev = to_float(window[-2].get("macd_histogram")) if len(window) >= 2 else None

        result = chanlun_analysis(
            window, current, macd_curr, macd_prev, divergence_bc=divergence_bc
        )
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
                    "divergence_kind": bp.get("divergence_kind"),
                    "forward_return_pct": round(fwd, 2),
                    "max_drawdown_pct": round(mdd, 2) if mdd is not None else None,
                    "win": fwd >= WIN_THRESHOLD * 100,
                    "stop_hit": mdd is not None and mdd <= STOP_THRESHOLD * 100,
                    "side": "buy",
                    "idx": i,
                })

        for sp in result.get("sell_points", []):
            fwd = _forward_return(bars, i, forward)
            mdd = _max_drawdown_after(bars, i, forward)
            if fwd is not None:
                signals.append({
                    "date": date_str,
                    "type": sp["type"],
                    "price": sp["price"],
                    "confidence": sp.get("confidence", 0),
                    "divergence_kind": sp.get("divergence_kind"),
                    "forward_return_pct": round(-fwd, 2),
                    "max_drawdown_pct": round(-mdd, 2) if mdd is not None else None,
                    "win": fwd <= -WIN_THRESHOLD * 100,
                    "stop_hit": mdd is not None and mdd >= WIN_THRESHOLD * 100,
                    "side": "sell",
                    "idx": i,
                })
    return signals


def _aggregate(signals: list[dict], target: str, mode: str = "legacy") -> dict[str, Any]:
    if not signals:
        return {"target": target, "mode": mode, "total_signals": 0, "by_type": {}}

    by_type: dict[str, list[dict]] = {}
    for s in signals:
        by_type.setdefault(s["type"], []).append(s)

    result: dict[str, Any] = {
        "target": target,
        "mode": mode,
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


def backtest_stock(
    target: str,
    days: int = 300,
    forward: int = FORWARD_DAYS,
    divergence_bc: str = "legacy",
    bars: list[dict] | None = None,
) -> dict[str, Any]:
    if bars is None:
        bars, err = _load_bars(target, days)
        if err:
            return {"target": target, "mode": divergence_bc, "error": err}
    assert bars is not None
    signals = _collect_signals(bars, forward, divergence_bc)
    return _aggregate(signals, target, mode=divergence_bc)


def _sig_key(s: dict) -> tuple:
    return (s.get("date"), s.get("type"), s.get("side"), round(float(s.get("price") or 0), 4))


def compare_stock(
    target: str,
    days: int = 300,
    forward: int = FORWARD_DAYS,
) -> dict[str, Any]:
    bars, err = _load_bars(target, days)
    if err:
        return {"target": target, "error": err}

    legacy_sigs = _collect_signals(bars, forward, "legacy")
    strict_sigs = _collect_signals(bars, forward, "strict")
    legacy = _aggregate(legacy_sigs, target, "legacy")
    strict = _aggregate(strict_sigs, target, "strict")

    legacy_keys = {_sig_key(s) for s in legacy_sigs}
    strict_keys = {_sig_key(s) for s in strict_sigs}
    only_legacy = [s for s in legacy_sigs if _sig_key(s) not in strict_keys]
    only_strict = [s for s in strict_sigs if _sig_key(s) not in legacy_keys]
    both = [s for s in legacy_sigs if _sig_key(s) in strict_keys]

    def _wr(group: list[dict]) -> float | None:
        if not group:
            return None
        return round(sum(1 for s in group if s["win"]) / len(group) * 100, 1)

    return {
        "target": target,
        "mode": "compare",
        "legacy": legacy,
        "strict": strict,
        "diff": {
            "both_count": len(both),
            "only_legacy_count": len(only_legacy),
            "only_strict_count": len(only_strict),
            "both_win_rate": _wr(both),
            "only_legacy_win_rate": _wr(only_legacy),
            "only_strict_win_rate": _wr(only_strict),
            "only_legacy_types": _count_types(only_legacy),
            "only_strict_types": _count_types(only_strict),
        },
    }


def _count_types(sigs: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in sigs:
        t = str(s.get("type") or "?")
        out[t] = out.get(t, 0) + 1
    return out


def _print_result(result: dict) -> None:
    target = result.get("target", "?")
    error = result.get("error")
    if error:
        print(f"  {target}: {error}")
        return

    if result.get("mode") == "compare":
        _print_compare(result)
        return

    total = result.get("total_signals", 0)
    mode = result.get("mode", "?")
    print(f"\n{'='*50}")
    print(f"  {target}  |  mode={mode}  |  总信号: {total}")
    print(f"{'='*50}")
    by_type = result.get("by_type", {})
    if not by_type:
        print("  无信号")
        return
    for stype in sorted(by_type.keys()):
        s = by_type[stype]
        icon = "🟢" if s["win_rate"] >= 60 else "🟡" if s["win_rate"] >= 45 else "🔴"
        print(
            f"  {icon} {stype}: {s['count']}次  胜率{s['win_rate']}%  "
            f"均收益{s['avg_return_pct']:+.1f}%  "
            f"最差{s['min_return_pct']:+.1f}%  止损率{s['stop_rate']}%"
        )


def _print_compare(result: dict) -> None:
    target = result["target"]
    leg = result["legacy"]
    st = result["strict"]
    diff = result["diff"]
    print(f"\n{'='*56}")
    print(f"  {target}  |  legacy vs strict")
    print(f"{'='*56}")
    print(f"  总信号  legacy={leg.get('total_signals', 0)}  strict={st.get('total_signals', 0)}")
    print(
        f"  差分  共有={diff['both_count']}  "
        f"仅legacy={diff['only_legacy_count']}(胜率{diff['only_legacy_win_rate']})  "
        f"仅strict={diff['only_strict_count']}(胜率{diff['only_strict_win_rate']})"
    )
    types = sorted(set(leg.get("by_type", {})) | set(st.get("by_type", {})))
    for t in types:
        if t not in _FOCUS_TYPES and t not in leg.get("by_type", {}) and t not in st.get("by_type", {}):
            continue
        a = leg.get("by_type", {}).get(t)
        b = st.get("by_type", {}).get(t)
        a_s = f"{a['count']}次/{a['win_rate']}%" if a else "—"
        b_s = f"{b['count']}次/{b['win_rate']}%" if b else "—"
        print(f"  {t}: legacy {a_s}  |  strict {b_s}")


def _merge_compare_summary(all_results: list[dict]) -> dict[str, Any]:
    """跨票汇总 compare 结果。"""
    focus: dict[str, dict[str, Any]] = {}
    totals = {
        "both": 0,
        "only_legacy": 0,
        "only_strict": 0,
        "only_legacy_wins": 0,
        "only_strict_wins": 0,
    }
    for r in all_results:
        if r.get("error") or r.get("mode") != "compare":
            continue
        d = r["diff"]
        totals["both"] += d["both_count"]
        totals["only_legacy"] += d["only_legacy_count"]
        totals["only_strict"] += d["only_strict_count"]
        # 用类型表估算 wins 不够准；下面按 by_type 汇总更稳
        for mode_key, label in (("legacy", "legacy"), ("strict", "strict")):
            for stype, s in r[mode_key].get("by_type", {}).items():
                slot = focus.setdefault(stype, {
                    "legacy_count": 0, "legacy_wins": 0,
                    "strict_count": 0, "strict_wins": 0,
                })
                if label == "legacy":
                    slot["legacy_count"] += s["count"]
                    slot["legacy_wins"] += int(round(s["count"] * s["win_rate"] / 100))
                else:
                    slot["strict_count"] += s["count"]
                    slot["strict_wins"] += int(round(s["count"] * s["win_rate"] / 100))

    by_type = {}
    for stype, s in focus.items():
        by_type[stype] = {
            "legacy_count": s["legacy_count"],
            "legacy_win_rate": round(s["legacy_wins"] / s["legacy_count"] * 100, 1) if s["legacy_count"] else None,
            "strict_count": s["strict_count"],
            "strict_win_rate": round(s["strict_wins"] / s["strict_count"] * 100, 1) if s["strict_count"] else None,
            "count_delta": s["strict_count"] - s["legacy_count"],
        }
    return {"totals": totals, "by_type": by_type}


def main() -> None:
    parser = argparse.ArgumentParser(description="缠论买卖点专项回测")
    parser.add_argument("--target", nargs="*", help="股票代码或名称")
    parser.add_argument("--pool", action="store_true", help="回测选股池全部票")
    parser.add_argument("--days", type=int, default=300, help="回测天数 (默认 300)")
    parser.add_argument("--forward", type=int, default=FORWARD_DAYS, help="前向验证天数 (默认 10)")
    parser.add_argument(
        "--mode",
        choices=("legacy", "strict", "compare"),
        default="legacy",
        help="背驰力度模式：legacy|strict|compare（默认 legacy）",
    )
    parser.add_argument("--out", type=str, default="", help="结果 JSON 输出路径")
    args = parser.parse_args()

    targets = args.target or []
    if args.pool:
        targets = [t for t in _load_pool() if t]
        if not targets:
            print("选股池为空，请先用 final_pool.py add 添加股票")
            return

    if not targets:
        print("用法: python3 scripts/backtest_chanlun.py --target 南网科技 --mode compare --days 300")
        return

    print(
        f"缠论买卖点回测  |  mode={args.mode}  |  回测天数: {args.days}  |  "
        f"前向验证: {args.forward}天"
    )
    print(f"{'='*56}")

    all_results: list[dict] = []
    for t in targets:
        if args.mode == "compare":
            result = compare_stock(t, days=args.days, forward=args.forward)
        else:
            result = backtest_stock(
                t, days=args.days, forward=args.forward, divergence_bc=args.mode
            )
        _print_result(result)
        all_results.append(result)

    payload: dict[str, Any] = {
        "mode": args.mode,
        "days": args.days,
        "forward": args.forward,
        "targets": targets,
        "results": all_results,
    }

    if args.mode == "compare" and len(all_results) >= 1:
        summary = _merge_compare_summary(all_results)
        payload["summary"] = summary
        print(f"\n{'='*56}")
        print("  汇总（跨票）")
        print(f"{'='*56}")
        for stype in sorted(summary["by_type"].keys()):
            s = summary["by_type"][stype]
            print(
                f"  {stype}: legacy {s['legacy_count']}次/"
                f"{s['legacy_win_rate']}%  →  strict {s['strict_count']}次/"
                f"{s['strict_win_rate']}%  (Δcount {s['count_delta']:+d})"
            )

    if args.out:
        out_path = Path(args.out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {out_path}")


if __name__ == "__main__":
    main()
