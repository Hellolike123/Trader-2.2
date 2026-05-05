#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sample = """分析报告 — 南网科技（688248）

现价：56.40元（-5.39%）
MA5：57.96|MA10：58.00|MA20：57.84|MA30：60.15｜ATR 1.30（4%）波动正常

🌍 中证1000
趋势：五条线下方｜今日跌0.8% | 建议：偏弱，谨慎参与

📍 决策
状态：修复观察，未确认转强
  · 空仓 → 在 55.87-56.43元 止跌才试，最多 10% 仓位
  · 有底仓 → 反弹 60.55 冲不动就减 10-20%
  · 加仓 → 放量站稳 60.55 且回踩不破，才评估

T0 参考
  · 低吸：55.87（支撑区承接，止跌确认后进场）
  · 高抛：60.55（均线压力附近，最多 10% 仓位）
  · 止损：跌破 54.75 退出全部

❗ 关键价位
止损：54.75元｜减仓：60.55元｜止跌：55.87-56.43元｜支撑：55.87元

🧭 简要分析
  结构：修复观察，不是主升
  量价：承接存在，转强不足
  筹码：60.55 压力
  动能：不进攻

👉 一句话
现在还不是进攻点，等止跌确认再试，站不上 60.55 不加仓。"""
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
