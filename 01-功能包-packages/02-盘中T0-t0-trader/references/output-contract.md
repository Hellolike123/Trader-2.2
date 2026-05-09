# Output Contract — t0-trader

> **This is the absolute truth for valid/invalid output.** Never generate output format from memory.

## Manual Card Output

Must start with `🎯 T0 盯盘助理` and use this structure:

```text
🎯 T0 盯盘助理
{name}（{symbol}）｜现价 xx.xx（+/-x.xx%）

🔍 扫描

当前：不动 / 低吸 / 高抛
买入：{状态}，观察{方向}。
卖出：{状态}，观察{方向}。

🚩 关键价位

低吸观察：... | 高抛观察：...
止损：xx.xx元 或 无

🕒 今日关键事件

{time} {description}
...

💰 仓位管控

当前：{action}
触发后：{action}
止损：xx.xx元 或 无

👀 下一步只盯

买入：...
卖出：...
止损：...
```

## Monitor Alert Output

Appears only on state changes (no fixed format):

```
南网科技 低吸触发 | 现价 52.73 | 买入 52.65 附近
```

Valid alert patterns: `低吸触发`, `高抛触发`, `止损退出`.

## Old Output Detection

If output contains any of these, rerun the script:

```
T0 执行卡
⏱️ 盘中 T0
📉 低吸计划
📈 高抛计划
规则版本：
数据状态：
今日做法：
当前动作：
先买后卖
先卖后买
```

Valid manual output has no markdown tables, bullet lists, bold markers, blockquotes, or `##/###` headings.
