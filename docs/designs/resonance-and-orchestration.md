# 目标架构法源：五层 + 编排 · 岗位共振 · 多场景

> **状态**：产品方向已定 · 已合入 `main`  
> **版本**：v0.8 · 2026-07-29（阶段 5 分包之后：买点盖 L2/L3、池/仓位吃共振档、T0 结构分边界、日线裁定听 decision_view）  
> **读者**：**所有后续 Agent / 人类**——只读本文 + `AGENTS.md`（含「改代码去哪」）即可接上方向  
> **报告/T0/池面板版式**：单票短中线双轨 + T0 结构参考卡 v2 已定；本文仍以职责与字段为主  
> **冲突时**：以本文产品铁律 + `trader_shared/` 实现为准；旧文若写「fusion 打分当总司令」视为过时  

**备份**：本文件在 git 版本库内（`docs/designs/`）。勿只写在对话里。

---

## 0. 给下一个 Agent 的 30 秒摘要

1. **产品**：多理论分析 → 岗位互补（共振）→ 原典策略自动触发 → 薄决策（纪律+主策略）→ 各场景展示。  
2. **不当**：厚 `weighted_score` 加权融合当分王；策略/展示层重跑缠论威科夫检测。  
3. **架构**：数据 / 分析 / 共振+策略+决策 / 展示 + **编排总管**（只排队）。  
4. **可扩展**：新理论→分析卡；新原典→策略 YAML；新用法→新编排入口（T0/池/候选池/仓位）读同一字段。  
5. **代码现状**：阶段 1～5 已落地（共振/策略/decision_view/流水线分包）。续：买点盖 L2/L3；选股池与仓位轮动读共振档（离散）；T0 的 `resonance` 是结构分非 `pullback_probe`；日线裁定出手听 decision_view。fusion 分仍作仪表（生产路径 = cards）。  
6. **详细边界**：`analysis-strategy-boundaries.md`；意见卡：`analysis-opinion-cards.md`。改实现见 `AGENTS.md`「改代码去哪」。

---

## 1. 一句话目标与铁律

```text
数据 → 各理论分析（意见卡）→ 岗位共振（齐不齐）→ 原典策略亮不亮
    → 纪律允不允许 → 报告 / T0 / 池 / 仓位 各取所需
```

**新开铁律**（产品；阶段 3 才接到出手代码）：

```text
可推荐新开  ⇔  共振齐  ∧  主入场策略可执行(executable)  ∧  纪律允许
```

- 「策略亮」= `strategy_match.gates.entry.executable is True`（mode=active）  
- `mode=plan`（清单未齐 / 买点失效 / 否决）**不算**可推荐新开  

**纪律铁律**（已有，保持）：只收紧出手/仓位/失效，**不改** `weighted_score` / support / stop。

**方向铁律**：出手/新开听共振∧策略∧纪律（`decision_view`）；fusion `weighted_score` 仅仪表。  
`FUSION_OVERRIDE_ENABLED` **默认 false**（不覆盖 `theory_status`）。新 Agent 勿再加厚 fusion 权重矩阵当产品主路径。

---

## 2. 架构：五层 + 编排

### 2.1 总图

```text
CLI / Skill（trader · t0 · review · portfolio …）
    ↓
编排层（多个入口，同一底座）
    · build_report          单票中短线
    · t0 build_plan/monitor 盘中执行卡
    · final_pool            选股池 / 候选池批量
    · final_portfolio       仓位轮动
    │  只调度，不算理论、不写加权公式
    ▼
数据层  data_provider / cache / 多源 fallback
    ▼
分析层  cores + plugins → analysis_cards（各理论各说各话）
    ▼
    ├─→ 共振     posts / grade（读卡；岗位互补，非计票打分）
    ├─→ 策略层   strategy/packs/*.yaml + 六闸 match
    └─→ 决策层   discipline 只收紧 + decision_view（新开只收紧）
    ▼
展示层  各场景纯展示（版式 TBD）
```

### 2.2 各层职责（Agent 挂模块时认层）

| 层 | 干什么 | 不干什么 | 代码锚点（现行） |
|----|--------|----------|------------------|
| **编排** | 按序调用各层，写 report/卡片 dict | 内嵌检测、加权公式、人话业务堆砌 | `report_builder.build_report`；`pool_cmds`；t0/review CLI 入口（引擎在 shared） |
| **数据** | 行情、快照、缓存、HA | 理论判断 | `data_provider` / `light_data` / `cache_utils` |
| **分析** | 理论计算 → **意见卡** | 互相加权成唯一真理；直接写「买30%」 | `analysis/`、`plugins/`、各 `*_core` |
| **共振** | 岗位 ✓/✗、档、冲突、缺岗 | 计票打分；重跑检测 | `resonance.py` → `report["resonance"]` |
| **策略** | 原典剧本自动 match | 改 weighted_score；import 检测实现 | `strategy/match.py` + `strategy/packs/` |
| **决策** | 纪律硬闸 + 薄仲裁 | 用分数平均抹掉冲突 | `mistery_gate` / `chan_discipline`；`decision_view.py`（已挂载） |
| **展示** | 渲染 | if Spring 则建议买入 | `report_core` / t0 输出 / pool 面板 |

