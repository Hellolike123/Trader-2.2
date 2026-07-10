# 纪律层展示粗改计划（去 mi 人设 · 保留门控）

> 状态：**P0 已实施**（D1–D3：失效展示 + 去品牌 + 模板/单测）  
> 日期：2026-07-10  
> 依据：产品结论——分析报告不需要 mi姐/Mistery 人设文案；**必须保留**「事实→纪律→出手」层；对外叫 **出手/纪律**，对内可继续用 `mistery_gate` + decision-subset 规则源  
> 关联：`docs/mid-short-dual-track-plan.md`（双轨展示）· `docs/short-midline-report-and-gate-plan.md`（门控骨架）· `mistery-core` skill  

---

## 0. 结论冻结（本计划边界）

| 问题 | 结论 |
|------|------|
| 报告里要不要 mi姐口吻 / Mistery 品牌文案？ | **不要** |
| 要不要删「出手」门控层？ | **不要删** |
| 支撑/买卖点谁画？ | 仍 **Trader**（周线缠 / 日线结构）；纪律层 **不改价** |
| 对外怎么称呼这一层？ | **出手**（主）+ 可选 **纪律说明/失效** |
| 对内模块名 `mistery_gate.py`？ | **P0 可保留**（少折腾 import）；文档写「纪律门控，规则源自 decision-subset」 |
| 聊天陪练 skill？ | **不动**；需要学思路时再开 mistery-core，与报告解耦 |

一句话：

```text
Trader 出图与状态  →  纪律门控裁动作  →  报告只写「出手/原因/失效」白话
                         ↑
              规则仍可读 decision-subset，不说 mi姐
```

---

## 1. 目标与非目标

### 1.1 目标（P0 粗改）

1. **用户可见面**（报告 / output-template / 风格说明）不出现：`Mistery`、`mi姐`、`mistery` 作产品名；统一「纪律」「出手」。  
2. **出手块结构固定**（⚡ 短线内，已有骨架上微调）：  
   - `出手：…`  
   - 原因仍可并进括号（现状）  
   - **新增可选一行**：`失效：…`（读 `mistery_gate.invalidation`，空则省略）  
3. 代码注释/文件头：标明「纪律门控 · 规则源 decision-subset」，避免新人以为报告要写 mi 人设。  
4. 单测：渲染产物不得含 `Mistery`/`mi姐`（若模板曾有）；`出手`/`失效` 关键词契约。

### 1.2 非目标（本轮不做）

- 不重写 `compute_mistery_gate` 规则表、不改 H1–H7 语义。  
- 不把 `mistery_gate` 模块强制 rename（可 P2 别名 `discipline_gate`）。  
- 不让纪律层重算生命线/买点/止损。  
- 不把陪练 skill 的对话体灌进报告。  
- 不改中短线双轨价引擎（周线/日线）。  
- 不做「回踩区进 gate」增强（可列 P1，见 §4）。

---

## 2. 现状对照

| 项 | 现状 | 粗改后 |
|----|------|--------|
| 报告出手文案 | 已是中性：`出手：现价不买 · 不追（…）` | 保持；补可选 `失效：` |
| 报告是否出现 Mistery/mi姐 | `report_core` 渲染路径 **基本无** | 扫 docs/模板，清品牌词 |
| 模块名 | `mistery_gate.py` / `report["mistery_gate"]` | **字段可保留**；注释与产品文档改「纪律门控」 |
| invalidation | gate 已算，报告 **未固定展示** | ⚡ 出手下展示一行（有则出） |
| style（趋势/情绪/不明） | gate 有，报告少展示 | P0 可选：不展示；P1 需要时 `类型：趋势` 一行 |
| position_cap | gate 有 | P0 不单独占行（出手文案已含仓位语义时足够） |

---

## 3. 报告契约（粗）

⚡ 短线块内顺序（在现有基础上）：

```text
⚡ 短线
  看法：…
  缠论：…
  动能：…
  裁定：…
  出手：现价不买 · 不追（现价追大约亏 x、赚 y，不划算）
  失效：收盘有效跌破 MA20(…)且反抽站不回；或跌破止损 xx.xx   ← 新增，空则整行省略
  关键价（短线）
    …
```

