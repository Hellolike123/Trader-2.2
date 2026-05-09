# Output Contract — review-trader

> **This is the absolute truth for valid output.** Never generate output from memory.

## Single After-Close Review (no markdown tables)

```text
📌 {name}｜{date}盘后复盘
收盘 {price}（{change_pct}）｜ 成本 {cost}｜ 浮盈亏 {pnl}

结论  {conclusion_text}  {model_summary}

📊 关键价位
支撑：{support} ｜ 压力：{pressure} ｜ 止损：{stop} ｜ 止盈：{take}
站上 {pressure} = 转强    跌破{support} = 修复失效

⚠️ 最大风险  放量跌破 {support}  含义：关键支撑失败

🔎 分时走势  {intraday_summary}

📈 五层打分
结构{s}/量价{v}｜筹码{c}｜动能{m}
缠论：{text}  威科夫：{text}  筹码：{text}  资金行为：{text}

🎯 信号判断  偏多：✓ {bullet}  ! 警惕：{bullet}

👉 一句话  {one_liner}
明天只有放量站稳 {pressure} 才算确认；否则继续按短线修复看。
如果放量跌破 {support}，这次修复判断失效。
```

Optional sections (present if data available):
- `ATR数据不足` or `💡 参考信息  日均波动约 ±{atr}元（占总价{pct}%）`
- `MACD（判断大方向）：目前{偏多/偏空/中性}...`
- `💰 筹码分布（近60日量价粗算）`
- `📋 今日信号回溯` (from signals.jsonl)

## Midday Review

Same format but title has `午间复盘` instead of `盘后复盘`.

## Compare Output

```text
📌 多股复盘比较｜{date}
结论：明天主盯{name}，副盯{name}。
排序依据是结构、量价、筹码压力、动能和持仓适配。
排序：1）{name}|{state}|总分 {score}|压力 {price}
主盯：...  副盯：...  只观察/先防守：...
明日动作：
筹码密集区（近60日量价粗算）：...
```

## Old Output Detection

If output contains markdown tables, T0 execution cards, `执行价`, or the two-table `trader` action report format, rerun the script.
