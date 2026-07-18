# 岗位共振 + 编排总管（业务与改造路线）

> **状态**：已立项 · 分支 `feat/resonance-orchestration`  
> **版本**：v0.1 · 2026-07-19  
> **报告版式**：未定（本文件不规定 emoji/排版）  
> **读者**：人类决策 + 开发 Agent

---

## 0. 一句话目标

多理论各自分析 → **岗位互补看齐不齐（共振）** → 原典策略自动亮 → **薄决策（纪律 + 主策略）** → 报告讲因果。

**不当**厚加权打分（fusion score）当总司令。

新开铁律（产品，阶段 3 才接到出手）：

```text
可推荐新开  ⇔  共振齐  ∧  主入场策略亮  ∧  纪律允许
```

---

## 1. 架构：五层 + 编排

```text
编排层  build_report（只排队调用，不算理论、不写加权公式）
    │
    ▼
数据层  data_provider / cache / 多源
    ▼
分析层  cores + plugins → analysis_cards
    ▼
    ├─→ 共振     局面图 posts / grade（读卡，不重跑检测）
    ├─→ 策略层   packs YAML + 六闸 match
    └─→ 决策层   discipline 只收紧 +（阶段 3）主策略择一
    ▼
展示层  render（版式 TBD；只读 report）
```

| 层 | 职责 |
|----|------|
| **编排** | 串阶段；现实现：`report_builder.build_report`（目标变瘦） |
| **数据** | 行情与快照 |
| **分析** | 各理论出意见卡；不互相加权成「真理」 |
| **共振** | 岗位 ✓/✗ 与档；服务策略/出手，不是计票打分 |
| **策略** | 原典剧本自动触发；不改 `weighted_score` |
| **决策** | 纪律硬闸 + 薄仲裁；fusion 分降为可选仪表 |
| **展示** | 纯展示 |

依赖：箭头只能向下或「分析 → 共振/策略/决策」分叉。策略/展示禁止重跑检测。

---

## 2. 场景：回踩试探（pullback_probe）

### 2.1 四岗

| 岗位 | id | 理论 | 绿灯（v0 启发式，可迭代） |
|------|-----|------|---------------------------|
| 背景 | `background` | 阶段 + 威科夫中线观感 | 非派发/衰退；中线观感非明确空 |
| 结构 | `structure` | 缠论买点/回踩 | 有买点类型或 price 在回踩/买点区 |
| 筹码 | `chip` | 筹码峰/搬家 | 无清仓级搬家警告；峰信息可用 |
| 动能 | `momentum` | 动量 | **确认岗**：direction 非强空则「不拆台」 |

原则：A/B/C 门闩；D 否决/降档，不强多单独开仓。

### 2.2 共振档 `grade`

| grade | 含义 |
|-------|------|
| `aligned` | A✓ B✓ C✓ 且 D 不拆台 |
| `momentum_veto` | A✓ B✓ C✓ 但 D 拆台 |
| `missing_structure` | 缺结构 |
| `missing_chip` | 缺筹码（结构有） |
| `missing_background` | 缺背景 |
| `conflict` | 结构偏多但背景否决等 |
| `empty` | 信息不足或均未形成 |

### 2.3 报告字段（版式未定，先定 JSON）

```text
report["resonance"] = {
  "schema_version": "resonance_v1",
  "scene": "pullback_probe",
  "grade": "aligned" | ...,
  "posts": {
    "background": {"ok": bool, "note": str},
    "structure":  {"ok": bool, "note": str},
    "chip":       {"ok": bool, "note": str},
    "momentum":   {"ok": bool, "note": str},  # ok=不拆台
  },
  "missing": ["structure", ...],
  "conflict": bool,
  "summary_line": str,   # 一句人话，渲染可选
}
```

**阶段 2（当前代码）**：只写入 `report["resonance"]`，**不改** discipline / conclusion / fusion 出手。

---

## 3. 改造阶段

| 阶段 | 内容 | 出手行为 |
|------|------|----------|
| **0** | 本文 + 索引 | 不变 |
| **1** | `build_resonance` + builder 挂载 + 单测 | **不变**（并行观察） |
| **2** | strategy context 可读共振；入场包可 match grade | 可选更严 |
| **3** | `decision_view`：新开听 共振∧策略∧纪律 | **改变** |
| **4** | fusion 退居仪表；报告主叙事改听 decision_view | 改变展示因果 |
| **5** | `build_report` 拆阶段函数（总管变瘦） | 行为冻结下重构 |

`report_builder` ~1800 行：**要拆，但不做第一步**；阶段 5 或阶段 1 后仅做「抽函数、行为不变」的小拆。

---

## 4. 代码落点（阶段 1）

| 路径 | 角色 |
|------|------|
| `trader_shared/resonance.py` | `build_resonance(report) → dict` |
| `report_builder.build_report` | cards 齐后调用，写入 `report["resonance"]` |
| `tests/test_resonance_pullback.py` | 四岗/分档离线单测 |

禁止：在 `resonance.py` 内 import 缠/威**检测实现**重算 K 线；只读 report / cards。

---

## 5. 与现有模块关系

| 现有 | 关系 |
|------|------|
| `analysis_cards` | 共振主输入 |
| `strategy_match` | 阶段 2 起可读共振 |
| `fusion_core` | 阶段 1 不动；阶段 3+ 降权 |
| `discipline` / C1 | 阶段 3 与共振对齐「缺岗」话术 |
| `render_short_midline` | 版式 TBD；勿过早绑死 |

### 5.1 多场景消费者（计划时必须考虑，阶段 1 不实现）

底座是同一套「数据 → 分析 → 共振 → 策略 → 纪律」；**T0 / 选股池 / 仓位是不同编排入口 + 展示**，禁止各写一套理论。

| 场景 | 已有入口（参考） | 与共振/决策的关系（规划约束） |
|------|------------------|-------------------------------|
| 单票中短线 | `build_report` / final_report | 主挂载点（阶段 1 已写 `resonance`） |
| **T0 交易卡片** | `01-功能包-packages/t0/`、monitor、`t0_candidate_core` | 盘中执行卡：触发价/大单/风控；可读短线关键价与纪律。场景可不同于 `pullback_probe`（有底仓 T0 ≠ 新开试探），后续可 `scene=t0_*` 或只消费纪律+短线策略闸 |
| **选股池** | `final_pool`、`~/.trader/pool.json`、rank/plan/refresh | 多票批量分析；共振档可作过滤/排序离散信号，不作厚打分王 |
| **仓位轮动** | portfolio 技能、`stage_positioning`（T+1、相关性等） | 组合层决策扩展；读多票阶段/纪律/（将来）decision_view，不重跑检测 |

写阶段 2～5 与拆 `build_report` 的计划时：**默认检查**「池批量、T0 卡片、仓位是否仍只消费统一字段、有无分叉智商」。  
版式（单票报告 / T0 卡 / 池面板）均可后定；**先字段契约，后展示。**

---

## 6. 验收（阶段 1）

- [ ] `build_resonance` 纯函数，无网  
- [ ] builder 失败不阻断主报告  
- [ ] 出手/仓位/文案与改前一致（golden 可选：字段新增允许）  
- [ ] 门禁相关单测绿  

---

*冲突时以产品铁律与本文为准；实现细节以 `resonance.py` 为准并回写本文。*