纪律：

- **禁止**行首写 `Mistery：` / `mi：` / `门控 YAML`。  
- **禁止** mi 陪练腔（「姐姐觉得」「咱们今天」）。  
- 失效句优先用 gate 已生成的 `invalidation` 字符串，不在 render 里另编一套长文。

---

## 4. 分层（加深可选，非本轮必须）

| 优先级 | 项 | 说明 |
|--------|-----|------|
| P0 | 去品牌 + 失效一行 + 文档口径 | 本计划主体 |
| P1 | 现价不在中线回踩区 → 纪律不新开 | **已实施**：gate 读 mid_pullback_low/high，区外砍轻仓/回踩/持有为观望 |
| P1 | `类型：趋势｜情绪｜不明` 一行 | 仅 style≠不明或需提示时 |
| P2 | 模块 rename `discipline_gate` + 兼容别名 | 避免大面积 import 抖动 |
| P2 | Agents.md 写清「报告=纪律，陪练=skill 对话」 | 协作约定 |

---

## 5. 文件改造清单（粗）

| 优先级 | 文件 | 动作 |
|--------|------|------|
| P0 | `report_core.py` `render_short_midline` | 出手后输出 `失效：`（有 invalidation） |
| P0 | `output-template.md` / `output-style-guide.md`（若有） | 样例去 Mistery 品牌；写「纪律/出手/失效」 |
| P0 | `docs/short-midline-report-and-gate-plan.md` 或短注 | 产品名改为「纪律门控」；规则源仍链 decision-subset |
| P0 | `mistery_gate.py` 文件头注释 | 「纪律门控实现；规则源 decision-subset；报告禁止 mi 人设」 |
| P0 | 相关单测 / `test_report_mid_short_sources` 等 | 断言无 `Mistery`/`mi姐`；有 invalidation 时出现 `失效` |
| P1 | `conclusion_block` 或 gate 输入 | 可选：接入「是否在回踩区」布尔 |
| — | `mistery-core` skill | **不改**；继续服务聊天陪练 |

**不改：** `midline_structure` / `key_prices` 主算法、fusion、major_stage。

---

## 6. 实施切片（若开工）

| 切片 | 内容 | 完成定义 |
|------|------|----------|
| D1 | render：失效一行 + 禁止品牌词扫描 | 真票/快照有 `失效` 或合理省略 |
| D2 | output-template + 计划/文档口径统一 | 样例与 §3 一致 |
| D3 | 注释与单测 | pytest 绿；无 mi 品牌断言 |
| D4（可选 P1） | 回踩区→纪律输入 | 规格另开，不塞进 D1 |

双 Agent（可选）：Implementer 按 D1–D3；Reviewer 勾「无品牌词 / 失效展示 / 门控未改价」。

---

## 7. 验收（粗）

| ID | 要求 |
|----|------|
| C1 | 默认短中线报告全文不含 `Mistery`、`mi姐`、`mistery`（代码路径名可在 debug JSON 保留字段名） |
| C2 | ⚡ 有 `出手：`；当 gate.invalidation 非空时有 `失效：` |
| C3 | 中线/短线关键价数字与改前同源（本轮不改编价） |
| C4 | gate 仍只读、不改写 stage/stop/support |
| C5 | 微信红线保持 |

说明：JSON/`report["mistery_gate"]` 键名 P0 **允许保留**（内部实现细节）；**C1 仅约束用户可见 Markdown 报告**。

---

## 8. 风险

| 风险 | 缓解 |
|------|------|
| 改名模块引发大面积 diff | P0 不 rename |
| 失效句过长刷屏 | 沿用 gate 现成短句；过长可截断到 80 字（若需要再定） |
| 用户以为「去掉了 mi 就没纪律」 | 文档写清：纪律还在，只是不叫 mi |

---

## 9. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-10 | 初版粗计划：去人设、留门控、出手/失效白话、价仍 Trader |
| 2026-07-10 | P0 实施：report_core 失效行；output-template 2.6.1；mistery_gate 注释；单测 C1/C2 |
| 2026-07-10 | P1：中线回踩区纪律 — 区外不新开（gate + run_analysis 接线 + 单测） |
