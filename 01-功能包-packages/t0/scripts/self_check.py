#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from monitor import detect_state_change, round_lot


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sample = """🎯 T0 盯盘助理
南网科技（688248.SH）｜现价 56.40（-5.39%）｜ATR 1.23（2.2%）波动偏大


🔍 扫描

当前：不动
提醒级别：轻仓做
买入：已触发，观察价 55.90
卖出：未触发，暂无有效观察价。

🚩 关键价位

低吸观察：55.90元附近 | 高抛观察：58.80元附近
低吸失效：55.22元跌破不接。 | 高抛取消：59.50元放量站上不卖。

📈 盘中走势

开盘段：56.00→56.80，上行，量能正常，有承接。
中段：56.80→55.90，回流，量能缩小，有承接。
最近：55.90→56.40，反弹，量能放大，有资金入，可关注。

🕒 今日关键事件

13:30 低吸买入｜触发55.78元。

💰 仓位管控

当前：不动
触发后：单次最多动用底仓的10%-20%
止损：55.22元 跌破不接

👀 下一步只盯

买入：盯 55.90 附近缩量回踩确认。
卖出：暂无有效观察价，先不盯高抛。
停止：跌破55.22元后，今天不再低吸。"""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_output.py")],
        input=sample,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    events = detect_state_change(
        {"data_status": "degraded", "buy_status": "观察中", "sell_status": "未进入候选区"},
        {
            "current_price": 11.95,
            "data_status": "degraded",
            "buy": {"status": "已触发", "invalid_price": 11.72, "execution_price": 11.94},
            "sell": {"status": "未进入候选区", "invalid_price": 12.48},
        },
    )
    if "BUY_TRIGGERED" not in events or round_lot(1350) != 1300:
        print("monitor self-check failed", file=sys.stderr)
        return 1
    print("T0_OUTPUT_VALIDATOR=OK")
    print("T0_MONITOR=OK")
    print("STANDARD_LIVE_SOURCE=TENCENT_SINA")
    print("AKSHARE_DEFAULT=OFF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
