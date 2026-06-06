# Output Template — t0

> **This is the absolute truth for output structure.** Never generate output format from memory.

## Manual Card Output (精简为 3 部分)

Must start with `🎯 T0 盯盘助理` and use this structure:

```text
🎯 T0 盯盘助理
{name}（{symbol}）｜现价 xx.xx（+/-x.xx%）

🔍 扫描
当前：不动 ｜ 止损：xx.xx
低吸：{状态}，{观察价}
高抛：{状态}，{观察价}
止盈：xx.xx

💰 资金异动（真实Tick）
全部卖出 5笔 -8022万
09:35 -2202万｜09:40 -1664万｜09:45 -1404万
净流入 -8022万，主力偏空

或

💰 分时估算（5m估算，非真实Tick）
全部卖出 5笔 -8022万
09:35 -2202万｜09:40 -1664万｜09:45 -1404万
净流入 -8022万，主力偏空

📋 盘中动态（有事件时显示）
{time} {icon} {event_description}

👀 下一步
跌破 xx.xx 后不再低吸
```

## Monitor Alert Output

Appears only on state changes (no fixed format):

```
南网科技 低吸触发 | 现价 52.73 | 买入 52.65 附近
```

Valid alert patterns: `低吸触发`, `高抛触发`, `止损退出`.
