#!/usr/bin/env python3
"""形态识别模块回测脚本

用法:
    python3 scripts/backtest_patterns.py --target 南网科技 --days 120
    python3 scripts/backtest_patterns.py --target 宁德时代 --days 120 --window 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    import trader_shared
except ImportError:
    _d = Path(__file__).resolve().parent
    for _ in range(8):
        if (_d / "trader_shared").is_dir():
            if str(_d) not in sys.path:
                sys.path.insert(0, str(_d))
            import trader_shared
            break
        _d = _d.parent
    else:
        raise

from trader_shared.pattern_core import detect_pattern
from trader_shared.volume_price import detect_volume_divergence
from trader_shared.fetchers import TencentFetcher


def fetch_daily_bars(code: str, days: int = 120) -> list[dict]:
    """获取日线数据。"""
    fetcher = TencentFetcher()
    return fetcher.fetch_qfq_daily(code, days=days)


def run_backtest(
    bars: List[dict],
    window: int = 60,
    max_hold_days: int = 20,
    stop_loss_pct: float = 0.05,
) -> dict:
    """运行形态识别回测 (改进版)。

    策略逻辑:
    - 滑动窗口检测形态
    - W底 → 买入，止损设在入场价下方
    - M头 → 卖出(如果有持仓)
    - 到达目标位 → 卖出
    - 跌破止损 → 卖出
    - 持有超过 max_hold_days → 卖出

    Args:
        bars: 日线数据
        window: 形态检测窗口大小
        max_hold_days: 最大持有天数
        stop_loss_pct: 止损比例 (默认5%)

    Returns:
        回测结果统计
    """
    if len(bars) < window + 10:
        return {"error": "数据不足", "total_bars": len(bars), "required": window + 10}

    closes = []
    for b in bars:
        try:
            c = float(str(b.get("close", 0)).replace(",", ""))
            closes.append(c)
        except (ValueError, TypeError):
            closes.append(0.0)

    trades = []
    position = None

    for i in range(window, len(closes)):
        current_price = closes[i]

        # 如果有持仓，检查退出条件
        if position is not None:
            days_held = i - position["entry_idx"]
            should_exit = False
            exit_reason = ""

            # 止损检查
            if current_price <= position["stop_loss"]:
                should_exit = True
                exit_reason = "止损"

            # 目标位检查
            elif position.get("target") and current_price >= position["target"]:
                should_exit = True
                exit_reason = "目标位"

            # 最大持有天数
            elif days_held >= max_hold_days:
                should_exit = True
                exit_reason = "到期"

            if should_exit:
                pnl_pct = (current_price - position["entry_price"]) / position["entry_price"]
                trades.append({
                    "entry_idx": position["entry_idx"],
                    "exit_idx": i,
                    "entry_price": position["entry_price"],
                    "exit_price": current_price,
                    "pnl_pct": pnl_pct,
                    "pattern": position["pattern"],
                    "hold_days": days_held,
                    "exit_reason": exit_reason,
                })
                position = None

        # 如果无持仓，检测信号
        if position is None:
            window_closes = closes[i - window:i + 1]
            window_highs = [bars[j].get("high", closes[j]) for j in range(i - window, i + 1)]
            window_lows = [bars[j].get("low", closes[j]) for j in range(i - window, i + 1)]

            try:
                highs_f = [float(str(h).replace(",", "")) for h in window_highs]
                lows_f = [float(str(l).replace(",", "")) for l in window_lows]
            except (ValueError, TypeError):
                continue

            result = detect_pattern(window_closes, highs_f, lows_f)

            if result.signal == 1 and result.pattern == "double_bottom":
                # 买入: W底确认
                stop_loss = current_price * (1 - stop_loss_pct)
                position = {
                    "entry_price": current_price,
                    "entry_idx": i,
                    "pattern": result.pattern,
                    "target": result.target if result.target > current_price else None,
                    "stop_loss": stop_loss,
                }
            elif result.signal == -1 and result.pattern == "double_top":
                # M头 → 如果有持仓则卖出
                if position is not None:
                    pnl_pct = (current_price - position["entry_price"]) / position["entry_price"]
                    trades.append({
                        "entry_idx": position["entry_idx"],
                        "exit_idx": i,
                        "entry_price": position["entry_price"],
                        "exit_price": current_price,
                        "pnl_pct": pnl_pct,
                        "pattern": position["pattern"],
                        "hold_days": i - position["entry_idx"],
                        "exit_reason": "M头卖出",
                    })
                    position = None

    # 统计结果
    if not trades:
        return {
            "total_trades": 0,
            "message": "回测期间无交易信号",
        }

    winning_trades = [t for t in trades if t["pnl_pct"] > 0]
    losing_trades = [t for t in trades if t["pnl_pct"] <= 0]

    total_pnl = sum(t["pnl_pct"] for t in trades)
    avg_pnl = total_pnl / len(trades)
    win_rate = len(winning_trades) / len(trades) if trades else 0

    avg_win = sum(t["pnl_pct"] for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = sum(t["pnl_pct"] for t in losing_trades) / len(losing_trades) if losing_trades else 0

    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    # 按退出原因统计
    exit_reasons = {}
    for t in trades:
        reason = t.get("exit_reason", "未知")
        if reason not in exit_reasons:
            exit_reasons[reason] = {"count": 0, "total_pnl": 0}
        exit_reasons[reason]["count"] += 1
        exit_reasons[reason]["total_pnl"] += t["pnl_pct"]

    return {
        "total_trades": len(trades),
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_pnl": avg_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "exit_reasons": exit_reasons,
        "trades": trades,
    }


def main():
    parser = argparse.ArgumentParser(description="形态识别回测")
    parser.add_argument("--target", required=True, help="股票代码或名称")
    parser.add_argument("--days", type=int, default=120, help="回测天数")
    parser.add_argument("--window", type=int, default=60, help="形态检测窗口")
    parser.add_argument("--max-hold", type=int, default=20, help="最大持有天数")
    parser.add_argument("--stop-loss", type=float, default=0.05, help="止损比例")
    args = parser.parse_args()

    print(f"获取 {args.target} 日线数据...")
    bars = fetch_daily_bars(args.target, days=args.days)
    print(f"获取到 {len(bars)} 根K线")

    if not bars:
        print("无法获取数据")
        return

    # 显示数据范围
    first_date = bars[0].get("date", "未知")
    last_date = bars[-1].get("date", "未知")
    print(f"数据范围: {first_date} ~ {last_date}")

    # 运行回测
    print(f"\n运行回测 (窗口={args.window}, 最大持有={args.max_hold}天, 止损={args.stop_loss:.0%})...")
    result = run_backtest(
        bars,
        window=args.window,
        max_hold_days=args.max_hold,
        stop_loss_pct=args.stop_loss,
    )

    # 输出结果
    print("\n" + "=" * 50)
    print("回测结果")
    print("=" * 50)

    if "error" in result:
        print(f"错误: {result['error']}")
        return

    if result.get("total_trades", 0) == 0:
        print(f"回测期间无交易信号 ({result.get('message', '')})")
        return

    print(f"总交易次数: {result['total_trades']}")
    print(f"盈利次数: {result['winning_trades']}")
    print(f"亏损次数: {result['losing_trades']}")
    print(f"胜率: {result['win_rate']:.1%}")
    print(f"总收益: {result['total_pnl']:.2%}")
    print(f"平均收益: {result['avg_pnl']:.2%}")
    print(f"平均盈利: {result['avg_win']:.2%}")
    print(f"平均亏损: {result['avg_loss']:.2%}")
    print(f"盈亏比: {result['profit_factor']:.2f}")

    # 退出原因统计
    if result.get("exit_reasons"):
        print("\n退出原因统计:")
        for reason, stats in result["exit_reasons"].items():
            avg = stats["total_pnl"] / stats["count"] if stats["count"] > 0 else 0
            print(f"  {reason}: {stats['count']}次, 平均收益 {avg:+.2%}")

    # 显示交易明细
    if result.get("trades"):
        print("\n交易明细:")
        print("-" * 60)
        for i, t in enumerate(result["trades"], 1):
            emoji = "🟢" if t["pnl_pct"] > 0 else "🔴"
            print(f"  {emoji} #{i}: {t['pattern']} | "
                  f"买入{t['entry_price']:.2f} → 卖出{t['exit_price']:.2f} | "
                  f"收益 {t['pnl_pct']:+.2%} | {t.get('exit_reason', '')}")


if __name__ == "__main__":
    main()
