# Output Contract — trader

> **This is the absolute truth for valid/invalid output.** Never generate output format from memory.

## Valid Output

Starts with: `分析报告 —`

Headings in order:

```
🌍 中证1000
📍 决策
T0 参考
❗ 关键价位
🧭 简要分析
```

Required rules:
- Top block includes `MA5 / MA10 / MA20 / MA30`; use `--` if unavailable.
- 🌍 中证1000 includes `趋势：`, `今日涨跌%`, `建议：`.
- 📍 决策 includes `状态：` and three bullet lines starting with `  ·`.
- `T0 参考` includes `低吸` `高抛` `止损`.
- `❗ 关键价位` is single inline line with pipe-separated values.
- `🧭 简要分析` now reflects the dual-status model:
  - `基础状态：<base_status>｜体系结论：<theory_status>`
  - then the inline summary string with `结构：` `量价：` `筹码：` `动能：`
- `state_label` is the display-layer summary for the theory side, not the base structure side.
- Buy-side wording must include `止跌确认`.
- Do not use `##/###`, bold headings, blockquotes, bullet lists (`-`/`*`), tables, or extra disclaimers.
- Do not output intraday execution prices or concrete order instructions.
- Do not output `⏱️ T0 简版`, `做T`, `t0-trader`, `执行价`.

## Old Output Detection

If output contains any of these, rerun the script:

```
⏱️ T0 简版
T0
做T
t0-trader
执行价
✅ 先给结论
🎯 今日行动
📏 仓位上限
🧭 为什么
⚠️ 如果走势不对
📌 最终行动卡
```

Valid output does NOT use markdown tables.
