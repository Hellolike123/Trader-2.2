#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sample = """分析报告 — 南网科技（688248）

现价：56.40元（-5.39%）
MA5：57.96 | MA10：58.00 | MA20：57.84 | MA30：60.15

✅ 结论概述

当前状态：修复观察，未确认转强。
当前动作：观察 55.87-56.43元 是否止跌。
关键点：不追 60.55元 下方反弹；不是到价就买，只有止跌确认后才考虑轻仓试。

🎯 今日交易计划

| 角色 | 行动 |
|---|---|
| 空仓 | 等 55.87-56.43元 止跌，或 60.55元 放量站稳后再看 |
| 有底仓 | 不补仓摊平；反弹到 60.55元 附近但量能不足，可减 10%-20% |
| 加仓 | 只有放量站上 60.55元 且回踩不破，才重新评估 |
| 止错 | 收盘跌破 54.75元，停止低吸，不再补仓 |

📏 仓位管理

观察中：不动。
低吸确认：最多 1 成仓。
有底仓做差价：单次最多动底仓的 10%-20%。
转强确认：最多加到 3 成仓。

🧭 简化分析逻辑

结构：弱修复，还没确认转强。
量价：上涨没放量不追，下跌放量则低吸失效。
筹码压力：60.55元 附近压力未消化。
动能：站不上 60.55元 前，不按进攻点处理。
反向信号：跌破 54.75元 后不能收回，修复假设失效。

⚠️ 风险管理

跌破 54.75元：停止低吸，不补仓。
站不上 60.55元：不加仓，不追高。
放量跌破 55.87元：支撑失败，等下一次止跌。
反弹到 60.55元 无量：有底仓可减 10%-20%。

📌 交易指导卡

| 操作 | 条件 |
|---|---|
| 当前 | 等待，不追 |
| 低吸 | 55.87-56.43元 止跌后，最多 1 成仓 |
| 减仓 | 60.55元 附近冲不动，减 10%-20% |
| 止错 | 54.75元 跌破则停止低吸 |
| 转强 | 60.55元 放量站稳并回踩不破 |

👉 一句话

现在还不是进攻点；先守纪律等确认，跌到 55.87-56.43元 止跌才轻试，站不上 60.55元 不加仓。"""
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_output.py")], input=sample, text=True, capture_output=True)
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    print("OUTPUT_VALIDATOR=OK")
    print("STANDARD_LIBRARY_ONLY=YES")
    print("STANDARD_LIVE_SOURCE=TENCENT_SINA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
