# phase_label 失败字样 Sanitize — Agent Handoff

> **状态**: done（2026-08-02）  

> **触发**: 报告光杆 failed 句已修（PR #39）；但 `phase_label` / `fail_reason` 等字段仍可含「Phase A 失败」，经 `build_wyckoff_card.phase_label`、view、详析映射若未 sanitize 仍可能露脸。  
> **上游**: `../wyckoff-phase-fail-copy-handoff.md` §1.2.6；`wyckoff-report-fail-copy-leak-handoff.md`

---

## 1. 必须（P-L1…P-L4）

| ID | 必须 |
|----|------|
| P-L1 | 凡**进入面板/卡 summary 可见面**的 `phase_label`（含 view / card / render），failed 语境不得保留「Phase A 失败」/「Phase A失败」主展示 |
| P-L2 | 优先在既有 `_panel_fail_copy` / view oneline 映射路径统一收口；`build_wyckoff_card` 写出的 `phase_label`/`main` 对用户可见字段同步 |
| P-L3 | 内部检测存储 `fail_reason` 可不改；若某路径把 `fail_reason` 原文贴进面板，则须映射 |
| P-L4 | pytest：卡/view 在 failed fixture 上 `phase_label` 可见值无「失败」禁词（或证明该字段永不渲染且 JSON 契约测试覆盖 sanitize） |

推荐：failed 时 `phase_label` 可见值改为如 `无明确阶段（Phase A 失效，破位未收回）`（与引擎语义一致，仅人话）。

---

## 2. 禁止

不改判定；不改 fusion/出手；不造假箱；不重开四区。

---

## 3. 验收

| ID | 项 |
|----|-----|
| M-L1 | failed fixture：card/view 可见 phase_label 无 `Phase A失败`/`Phase A 失败` |
| M-L2 | 相关 pytest 绿；门禁绿 |
| M-L3 | diff 限于 wyckoff 展示映射 + 测 + 本 handoff |
