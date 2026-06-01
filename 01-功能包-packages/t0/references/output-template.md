# Output Template — t0

> **This is the absolute truth for output structure.** Never generate output format from memory.

## Manual Card Output (精简为 4 部分)

Must start with `🎯 T0 盯盘助理` and use this structure:

```text
🎯 T0 盯盘助理
{name}（{symbol}）｜现价 xx.xx（+/-x.xx%）

🔍 扫描
当前：不动 / 低吸 / 高抛
低吸：{状态}，{观察价}
高抛：{状态}，{观察价}
止损：xx.xx 元

📋 盘中动态
{time} {icon} {event_description}
...

👀 下一步
买入：{观察价}是否5m止跌
卖出：{观察价}是否冲高失败
止损：跌破{止损价}后不再低吸
```

## Monitor Alert Output

Appears only on state changes (no fixed format):

```
南网科技 低吸触发 | 现价 52.73 | 买入 52.65 附近
```

Valid alert patterns: `低吸触发`, `高抛触发`, `止损退出`.
