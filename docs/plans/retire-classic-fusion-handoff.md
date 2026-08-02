# 退役 classic 模式 / mappers — Agent Handoff

> **状态**: mother_law（实现中）· 2026-08-02  
> **基线**: `cursor/arch-cleanup-complete-1c6b`（#53）· 分支 `cursor/retire-classic-fusion-1c6b`  
> **拍板**: 用户明确要求做「删 classic 模式/mappers」。  
> **双 Agent**: 写落地 / 查对照。

---

## 0. 法源

1. `BUSINESS.md` §2.7 / `analysis-strategy-boundaries.md` §5：生产 = cards；classic deprecated。  
2. `fusion-no-silent-classic`：生产失败已禁静默 classic。  
3. 本手递：**生产与默认路径彻底去掉 classic / compare 热路径**；mappers 退出可 import 生产树。

---

## 1. 必须

| ID | 项 |
|----|-----|
| C1 | `_fusion_input_mode`：`classic`/`false`/`0`/`off`/`compare`/`both`/`dual` → **一律当 `cards`**，并 `DeprecationWarning`（说明已退役） |
| C2 | `merge_decisions` **删除** `_mode == "classic"` / `"compare"` 分支与 `_classic_three()` 热调用 |
| C3 | `fusion_classic_mappers.py`：从生产包移除——`git mv` 到 `02-共享模块-shared/trader_shared/_deprecated/fusion_classic_mappers.py`（或 `docs/_deprecated/`）；生产代码 **零** import |
| C4 | `fusion_core.__getattr__` 不再懒导出 classic mapper 符号（置信度仍走 `fusion_confidence`） |
| C5 | 测例：旧「classic 路径」改为断言「设 classic env 仍走 cards / 发 DeprecationWarning」；删/改依赖 `_classic_three` 的对账断言；`test_arch_boundaries` 可断言 analysis+fusion_core 热路径无 classic_mappers |
| C6 | 文档：BUSINESS §2.7、boundaries §5、AGENTS、fusion-guide、ARCHITECTURE——写明 classic/compare **已退役**；对照脚本 `scripts/compare_fusion_paths.py` 文首标 obsolete 或改打印「已退役」退出 |
| C7 | `fusion_confidence` **保留**（cards 仍用） |

---

## 2. 禁止

1. 不改 DV / 共振 / 池分道 / 出手铁律 / A2。  
2. 不拆 wyckoff_events / light_data / short_midline。  
3. 不改 `cards_failed` 中性降级语义。  
4. 不加厚 weighted_score。  
5. 不把 `_deprecated` 再挂回生产 import。

---

## 3. 可改白名单

- `fusion_core.py`  
- `fusion_classic_mappers.py` → `_deprecated/`  
- 相关 tests（`test_fusion_from_cards` / `test_production_path_defaults` / `test_fusion_cards_parity` / `test_arch_boundaries` / `test_fusion_path_compare` 等）  
- `scripts/compare_fusion_paths.py` / `fusion_path_compare.py`（obsolete 或瘦身）  
- BUSINESS / boundaries / AGENTS / ARCHITECTURE / fusion-guide  
- 本文手递  

---

## 4. 验收

| ID | 项 |
|----|-----|
| A1 | `FUSION_FROM_CARDS=classic` → merge 仍 `fusion_input_path` 属 cards 族（`cards`/`cards_failed`），且有 DeprecationWarning |
| A2 | 生产源码（不含 `_deprecated/`）无 `import fusion_classic_mappers` |
| A3 | 默认 cards 测与门禁绿 |
| A4 | 文档无「生产可 classic / compare 对账」现行表述 |
| A5 | 查 Agent PASS |

---

## 5. 双 Agent

写：实现 + 测 + 文档 + push。  
查：grep 生产树零 classic_mappers；复跑 A1–A3。
