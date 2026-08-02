# 架构 follow-up：置信度软抽 + 日线裁定去 fusion.action — Agent Handoff

> **状态**: impl_done（写+查 PASS；已并 #53）· 2026-08-02  
> **基线**: `cursor/arch-cleanup-complete-1c6b` · PR [#53](https://github.com/Hellolike123/Trader-2.2/pull/53)  
> **双 Agent**: 写落地 ✅ / 查 PASS ✅。

---

## 0. 法源

1. `analysis-strategy-boundaries.md` §0 / §1.1：依赖方向；禁止从 fusion.action 推断出手。  
2. `resonance-and-orchestration.md` §1：出手听 DV；fusion 仅仪表。  
3. `AGENTS.md`：日线裁定听 decision_view；禁止 fusion.action 单独推「宜追」；Classic 动量已委托 cards，勿在 cards 复制映射。  
4. `arch-residual-cleanup-handoff.md` §2.6：daily_ruling 去 action 须另开手递（本文即是）。  
5. `fusion-no-silent-classic-handoff.md`：不删 classic mappers。

---

## 1. 必须

### F1｜置信度软抽（破 analysis→classic 依赖）

| ID | 项 |
|----|-----|
| F1a | 新建中性模块（建议 `fusion_confidence.py`）承载 `_score_to_confidence` + `_load_confidence_params`（从 classic_mappers 迁出或经典 re-export） |
| F1b | `analysis/fusion_card_signals.py` **零** import `fusion_classic_mappers`；改 import 中性模块 |
| F1c | `fusion_classic_mappers` 可从中性模块 re-export 保持旧 import 兼容 |
| F1d | AST 测：`analysis/*.py` 不得 import `fusion_classic_mappers` |
| F1e | 置信数值与抽前一致（含 calibrated_params fallback） |

### F2｜日线裁定不读 fusion.action

| ID | 项 |
|----|-----|
| F2a | `build_daily_ruling` **删除** `fusion.get("action")` → `reduce_like` → 强制「不宜追高」 |
| F2b | stance 只听：`gate_action`（盘纪律档）· `chase_ok` · `decision_view.allow_new_recommend` · `resonance.grade` |
| F2c | `weighted_score` **仅**定 bias（偏多/偏空/中性），不得单独推「宜追」 |
| F2d | 词表不变：`偏多|偏空|中性` + `宜追|不宜追高|观望` |
| F2e | 纪律 `gate_action` 含减仓/观望/不做/止损离场/不新开 → 仍「不宜追高」（覆盖旧 reduce_like 意图） |
| F2f | 测：仅 fusion.action=减仓/空仓、纪律未挡、DV 绿、chase_ok、无 conflict → **不得**因 action 变「不宜追高」；既有 DV/conflict/gate 测仍绿 |

---

## 2. 禁止

1. 不删 classic 模式 / mappers 文件。  
2. 不发明新 stance 词。  
3. 不改 DV / 共振 / 池分道 / fusion 权重 / A2 / golden 骨架。  
4. 不拆巨石文件。  
5. 不在 cards 内复制第二套 U 型映射实现（只改 import 源）。

---

## 3. 可改白名单

- `trader_shared/fusion_confidence.py`（新建）  
- `trader_shared/fusion_classic_mappers.py`  
- `trader_shared/analysis/fusion_card_signals.py`  
- `trader_shared/conclusion_block.py`（`build_daily_ruling`）  
- `trader_shared/fusion_core.py`（仅若 `__getattr__` 需指向新模块）  
- `tests/test_arch_boundaries.py` / `tests/test_daily_ruling_decision_view.py`（或新建）  
- 本文手递  

---

## 4. 验收

| ID | 项 |
|----|-----|
| A1 | analysis 包 AST 无 classic_mappers import |
| A2 | score→confidence 抽样同值 |
| A3 | build_daily_ruling 源码不读 `fusion["action"]` |
| A4 | action-only 减仓夹具 → 不宜因 action 收紧；gate_action=减仓 → 仍不宜追高 |
| A5 | 既有 daily_ruling / fusion_from_cards / gate 绿 |
| A6 | 查 Agent PASS |

---

## 5. 双 Agent

写：实现 + 测 + push 本分支（更新 #53）。  
查：对照本文；grep analysis→classic、build_daily_ruling→action。
