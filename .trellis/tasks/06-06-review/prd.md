# PRD: 盘后复盘输出格式优化

## 背景

当前 review 盘后复盘输出有 14 节，在手机上显示太长、信息重复。需要精简并统一为 trader 风格（价格左、说明右，`←` `→` 对齐）。

## 目标

将 14 节压缩为 9 节，手机一屏至一屏半可见，每节 2-4 行。

## 新输出格式

```
盘后复盘 — {name}（{code}）

收盘：{price}元（{change_pct}）

📊 {major_stage} + {momentum} → {action}

📊 关键价位
  {support_price}  ← {support_label}
  {close_price}  ← 收盘价
  {pressure_price}  ← {pressure_label}

🔎 分时与大单
  {time}  {direction} {amount}万（{meaning}）
  {time}  {direction} {amount}万（{meaning}）
  回溯：{summary}

📈 五层打分
  结构 {s}  量价 {v}  筹码 {c}  动能 {m}
  缠论  {chanlun_short}
  威科夫  {wyckoff_short}
  MACD {macd_dir}  RSI {rsi_val} {rsi_label}  ADX {adx_val} {adx_label}
  ATR ±{atr_val}（{atr_pct}%）{atr_note}

🎴 股性透视
  买入 {n}次 {wins}胜{losses}负 胜率{win_rate}% 平均{avg_return}
  卖出 {n}次 {wins}胜{losses}负 胜率{win_rate}%
  ⚠️ 样本不足，仅供参考

💰 主力资金
  近5日 {cum_flow}万（{trend}）
  今日 {today_flow}万  价资{relation}

💰 筹码分布
  {price} [{bar}] {share}% {emoji} {level}
  {price} [{bar}] {share}% {emoji} {level}
  {chip_migration_text}

📍 明日
  {pressure} 站稳 → 加仓
  {support} 跌破 → 止损
```

## 关键设计

### 合并原则
1. 🔎 分时走势 + 💰 主力资金中的大单回溯 → 合并为 🔎 分时与大单（只出现一次）
2. 结论 + model_summary + 👉 一句话 → 合并为结论一行
3. ⚠️ 最大风险 → 内联到 📊 关键价位最后
4. 🎯 信号判断 → 去掉（结论重复）
5. 💰 筹码分布 + 📋 历史信号 + 📍止盈进度 → 尾部合并

### 新增内容
1. 📊 阶段标签（蓄势期+转弱→低吸高抛）— 从 stage_result 读取，放在标题后第一行
2. RSI / ADX — 在五层打分中显示（比 MACD 更敏感）
3. 🎴 股性透视 — 复用 trader 的 `_load_historical_win_rate` 逻辑
4. 筹码搬家结论行 — 从 chip_migration 读取

### 手机适配
- 每行不超过 20 字
- 价格在左、说明在右，`←` `→` 对齐
- 每节之间空行
- 禁用 Markdown 标题/表格/加粗

## 数据源

| 字段 | 来源 |
|------|------|
| stage | review["stage_result"]["major_stage/momentum/action"] |
| 大单 | review["big_order"]（已存在，从 tick_cache 或 fetch_ticks） |
| RSI/ADX | 新加：review["momentum_raw"]（需从 theory_verdicts 传出来） |
| 股性卡 | 新加：`_load_historical_win_rate(provider, symbol, name)` 从 signals.jsonl + kline 计算 |
| 筹码搬家 | review["chip_migration"]["warning_text"]（已存在） |
