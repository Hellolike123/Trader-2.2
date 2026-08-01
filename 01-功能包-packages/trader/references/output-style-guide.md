# Output Style Guide — trader

> Format rules specific to trader output. Absolute structure: `output-template.md`.
> Production render: `trader_shared.report_core.render_single` → default `render_short_midline`.
> Pipeline: `report_builder` → `attach_short_midline_and_decision` → `render_short_midline`
> （builder 内：mid_key_prices + mistery_gate + chan_discipline merge → conclusion → attach）。

## Prohibited Content

- Do not invent intraday order instructions beyond script-rendered T0 lines.
- Do not write mi姐 / Mistery brand words in user-facing Markdown (internal field may still be `mistery_gate`).
- Do not use R:R jargon like `2.1R` / `不足 1R`.
- Do not put stage words (蓄势/主升/派发…) into highlights/risk mashups; stage lives inside `威科夫：` only（无独立 `阶段：` 行）.
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
✅ 出手
共振： / 新开： / 动作： / 破位看：
📏 仓位上限
🧭 中线 / ⚡ 短线（作主分区标题）
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

Matches `report_renderer/short_midline.py` (`render_short_midline`)；契约见 `output-template.md` / handoff §0.1-10：

1. Title: `分析报告 — {name}（{code}）｜短中线`
2. `📊 价格状态`：现价（MA20/MA250）；`综合动能 … ｜ {板块指数} ±x% ｜ {行业短名}? ±x% ｜ 个股 ±x%`（不写正常/偏弱/跑赢）；量价行含 ATR14
3. `📐 理论分析`
   - `中线`：`威科夫：` / optional L3 下沿上沿+量度 / `缠论：` / optional 位置·筹码…
   - `短线`：`缠论：` → optional 买点 → `威科夫：`（仅对照）→ optional L3/事件 → `动能：` → `资金：`
4. `🎯 支撑阻力`
   - `中线` ← `mid_key_prices`（无 🌟；已破生命线提示「已跌破」）
   - `短线` ← `key_prices`（止损/低吸或支撑/🌟现价/卖点）+ optional 日内 T0
5. `✅ 门禁`：`结论：` → optional `还差：` → optional `等待：` → `作废：` → optional `附：`
6. `✅ 亮点` / `⚠️ 风险` / optional `📌 明日策略` / 入池提示

## C1 Entry Line（字段口径；面板并入「还差」）

From `chan_discipline.build_entry_checklist` / `format_entry_line_c1`（字段仍写 `entry_line`；**面板不再单独打「新开：」行**）:

| Flag | Label |
|------|----------------|
| mid_ok | 中线趋势 |
| in_pullback | 回踩到位 |
| short_trigger | 买点信号 |
| conf_ok | 融合置信（非「方向一致」） |
| fund_ok | 筹码资金稳 |

- All five True → 字段 `新开：可试探 · 五项齐了`；面板可省略「还差」
- Else → 字段 `新开：先别买 · …`；面板「还差」合并共振缺岗 + C1 缺项（去重，>5 折叠）

## Discipline / 门禁展示

- Merge: `mistery_gate` + `chan_discipline` via `merge_discipline` — **only tighten** caps/actions
- Never rewrite major_stage / fusion scores / support / stop prices via discipline
- User-facing panel: `✅ 门禁` 的 `结论/还差/等待/作废/附` — not mi/Mistery；**不用「出手」作分区标题**
- 等待/作废价须能在支撑阻力找到同号（已破生命线优先收回；空仓作废=破止损）
- Mid target alone must not greenlight a buy; need short trigger + checklist

## Fixed Keywords

- Must keep the words 止损 and 买 somewhere in the short key-price / ladder lines
- WeChat plain text: no `#` headings, `**bold**`, markdown tables, `---` rules

## Additional Rules

- Prefer script markdown; do not re-compose from memory
- Direction / new entries follow `decision_view` (resonance ∧ strategy ∧ discipline); `fusion.weighted_score` is instrument-only
- Mid key prices come from weekly engine (`mid_key_prices.py`), not daily `find_key_levels` success path