### 2.3 为何要有编排层（给听不懂的人）

五层是**工种**；编排是**总管喊开工顺序**。  
没有编排，模块不会自己串起来。总管（`build_report`）只排队；胖逻辑已下沉 `report_pipeline/`——**保持瘦**，勿堆回 monolith。

---

## 3. 业务选择：共振，不是厚打分

| | 厚融合打分 | 岗位共振（本方向） |
|--|------------|-------------------|
| 问题 | 各席多少分加总？ | 各岗位是否合格、是否互补、哪里冲突？ |
| 输出 | 连续分 → 映射动作 | 档 + 缺岗 + 冲突 + 是否可推策略 |
| 风险 | 强信号被平均掉 | 做成计票/加权换皮则退化 |

**四岗（场景 `pullback_probe` 回踩试探）**：

| 岗位 | id | 角色 | 时框（与 `BUSINESS.md` §2.0 一致） |
|------|-----|------|-----------------------------------|
| 背景 | background | 阶段/威科夫中线：能不能谈试探 | **周线威科夫**（不足不参与；禁日线冒充） |
| 结构 | structure | 缠论买点/回踩区：位到了没有 | **日线缠论**（短线扳机；可加小级别确认） |
| 筹码 | chip | 峰/搬家：成本稳不稳 | 日线筹码 |
| 动能 | momentum | **确认/否决**：不拆台即可，不强多单独开仓 | 日线动量；不改阶段、不单独开仓 |

**grade**：`aligned` / `momentum_veto` / `missing_*` / `conflict` / `empty`（见 `resonance.py`）。  
产品法源互链：`BUSINESS.md` §2.0（中线状态=威科夫周线；短线交易=缠论日线）。

---

## 4. 多场景消费者（计划时必须考虑）

底座统一；**禁止** T0/池/仓位各自重写缠论。

| 场景 | 入口（参考） | 编排角色 | 备注 |
|------|--------------|----------|------|
| 单票中短线 | `final_report` → `build_report` | 主路径；阶段 1 已写 resonance | 报告版式 TBD |
| **T0 交易卡片** | `01-功能包-packages/t0/` | 盘中：quote/分钟 + 关键价/纪律 | ✅ 禁止 `attach_resonance`/`pullback_probe`；plan.`resonance`=`t0_structure_score_v1`（非岗位共振） |
| **选股池** | `final_pool`、`~/.trader/pool.json` | 用户自选 → 策略分道 rank/plan | ✅ 分道：可盯/等齐/先别碰/计划过时；排序 lane→共振→威科夫吸筹链→RS→可碰→分；入池软门槛；`total_score` 仅附录 |
| **候选池** | 自建名单 → 同一分析底座 | 批量筛选后再入正式池 | 与正式池同构，不同名单源 |
| **仓位轮动** | portfolio、`stage_positioning` | 组合 cap、T+1、相关性 | ✅ 读池内 `resonance_grade` 离散提权/降权；排序次键共振档 |

持久化参考：`pool.json`、`signals.jsonl`、T0 state 等见 `AGENTS.md`。

---

## 5. 如何加模块（菜谱）

| 你要加 | 挂哪一层 | 怎么做 |
|--------|----------|--------|
| 新数据源 | 数据 | Fetcher + provider；分析只吃 snapshot |
| 新理论/指标 | 分析 | core/plugin → `build_xxx_card` → 卡契约文档 |
| 新岗位/场景共振 | 共振 | `build_resonance(..., scene=)` 读卡；禁检测 import |
| 新原典剧本 | 策略 | `strategy/packs/*.yaml` + context 字段 |
| 新硬规矩 | 决策/纪律 | gate 只收紧 |
| 新用法（T0/池/候选） | **新编排入口** | 调底座，拼自己的展示；不复制 cores |
| 新面板文案 | 展示 | 只读字段 |

**红线**（与 `analysis-strategy-boundaries` 一致）：

- 策略/展示禁止 import `wyckoff_events` / `chan_geometry` 等检测实现  
- 禁止为加包去改 `weighted_score` 公式  
- 编排禁止无限堆业务 if；业务进对应层  

---

## 6. 改造阶段与代码现状

