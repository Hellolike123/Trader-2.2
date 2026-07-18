# 缠论操盘剩余项实施计划（P1/P2 打包）

> 状态：**Implementer 已完成 R1–R10**（待 Reviewer 审计）  
> 日期：2026-07-10  
> 前提：方案 B P0 已落地（`chan_discipline` + merge）  
> 原则：只收紧不放宽；不改笔算法；不在 chan_core 写禁止开仓  
> 操盘教义：`docs/chan-ops-playbook.md`（已从桌面入库）

---

## 实施状态（Implementer）

| ID | 状态 |
|----|------|
| R1 买点阶梯 cap | ✅ |
| R2 盘整禁重仓 | ✅ |
| R3 low_zone 短闸 | ✅ |
| R4 中/短分闸 | ✅ |
| R5 suggested_pct 同步 | ✅ |
| R6 中枢位置 | ✅ |
| R7 同级标注 | ✅ |
| R8 破生命线/中枢 | ✅ |
| R9 weekly_frame | ✅ |
| R10 文档 | ✅ |

---

## 范围清单

### P1 纪律/仓位

| ID | 项 | 实现要点 |
|----|-----|----------|
| R1 | 一买试 / 二买加 / 三买主 | `buy_point_types` → cap：一类≤5、二类≤10、三类+中线允许多→min(阶段上限,50)；无买点不强制 |
| R2 | 盘整禁趋势重仓 | structure_type 含「盘整」→ action 不得轻仓以上开仓语义；cap≤10 或观望；notes |
| R3 | 短线 low_zone 第二道门禁 | current 不在 low_zone 且试图新开 → allow_new_entry_short=False；总闸 AND |
| R4 | 中/短分闸字段落地 | `allow_new_entry_mid/short`、`suggested_pct_cap_mid/short` 真实赋值；总 `allow_new_entry = mid and short` |
| R5 | suggested_pct 全链路 | position_info.suggested_pct 与 report.suggested_pct 同步被 discipline 裁；context 文案 |

### P2 展示/卖侧/周框

| ID | 项 | 实现要点 |
|----|-----|----------|
| R6 | 中枢位置一行 | `pivot_position`: 中枢内\|中枢上(回踩中)\|中枢下(反抽中)\|中枢外\|未知；🧭 与 ⚡ 可各一行（周/日 zone） |
| R7 | 同级标注 | 短线专家缠论、中线缠论行：背驰/买卖点带「（同级）」 |
| R8 | 破生命线/中枢减仓语义 | current < life_line 或 current < zh_bottom（有效中枢）→ action 倾向减仓/观望（有仓减、无仓不新开）；notes；与 invalidation 对齐不重复长文 |
| R9 | weekly_frame | 基于 weekly_bars + life/中枢：完好\|紧张\|破坏；写入 report；破坏 → 不新开（chan 或 merge） |
| R10 | 文档 | playbook 已入库；更新 chan-discipline-b-plan / discipline 状态；output-template 补位置行与分仓 |

### 明确不做

- 重写分型/笔/段  
- 新中线主引擎  
- mi 人设进报告  
- pack_all / 全仓修无关红测（除非本 PR 直接打坏）

---

## 模块改动

| 文件 | 动作 |
|------|------|
| `chan_discipline.py` | R1–R4、R8、R9 消费；分 mid/short 闸 |
| `mistery_gate.py` | 尽量不膨胀；weekly_frame 破坏可只在 chan |
| `midline_structure` 或小工具 | `compute_pivot_position(current, zones)` 可放 chan_discipline |
| `run_analysis.py` | 传 buy_points、structure_type 日/周、low_zone、zones；写 weekly_frame；同步 position_info |
| `report_core.py` | 位置行；同级；分仓可选一行；discipline notes |
| `conclusion_block.py` | 读新 notes |
| `output-template.md` | 样例更新 |
| `tests/test_chan_discipline.py` 等 | 覆盖 R1–R9 |
| `docs/audit/chan-ops-remaining-review.md` | Reviewer 产出 |

---

## 验收

| ID | 要求 |
|----|------|
| V1 | 一类买 cap≤5；三类+中线多可更高但仍≤阶段 max |
| V2 | 盘整 + 走强表本可轻仓 → 被压到观望或 cap≤10 |
| V3 | 在中线回踩内但 low_zone 外 → short 闸否决或总否决新开 |
| V4 | allow_new_entry == (mid and short) |
| V5 | position_info.suggested_pct 与 report 一致被裁 |
| V6 | 报告含位置：中枢… |
| V7 | 缠论文案含（同级）当有买卖点/背驰 |
| V8 | 破 life → notes/动作收紧 |
| V9 | weekly_frame 有值；破坏不新开 |
| V10 | merge 仍只收紧；pytest 相关绿 |

---

## 双 Agent

- Implementer：本清单 R1–R10  
- Reviewer：持本文件 + playbook，写 audit，V1–V10  
