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
均线空头排列｜今日跌0.8% | 建议：偏弱，谨慎参与

🧭 简要分析
修复观察，未确认转强，量价确认不足

📍 决策
状态：修复观察，未确认转强
  · 空仓 → 在 55.87-56.43元 止跌确认才试，最多 10% 仓位
  · 有底仓 → 反弹 60.55 冲不动就减 10-20%
  · 加仓 → 放量站稳 60.55 且回踩不破，才评估

❗ 关键价位
54.75  ← 止损位（ATR）
55.87  ← 防守位（ATR）
  ┆
55.50  ← 有量支撑
  ┆
56.40  ← 当前位置
60.55  ← 确认位（ATR）
  ┆
61.20  ← 套牢压力区

✨ 亮点
当前 56.40 仍站在防守位 55.87 上方，结构在修复 → 等站稳 60.55 确认转强

⚠️ 风险
最大风险不是没反弹，而是 60.55 未确认前提前追入。若跌破 55.87 防守位，预期要先收回来

回复 1 入池"""
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
