# known-gaps 收口 — Agent Handoff

> **状态**: active（2026-08-02）  
> **前置**: #46 已合；清单见 `docs/plans/known-gaps.md` / `BUSINESS.md` §2.2  
> **本 PR**: 修可对齐的代码差 + 文档取舍写死；**不**开 W-DIFF-7（深刺穿 ST 需产品裁决）。  
> **双 Agent**: 写落地 / 查对照。

---

## 1. 必须（G-K1…G-K5）

### G-K1｜破位须有 close（W-DIFF-6）

- **法源**: `wyckoff-structure-anchor-handoff.md` §3.1：`low < floor` **且** `close < sc_low`  
- **改**: `_phase_a_breakdown`：`close is None` → **skip 该棒**（`continue`），不得判 failed  
- **测**: close 缺失 + 深刺穿 → 不 failed；close 低于 sc_low → failed  

### G-K2｜`report["wyckoff"]` 不回退日线（W-DIFF-3）

- **改**: `assemble_stage`：`report["wyckoff"]` **等于** `wyckoff_midline`（周线结果或 insufficient 桩），**禁止** `or daily`  
- **保留**: `wyckoff_daily` / `wyckoff_midline` 分轨不变  
- **测**: mid 不足时 `report["wyckoff"].timeframe == "insufficient"`，且 ≠ daily 对象  

### G-K3｜`zones_count` 双口径（C-DIFF-5）

- **改**: `build_chanlun_view`（或等价）透出：  
  - `zones_count` = 引擎 raw 窗口数（与 `chan["zones_count"]` 一致，若有）  
  - `pivot_count` = 合并后中枢数（`len(zones)` / `chan["pivot_count"]`）  
- **面板**: 中枢行可读为 `中枢：{pivot}｜窗{raw}`（或等价；微信红线）；`output-template` 同步一句  
- **测**: raw≠merged 夹具两者皆正确且面板可区分  

### G-K4｜背驰展示 vs 一类扳机（C-DIFF-3/4）文档钉死

- **改代码可选**: 本 PR **不强制**统一 multi/area（属产品取舍）  
- **必须文档**: `formulas.md` §5/§6 明示：展示背驰可用 multi；一类/历史一类扳机 **面积-only**  
- `known-gaps.md` / BUSINESS：该项标为 **已声明取舍**（非未修 bug）

### G-K5｜清单更新

- `known-gaps.md`：去掉已修项；保留 W-DIFF-7（产品裁决）  
- `BUSINESS.md` §2.2 已知未修列表同步删/改  

---

## 2. 禁止

1. 不改 fusion / 出手 / 池分道。  
2. 不裁定 W-DIFF-7（深刺穿收回算 ST）。  
3. 不重开报告四区。  
4. 不把一类扳机改成 multi（除非手递将来另开）。

---

## 3. 可改

- `wyckoff_events._phase_a_breakdown`  
- `report_pipeline/assemble_stage.py`  
- `chanlun_run.py` / `chanlun_render.py` / output-template  
- `formulas.md`、`known-gaps.md`、`BUSINESS.md`  
- 相关 pytest  

---

## 4. 验收

| ID | 项 |
|----|-----|
| M-G1 | close None 不破位；有 close 才破 |
| M-G2 | wyckoff 别名 = midline，不回退 daily |
| M-G3 | zones_count + pivot_count 可核 |
| M-G4 | formulas 钉死 multi vs area |
| M-G5 | known-gaps 只剩产品裁决项（或空表+指针） |
| M-G6 | 门禁绿；查 Agent PASS |

---

## 5. 双 Agent

写：实现 + 测 + 文档 + push（`cursor/known-gaps-close-514d`）。  
查：对照本文；复验旧坏例；禁扩 scope。
