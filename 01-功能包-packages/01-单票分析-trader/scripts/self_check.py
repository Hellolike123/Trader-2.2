#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_validate(text: str) -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_output.py")],
        input=text, text=True, capture_output=True,
    )
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    return 0


def main() -> int:
    # Sample covers the current render_markdown structure:
    #  - 筹码支撑/压力在关键价位阶梯
    #  - 分层风险（亮点/风险）
    #  - 止跌确认/止损/最多等固定文本
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

    rc = _run_validate(sample)
    if rc != 0:
        return rc

    # Second sample: verify the validator also accepts the newer 冲高减仓 branch
    sample2 = """分析报告 — 测试股份（688001）

现价：56.40元（+2.10%）
MA5：55.96|MA10：55.50|MA20：54.84|MA30：53.15｜ATR 1.30（4%）波动正常

🌍 中证1000
均线多头排列｜今日涨1.5% | 建议：偏多，积极观察

🧭 简要分析
转强确认中，注意减仓，承接存在，转强不足

📍 决策
状态：转强确认中，注意减仓
  · 空仓 → 在 55.20-55.50元 止跌确认才试，最多 10% 仓位
  · 有底仓 → 57.50 冲不动就减 10-20%
  · 加仓 → 放量站稳 57.50 且回踩不破，才评估

❗ 关键价位
53.75  ← 止损位（ATR）
55.20  ← 防守位（ATR）
55.34  ← 有量支撑
56.40  ← 当前位置
57.50  ← 确认位（ATR）
58.80  ← 减仓位（ATR）
59.20  ← 套牢压力区

✨ 亮点
现价接近压力区，有反弹机会

⚠️ 风险
冲高缩量先减仓，放量突破 57.50 再接回

回复 1 入池"""

    rc2 = _run_validate(sample2)
    if rc2 != 0:
        return rc2

    print("OUTPUT_VALIDATOR=OK")
    print("STANDARD_LIBRARY_ONLY=YES")
    print("STANDARD_LIVE_SOURCE=TENCENT_SINA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
