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

v2.3 合法骨架：`🎯` + 短结论 + `⚡ 今日剧本`（有仓）+ `📌 盘面` + `📌 买卖价` + 失效/参考。  
结论含 `看反T/看正T/观望/宜不做` + `人确认`；持仓纪律并入剧本，不再单独 `📉`。

## Additional Rules

- Valid manual output has no markdown tables, bullet lists, bold markers, blockquotes, or `##/###` headings.
- WeChat: prefer short lines; fullwidth `｜` ok; avoid long `·` chains and 5m-distance noise.
