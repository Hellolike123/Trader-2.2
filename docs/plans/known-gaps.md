# 已知未修差异（诚实列表）

> **状态**: 指针（与 `BUSINESS.md` §2.2 同源）  
> **用途**: Agent 勿假装零差；**禁止**把本页写成待办诱惑大重构。  
> **禁止**: 本页不授权改 fusion / 出手 / 池分道 / 区间算法。

| 项 | 说明 |
|----|------|
| （当前无未修代码差） | — |

**已声明取舍**（非未修 bug）：
- 背驰展示可用 multi（`detect_divergence` / `_stroke_force_weaker_multi`）；一类/历史一类扳机面积-only（`_stroke_force_weaker`）。见 `formulas.md` §5.1a / §6。
- **W-DIFF-7 深刺穿收回与 ST**：破位仅当 `low < sc_low×(1−MAX_PIERCE)` **且** `close < sc_low`；深刺穿但 `close ≥ sc_low` 收回 → 不算破位；未 failed 且满足既有 ST 条件时**允许**认 ST（不因「曾刺穿过 floor」单独否决）。法源：`done/w-diff7-st-pierce-decision-handoff.md` + structure-anchor §3.1；**不改** ST 检测阈值/公式。

已修（勿再当 gap）：forming 上沿、破位冷启动排除、ZG/ZD 极值 → `done/range-diff-fixes-handoff.md`；
`close is None` 不破位、`report["wyckoff"]` 不回退日线、`zones_count`/`pivot_count` 双口径 → `done/known-gaps-close-handoff.md`（G-K1…G-K3）。
