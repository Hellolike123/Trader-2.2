# 缠论操盘剩余项（R1–R10）Review

> 日期：2026-07-10  
> 验收唯一规格：`docs/plans/done/chan-ops-remaining-backlog-plan.md`（V1–V10）  
> 参考：`docs/guide/chan-ops-playbook.md` · `docs/plans/done/chan-discipline-b-plan.md`  
> 审查范围：只读验收 Implementer 落地；**不改业务实现**  
> 总判：**APPROVE**
>
> **路径勘误（本周期维护）**：生产接线为 `report_pipeline.attach_short_midline` /
> `report_renderer/short_midline.py`（非旧 monolith `report_core` 手拼）；产品 UI 标签为
> `（本周期）`（理论仍可称同级别分解）。P0 A1–A5 合同说明见文末或
> `docs/audit/chan-p0-p1-contract-note.md`。

---

## 总览

R1–R10 已在 `chan_discipline` / `run_analysis` / `attach_short_midline` + `short_midline` 渲染 /
单测 / `output-template` 链路落地。  
原则核对：只收紧不放宽；`chan_core` 无禁止开仓；买点阶梯 / 盘整 / low_zone / 分闸 / 位置 /
本周期标注 / 破位 / 周框均有实现与测试。  
指定 pytest：**85 passed**（0.07s）。

---

## V1–V10 验收表

| ID | 要求 | 结果 | 证据 |
|----|------|------|------|
| V1 | 一类买 cap≤5；三类+中线多可更高但仍≤阶段 max | **PASS** | `_buy_point_cap`：一类→5、二类→10、三类+中线非弱→`min(阶段上限,50)` 且不额外收紧；一类优先最严（`chan_discipline.py` L248–275, L430–443）。单测 `TestR1BuyPointCap`；现勘 cap 一类=5 / 三类=30≤50 |
| V2 | 盘整 + 走强表本可轻仓 → 被压到观望或 cap≤10 | **PASS** | 日/周 `structure_type` 含「盘整」→ `_tighten_cap` ≤10 + notes「盘整不做趋势重仓」；仍允许新开时 action 最多「轻仓试错」（L414–428, L519–526）。`TestR2PanZhengNoHeavy`；merge 用例 cap≤10 且非「持有/回踩低吸」重仓语义 |
| V3 | 在中线回踩内但 low_zone 外 → short 闸否决或总否决新开 | **PASS** | R3：`in_lz is False` → `_block_short`（L445–450）。现勘：mid=True / short=False / total=False。`TestR3LowZoneShortGate` |
| V4 | `allow_new_entry == (mid and short)` | **PASS** | 汇总 L505–506：`allow_new = allow_mid and allow_short`；merge 侧 L649 + L708–709 分闸透传后总闸仍等于 mid∧short（gate 否决时两边同 False）。`TestR4SplitGates` / `test_merge_preserves_split_fields` |
| V5 | `position_info.suggested_pct` 与 report 一致被裁 | **PASS** | `run_analysis.py` L1706–1741：按 `discipline.suggested_pct_cap` / `allow_new_entry` 算 `_final_sug`，同时写 `report["suggested_pct"]` 与 `report["position_info"]["suggested_pct"]`；context 文案同步。`position_info` 在 L1350–1357 必建 |
| V6 | 报告含位置：中枢… | **PASS** | `compute_pivot_position` → `中枢内\|中枢上(回踩中)\|中枢下(反抽中)\|中枢外\|未知`。`run_analysis` 写 `pivot_position_weekly/daily`。渲染：`attach_short_midline` → `short_midline.py` 🧭/⚡ 各一行 `位置：…`。`output-template.md` 样例已补。`TestR6PivotPosition` |
| V7 | 缠论文案含（本周期）当有买卖点/背驰 | **PASS** | `needs_same_level_tag` / `append_same_level_tag`（产物文案 `（本周期）`，兼容旧「同级」）。`short_midline` 中线/短线缠论行追加。`TestR7SameLevelTag`；template 样例 `顶背驰 · 看跌（本周期）` |
| V8 | 破 life → notes/动作收紧 | **PASS** | `current < life_line` → 双闸否决 + notes「跌破中线生命线」；有仓 `action_override=减仓`，无仓观望（L452–480）。中枢下沿同理（L481–489）。`TestR8LifeZhBreak`；现勘有仓减仓 |
| V9 | `weekly_frame` 有值；破坏不新开 | **PASS** | `compute_weekly_frame` → 完好\|紧张\|破坏（数据不足 None）（L146–183）。`run_analysis` 写入 `report["weekly_frame"]`（L1584–1587）；`apply_chan_discipline` 对「破坏」双闸否决（L491–503）。`TestR9WeeklyFrame` |
| V10 | merge 仍只收紧；pytest 相关绿 | **PASS** | `merge_discipline`：False 赢 / action rank 只收紧 / cap=min / notes 并集（L628–730）；`TestT3MergeTightenOnly` 恶意放宽仍观望。pytest 见下 |

