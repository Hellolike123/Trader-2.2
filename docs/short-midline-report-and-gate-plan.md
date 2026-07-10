# 短中线报告 + Mistery 门控 实施计划

> 状态：待实施  
> 日期：2026-07-10  
> 范围：Trader 单票报告（`build_report` / `render_markdown` / `report_core`）+ Mistery 门控层  
> 不做：重写缠/威/动算法；不改 T0 主逻辑（仅报告末行提示）；不强制本阶段上线真周线专家重算

---

## 0. 目标与非目标

### 目标

1. 单票报告改为 **「短中线」双层叙事**：中线看法 + 短线看法 + 出手。
2. 接入 **Mistery 门控**（`decision-subset.md`）：状态仍由现有引擎算，门控只做放行/类型/失效/仓位裁切。
3. **关键价**始终展示买卖点（**不依赖是否持仓**）；用 **人话两句** 表达亏/赚（不用 R:R 术语）。
4. **🗳️ 日线三专家** 放在结论与关键价之间，含 **日线裁定**。
5. 微信格式红线不变；与现有 fusion / stage / structure 字段对接，禁止门控改写状态数字。

### 非目标（本阶段）

- 三专家主周期整体改周线重跑（留作 P2）。
- 自动推送/微信机器人改造。
- 选股池 rank/plan 全量改版（可复用门控字段，UI 后置）。
- 把 T0 改成中线执行器。

---

## 1. 产品契约（已与用户对齐，冻结）

### 1.1 报告结构（顺序冻结）

```text
分析报告 — {名}（{码}）｜短中线

现价 …
  阶段｜动能｜大盘
  MA5｜MA20（有则 MA250）
  量比等（可选一行）

🎯 结论
  中线看法：…
  短线看法：…
  出手：…
  原因：…（可含现价亏赚摘要；与关键价两句不重复长篇）
  本周：…
  说明：…（仅中线 vs 短线/日线冲突时）

🗳️ 日线三专家
  缠论：…
  动量：…
  威科夫：…
  日线裁定：…

📍 关键价
  止损卖点
  买点区
  🌟 现价
  短线卖点区
  波段卖点区

  {买点} 买：亏约 X / 赚约 Y（远看 Z）
  {现价} 追：亏约 A / 赚约 B → 不追|可考虑

🗺 空间参考（不指挥下单）
  近端｜波段｜远端

✅ 亮点
⚠️ 风险
📌 本周只做：…
T0：…
当前池 …
```

### 1.2 分层语义（禁止混淆）

| 层 | 含义 | 数据来源 |
|----|------|----------|
| **中线看法** | 故事在不在、能否跟踪/持有叙事 | `major_stage`、派发/衰退、（P1+）周线框；**不是**日线 fusion 单独决定清仓 |
| **短线看法** | 追不追、冲高/回踩 | `scene`/`theory_status`、三专家摘要 |
| **出手** | 现在执不执行（买/不追/减等） | **Mistery 门控** + 现价相对买点 + 人话亏赚 |
| **日线三专家 + 裁定** | 日线时点依据 | 现有 chan/mom/wyckoff + fusion 映射为人话裁定 |
| **关键价** | 买卖点地图，**不看仓位** | structure + key_levels + MA20 |
| **亏赚两句** | 计划质量 + 现价是否追 | 买点/现价 vs 止损/近端卖点 |

### 1.3 门控（Mistery subset）职责

只读输入 → 输出 `mistery_gate`，**禁止**改写 `major_stage` / fusion 分 / support / stop。

- 硬否决 H1–H7（regime 很差、衰退、派发不加、无止损、盈亏比差、四不做、禁止摊平）
- 类型闸：趋势 / 情绪 / 不明
- 阶段×动能 → 动作表
- 520 / stop·support 近似失效
- 仓位裁切 ≤50% 天花板；`regime=偏弱` 试错/低吸再降一档

规格源（唯一）：

`~/.grok/skills/mistery-core/references/decision-subset.md`

### 1.4 买卖点与仓位

- **买卖点始终展示**，与 `has_position` 无关。
- 持仓仅影响可选文案（T0 提示、有仓时「减」的执行语义），**不删除**卖点/买点。
- 空仓时 fusion「减仓」→ 日线裁定译为「不宜追高/不新开」，禁止主结论只写「减仓」造成无仓误解。

### 1.5 中线 vs 短线（本阶段可落地定义）

| | 中线（本阶段） | 短线（本阶段） |
|--|----------------|----------------|
| 主输入 | `major_stage`、是否派发/衰退、大盘 | 三专家 + scene + 现价相对关键价 |
| 生命线 | P0：MA20 / stop 失效（subset §4）；P1：加真周线破位 | 日线结构 stop/support/confirm |
| 更新体感 | 故事慢变 | 日更 |

**P1 增强（计划内可排期，勿遗漏）：**  
在门控后增加可选 `weekly_frame`：`完好|紧张|破坏`（真 `weekly_bars`，废除 proxy 周收若触及）。  
破坏 → 战略减/清倾向；完好 + 日线偏空 → 中线「可跟踪/持有叙事」+ 出手「不追/不加」。

