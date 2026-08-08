# Output Style Guide — trader

> Format rules specific to trader output. Absolute structure: `output-template.md`.
> Production render: `trader_shared.report_core.render_single` → default `render_short_midline`.
> Pipeline: `report_builder` → `attach_short_midline_and_decision` → `render_short_midline`
> （builder 内：mid_key_prices + mistery_gate + chan_discipline merge → conclusion → attach）。


## 中短线标题挂灯

- 固定形态：`🧭 中线｜{🔴 防守|🟡 观望|🟢 可跟踪}`、`⚡ 短线｜{🔴 不新开|🟡 仅观察|🟢 去看trader}`
- 灯在标题行，**不写**「操作灯」三字；绿=资格不是可买
- 下面威科夫/缠论仍是解释层；出手仍看 `新开/动作/decision_view`
## Prohibited Content

- Do not invent intraday order instructions beyond script-rendered T0 lines.
- Do not write mi姐 / Mistery brand words in user-facing Markdown (internal field may still be `mistery_gate`).
- Do not use R:R jargon like `2.1R` / `不足 1R`.
- Do not put stage words (蓄势/主升/派发…) into independent lines; no `阶段：` / `看法：` / `定论：` on panel — stage detail under `威科夫：`, 缠论分行自读.
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
2. Meta: 现价（含 MA20/MA250）；`环境：宽基±% ｜ 主交易板块±% ｜ 强于/弱于/持平板块` → `概念：标签…` → `量能：量比/换手/调整/位置/ATR14`（不写正常/偏弱/跑赢；概念不做假指数；年线下方警告）
3. `🧭 中线`
   - **无**独立 `阶段：` 行（`midline_stage` 字段供共振；细读见威科夫）
   - **无** `定论：` 行（midline_verdict_note 仅字段/池侧）
   - `威科夫：` / `缠论：` ← View / `*_midline` only
   - optional `位置：` ← pivot_position_weekly
   - `关键价（中线）` 生命线 / 回踩区 / 压力 / 目标 ← `mid_key_prices`（周线引擎，无 🌟）
4. `⚡ 短线`（A 版读序）
   - `缠论：` → optional 买点 → `威科夫：`（日线短波：先侧后主灯；`短波吸筹|短波派发 · 灯… · 不作买点`；禁止「日线阶段：」/独立「事件：」；箱体 lo-hi / 箱体未成形）→ `动能：` → `资金：`（有依据先 `买盘占优/卖盘占优`；短：`5日净额 · 价资 · 主力x/10·档位 · 大单`；不重复量能）
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

## Momentum line (动能)

- Total word from `fusion.signals_detail.momentum.direction`: `1/bullish → 偏强`，`-1/bearish → 偏弱`，`0/neutral → 中性`
- No `direction`, or reason contains `数据不足`: do not prepend a total word
- `中性 + 动量中性` → `动能：中性`; otherwise `动能：{total} · {reason}`

## Fund line (资金)

- Do **not** repeat 量能 row (平量/量比/近N日).
- With evidence, prepend `买盘占优 · ` or `卖盘占优 · ` first: `卖盘占优 · 5日净出1719万 · 价资看不出 · 主力1/10·撤离 · 大单偏卖`
- Bias evidence order: `big_order_direction/big_order_summary` first; otherwise `cum_flow_5d_wan` (`|x|>=100` 万) or `cum_flow_10d_wan` (`|x|>=3000` 万) sign
- No evidence: keep the original fund line unchanged
- 价资 display glossary: 价涨钱进/出 · 价跌钱进/出 · 横盘钱进/出 · 价资都淡 · 价资看不出
- 主力 score is **/10** with tier: ≥9强势 · ≥6参与 · ≥3观望 · <3撤离
- Amount words already carry direction; use absolute value (no `净出-1200万`)
