# 交易员报告 Phase 失效文案漏网 — Agent Handoff

> **状态**: done（2026-08-02）  

> **触发**: 干跑宁德时代 `final_report` 中线仍见 `威科夫：Phase A失败 · 破位未收回 · 不据此开仓`；威科夫 skill 卡已按 P-C* 清扫，**报告光杆路径漏网**。  
> **上游法源**: `../wyckoff-phase-fail-copy-handoff.md`（P-C*）；`wyckoff-fail-copy-cleanup-handoff.md`（C-L*）  
> **产品裁决**: 凡**直接进面板**的人话，failed 写「失效」不写「失败」；不改判定字段内部原文（除非该串直接进面板）。

---

## 1. 必须（R-F1…R-F6）

| ID | 必须 |
|----|------|
| R-F1 | `format_wyckoff_midline_light`：`phase_a_status==failed` → 可见面含 `Phase A 失效`，**不得**含 `Phase A失败` / `Phase A 失败` |
| R-F2 | `format_wyckoff_daily_phase_light`：同上 |
| R-F3 | 失败无新强势语义对齐：须含「须重新寻底」或与 P-C 无强势档同义；保留「不据此开仓」/「仅对照」等报告既有约束语可 |
| R-F4 | `wyckoff_view` 等**直接进面板**的 failed 映射同步（如 `phase_a_failed` 人话）；内部 `fail_reason` 存储串若不进面板可不改 |
| R-F5 | pytest：更新仍断言 `Phase A失败` 的用例为 `Phase A 失效`；新增/加固报告光杆路径禁词测 |
| R-F6 | 重跑样本：宁德时代（或等价 failed fixture）`final_report` / 光杆 format 无禁词 |

推荐可见句（可微调分隔符，语义勿漂）：

- 中线：`威科夫：Phase A 失效｜须重新寻底｜不据此开仓`
- 日线光杆：`Phase A 失效｜须重新寻底｜仅对照`

---

## 2. 禁止

1. 不改 `phase_a_status=failed` / L0 / fusion / decision_view / 池分道。  
2. 不实现报告四区重组。  
3. 不造日线 L0 假雏形箱。  
4. 不把「失败」改回面板主展示。  
5. 不为凑绿削弱禁词测。

---

## 3. 可改 / 勿改

| 可改 | 勿改 |
|------|------|
| `wyckoff_core.py` 中 `format_wyckoff_*_light` failed 返回串 | 检测阈值 / 事件判定 |
| `wyckoff_view.py` 面板映射文案 | `short_midline` 四区骨架 |
| 相关 pytest（structure_anchor / tr_maturity / skill_render 等） | fusion / 出手 |
| 本 handoff；必要时一句同步 phase-fail-copy「报告光杆已覆盖」 | 大面积改 `fail_reason` 内部字段 |

例外依据：phase-fail-copy §1.2.6 — *除非该字符串直接进面板*。

---

## 4. 验收

| ID | 项 | 如何验 |
|----|-----|--------|
| M-R1 | 光杆 format failed fixture 无 `Phase A失败`/`Phase A 失败`，有 `Phase A 失效` | pytest |
| M-R2 | 原断言 `Phase A失败` 的测已改并对齐新句 | pytest |
| M-R3 | 门禁或相关 wyckoff 测绿 | `run-gate-tests.sh` 或子集 |
| M-R4 | diff 不碰 fusion/出手/池分道 | `git diff` |

---

## 5. 双 Agent

- **写 Agent**：按 R-F* 改 + 测 + commit/push。  
- **查 Agent**：对照本文 + P-C 禁词表；列 must-fix。