---

## 红线

| 红线 | 结果 | 证据 |
|------|------|------|
| 不在 `chan_core` 写禁止开仓 | **PASS** | `chan_core.py` 无 `allow_new_entry` / `discipline` /「禁止开仓」；裁剪仅 `chan_discipline` + merge + `run_analysis` 砍仓 |
| 只收紧不放宽 | **PASS** | merge：gate 观望/减仓/止损不可被 chan 放宽为开仓；cap 取 min；否决新开时开仓类 action→观望 |
| 不改笔算法 / 无新中线主引擎 | **PASS** | 改动集中在 discipline / 报告展示 / 接线；无 `chan_core` 分型笔段重写 |
| 报告无 mi/Mistery 人设 | **PASS** | template 与 report 出手/失效/纪律白话；无品牌词新增 |

---

## 模块对照（R1–R10）

| ID | 模块落点 | 结果 |
|----|----------|------|
| R1 买点阶梯 | `chan_discipline._buy_point_cap` + short 侧 tighten | **PASS** |
| R2 盘整禁重仓 | structure_type 日/周 + cap≤10 + 轻仓试错 | **PASS** |
| R3 low_zone 短闸 | `low_zone_lower/upper` → `allow_new_entry_short` | **PASS** |
| R4 中/短分闸 | mid/short allow + cap 真实赋值；总闸 AND | **PASS** |
| R5 suggested_pct 同步 | report + position_info 双写 + context | **PASS** |
| R6 中枢位置 | `compute_pivot_position` + 报告两行 | **PASS** |
| R7 本周期标注 | 中/短缠论行 `（本周期）` | **PASS** |
| R8 破生命线/中枢 | 不新开；有仓减仓；notes | **PASS** |
| R9 weekly_frame | 计算写入 report；破坏不新开 | **PASS** |
| R10 文档 | playbook 已入库；b-plan 状态；output-template v2.7.0 | **PASS** |

---

## 接线顺序（run_analysis）

```text
mid_key_prices
→ weekly_frame + pivot_position_weekly/daily
→ mid_view 文案
→ compute_mistery_gate（无回踩/买点主裁）
→ apply_chan_discipline（回踩/买点/盘整/low_zone/life/zh/weekly_frame）
→ merge_discipline
→ 裁 suggested_pct + position_info.suggested_pct
→ build_conclusion_block(discipline=…)
```

与方案 B + 剩余项计划一致。

---

## pytest

```bash
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_chan_discipline.py \
  02-共享模块-shared/tests/test_mistery_gate.py \
  02-共享模块-shared/tests/test_conclusion_midline.py \
  02-共享模块-shared/tests/test_report_mid_short_sources.py -q
```

**结果：85 passed in 0.07s**

覆盖：T1–T7（P0）+ R1–R9 单测 + gate 迁出回归 + weekly_frame 双保险 + conclusion/report mid-short 源。

---

## 阻断 / 非阻断

### 阻断项

无。

### 非阻断（可选后续）

| # | 说明 | 建议 |
|---|------|------|
| N1 | V5 无独立集成测断言 `position_info.suggested_pct == report.suggested_pct`（接线明确） | 可加 1 条 mock 级测，非必须 |
| N2 | 破 life 时 `life_break` 与 `weekly_frame_break` 双 notes（阈值：life 任意跌破 vs 框 0.995） | 可接受；若嫌吵可 notes 去重合并 |
| N3 | `weekly_frame` 写入 report 但未单独成报告行（结论块可消费；V9 不要求展示） | 可选 🧭 下「周框：完好/紧张/破坏」 |
| N4 | R7 无 `short_midline` 渲染级单测（逻辑 + template 已齐） | 可选快照测 |

---

## 总判

**APPROVE**

V1–V10 全部 PASS；红线全部 PASS；无阻断项。  
Implementer 的 R1–R10 可作为 P1/P2 打包合入，无需 REQUEST_CHANGES。

---

## P0 / P1 合同附注（不改写 BUSINESS）

P0 A1–A5 代码实现的是既有 `BUSINESS.md` §2.0 / §2.1 合同（详见
`docs/audit/chan-p0-p1-contract-note.md`）：`stage`=周威科夫；`daily_fallback` 仅展示；
C1 / 共振正式买点只认一/二/三类；类一/类二为观察档。P1 假趋势 demote→盘整见
`formulas.md` §9 + `classify_structure`（不发明 `structure_type=假趋势`）。
