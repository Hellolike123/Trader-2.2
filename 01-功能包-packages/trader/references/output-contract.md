# Output Contract — trader

> **This is the absolute truth for valid/invalid output.** Never generate output format from memory.

## Valid Output

Starts with: `分析报告 —`

Headings in order:

```
🌍 大盘
🧭 阶段判断
📍 决策
T0 参考
❗ 关键价位
✨ 亮点
⚠️ 风险
👉 一句话
```

Required rules:
- Top block includes `MA5 / MA10 / MA20 / MA30`; use `--` if unavailable.
- `ATR` line follows MA line.
- 🌍 大盘 includes `中证1000｜大阶段：{stage}期｜今日{change}`.
- 🧭 阶段判断 includes `大阶段：{stage}期` and `短期动能：{momentum}`.
- 📍 决策 includes `{stage_label} → {action}` and `仓位参考：{stage}期上限 {pct}%`.
- `T0 参考` includes `低吸` `高抛` `止损`.
- `❗ 关键价位` lists prices with `←` labels (止损位/防守位/当前位置/确认位).
- `👉 一句话` is the final one-line summary.
- Buy-side wording must include `止跌确认`.
- Do not use `##/###`, bold headings, blockquotes, bullet lists (`-`/`*`), tables, or extra disclaimers.
- Do not output intraday execution prices or concrete order instructions.
- Do not output `⏱️ T0 简版`, `做T`, `执行价`.
- 250日线下方时，首行显示 `⚠️ 250日线下方，一票否决，建议不参与`，然后继续完整分析。

## Old Output Detection

If output contains any of these, rerun the script:

```
⏱️ T0 简版
做T
执行价
✅ 先给结论
🎯 今日行动
📏 仓位上限
🧭 为什么
⚠️ 如果走势不对
📌 最终行动卡
🧭 简要分析
基础状态：
体系结论：
```

Valid output does NOT use markdown tables.
