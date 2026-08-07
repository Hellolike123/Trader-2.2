# 已知未修差异（诚实列表）

> **状态**: 指针（与 `BUSINESS.md` §2.2 同源）  
> **用途**: Agent 勿假装零差；**禁止**把本页写成待办诱惑大重构。  
> **禁止**: 本页不授权改 fusion / 出手 / 池分道 / 区间算法。

| 项 | 说明 |
|----|------|
| 缠论方向消费双口径（2026-08-08 审计） | `resolve_chanlun_primary` 与 `format_chanlun_theory_line` 对同一结果的优先级/方向可能打架（一类买 + 顶背驰：主解析看涨、理论行看跌）；需人工裁定谁优先并对齐。详见 chanlun-audit 记录。 |
| 缠论趋势概念三轨并行（2026-08-08 审计） | `structure_type` / `trend_label` / `higher_trend` 同名不同义，渲染层混合成句；需集中定义并明确 `higher_trend` 置信门槛。 |
| 缠论未合同化取舍（2026-08-08 审计） | §11A 单边阈值、二类买/卖 MA 偏移窗口、三分型切点语义、Bug R 段起点“共用转折笔”约定只在代码/注释，未进 `formulas.md`；需补法源或人工裁定。 |
| 缠论性能与重复实现（2026-08-08 审计） | `_recompute` 缓存未被 `get_analysis` 消费（双倍几何计算）；三份解包 helper、两份 config fallback 重复；建议后续收敛。 |

**已声明取舍**（非未修 bug）：
- 背驰展示可用 multi（`detect_divergence` / `_stroke_force_weaker_multi`）；一类/历史一类扳机面积-only（`_stroke_force_weaker`）。见 `formulas.md` §5.1a / §6。
- **W-DIFF-7 深刺穿收回与 ST**：破位仅当 `low < sc_low×(1−MAX_PIERCE)` **且** `close < sc_low`；深刺穿但 `close ≥ sc_low` 收回 → 不算破位；未 failed 且满足既有 ST 条件时**允许**认 ST（不因「曾刺穿过 floor」单独否决）。法源：`done/w-diff7-st-pierce-decision-handoff.md` + structure-anchor §3.1；**不改** ST 检测阈值/公式。

已修（勿再当 gap）：forming 上沿、破位冷启动排除、ZG/ZD 极值 → `done/range-diff-fixes-handoff.md`；
`close is None` 不破位、`report["wyckoff"]` 不回退日线、`zones_count`/`pivot_count` 双口径 → `done/known-gaps-close-handoff.md`（G-K1…G-K3）。
