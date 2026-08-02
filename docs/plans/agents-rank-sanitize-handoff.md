# AGENTS 补 chanlun + rank phase_label sanitize — Agent Handoff

> **状态**: done（2026-08-02）  

> **产品裁决**: 文档对齐 + rank 面板可见面收口；不改判定 / fusion / 分道 / 出手。  
> **上游**: `skill-usage-guide-chanlun-handoff.md`（S-U4 余债）；`wyckoff-phase-label-fail-sanitize-handoff.md`（P-L1 漏网 rank）

---

## 1. 必须（A-R1…A-R5）

| ID | 必须 |
|----|------|
| A-R1 | `AGENTS.md` Skill 速查表增加 `chanlun`：一句话=缠论结构学术卡；入口=`final_chanlun.py --target`；注明不下单、不覆盖周线威科夫阶段 |
| A-R2 | `AGENTS.md` 推荐工作流增加一行缠论卡命令（放在威科夫附近即可） |
| A-R3 | `render_wyckoff_rank`（及若有的 row builder 写入面板前）对 `phase_label` 走 `_panel_fail_copy`（或等价），面板不得出现 `Phase A失败` / `Phase A 失败` |
| A-R4 | pytest：rank 渲染 failed fixture 禁词 + 含 `Phase A 失效`（或 sanitize 后的同义无「失败」） |
| A-R5 | 下列已合入手递文首改 `status: done`：`skill-usage-guide-chanlun`、`wyckoff-phase-label-fail-sanitize`、`wyckoff-report-fail-copy-leak`、`ci-gate-python-portable`、`wyckoff-fail-copy-cleanup`（若仍 active）；本 handoff 合入后也可标 done |

---

## 2. 禁止

1. 不改池分道 / fusion / decision_view。  
2. 不改引擎 `phase_a_status` 判定与内部 `fail_reason` 存储（除非直接进 rank 面板且无法映射）。  
3. 不重开报告四区。  
4. 不扩门禁 TESTS（除非新测本就离线且必要——本轮优先只加单元测文件内用例，可不入门禁）。

---

## 3. 可改 / 勿改

| 可改 | 勿改 |
|------|------|
| `AGENTS.md`（速查表 + 工作流） | `short_midline` 骨架 |
| `wyckoff_render.render_wyckoff_rank`（及必要的 rank row 组装） | `classify` / pool 分道 |
| 相关 pytest（如 `test_wyckoff_skill_render`） | fusion / 出手 |
| 本 handoff + 已合 handoff 文首 status | 检测阈值 |

---

## 4. 验收

| ID | 项 |
|----|-----|
| M-A1 | AGENTS 速查表有 chanlun 行与命令 |
| M-A2 | `render_wyckoff_rank` failed 行无「Phase A失败」类禁词 |
| M-A3 | 相关 pytest 绿；门禁绿（`TRADER_CI_PYTHON=python3` 可） |
| M-A4 | 已合 handoff 文首多为 done；diff 无 fusion/出手 |

---

## 5. 双 Agent

- **写 Agent**：按 A-R* 落地 + 测 + commit/push。  
- **查 Agent**：对照本文；禁扩业务。
