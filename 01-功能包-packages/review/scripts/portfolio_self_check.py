#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sample = """轮动仓位 — 中国铝业 + 南网科技 + 三安光电

📌 组合

  主仓  中国铝业  10%
      状态：低吸观察
  副仓  南网科技  10%
      状态：防守观察
  观察  三安光电  0%
      状态：等转强
💵 现金  80%

🎯 操作

  中国铝业  当前10%  →  加仓→20%  站稳12.60再加  降仓→7%  跌破11.76  止损11.52
  南网科技  当前10%  →  加仓→20%  站稳55.58再加  降仓→7%  跌破53.00  止损51.65
  三安光电  建仓→10%  站稳14.75

📍 关键价位

  中国铝业  买11.76-11.88  防11.76  损11.52  减13.36
  南网科技  买52.73-53.36  防53.00  损51.65  减58.00
  三安光电  买13.89-14.03  防14.30  损13.47  减16.00

🧭 结论

  中国铝业  塔1级15%  主仓  10%
  南网科技  塔3级60%  副仓  10%
  按计划执行，等信号确认后逐步建仓。

  利弗莫尔："不要试图在最高点卖出，也不要在最低点买入。"
  控制仓位比选对股票更重要。"""
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_output.py")], input=sample, text=True, capture_output=True)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    print("PORTFOLIO_OUTPUT_VALIDATOR=OK")
    print("STANDARD_LIBRARY_ONLY=YES")
    print("STANDARD_LIVE_SOURCE=TENCENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