### 1.6 人话亏赚（冻结句式）

```text
{buy_ref} 买：亏约 {risk} / 赚约 {reward}（远看 {far}）
{px} 追：亏约 {risk2} / 赚约 {reward2} → 不追|可考虑
```

- 风险 = 买点(或现价) − 止损（元，一位小数即可）
- 近端赚 = 短线卖点 − 买点(或现价)
- 禁止主报告写「2.1R」「不足 1R」

### 1.7 微信红线

沿用 `report_core` / AGENTS：无 `#` / `---` / `**` / 表格 / `>` / `*-` 列表。

---

## 2. 架构与数据流

```text
build_report()
  → 现有：quote, bars, chan, mom, wyckoff, fusion, structure, key_levels, stage…
  → NEW: compute_mistery_gate(report_fields)  # 纯函数，只读
  → NEW: build_key_prices(...)               # 买点区/卖点/亏赚两句
  → NEW: build_conclusion_block(...)         # 中线/短线/出手/原因/本周
  → report["mistery_gate"] = …
  → report["key_prices"] = …
  → report["conclusion"] = …
  → render_markdown / render_single 按新模板输出
```

挂载点（与 mistery-core 一致）：**融合层之后、仓位定稿前、渲染之前。**

---

## 3. 模块与文件改造清单

| 优先级 | 文件 | 动作 |
|--------|------|------|
| P0 | `02-共享模块-shared/trader_shared/mistery_gate.py` **新建** | 实现 decision-subset 门控纯函数 |
| P0 | `02-共享模块-shared/trader_shared/key_prices.py` **新建**（或并入 structure 旁路） | 关键价 + 亏赚两句 |
| P0 | `02-共享模块-shared/trader_shared/conclusion_block.py` **新建** | 中线/短线/出手文案 |
| P0 | `01-功能包-packages/trader/scripts/run_analysis.py` | `build_report` 组装新字段 |
| P0 | `02-共享模块-shared/trader_shared/report_core.py` 与/或 `run_analysis.render_markdown` | 新模板渲染（以当前实际渲染入口为准，避免双源漂移） |
| P0 | `01-功能包-packages/trader/references/output-template.md` | 更新绝对输出契约 |
| P0 | skill 侧 `~/.agents/skills/trader/references/output-template.md`（若与包内同步脚本存在则走打包） | 与包内契约一致 |
| P0 | `02-共享模块-shared/tests/test_mistery_gate.py` **新建** | 门控单测 |
| P0 | `02-共享模块-shared/tests/test_key_prices.py` **新建** | 亏赚与买卖点 |
| P0 | `01-功能包-packages/trader/tests/` 报告快照/契约测 | 新模板关键字 |
| P1 | `weekly_frame` 小模块 | 真周 K 完好/破坏 |
| P1 | Agents.md / fusion-guide 短注 | 短中线 + 门控说明 |
| P2 | 周线三专家 strategic_fusion | 另立项 |

**渲染入口注意：** 仓库同时存在 `report_core.render_single` 与 `run_analysis.render_markdown`。实施前 **grep 确认 final_report 实际调用链**，只改真实路径，或抽一层共用 `render_short_midline(r)` 避免两套模板。

---

## 4. 核心算法规格

### 4.1 `compute_mistery_gate(inputs) -> dict`

输入（与 subset §0 对齐）：

- `major_stage`, `short_term_momentum` / `momentum` 标签
- `theory_status` / `scene`
- `regime`
- `current`, `support`, `stop`, `confirm`
- `suggested_pct`（可选）
- `ma20`（可选）
- 可选：量能/换手供类型启发式

输出（subset §7）：

```python
{
  "hard_block": "none" | "H1" | ... | "H7" | "H5+H6",
  "style": "趋势" | "情绪" | "不明",
  "action": "观望" | "轻仓试错" | "回踩低吸" | "持有" | "减仓" | "止损离场" | "不做",
  "invalidation": str,
  "position_cap_pct": float,
  "notes": str,
}
```

映射到报告「出手」人话：

| gate.action | 出手文案（示例） |
|-------------|------------------|
| 不做 / 观望 | 现价不买 · 不追 |
| 轻仓试错 / 回踩低吸 | 可按买点挂 · 仓位 x% |
| 持有 | 持有叙事 · 是否暂停加看日线 |
| 减仓 / 止损离场 | 减仓 / 止损离场（点位见关键价） |

**盈亏比 H5：**  
用关键价计算结果：`reward_near <= risk`（或 `< min_rr * risk`，默认 min_rr=1.0 与 subset「目标≤止损」一致；可配置 1.5）。

### 4.2 `build_key_prices(...)`

| 字段 | 来源规则 |
|------|----------|
| stop_sell | `stop` |
| buy_zone_low/high | 优先 support 附近区间：如 `[support, support*1.005]` 或现有 `low_zone_*`；夹在 stop 与 current 合理侧 |
| short_sell_zone | `ma20`～`confirm` 或 resistance/confirm 带 |
| swing_sell | `key_levels.short_resist` 等 |
| buy_ref | 买区中轴或上沿（**全库统一：建议中轴**，文档写死） |
| 两句亏赚 | 见 §1.6 |