| 阶段 | 内容 | 出手行为 | 状态 |
|------|------|----------|------|
| **0** | 本文法源 | 不变 | ✅ |
| **1** | `build_resonance` + builder 挂载 + 单测 | **不变** | ✅ `resonance.py` / `test_resonance_pullback.py` |
| **2** | strategy context 可读共振；包可 match grade | 可选更严（旧包不变） | ✅ `build_match_context` 暴露 `resonance_*`；YAML `field: resonance_grade` |
| **3** | decision_view：新开听 共振∧策略∧纪律 | **改变**（只收紧；禁止新开时 caps/`suggested_pct` 归零） | ✅ `decision_view.py`；caps 由 `apply_execution_caps` 在 DV/fail-closed 后收口；不改 fusion 分 |
| **4** | fusion 退居仪表；展示主叙事跟 decision_view | 改变因果 | ✅ `format_decision_narrative_lines` + `render_short_midline` 共振/决策/新开/仪表；`weighted_score`/`action` 不微调 major_stage / chase_ok / holding_hint / chip confidence |
| **5** | `build_report` 拆阶段函数（总管变瘦） | 行为冻结重构 | ✅ pipeline：短中线+stage_pack+风险旗/live_bar；fusion 标 `product_role=instrument`；`report["decision"]` 别名；见 `plans/done/build-report-pipeline-refactor.md`。**挂接顺序（A1）**：`run_pre_cards_stage` 在 context 后早跑；`run_fusion_merge_stage`（merge+verbatim+tag instrument）在 **stage_pack 之后、attach_short_midline 之前**。structure/chip/stage/stage_pack 不消费 fusion。**延期（A2 仍不做）**：勿把 merge 挪到 decision_view 之后（仪表仍在决策栈前可见；A2 继续 defer）。 |

**阶段 1 字段**：

```text
report["resonance"] = {
  schema_version, scene, grade, posts{background,structure,chip,momentum},
  missing, conflict, summary_line
}
```

多周期打分（`multi_timeframe_resonance.calc_resonance`）写入 **`report["mtf_resonance"]`**，禁止占用 `report["resonance"]`。

实现：`trader_shared/resonance.py`  
挂载：`report_builder` 在 `ensure_report_analysis_cards` 之后、`match_strategies` 之前。

**编排瘦身**：阶段 5 已把短中线挂接拆进 `report_pipeline/attach_*.py`；`report_builder` 以排队为主，勿再堆回 monolith。

---

## 7. 额外建议（给产品/工程，非强制立刻做）

1. **先字段契约、后版式**：单票/T0/池面板都可以后画皮。  
2. **候选池与正式池同构**：只换名单与过滤阈值，共用 `build_report`/共振。  
3. **T0 场景独立**：勿强行套 `pullback_probe`；可共享纪律与关键价。  
4. **decision_view 一处出口**：减少 fusion/conclusion/discipline 多嘴。  
5. **门禁**：新测无网；全量历史红项勿塞 pre-push。  
6. **文档单一法源**：产品方向以**本文**为准；boundaries 管 import 红线；AGENT 链到本文。  
7. **fusion**：兼容与回测可留；新功能默认不依赖加厚权重。  

---

## 8. 相关文件速查

| 用途 | 路径 |
|------|------|
| **本文（产品+架构法源）** | `docs/designs/resonance-and-orchestration.md` |
| 分析/策略 import 红线 | `docs/designs/analysis-strategy-boundaries.md` |
| 意见卡字段 | `docs/designs/analysis-opinion-cards.md` |
| 策略包 / 六闸 | `strategy-pack.md` / `strategy-gates.md` |
| 共振实现 | `trader_shared/resonance.py` |
| 薄决策视图 | `trader_shared/decision_view.py` → `report["decision_view"]` |
| 流水线阶段包 | `trader_shared/report_pipeline/`（`fusion_stage` / `structure_stage` / `chip_stage` / `assemble_stage` / `attach` 等） |
| 单票编排 | `trader_shared/report_builder.py`（只排队） |
| 策略匹配 | `trader_shared/strategy/match.py` |
| T0 引擎 | `trader_shared/t0_*.py`；包内 `01-功能包-packages/t0/scripts/` 为 identity shim |
| 复盘 / 仓位引擎 | `trader_shared/review_*.py` / `portfolio_*.py`；包内 scripts 为 shim |
| 选股池 | `trader/scripts/final_pool.py`（薄入口）+ `trader/scripts/pool_cmds/` |
| Agent 总入口 | `AGENTS.md`（改代码地图）/ `AGENTS_DEEP.md` |

---

## 9. Agent 自检清单

- [ ] 我加的是理论/策略/编排/展示中的哪一种？  
- [ ] 是否只通过卡/共振/纪律字段下传？  
- [ ] 是否重跑了检测或加厚了 fusion？  
- [ ] 若动出手：是否仍满足 共振齐∧策略亮∧纪律过？  
- [ ] 是否考虑 T0/池/仓位仍能只读同一字段？  
- [ ] 是否更新了本文或 boundaries（若改了契约）？  

---

*写计划、拆 builder、接 T0/池时：打开本文。对话结论以 git 中本文为准。*
