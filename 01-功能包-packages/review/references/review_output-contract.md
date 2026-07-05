# Output Contract — review

> **This is the absolute truth for valid output.** Never generate output format from memory.

## Single Review (盘后复盘 / 午间复盘)

```text
盘后复盘 — {name}（{code}）

收盘：{price}元（{change_pct}）

📊 阶段定位：{major_stage} + {momentum} → {stage_action}

结论：{conclusion}

📊 关键价位
  {support_price_1}  ← {support_label_1}
  {support_price_2}  ← {support_label_2}
  {support_price_3}  ← {support_label_3}
  {pressure_price_1}  ← {pressure_label_1}
  {pressure_price_2}  ← {pressure_label_2}
  {pressure_price_3}  ← {pressure_label_3}
站上 {key_pressure} = 转强  跌破 {key_support} = 修复失效

🔎 分时与大单
  {time}  {side} {amount}万 / {hands}手（{meaning}）
  回溯：{summary}

📈 五层打分
  结构 {structure}  量价 {volume}  筹码 {chip}  动能 {momentum}
  缠论  {chanlun_short}
  威科夫  {wyckoff_short}
  MACD {dir}  RSI {val} {label}  ADX {val} {label}
  ATR ±{atr14:.2f}（{atr_ratio*100:.1f}%）{note}

🎴 股性透视
  买入 {n}次 {wins}胜{losses}负 胜率{rate}% 平均{avg_pnl:+.2f}%
  卖出 {n}次 {wins}胜{losses}负 胜率{rate}%
  ⚠️ 样本不足，仅供参考

💰 主力资金
  近5日 {cum_5d:+.0f}万（{trend}）
  今日 {today_flow:+.0f}万  价资{relation}

💰 筹码分布
  {price:.2f} [{bar}] {share:.1f}% {emoji}{level}
  {migration_text}

📍 明日
  {key_pressure} 站稳 → 加仓
  {key_support} 跌破 → 止损
```

### Section rules（条件显示）

- 📊 阶段定位 — 当 `stage_result` 不可用（无 major_stage）时隐藏
- 📈 ATR — 当 `atr_data.available` 不为 True 时隐藏
- 📈 MACD/RSI/ADX — 当对应的 `momentum_raw` 数据缺失时隐藏
- 🎴 股性透视 — 当 `signals.jsonl` 中该 symbol 信号数 < 1 时隐藏
- 💰 主力资金 — 当 `main_force` 数据不可用或阶段为 "unknown" 时隐藏
- 💰 筹码分布 — 当 `chip_distribution` 无 peaks 时隐藏
- 🔔 今日信号回顾 — 当无 wyckoff 信号且无筹码搬家警告时隐藏（由 `review_render._build_signal_review_section` 生成）
- 🎯 明日行动 — 当使用 `review_render._build_tomorrow_action_section` 时出现，替代更简单的 📍 明日

### 判读规则

- RSI < 30 → `超卖`  RSI > 70 → `超买`  RSI < 45 → `偏弱`  RSI > 55 → `偏强`  else `中性`
- ADX > 25 且 strong_trend → `趋势强`  else `无趋势`
- MACD: 当 macd_line > dea 时 = `偏多`, 当 macd_line < dea 时 = `偏空`, 否则 = `中性`；柱状线绝对值 < 0.01 标注 "(不算强)"
- 筹码搬家: 支撑减少+阻力增加 → `筹码在搬家，主力出货`; 支撑增加+阻力减少 → `主力在吸筹`; else `底部筹码基本稳定`

## Compare Output

```text
📌 多股复盘比较｜{date}

结论：
明天主盯{main_name}，副盯{deputy_name}。
排序依据是结构、量价、筹码压力、动能和持仓适配。

排序：
1）{name}|{state}|总分 {score}|压力 {key_pressure}
...

主盯：
{main_name}｜{main_state}
理由：
结构分 {structure_score}，量价分 {volume_score}，动能分 {momentum_score}。
关键压力 {main_key_pressure}，关键支撑 {main_key_support}。
动作：{main_action}

副盯：
{deputy_name}｜{deputy_state}
理由：
结构分 {structure_score}，量价分 {volume_score}，动能分 {momentum_score}。
关键压力 {deputy_key_pressure}，关键支撑 {deputy_key_support}。

只观察 / 先防守：
{rest_name}｜先防守｜{rest_state}｜{rest_first_block}

明日动作：
{name}：主盯 {key_pressure} 能否放量站稳。
{name}：副盯，不追高，守住 {key_support} 继续观察。
{name}：不主动加仓，等结构重新确认。

筹码密集区（近60日量价粗算）：
{name}：{price}({level}), {price}({level})
```

## Format Rules (CRITICAL)

1. **首行** 必须是 `盘后复盘 — {名称}（{代码}）`
2. **禁用** Markdown 标题 (#), 表格 (|...|), 加粗 (**), 列表 (*/-)
3. 每节之间空一行
4. `🔎 分时与大单` 中：优先显示 big_order.events（每个 event 包含 time/side/amount_wan/hands/meaning/near_focus/focus_label），若 tick 数据不足则降级为 intraday.lines（5分钟量柱叙事）
5. `📈 五层打分` 中：`结构` = theory.scores.structure，`量价` = theory.scores.volume，`筹码` = theory.scores.chip，`动能` = theory.scores.momentum
6. 手机适配：每行不超过 20 字

## JSON 输出入口

单票复盘 JSON 由 `review_single.run_single(target, cost, trade_date, output="json", session)` 生成，返回 `render_json(review)` 即 `build_review()` 的完整返回 dict。

## Old Output Detection

If output contains markdown tables, T0 execution cards, `执行价`, or the two-table `trader` action report format, rerun the script.
