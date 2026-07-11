# Output Template — t0

> **This is the absolute truth for valid output.** Never generate output format from memory.

## Manual Card Output

Markdown output from `render_markdown()` — used when `final_t0.py` is invoked without `--monitor`.

Must start with `🎯 T0 盯盘助理`:

```text
🎯 T0 盯盘助理
{name}（{symbol}）｜现价 xx.xx（+x.xx%）

📌 触发价
当前：{低吸/高抛/不动} ｜ 止损：xx.xx元
低吸：{状态}，{观察价以下}
高抛：{状态}，{观察价附近}
止盈：xx.xx｜xx.xx｜xx.xx
波动：{level_advice}
低吸还差 x.x%（约N根5m线）    （← 新增：距触发价量化提示）

💰 大单异动
买入 X笔 Y万 ｜ 卖出 X笔 Z万
09:35 +2202万  09:40 -1664万  09:45 -1404万
净流入 -802万，主力偏空

或（使用5m分时估算时，无Tick数据）

💰 分时估算
全部买入 X笔 +Y万
09:35 +2202万  09:40 +1664万  09:45 +1404万
净流入 +527万，主力偏多
（5m分时估算，非真实Tick数据）

📈 操作建议
{order_book line}
{time} {level}｜{description}，现价xx.xx元。
🔴 购买高潮（BC）信号 {reason} 动作：减仓 1/3
⚠️ 弱势信号（SOW）{reason} 动作：关注，准备减仓
🔴 筹码搬家清仓信号 {warning_text} 动作：清仓

🚨 应急指引                                          （← 新增段：非标准场景）
放量接近高抛区，可分批提前减仓
盘中急跌靠近低吸区，等5m止跌信号再动手
ICT: 下扫 xx.xx 后收回，辅助低吸确认

⚠️ 风控提醒
跌破 xx.xx元 止损退出
⚠️ 数据不完整，盘中判断可能不准
```

### Sections（条件显示规则）

> 五段精简结构（触发价 / 大单异动 / 操作建议 / 应急指引 / 风控提醒）。

- `📌 触发价` — 始终显示。含当前动作、止损价、低吸/高抛观察价；有止盈计划且 `risk_r > 0` 时显示止盈；有 ATR 波动提示时显示波动。**新增**：距触发价距离量化提示（% + 估算5m K线根数）。
- `💰 大单异动` — 有 tick 数据且存在大单事件时显示；无 tick 数据时显示 `💰 分时估算`（互斥）。
- `📈 操作建议` — 有 `order_book` 动态、盘中关键事件(`history`) 或 实时信号(BC/UTAD/SOW/筹码搬家) 时显示，合并原「盘中动态」与「实时信号」两段。
- `🚨 应急指引` — **新增**：覆盖非标准场景（放量未到高抛区/急跌未到低吸区/临近涨跌停/双触发并存/ICT辅助提示），有场景触发时显示。
- `⚠️ 风控提醒` — 始终显示。含止损退出/不再低吸；`data_status` 为 `partial`/`degraded` 时追加数据提示。

## Monitor Alert Output

Appears only on state changes from `final_t0.py --monitor`:

```
{name} {低吸触发/高抛触发/止损退出} | 现价 xx.xx | {buysell} xx.xx 附近
```

Valid alert patterns: `低吸触发`, `高抛触发`, `止损退出`.
