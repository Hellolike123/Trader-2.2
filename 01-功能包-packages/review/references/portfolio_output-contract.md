# Output Contract — review (portfolio)

> **This is the absolute truth for valid output.** Never generate output from memory.

## Rotation Output (四阶段轮动)

```text
轮动仓位 — {name_a} + {name_b}

🔔 决策：不动 / 轮动（{类型}）

📝 分析
  {name_a}在{stage}期，{reason}。
  {name_b}在{stage}期，{reason}。
  {conclusion}。

📊 持仓
  {name_a}：{stage}+{momentum} ｜ 现价 {price} ｜ 浮盈 {pnl}%
  {name_b}：{stage}+{momentum} ｜ 现价 {price} ｜ 浮盈 {pnl}%

🔁 轮动方案（仅轮动时显示）
  从{name_a}减 {pct}%，释放约 {pct}% 总仓
  {name_b}承接 {pct}%，剩余留现金

📍 关键价位
  {name_a}：确认 {confirm} ｜ 防守 {stop}
  {name_b}：确认 {confirm} ｜ 防守 {stop}

👀 触发条件
  {name_a}跌破 {stop} → 减仓/清仓
  {name_b}站上 {confirm} → 可以加仓
```

Rotation types: `风控退出`（清仓）、`强轮动`（1/3）、`轻轮动`（1/6）、`标准轮动`（25%）。

No markdown tables. Use indented alignment.
Do not output: `ATR14=`, `极端波动`, `高波动`, `低波动`.

## Old Output Detection

If output contains markdown tables or old format without stage info, rerun the script and return stdout verbatim.