现价在买点上方且现价亏赚不划算 → 出手倾向不追（与门控一致）。

### 4.3 `build_conclusion_block(...)`

- 中线看法：由 stage 表驱动短句库（蓄势/主升/派发/衰退 + 偏强偏弱）
- 短线看法：由 scene + 日线裁定摘要
- 出手：gate + 现价相对买点
- 原因：优先引用亏赚两句中「追」的结论，避免与关键价重复三段
- 本周：单焦点动作
- 说明：仅 `中线可跟踪` 且 `日线偏空/不追` 等冲突时

### 4.4 日线裁定

```text
偏多/偏空/中性 + 宜追|不宜追高|观望
```

由 fusion direction / weighted_score / scene 映射；**主报告不展示 raw score**，可选 debug 字段。

---

## 5. 实施任务分解（双 Agent）

### Agent A — 实现（Implementer）

按顺序：

1. **锁定渲染入口**（final_report → 哪个 render）
2. 实现 `mistery_gate.py` + 单测（华工类：蓄势偏强×震荡×冲高×盈亏比差 → 不做/观望，cap 0）
3. 实现 `key_prices.py` + 亏赚两句单测
4. 实现 `conclusion_block.py`
5. 接入 `build_report` 字段
6. 改 `render_*` 为冻结模板
7. 更新 `output-template.md`
8. 跑相关 pytest；用华工 `final_report --output markdown` 人工对照样例

### Agent B — 审查（Reviewer）

审查清单：

- [ ] 是否改写了 major_stage / fusion 数值（禁止）
- [ ] 买卖点是否在无仓时仍输出
- [ ] 是否出现 R:R 术语或「未授权隐藏买价」旧逻辑
- [ ] 空仓主结论是否仍只写「减仓」
- [ ] 门控是否覆盖 H1–H7 与阶段×动能表
- [ ] 微信红线
- [ ] 双渲染入口是否漂移
- [ ] 测试是否覆盖华工否决路径与放行路径至少各 1
- [ ] P1 周线框是否在计划/代码中有 TODO 或已实现（勿静默遗漏）
- [ ] 与 `decision-subset.md` 字段名一致

审查产出：`docs/audit/short-midline-gate-review.md`（通过/问题列表）。

### 协作流程

```text
1. 本计划确认
2. Agent A 按 P0 实现 + 自测
3. Agent B review diff + 跑测 + 对照契约
4. A 修 B 的阻塞项
5. 人工用华工/一只放行票各看一眼全文
```

---

## 6. 验收标准（P0 Done）

1. `final_report.py --target 华工科技 --output markdown` 输出含：
   - `｜短中线`
   - `🎯 结论` 五行结构（说明可缺）
   - `🗳️ 日线三专家` + `日线裁定`
   - `📍 关键价` + 两句亏赚
   - 无独立「门控 YAML」块（门控融进出手/原因）
2. 华工类场景：出手为不买/不追；关键价仍有买点与卖点。
3. 单元测试：门控 H5/H6、阶段表观望、亏赚计算符号与取整。
4. 不回归：`build_report` JSON 仍含原 fusion/stage 字段；新增字段向后兼容。

---

## 7. 风险与回退

| 风险 | 缓解 |
|------|------|
| 双 render 只改一处 | 先锁定入口；抽 `render_short_midline` |
| 门控过严导致全市场不做 | min_rr 可配置；单测锁定边界 |
| 买点区启发式不准 | 优先复用 low_zone/support；标注 notes |
| 与旧 output-template 测试冲突 | 同步更新契约测试与 Old Output Detection |

回退：feature flag `SHORT_MIDLINE_REPORT=1`（默认 true 或 false 由实现时定，**建议默认 true 但可 env 关回旧模板**）。

---

## 8. 用户已拍板文案备忘（防遗漏）

- 标题后缀：`｜短中线`
- 门控+授权合并为 **出手** 人话，不写 H5 给终端用户（内部字段可保留 code）
- 原因与「失效段」合并，不单开盈亏比段落
- 关键价名称暂定 **关键价**
- 亏赚 **两句** 格式
- 三专家保留，icon **🗳️**，位于结论与关键价之间
- 日线裁定人话；融合分不进主卡
- 买卖点不看仓位
- Mistery subset 为纪律源；周期上 P0=520/日线结构，P1=周线框

---

## 9. 样例锚点（华工，逻辑回归用）

输入特征：蓄势偏强、震荡、冲高减仓、顶背驰、大盘偏弱、空仓、现价在买点上方、近端盈亏不划算。

期望：

- 中线：可跟踪 / 故事未结束  
- 短线：不适合追  
- 出手：不买·不追  
- 日线裁定：偏空，不宜追高  
- 关键价：止损/买点/现价/卖点齐全 + 两句亏赚  
- 无「试探买 10%」类未放行指令  

---

## 10. 下一步

1. 用户确认本计划（或批注修改）。  
2. 启动 **Implementer Agent** 按 §5.A。  
3. 完成后启动 **Reviewer Agent** 按 §5.B。  
4. 人工过目华工全文后合并。
