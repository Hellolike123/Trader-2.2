# 缠论 Skill B·中剪报告 — Agent Handoff

> **status**: active  
> **日期**: 2026-08-03  
> **对照**: 威科夫 B·中剪 [`wyckoff-detail-slim-b-handoff.md`](./wyckoff-detail-slim-b-handoff.md)（只复用形态，不抄 SC/箱体/L0–L3）  
> **母法源**: [`chanlun-skill-deep-card-handoff.md`](./chanlun-skill-deep-card-handoff.md)、[`chanlun-skill-playbook.md`](./chanlun-skill-playbook.md)、`BUSINESS.md` §2.0 / §2.1  
> **代码**: `trader_shared/chanlun_run.py` / `chanlun_render.py`；入口 `01-功能包-packages/chanlun/scripts/final_chanlun.py`

---

## 0. 30 秒摘要

1. 默认 `--target` 出 **B·中剪**（`render_chanlun_slim`）：总览 → 周线灯 → 日线灯 → 变化 → 推演。  
2. `--brief` 保留旧薄卡（`render_chanlun_card`）。  
3. 灯 = 正式一/二/三类买 + 一/二/三类卖；类一/类二仅观察追加。  
4. **禁止**手补买卖点、下单词、覆盖周线威科夫中线阶段、写箱体/量度。

---

## 1. 输出骨架

见 `01-功能包-packages/chanlun/references/output-template.md`（与 render 同源）。

```text
{名}（{码}）｜现价 {price}
周线副读：{偏多|偏空|回调偏空|反弹偏多|中性}｜{大结构内本波，如上涨趋势内回调}｜{可盯|慎做|先别做}
日线本波：{笔向/主买卖点短句}
入池：{建议入池｜暂不建议入池（短因）｜结构偏空，暂不建议入池}

🧭 周线 · 结构副读
  {一句话}
  灯
  {●|○} 一类买 {价?}
  …
  {●|○} 三类卖 {价?}
  （观察档已亮追加）

⚡ 日线 · 本波
  {一句话}
  笔：…｜当前笔：…｜近笔：…
  中枢：{pivot}｜窗{raw}｜段：{n}
  灯
  …

🔔 变化          ← 有新亮或熄灭才出
  新亮：…；熄灭：…

🔮 推演
  现在 / 若变好 / 若变坏 / ⭐ 盯
  本卡不下单；出手/分道看 trader；中线阶段看威科夫
```

---

## 2. 规则

### 2.1 灯表

| 正式满灯（必列） | 来源 |
|------------------|------|
| 一类买 / 二类买 / 三类买 | `buy_points[].type` 精确匹配 |
| 一类卖 / 二类卖 / 三类卖 | `sell_points[].type` 精确匹配 |

- ● = 引擎数组已有该 type；价取 `price`（有则）。  
- ○ = 未形成。  
- `类一*` / `类二*`：仅已亮时追加「类×（观察）{价}」，**不进**正式六灯冒充正式。  
- render **禁止**从 `buy_point_text` 或文案反推。

### 2.2 姿态（总览第三段）

| 档 | 条件（短因优先日线） |
|----|----------------------|
| 先别做 | 日线不足；或日线有正式卖且无正式买 |
| 可盯 | 日线有正式买，且无 `tip_leave` 降级 |
| 慎做 | 其余 |

### 2.3 入池软建议（不下单）

| 档 | 条件 |
|----|------|
| 结构偏空，暂不建议入池 | 日线正式卖且无正式买；或周线正式卖为主且日线无正式买 |
| 建议入池 | 日线正式二类/三类买，且周线非「仅正式卖」 |
| 建议入池（日线一类买，待确认） | 日线仅一类买为正式买 |
| 暂不建议入池（无正式买点） | 默认 |

### 2.4 推演短句

四块人话：现在 / 若变好 / 若变坏 / 盯。  
只写引擎可核对事实；正式点才进主结论。观察档可附「另有…（观察，不算正式）」或「观察档已亮（不算正式）」。  
禁止「接近一买」「潜在三买」「宜买」；禁止「笔结构延续且出现更高阶…；现 暂无…」这类拧句。

### 2.5 变化快照

- 文件：`~/.trader/chanlun_light_snapshot.json`（`trader_paths` key `chanlun_light_snapshot`）  
- 比日/周已亮买卖点 type 集合；首次或仅仍亮 → 省略整块 `🔔 变化`。

---

## 3. CLI

| 命令 | 渲染 |
|------|------|
| `final_chanlun.py --target X` | `render_chanlun_slim` |
| `… --brief` | `render_chanlun_card`（旧薄卡） |
| `… --output json` | plan 精简 JSON（无大 raw） |

---

## 4. 测例（必须）

| ID | 期望 |
|----|------|
| C-B1 | 默认卡含 `🧭 周线` / `⚡ 日线` / `🔮 推演`；六灯竖排 |
| C-B2 | 无买卖点 → 六灯全 ○；无手补类型 |
| C-B3 | 类二买仅观察追加，正式表该位仍 ○（若无正式同名） |
| C-B4 | midline `daily_fallback` → 周线句含「（日线）」 |
| C-B5 | 微信红线 + 无下单词 |
| C-B6 | `--brief` 仍出旧「缠论 — …｜短中线结构卡」 |

---

## 5. 可改 / 勿改

**可改**: `chanlun_run.py` / `chanlun_render.py` / chanlun skill references / `pack_all` 纳入 chanlun / `trader_paths` 新 key / 本 handoff + 测。

**勿改**: fusion / decision_view / 威科夫中线定论 / 池分道 / `chan_geometry` 成笔算法 / 在 skill 包复制引擎。
