#!/usr/bin/env python3
"""T0 三重共振信号回测脚本

对指定标的逐日回测 Al Brooks + 威科夫 + 动量三重共振信号的效果。

用法:
    python3 scripts/backtest_t0.py --target 平安银行 --days 30
    python3 scripts/backtest_t0.py --target 688248 --days 60
    python3 scripts/backtest_t0.py --pool --days 20
"""
from __future__ import annotations

import sys
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _parse_date(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# ── 信号引擎（复用现有 T0 模块） ────────────────────────────────────────────

def _run_t0_signals(
    code: str,
    bars_5m: list[dict],
    bars_15m: list[dict] | None,
    cur_price: float,
) -> dict[str, Any]:
    """对给定 K 线数据跑 T0 三重共振信号。"""
    from price_point_engine import (
        build_candidate_zones,
        find_key_levels,
        check_resonance,
        latest_indicator_state,
        completed_5m_bars,
    )
    from trader_shared.ab_price_action import analyze_ab

    report_data = {
        "kline_5m": bars_5m,
        "kline_5m_completed": completed_5m_bars(bars_5m),
        "kline_15m": bars_15m or [],
        "current_price": cur_price,
        "quote": {"low": cur_price * 0.99, "high": cur_price * 1.01, "pre_close": cur_price},
        "daily_bars": [],
    }
    completed = report_data["kline_5m_completed"]
    if len(completed) < 10:
        return {"error": "5m数据不足"}

    key_levels = find_key_levels(report_data)
    zones = build_candidate_zones(report_data, key_levels)
    state = latest_indicator_state(completed)

    ab_result = analyze_ab(completed, current_price=cur_price)
    resonance = check_resonance(report_data, zones, state, ab_result=ab_result)

    return {
        "resonance": resonance,
        "ab_result": ab_result,
        "zones": zones,
        "key_levels": key_levels,
    }


# ── 回测核心 ────────────────────────────────────────────────────────────────

def _fill_bars_for_date(
    provider,
    sec,
    target_date: str,
    days_back: int = 60,
) -> tuple[list[dict], list[dict]]:
    """拉取某日及之前的 K 线数据。

    Returns:
        (bars_5m, bars_15m)
    """
    try:
        bars_5m_all = provider.fetch_5m(sec, datalen=800)
    except Exception:
        bars_5m_all = []

    try:
        bars_15m_all = provider.fetch_15m(sec, datalen=800)
    except Exception:
        bars_15m_all = []

    # 只保留到 target_date 当天及之前的数据
    dt = _parse_date(target_date)
    if dt is None:
        return bars_5m_all, bars_15m_all

    next_day = dt + timedelta(days=1)
    next_str = next_day.strftime("%Y-%m-%d")

    bars_5m = [b for b in bars_5m_all if str(b.get("time", b.get("date", ""))) < next_str]
    bars_15m = [b for b in bars_15m_all if str(b.get("time", b.get("date", ""))) < next_str]

    return bars_5m, bars_15m


def _check_target_vs_stop(
    entry: float, forward_bars: list[dict],
    target_pct: float = 0.01, stop_pct: float = -0.008,
    slippage: float = 0.001, direction: str = "buy",
) -> dict:
    """检查后续棒线中先触达 1R 目标还是先止损。

    严格回测方法：
    - 买入信号（direction="buy"）：price >= entry*1.01 → 止盈, price <= entry*0.992 → 止损
    - 卖出信号（direction="sell"）：price <= entry*0.99 → 止盈, price >= entry*1.008 → 止损
    - 含滑点

    Returns:
        {"hit_target": bool, "hit_stop": bool, "pnl_pct": float, "bars_to_hit": int|None}
    """
    if not forward_bars:
        return {"hit_target": False, "hit_stop": False, "pnl_pct": 0.0, "bars_to_hit": None}

    if direction == "buy":
        target_price = entry * (1 + target_pct - slippage)
        stop_price = entry * (1 + stop_pct - slippage)
        hit_cond = lambda high, low: high >= target_price
        stop_cond = lambda high, low: low <= stop_price
    else:
        target_price = entry * (1 - target_pct + slippage)
        stop_price = entry * (1 - stop_pct + slippage)
        hit_cond = lambda high, low: low <= target_price
        stop_cond = lambda high, low: high >= stop_price

    hit_target = False
    hit_stop = False
    bars_to_hit = None

    for idx, bar in enumerate(forward_bars):
        high = float(bar.get("high", 0))
        low = float(bar.get("low", 0))

        if hit_cond(high, low):
            hit_target = True
            bars_to_hit = idx + 1
            break
        if stop_cond(high, low):
            hit_stop = True
            bars_to_hit = idx + 1
            break

    if hit_target:
        pnl = target_pct * 100
    elif hit_stop:
        pnl = stop_pct * 100
    else:
        last_close = float(forward_bars[-1].get("close", entry))
        if direction == "buy":
            pnl = (last_close - entry) / entry * 100
        else:
            pnl = (entry - last_close) / entry * 100

    return {"hit_target": hit_target, "hit_stop": hit_stop,
            "pnl_pct": round(pnl, 2), "bars_to_hit": bars_to_hit}


def _choose_close_price(invalid_price: float | None, bars_5m: list[dict]) -> float:
    """选择出场价格：止损价或近期低点。"""
    if invalid_price and invalid_price > 0:
        return invalid_price
    if bars_5m:
        low = float(bars_5m[-1].get("low", 0) or 0)
        return low if low > 0 else 0
    return 0


def backtest_t0(target: str, days: int = 60) -> list[dict]:
    """对单只股票运行 T0 三重共振逐棒回测。

    流程:
    1. 获取历史 5m K 线数据
    2. 从第 50 根棒开始，逐棒向前滑动
    3. 每滑到一根新棒，用当前及历史数据跑 T0 信号
    4. 记录信号，用后续棒线验证（未来 N 根的最高/最低）

    Returns:
        [{"date","signal","resonance_count","entry","pnl_pct","max_price","min_price","hit_1r","ab","wyckoff","momentum",...}]
    """
    from data_provider import get_provider

    # 修正 path 让 T0 脚本能 import
    t0_dir = str(Path(__file__).resolve().parent.parent / "01-功能包-packages" / "t0" / "scripts")
    if t0_dir not in sys.path:
        sys.path.insert(0, t0_dir)

    provider = get_provider()
    sec = provider.resolve_security(target)

    bars_all = provider.fetch_5m(sec, datalen=800)
    bars_15m = provider.fetch_15m(sec, datalen=800)

    if not bars_all:
        print("  ❌ 无5m数据")
        return []

    n_bars = len(bars_all)
    # 用第 50 根开始（积攒足够数据计算指标）
    warmup = min(50, n_bars // 3)
    if n_bars < warmup + 5:
        print(f"  ❌ 数据不足 ({n_bars}根)")
        return []

    results: list[dict] = []
    stride = max(1, n_bars // (days or 60))  # 控制回测点数，最多 days 个点

    print(f"  总棒数: {n_bars}, 滑窗步长: {stride}, 回测点数: ~{n_bars // stride}")

    for i in range(warmup, n_bars, stride):
        # 使用截至当前位置的 5m 数据
        cur_bars = bars_all[:i + 1]
        try:
            cur_price = float(cur_bars[-1].get("close", 0))
        except (TypeError, ValueError):
            continue
        if cur_price <= 0:
            continue

        try:
            sig = _run_t0_signals(target, cur_bars, bars_15m, cur_price)
        except Exception:
            continue
        if "error" in sig:
            continue

        res = sig["resonance"]
        buy_green = res.get("buy_green", False)
        sell_red = res.get("sell_red", False)
        lights = res.get("lights", {})

        ab_info = lights.get("ab", {})
        wyck_info = lights.get("wyckoff", {})
        mom_info = lights.get("momentum", {})

        buy_count = sum(1 for v in lights.values() if v.get("buy"))
        sell_count = sum(1 for v in lights.values() if v.get("sell"))
        max_count = max(buy_count, sell_count)

        if max_count == 0:
            continue

        # 用后续 24 根 5m（约 2 小时）验证，设 1R=1%, 止损=0.8%
        forward = bars_all[i + 1:i + 1 + 24]
        entry_price = cur_price
        is_buy = buy_green or buy_count > sell_count
        ver = _check_target_vs_stop(entry_price, forward, target_pct=0.01, stop_pct=-0.008,
                                    direction="buy" if is_buy else "sell")

        bar_time = str(cur_bars[-1].get("time", cur_bars[-1].get("date", "")))
        result = {
            "date": bar_time[:16] if " " in bar_time else bar_time,
            "signal": "buy_green" if buy_green else ("sell_red" if sell_red else f"partial{'买' if buy_count > sell_count else '卖'}"),
            "resonance_count": max_count,
            "entry": round(entry_price, 2),
            "pnl_pct": ver["pnl_pct"],
            "hit_target": ver["hit_target"],
            "hit_stop": ver["hit_stop"],
            "bars_to_hit": ver.get("bars_to_hit"),
            "ab": {"buy": ab_info.get("buy", False), "sell": ab_info.get("sell", False),
                   "reason": ab_info.get("reason", "")},
            "wyckoff": {"buy": wyck_info.get("buy", False), "sell": wyck_info.get("sell", False)},
            "wyckoff": {"buy": wyck_info.get("buy", False), "sell": wyck_info.get("sell", False)},
            "momentum": {"buy": mom_info.get("buy", False), "sell": mom_info.get("sell", False)},
            "always_in": ab_info.get("always_in", "?"),
        }
        results.append(result)

    return results


# ── 报告渲染 ────────────────────────────────────────────────────────────────

def render_backtest_report(results: list[dict], name: str) -> str:
    """渲染回测报告。"""
    if not results:
        return f"## {name} — 回测无信号\n\n回测期间未产生任何有效信号。"

    total = len(results)
    wins = [r for r in results if r["pnl_pct"] > 0]
    losses = [r for r in results if r["pnl_pct"] <= 0]
    signals = set(r["signal"] for r in results)

    avg_win = round(sum(r["pnl_pct"] for r in wins) / len(wins), 2) if wins else 0
    avg_loss = round(sum(r["pnl_pct"] for r in losses) / len(losses), 2) if losses else 0
    best = max(results, key=lambda r: r["pnl_pct"])
    worst = min(results, key=lambda r: r["pnl_pct"])
    hit_target = sum(1 for r in results if r["hit_target"])
    hit_stop = sum(1 for r in results if r["hit_stop"])
    na = total - hit_target - hit_stop

    lines = [
        f"## {name} — T0 三重共振回测报告",
        "",
        f"回测区间: {results[0]['date']} ~ {results[-1]['date']}",
        f"总信号数: {total}",
        f"胜率: {len(wins)/total*100:.0f}% ({len(wins)}/{total})",
        f"平均盈利: +{avg_win:.2f}%" if avg_win else "",
        f"平均亏损: {avg_loss:.2f}%" if avg_loss else "",
        f"触及1R止盈: {hit_target}/{total} ({hit_target/total*100:.0f}%)",
        f"触及止损: {hit_stop}/{total} ({hit_stop/total*100:.0f}%)",
        f"未完成: {na}/{total} ({na/total*100:.0f}%)",
        f"最大盈利: +{best['pnl_pct']:.2f}% ({best['date']})",
        f"最大亏损: {worst['pnl_pct']:.2f}% ({worst['date']})",
        "",
    ]

    # 按信号类型统计
    lines.append("### 信号类型分布")
    lines.append("")
    for st in sorted(signals):
        group = [r for r in results if r["signal"] == st]
        g_wins = [r for r in group if r["pnl_pct"] > 0]
        g_total = len(group)
        lines.append(f"- {st}: {g_total}次, 胜率{len(g_wins)/g_total*100:.0f}%")
    lines.append("")

    # 最近 20 个信号详情
    lines.append("### 最近信号详情")
    lines.append("")
    lines.append("日期 | 类型 | 灯数 | 入场 | 止盈/止损 | 耗时(K线)")
    lines.append("-----|------|------|------|----------|----------")
    for r in results[-20:]:
        label = r["signal"]
        outcome = "止盈" if r["hit_target"] else ("止损" if r["hit_stop"] else "未完成")
        bars_s = str(r.get("bars_to_hit", "")) if r.get("bars_to_hit") else "-"
        lines.append(f"{r['date']} | {label} | {r['resonance_count']} | {r['entry']} | {outcome} {r['pnl_pct']:+.2f}% | {bars_s}")

    return "\n".join(lines)


# ── CLI 入口 ────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="T0 三重共振信号回测")
    parser.add_argument("--target", type=str, help="股票名称或代码")
    parser.add_argument("--days", type=int, default=30, help="回测天数")
    parser.add_argument("--pool", action="store_true", help="回测选股池全部票")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    if args.pool:
        from trader_shared.trader_paths import path as trader_path

        pool_path = trader_path("pool")
        if not pool_path.exists():
            print(f"选股池文件不存在: {pool_path}")
            return 1
        pool = json.loads(pool_path.read_text(encoding="utf-8"))
        targets = list(pool.keys())
        print(f"选股池共 {len(targets)} 只票\n")
    elif args.target:
        targets = [args.target]
    else:
        targets = ["平安银行"]

    all_results = {}
    for t in targets:
        print(f"📊 回测 {t}...", end=" ", flush=True)
        t0 = time.time()
        results = backtest_t0(t, days=args.days)
        elapsed = time.time() - t0
        print(f"完成 ({elapsed:.1f}s, {len(results)}个信号)")
        if args.json:
            all_results[t] = results
        else:
            print()
            print(render_backtest_report(results, t))
            print()

    if args.json:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
