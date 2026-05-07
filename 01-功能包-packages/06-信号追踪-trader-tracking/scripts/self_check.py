#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


SAMPLE = """📌 南网科技｜2026-04-29盘后复盘
收盘 56.44（+3.16%）
成本 57.60｜浮盈亏约 -2.01%

结论：
短线止跌修复，但还不是反转。
五层模型里，结构和量价转好，筹码压力和中期趋势还没解除。

明天只看两个点：
1）57.60 能否放量站稳
2）56.44 跌破后能否快速收回

📊 今日状态
开 55.12｜高 56.98｜低 54.18｜收 56.44
成交 390.6万手

量能重点：
上午 265.0万手，占全天 68%
午后 126.0万手，占全天 32%
09:35 最大量柱 35.7万股

说明：
今天主要博弈集中在上午。
午后缩量，说明抛压减轻，但买盘延续性还不够。

📈 走势结构
全天：开盘下冲反转

09:35-10:00｜开盘急杀：55.12→54.18，区间 54.18-55.12。

理论定位：
缠论：短线修复段，尚未完成向上离开。
威科夫：接近 Spring 类修复，但午后缩量确认不足。
筹码：57.60 是你的成本压力区；轻量估算不等同真实筹码分布。
资金行为：有吸筹/洗盘嫌疑，但证据不足以确认。
动能：早盘改善，午后未延续。

🔎 信号判断

偏多：
✓ 结构：两次接近位置止跌

警惕：
! 动能：强点在早盘，明天需要重新放量确认

🎯 明日关键价位

支撑：
56.44 今日收盘价，守住偏强

压力：
57.60 你的成本，最关键

关键区间：
56.44-57.60
站不上，仍按短线修复看。

🧭 明日应对

强势：
条件：
早盘站上 57.60

最大风险：
放量跌破 54.18

👉 一句话
现在不适合割肉，也不适合提前加仓。

明天只有"放量站稳 57.60"，才算结构、量价、动能一起确认；
否则继续按短线修复看。

如果放量跌破 54.18，这次止跌判断失效。"""


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_output.py")],
        input=SAMPLE,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    print("REVIEW_TRADER_OUTPUT_VALIDATOR=OK")
    print("STANDARD_LIVE_SOURCE=TENCENT_SINA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
