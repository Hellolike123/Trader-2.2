# Output Style Guide — t0

> Format rules specific to t0 output. For global WeChat formatting rules, see `AGENTS.md` section "通用输出格式约束与日常工作流高分示例".

## Old Output Detection

If output contains any of these, rerun the script（含 v1 指令叙事与旧四段式）:

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
🚩 关键价位
🕒 今日关键事件
💰 仓位管控
👀 下一步只盯
三重共振买
三重共振卖
三重共振 → 可执行
可执行 
可低吸
可加仓
做T指令
📌 执行
🔗 信号
```

v2.2 合法骨架：`🎯` + 短结论 + `📌 盘面` + `📌 买卖价` + 失效 + 可选做T清单/`💰`/持仓纪律。  
清单：`做T清单（人勾选）` 或劝退时 `今日宜不做（人确认）`；结论可含 `宜不做`。

## Additional Rules

- Valid manual output has no markdown tables, bullet lists, bold markers, blockquotes, or `##/###` headings.
- WeChat: prefer short lines; fullwidth `｜` ok; avoid long `·` chains and 5m-distance noise.
