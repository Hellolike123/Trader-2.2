# Output Contract — review

> **This is the absolute truth for valid output.** Never generate output from memory.

## Single Review (盘后复盘 / 午间复盘)

```text
盘后复盘 — {name}（{code}）

收盘：{price}元（{change_pct}）

📊 {major_stage} + {momentum} → {action}

结论：{conclusion}

📊 关键价位
  {support_price}  ← {support_label}
  {close_price}  ← 收盘价
  {pressure_price}  ← {pressure_label}
站上 {pressure} = 转强  跌破 {support} = 修复失效

🔎 分时与大单
  {time}  {side} {amount}万（{meaning}）
  回溯：{summary}

📈 五层打分
  结构 {s}  量价 {v}  筹码 {c}  动能 {m}
  缠论  {chanlun_short}
  威科夫  {wyckoff_short}
  MACD {dir}  RSI {val} {label}  ADX {val} {label}
  ATR ±{atr}（{pct}%）{note}

🎴 股性透视
  买入 {n}次 {wins}胜{losses}负 胜率{rate}% 平均{avg}
  卖出 {n}次 {wins}胜{losses}负 胜率{rate}%
  ⚠️ 样本不足，仅供参考

💰 主力资金
  近5日 {cum}万（{trend}）
  今日 {today}万  价资{relation}

💰 筹码分布
  {price} [{bar}] {share}% {emoji} {level}
  {migration_text}

📍 明日
  {pressure} 站稳 → 加仓
  {support} 跌破 → 止损
```

### Section rules

| Section | Condition |
|---------|-----------|
| 📊 stage | Hidden if stage_result data unavailable |
| 🎴 股性透视 | Hidden if signals.jsonl missing or < 1 signal |
| 💰 主力资金 | Hidden if main_force data unavailable |
| 💰 筹码分布 | Hidden if no chip distribution peaks |
| ATR | Hidden if atr_data unavailable |
| MACD/RSI/ADX | Hidden if momentum_raw unavailable |

### 判读规则

- RSI < 30 → `超卖`  RSI > 70 → `超买`  RSI < 45 → `偏弱`  RSI > 55 → `偏强`  else `中性`
- ADX > 25 且 strong_trend → `趋势强`  else `无趋势`
- MACD: `偏多` / `偏空` / `中性`
- 筹码搬家: 支撑减少+阻力增加 → `筹码在搬家，主力出货`; 支撑增加+阻力减少 → `主力在吸筹`; else `底部筹码基本稳定`

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

## Format Rules (CRITICAL)

1. **首行** 必须是 `盘后复盘 — {名称}（{代码}）`
2. **禁用** Markdown 标题 (#), 表格 (|...|), 加粗 (**), 列表 (*/-)
3. 每节之间空一行
4. 价格在左、说明在右，用 `←` `→` 对齐
5. 手机适配：每行不超过 20 字

## Old Output Detection

If output contains markdown tables, T0 execution cards, `执行价`, or the two-table `trader` action report format, rerun the script.
