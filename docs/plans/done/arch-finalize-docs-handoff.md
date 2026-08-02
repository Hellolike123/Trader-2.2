# 架构收口收尾：文档真相 + 归档 + 软清理 — Agent Handoff

> **状态**: done（2026-08-02；迁入 `docs/plans/done/`；写 Agent 落地）  
> **基线**: `cursor/arch-cleanup-complete-1c6b`（#53）  
> **双 Agent**: 写落地 / 查对照；push 更新 #53。

---

## 0. 法源

1. 已落地合同：`fusion-no-silent-classic`（`cards_failed`）· `signal-fusion-override-gate` · `pool-quote-provider` · `arch-followup-soft-thin-ruling`  
2. `docs/plans/README.md` 三桶：一次性 handoff → `done/`  
3. `ARCHITECTURE.md` / `BUSINESS.md` §2.7 须与代码一致  
4. residual：verbatim / breakdown 仪表化精神

---

## 1. 必须

| ID | 项 |
|----|-----|
| D1 | `BUSINESS.md` §2.7：cards 失败 = 中性/`cards_failed`，**禁止**再写静默回退 classic |
| D2 | `fusion-guide.md`：同上；`fusion_input_path` 枚举含 `cards_failed`；仪表口径 |
| D3 | `ARCHITECTURE.md`：补 `cards_failed` / `fusion_confidence` / `data_access.get_quotes`；日期可更新 |
| D4 | `AGENTS.md`：一句 `cards_failed`；「改代码去哪」可点 `fusion_confidence` / `get_quotes` |
| D5 | 五份一次性 handoff **git mv → `docs/plans/done/`**，文首改 `done`：signal-fusion-override / pool-quote-provider / fusion-no-silent-classic / arch-residual-cleanup / arch-followup-soft-thin-ruling |
| D6 | `docs/plans/README.md`：修断链；done 索引补上列；本收尾手递亦可进 done |
| D7 | `report_presentation.py`：删未用 `TencentFetcher` import；`_fusion_breakdown` 改仪表文案（分数/regime/分歧+仅参考），禁 `融合层：{action}` 指令主句 |
| D8 | `fusion_card_signals.py` 过时 docstring「回退 classic」改正 |
| D9 | 可选：`stage_detect.action_for_holding_state` 参数/doc 标明纪律 action（**不**改 report 键 `fusion_holding_hint`） |

---

## 2. 禁止

1. 不删 classic 模式/mappers。不 A2。不拆巨石。不四区。  
2. 不改出手/DV/池分道/golden 骨架。  
3. 不把母法源（wyckoff/chanlun 现行）挪进 done。

---

## 3. 验收

| ID | 项 |
|----|-----|
| A1 | BUSINESS/fusion-guide/ARCHITECTURE 无「cards 失败回退 classic」 |
| A2 | 五手递在 `done/`；README 无断链 |
| A3 | `_fusion_breakdown` 无「融合层：{action}」主句；无死 TencentFetcher import |
| A4 | 门禁绿 |
| A5 | 查 Agent PASS |

写完后本文亦 `done`。
