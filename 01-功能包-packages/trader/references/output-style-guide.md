# Output Style Guide — trader

> Format rules specific to trader output. Absolute structure: `output-template.md`.
> Production render: `trader_shared.report_core.render_single` → default `render_short_midline`.
> Pipeline: `report_builder` → `attach_short_midline_and_decision` → `render_short_midline`
> （builder 内：mid_key_prices + mistery_gate + chan_discipline merge → conclusion → attach）。

## Prohibited Content

- Do not invent intraday order instructions beyond script-rendered T0 lines.
- Do not write mi姐 / Mistery brand words in user-facing Markdown (internal field may still be `mistery_gate`).
- Do not use R:R jargon like `2.1R` / `不足 1R`.
- Do not put stage words (蓄势/主升/派发…) into 中线「看法」; no independent `阶段：` / `看法：` lines — stage detail under `威科夫：`, bias under `定论：`.
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

(`SHORT_MIDLINE_REPORT=false` **已忽略**，无法回退旧 `🎯`+`📍 决策`；始终 `render_short_midline`。)

## Short-midline Layout (code order)

Matches `report_renderer/short_midline.py` (`render_short_midline`):

1. Title: `分析报告 — {name}（{code}）｜短中线`
2. Meta: 现价（含 MA20/MA250）；`综合动能 … ｜ {板块指数} ±x% ｜ {行业短名} ±x% ｜ 个股 ±x%`（不写正常/偏弱/跑赢）；量价行可选量比/换手/调整天数，ATR14（含复权口径）并入同行列；年线下方警告
3. `🧭 中线`
   - **无**独立 `阶段：` 行（`midline_stage` 字段供共振；细读见威科夫）
   - optional `定论：` ← midline_verdict_note + 可选偏多/偏空短因（**无**独立 `看法：` 行）
   - `威科夫：` / `缠论：` ← View / `*_midline` only
   - optional `位置：` ← pivot_position_weekly
   - `关键价（中线）` 生命线 / 回踩区 / 压力 / 目标 ← `mid_key_prices`（周线引擎，无 🌟）
4. `⚡ 短线`（A 版读序）
   - `缠论：` → optional 买点 → `威科夫：`（日线只对照；禁止「日线阶段：」；箱体 lo-hi / 箱体未成形）→ optional `事件：` → `动能：` → `资金：`
   - （空行）→ `共振：` → `新开：` → `动作：` → optional `原因：` → `破位看：`
   - `关键价（短线）` 止损 / 买点区 / `🌟 现价` / 卖点区 + 买/追亏赚两行 ← `key_prices`
5. optional `说明：` when mid/short conflict
6. `✅ 亮点` / `⚠️ 风险` / optional `📌 本周只做` / `T0：…` / 入池提示

## C1 Entry Line

From `chan_discipline.build_entry_checklist` / `format_entry_line_c1`（买点盖失败时由 `attach_buy_point` 强制收紧）:

| Flag | Label |
|------|----------------|
| mid_ok | 中线趋势 |
| in_pullback | 回踩到位 |
| short_trigger | 买点信号 |
| conf_ok | 融合置信（非「方向一致」） |
| fund_ok | 筹码资金稳 |

- All five True → `新开：可试探 · 五项齐了`
- Else → `新开：先别买 · …`（人话缺项，非旧版「否（缺：…）」模板）
- Display is compact one line; do not expand five ticks unless debugging JSON

## Discipline (动作 / 新开 / 破位看)

- Merge: `mistery_gate` + `chan_discipline` via `merge_discipline` — **only tighten** caps/actions
- Never rewrite major_stage / fusion scores / support / stop prices via discipline
- User-facing: `动作` / `新开` / `破位看` / 纪律 — not mi/Mistery；**不用「出手」作主标签**
- Mid target alone must not greenlight a buy; need short trigger + checklist

## Fixed Keywords

- Must keep the words 止损 and 买 somewhere in the short key-price / ladder lines
- WeChat plain text: no `#` headings, `**bold**`, markdown tables, `---` rules

## Additional Rules

- Prefer script markdown; do not re-compose from memory
- Direction / new entries follow `decision_view` (resonance ∧ strategy ∧ discipline); `fusion.weighted_score` is instrument-only
- Mid key prices come from weekly engine (`mid_key_prices.py`), not daily `find_key_levels` success path
