# Output Contract — trader-portfolio

> **This is the absolute truth for valid output.** Never generate output from memory.

## Default --targets output

```text
轮动仓位 — xxx + xxx

🌍 大盘{level} | {note}
📌 组合
    主仓  xxx  仓位 xx%
          状态：xxx
          成本 xx.xx ｜ xxx 股 ｜ 浮盈 +/-x.x%
    副仓  xxx  仓位 xx%
    现金  xx%

🎯 操作
  xxx（现价xx.xx元）
    · 当前仓位：xx%
    · 加仓：站稳 xx.xx + 回踩不破 → 加到 xx%
    · 防守：跌破 xx.xx → 减至 xx%
    · 止损：跌破 xx.xx → 清仓

📍 关键价位
  xxx  买 xx.xx-xx.xx  防xx.xx  损xx.xx  减xx.xx

🧭 结论  主仓  xxx  xx%（{status}）
💡 分析  {advice}
```

No markdown tables. Use indented alignment. ATR uses plain language (波幅偏高/偏大/正常/较低).
Do not output: `ATR14=`, `极端波动`, `高波动`, `低波动`.

## Snapshot mode (--snapshot)

Same structure above, with marker line `规则版本：trader_portfolio_rotation_v1` after the title.

## Old Output Detection

If output contains markdown tables, rerun the script and return stdout verbatim.
