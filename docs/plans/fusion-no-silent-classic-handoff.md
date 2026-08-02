# 生产 cards 失败禁止静默回退 classic — Agent Handoff

> **状态**: mother_law（写 Agent 已落地，待查）· 2026-08-02  
> **基线**: `main` @ #49 后（与 #50 / #51 独立）  
> **分支**: `cursor/fusion-no-silent-classic-1c6b`  
> **双 Agent**: 写落地 / 查对照；查完修完再 PR。  
> **失败态写死**: `fusion_input_path=cards_failed`（中性三席，不静默 classic）。

---

## 0. 法源

1. [`docs/designs/analysis-strategy-boundaries.md`](../designs/analysis-strategy-boundaries.md) §5：生产默认 **cards**；`classic` deprecated 仅对照；禁止文档/Agent 写成默认 classic。  
2. [`BUSINESS.md`](../../BUSINESS.md) §2.7（Fusion 生产路径 = cards）。  
3. [`docs/designs/resonance-and-orchestration.md`](../designs/resonance-and-orchestration.md) §7：fusion 兼容可留；新功能默认不依赖加厚/回退权重。  
4. 现状：`fusion_core.merge_decisions` 在 `_mode == cards` 且 `_three_signals_via_cards` 返回 `None` 时 **静默** `_classic_three()` 并把 `fusion_input_path` 标成 `classic`——生产路径悄悄换轨。

---

## 1. 必须

| ID | 项 |
|----|-----|
| M1 | 默认/`cards` 模式：cards 适配失败时 **禁止** 调用 `_classic_three()` / classic mappers |
| M2 | 失败时：三席用中性占位（`direction=0`、低 confidence、reason 标明 cards 失败）；`fusion_input_path` 标为可区分失败态（建议 `cards_failed` 或保持 `cards` 并加 `fusion_cards_error` 字段——二选一写死并测） |
| M3 | 显式 `FUSION_FROM_CARDS=classic`：行为可保留（含 `classic_via_cards` / 真 classic 回退） |
| M4 | `compare`：对账路径可继续用 classic 一侧；主结果仍优先 cards（既有语义） |
| M5 | pytest：默认模式强制 `_three_signals_via_cards → None` → 断言 **未** 走 classic mapper、path 为失败态、方向中性 |
| M6 | 同步 boundaries / 手递一句：生产 cards 失败 = 降级中性，不静默 classic |

---

## 2. 禁止

1. 不删 `fusion_classic_mappers.py`（本 PR 只断生产静默回退）。  
2. 不改 `decision_view` / 共振 / 池分道 / 出手铁律。  
3. 不加厚 `weighted_score` 公式。  
4. 不改微信面板 / golden（除非 fusion 失败文案已暴露且合同要求——默认不改）。  
5. 不把默认改回 classic。

---

## 3. 可改白名单

- `02-共享模块-shared/trader_shared/fusion_core.py`  
- `02-共享模块-shared/tests/test_fusion_from_cards.py`（或新建 `test_fusion_cards_fail_closed.py`）  
- `docs/designs/analysis-strategy-boundaries.md` §5 一句（生产失败语义）  
- 本文手递  

---

## 4. 验收

| ID | 项 |
|----|-----|
| A1 | 默认模式 + monkeypatch `_three_signals_via_cards` 返 None → 无 classic 调用；席位中性；path=失败态 |
| A2 | `fusion_from_cards="classic"` 旧测仍绿 |
| A3 | cards 成功路径仍 `fusion_input_path=="cards"` |
| A4 | 相关 pytest + 门禁不红 |
| A5 | 查 Agent PASS |

---

## 5. 双 Agent

写：实现 + 测 + 文档一句 + push。  
查：对照本文；确认源码无「cards 失败 → `_classic_three`」；复跑 A1–A3。
