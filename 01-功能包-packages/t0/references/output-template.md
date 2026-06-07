# Output Template — t0

> **This is the absolute truth for output structure.** Never generate output format from memory.

## Manual Card Output

Markdown output from `render_markdown()` — used when `final_t0.py` is invoked without `--monitor`.

Must start with `🎯 T0 盯盘助理`:

```text
🎯 T0 盯盘助理
{name}（{symbol}）｜现价 xx.xx（+x.xx%）

🔍 扫描
当前：{低吸/高抛/不动} ｜ 止损：xx.xx元
低吸：{状态}，{观察价}
高抛：{状态}，{观察价}
止盈：xx.xx｜xx.xx｜xx.xx

💰 资金异动
买入 X笔 Y万 ｜ 卖出 X笔 Z万
09:35 +2202万  09:40 -1664万  09:45 -1404万
净流入 -802万，主力偏空

或（使用5m分时估算时）

💰 分时估算
全部买入 X笔 +Y万
09:35 +2202万  09:40 +1664万  09:45 +1404万
净流入 +527万，主力偏多
（5m分时估算，非真实Tick数据）

📋 盘中动态（有事件时显示）
{time} {level}｜{description}，现价xx.xx元。

🔔 实时信号（有信号时显示）
  🔴 购买高潮（BC）信号
    {reason}
    动作：减仓 1/3
  ⚠️ 弱势信号（SOW）
    {reason}
    动作：关注，准备减仓
  🔴 筹码搬家清仓信号
    {warning_text}
    动作：清仓

👀 跌破 xx.xx元 止损退出
```

### Sections

| Section | Condition |
|---------|-----------|
| `止盈` | Shown only when `exit_plan` has items AND `risk_r > 0` |
| `💰 资金异动` | Shown when tick data is available and events exist |
| `💰 分时估算` | Shown when only 5m bar estimates exist (no tick data) |
| `📋 盘中动态` | Shown when `order_book` or `history` data exists |
| `🔔 实时信号` | Shown when wyckoff signals (BC/UTAD/SOW) or chip migration warnings exist |
| Footer text | `止损退出` when buy state is `可执行`; `后不再低吸` otherwise |

## Monitor Alert Output

Appears only on state changes from `final_t0.py --monitor`:

```
{name} {低吸触发/高抛触发/止损退出} | 现价 xx.xx | {buysell} xx.xx 附近
```

Valid alert patterns: `低吸触发`, `高抛触发`, `止损退出`.
