# Output Template — trader

> **This is the absolute truth for output structure.** Never generate output format from memory.

## Valid Output

Starts with: `分析报告 —`

Headings in order:

```
🌍 大盘
🧭 阶段判断
💰 主力资金
📍 决策
T0 参考
❗ 关键价位
✨ 亮点
⚠️ 风险
👉 一句话
```

## Required Fields

- Top block includes `MA5 / MA10 / MA20 / MA30`; use `--` if unavailable.
- `ATR` line follows MA line.
- 🌍 大盘 includes `中证1000｜{regime}｜今日{change}%｜{skill_note}`.
  - regime is market env level (正常/偏弱/很差), NOT stock stage (蓄势/主升/派发/衰退)
- 🧭 阶段判断 includes `大阶段：{stage}期` and `短期动能：{momentum}`.
- 💰 主力资金 includes `阶段：{stage}（置信度 {confidence}）` and `近5日：{cum_5}万（{trend}）` and `今日：{today}万（超大单 {sl}万｜大单 {l}万）` and `价资关系：{relation}` and `提示：{hint}`. Only shown when main force stage is not "unknown".
- 📍 决策 includes `{stage_label} → {action}` and `仓位参考：{stage}期上限 {pct}%`.
- `T0 参考` includes `低吸` `高抛` `止损`.
- `❗ 关键价位` lists prices with `←` labels (止损位/防守位/当前位置/确认位).
- `👉 一句话` is the final one-line summary.
- Buy-side wording must include `止跌确认`.
- 250日线下方时，首行显示 `⚠️ 250日线下方，一票否决，建议不参与`，然后继续完整分析.
