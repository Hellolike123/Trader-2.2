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
📏 仓位上限
🧭 为什么
⚠️ 如果走势不对
📌 最终行动卡
🧭 简要分析
📍 价格阶梯
📍 买卖点
```

## Fusion Verbatim Rule

- The `🎯 {stage} → {action}` line MUST appear after the MA line.
- Below it, the dual status line: `基础状态：{base_status} ｜ 体系结论：{theory_status}` MUST appear.
- The emoji is always 🎯 for consistency.

## Decision Section Rule

- The section title MUST be `📍 决策` (not `📍 操作建议` or `📍 价格阶梯`).
- After the title, a decision summary block:
  - Status line: `状态：{base_status}`
  - Empty position: `空仓：在 {low_zone_lower}-{low_zone_upper}元 试探买 {position_cap}%，止损 {stop}`
  - Has position: `有底仓：反弹 {take} 冲不动减`
- Price ladder follows below (sorted from low to high).
- Each line MUST include a reason in parentheses.
- Stop loss line: `{price} 止损（跌破支撑，趋势破坏）`
- Trial buy line: `{price} ← 试探买 {position}%（{reason}，盈亏比 {R}:1，{win_rate}% 胜率回本，止损 {stop}）`
- Sell lines: `{price} → 卖 {ratio}%（{reason}）`
- Stage exit: `阶段转派发 → 清仓（主力出货，趋势结束）`

## Additional Rules

- Valid output does NOT use markdown tables.
- Valid output does NOT use `高抛区间`, `压力`, `支撑回踩观察` (these have been removed).
