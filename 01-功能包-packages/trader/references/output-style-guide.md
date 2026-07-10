# Output Style Guide — trader

> Format rules specific to trader output. Absolute structure: `output-template.md`.
> Production render: `trader_shared.report_core.render_single` → default `render_short_midline`.
> Pipeline: `run_analysis.build_report` → mid_key_prices + mistery_gate + chan_discipline merge → conclusion → render.

## Prohibited Content

- Do not invent intraday order instructions beyond script-rendered T0 lines.
- Do not write mi姐 / Mistery brand words in user-facing Markdown (internal field may still be `mistery_gate`).
- Do not use R:R jargon like `2.1R` / `不足 1R`.
- Do not put stage words (蓄势/主升/派发…) into 中线「看法」; stage only under `阶段：`.
- Do not backfill 中线 威科夫/缠论 from daily experts; mid fields only (`*_midline`).
- Do not hand-write a full report when `--output markdown` succeeds.

## Old Output Detection

If output contains any of these **as the main single-ticket layout**, rerun the script
(`final_report.py` / `render_single`). Default path is short-midline dual-track.

```
🎯 蓄势期 →
🎯 {stage} → {action}
基础状态：
体系结论：
📍 决策
📍 价格阶梯
📍 买卖点
🗳️ 短线专家
🗺 空间参考
✅ 先给结论
📏 仓位上限
🧭 为什么
🧭 简要分析
⏱️ T0 简版
做T
执行价
```

Valid first line must look like:

```
分析报告 — {名}（{码}）｜短中线
```

(Legacy only when `SHORT_MIDLINE_REPORT=false`; do not treat legacy as current product default.)

## Short-midline Layout (code order)

Matches `report_core.render_short_midline`:

1. Title: `分析报告 — {name}（{code}）｜短中线`
2. Meta: 现价；`动能 … ｜ 大盘 …`；`MA5 ｜ MA20 ｜ MA250`；可选量比/换手；年线下方警告
3. `🧭 中线`
   - `阶段：` ← major_stage（入池/轮动/纪律输入）
   - `看法：` ← 周线结论（conclusion.midline；非四阶段词）
   - `威科夫：` / `缠论：` ← `wyckoff_midline` / `chanlun_midline` only
   - optional `位置：` ← pivot_position_weekly
   - `关键价（中线）` 生命线 / 回踩区 / 压力 / 目标 ← `mid_key_prices`（周线引擎，无 🌟）
4. `⚡ 短线`
   - `看法：` / 日线缠论 / optional `位置：` / 动能 / `裁定：`
   - **C1** `新开：否（缺：…）` 或 `新开：可试探（清单全绿）`
   - `出手：` + optional `分仓：` + optional `失效：`
   - `关键价（短线）` 止损 / 买点区 / `🌟 现价` / 卖点区 + 买/追亏赚两行 ← `key_prices`
5. optional `说明：` when mid/short conflict
6. `✅ 亮点` / `⚠️ 风险` / optional `📌 本周只做` / `T0：…` / 入池提示

## C1 Entry Line

From `chan_discipline.build_entry_checklist` / `format_entry_line_c1`:

| Flag | Label in 缺： |
|------|----------------|
| mid_ok | 中线趋势 |
| in_pullback | 回踩到位 |
| short_trigger | 买点信号 |
| conf_ok | 信号一致 |
| fund_ok | 筹码资金稳 |

- All five True → `新开：可试探（清单全绿）`
- Else → `新开：否（缺：A｜B）` (labels joined by `｜`)
- Display is compact one line; do not expand five ticks unless debugging JSON
- Render also demotes trial wording in `出手` if checklist not all_green

## Discipline (出手 / 分仓 / 失效)

- Merge: `mistery_gate` + `chan_discipline` via `merge_discipline` — **only tighten** caps/actions
- Never rewrite major_stage / fusion scores / support / stop prices via discipline
- User-facing words: 出手 / 失效 / 纪律 / 新开 / 分仓 — not mi/Mistery
- `分仓：中线≤x% ｜ 短线≤y% ｜ 总≤z%` when cap fields present
- Mid target alone must not greenlight a buy; need short trigger + checklist

## Fixed Keywords

- Must keep the words 止损 and 买 somewhere in the short key-price / ladder lines
- WeChat plain text: no `#` headings, `**bold**`, markdown tables, `---` rules

## Additional Rules

- Prefer script markdown; do not re-compose from memory
- Direction for fusion still uses `fusion.weighted_score`; stage/momentum are inputs not final direction
- Mid key prices come from weekly engine (`mid_key_prices.py`), not daily `find_key_levels` success path
