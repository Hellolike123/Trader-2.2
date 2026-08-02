# signal_core fusion 覆盖须听 FUSION_OVERRIDE — Agent Handoff

> **状态**: mother_law（写 Agent 已落地，待查）· 2026-08-02  
> **基线**: `main` @ PR #49 合入后（`cursor/plans-index-sync-514d`）  
> **分支**: `cursor/signal-fusion-p0-1c6b`  
> **双 Agent**: 写落地 / 查对照；查完修完再 PR。

---

## 0. 法源（先读）

1. [`docs/designs/resonance-and-orchestration.md`](../designs/resonance-and-orchestration.md) §1 方向铁律：出手/新开听共振∧策略∧纪律；fusion `weighted_score`/`action` 仅仪表；`FUSION_OVERRIDE_ENABLED` **默认 false**。  
2. [`docs/designs/analysis-strategy-boundaries.md`](../designs/analysis-strategy-boundaries.md) §0：禁止从 fusion 分/action 直接推断方向；fusion 默认不微调出手。  
3. [`ARCHITECTURE.md`](../../ARCHITECTURE.md) §1：Fusion 仅仪表；新开铁律跟 `decision_view`。  
4. 对照实现（已正确闸）：`decision_core.py` / `t0_candidate_core.py` 均 `if FUSION_OVERRIDE_ENABLED and ...`。

---

## 1. 问题（必须修）

`signal_core.build_signal` 在 `fusion.confidence > 0.4` 且有非零 `signals_detail` 时，**无条件**用 `_map_fusion_to_signal(fusion.action)` 改写 `signal_type` / `direction` / `action`，并打 `fusion_override=True`。

同时 `decision_persist_fields` 已听 `decision_view.allow_new_recommend` → **落盘 signals 的方向/类型可与「是否允许新开」矛盾**。

这是 fusion 在信号侧的暗指挥，违方向铁律。

---

## 2. 必须

| ID | 项 |
|----|-----|
| M1 | `build_signal` 的 fusion remap **仅当** `FUSION_OVERRIDE_ENABLED is True` 且置信度超过阈值（与 `decision_core` 一致：读 `FUSION_CONFIDENCE_THRESHOLD`，默认沿用现有 `> threshold` 语义；若现码写死 `0.4` 则改为读 config 阈值） |
| M2 | 默认（override=false）：即使 fusion action 与 `signal_state` 方向冲突，也**不得**改写；不得写 `fusion_override=True` |
| M3 | 显式 `FUSION_OVERRIDE_ENABLED=true` 且过阈值：保留旧 remap 行为（对照/回测） |
| M4 | `decision_persist_fields` 行为不变（仍只听 DV） |
| M5 | 新增 pytest 锁 M1–M3；相关旧测仍绿 |
| M6 | （可选增强）`test_arch_boundaries` 或同文件：静态/注释断言「信号落盘出手不得无闸读 fusion.action」——若加测须可维护，禁止假阳性 |

---

## 3. 禁止

1. 不改 `decision_view` / resonance / strategy packs / 池分道。  
2. 不加厚 fusion 权重；不把 classic 退役塞进本 PR。  
3. 不改微信面板骨架 / golden（本 PR 无展示契约变更）。  
4. 不删 `_FUSION_ACTION_MAP`（对照路径仍要）。  
5. 不把缺 DV 时用 discipline 冒充允许新开（M4 既有合同）。

---

## 4. 可改白名单

- `02-共享模块-shared/trader_shared/signal_core.py`  
- `02-共享模块-shared/tests/test_signal_checkup.py`（或新建 `test_signal_fusion_override.py`）  
- `01-功能包-packages/trader/tests/test_fusion_integration.py`（仓外旧测：对齐默认不 remap / 显式开启才 remap）  
- 可选：`02-共享模块-shared/tests/test_arch_boundaries.py`  
- 本文手递状态行；`docs/plans/README.md` 仅当需挂索引时一行  

---

## 5. 验收表

| ID | 验收 |
|----|------|
| A1 | 默认 env：构造「signal_state 偏多 / fusion.action 映射偏空且 conf>阈值」→ `build_signal` direction **等于** signal_state，无 `fusion_override` |
| A2 | monkeypatch/env `FUSION_OVERRIDE_ENABLED=true` + 同夹具 → direction 被 remap，且 `fusion_override is True` |
| A3 | `decision_persist_fields` / 既有 checkup 测仍过 |
| A4 | `python3 -m pytest` 针对新增+`test_signal_checkup`+（若改）`test_arch_boundaries` 绿 |
| A5 | 查 Agent 对照本文 M*/禁止项全部 ✅ |

---

## 6. 双 Agent

| 角色 | 职责 |
|------|------|
| **写** | 只读本文 + 上列法源 → 改 `signal_core` + 测 → commit/push 本分支 |
| **查** | 独立对照本文逐项 ✅/❌；复现 A1/A2；找「仍无闸读 fusion.action 改方向」；默认不改码，列必须再改 |

父 Agent：查完修完再开/更新 PR。
