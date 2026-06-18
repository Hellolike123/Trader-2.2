# Output Style Guide — trader

> Format rules specific to trader output. For global WeChat formatting rules, see `AGENTS.md` section "通用输出格式约束与日常工作流高分示例".

## Prohibited Content

- Do not output intraday execution prices or concrete order instructions.
- Do not output `⏱️ T0 简版`, `做T`, `执行价`.

## Old Output Detection

If output contains any of these, rerun the script:

```
⏱️ T0 简版
做T
执行价
✅ 先给结论
🎯 今日行动
📏 仓位上限
🧭 为什么
⚠️ 如果走势不对
📌 最终行动卡
🧭 简要分析
基础状态：
体系结论：
```

## Fusion Verbatim Rule

- The `融合｜{emoji} {action}（加权分 X.XX，置信度 XX%）` line MUST appear between the stage summary (`📊 XX期`) and the buy/sell section (`📍 买卖点`).
- This line comes from `fusion.fusion_verbatim` in the JSON output. Copy it verbatim; do NOT paraphrase or omit it.
- The emoji (🟢/🔴/🟡/⚪) and the weighted_score direction MUST be consistent. If they conflict, rerun the script.

## Additional Rules

- Valid output does NOT use markdown tables.
