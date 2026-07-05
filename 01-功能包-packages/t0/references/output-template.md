# Output Template — t0

> **This is the absolute truth for valid output.** Never generate output format from memory.

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

### Sections（条件显示规则）

- `止盈` — 当 `exit_plan` 有项目且 `risk_r > 0` 时显示
- `💰 资金异动` — 当 tick 数据可用且有事件时显示
- `💰 分时估算` — 仅当有 5m bar 估算（无 tick 数据）时显示，与「资金异动」互斥
- `📋 盘中动态` — 当有 `order_book` 或 `history` 数据时显示
- `🔔 实时信号` — 当有 wyckoff 信号（BC/UTAD/SOW）或筹码搬家警告时显示
- Footer text — 当 buy 状态为 `可执行` 时显示 `止损退出`；否则显示 `后不再低吸`

## Monitor Alert Output

Appears only on state changes from `final_t0.py --monitor`:

```
{name} {低吸触发/高抛触发/止损退出} | 现价 xx.xx | {buysell} xx.xx 附近
```

Valid alert patterns: `低吸触发`, `高抛触发`, `止损退出`.
