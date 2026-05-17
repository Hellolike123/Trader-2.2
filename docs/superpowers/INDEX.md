# Superpowers 计划索引

最后更新：2026-05-17

本目录集中管理 Trader 2.0 体系的功能增强计划（plans/）、设计规格（specs/）和设计审查（reviews/），确保跨 Skill 的架构变更可追溯、可审查。

---

## Plans

| 文件名 | 简要描述 | 创建日期 | 状态 | 前置依赖 |
|--------|---------|----------|------|---------|
| `2026-05-12-signal-id-unification-plan.md` | 用单一 `make_signal_id()` 替换双 ID 系统，统一三个 JSONL 文件的主键 | 2026-05-12 | 待实施 | 无（基础设施） |
| `2026-05-12-signal-id-phases-3-4-plan.md` | Phase 1 完成后清理废弃的 `stable_id()` 和 3-key 降级逻辑 | 2026-05-12 | 待实施 | Signal ID Unification Phase 1-2 |
| `2026-05-12-signal-lifecycle-plan.md` | 给信号记录加 `status` 字段（active/completed/expired）及状态迁移守卫 | 2026-05-12 | 待实施 | Signal ID Unification |
| `2026-05-12-fusion-integration-plan.md` | 让 `build_signal()` 在融合层置信度 > 0.2 时优先使用融合决策 | 2026-05-12 | 待实施 | Fusion Activation |
| `2026-05-12-pool-fusion-plan.md` | 池记录存储融合层输出，在 show/compare/rank 中展示 | 2026-05-12 | 待实施 | Fusion Integration |
| `2026-05-12-tracking-fusion-breakdown-plan.md` | 将 `fusion_override` 从 signal 传播到 result，在追踪面板增加融合覆盖维度 | 2026-05-12 | 待实施 | Fusion Integration + Signal ID Unification |
| `2026-05-06-portfolio-allocation-and-market-filter.md` | 用 Score 比例分配替代 ATR 固定分配，并接入大盘过滤信号降级 | 2026-05-06 | 待实施 | 无 |
| `t0_enhancement_plan.md` | 补全 t0-trader 缺失指标（布林带/KDJ/ATR% 等）和风控逻辑 | — | 待实施 | Signal ID Unification（信号追踪依赖） |
| `2026-05-12-signal-id-unification-plan.md.v1` | Signal ID 统一模型 v1 历史版本（已被主版本替代） | 2026-05-12 | 已废弃 | — |

## Specs

| 文件名 | 对应计划 | 简要描述 |
|--------|---------|---------|
| `2026-05-12-signal-id-unification-design.md` | Signal ID Unification | 统一信号 ID 模型设计：SHA256[:16] 单一函数、双字段共存、三级降级匹配 |
| `2026-05-12-signal-id-unification-design.md.v1` | Signal ID Unification | v1 设计稿（已被 v2 替代） |
| `2026-05-12-signal-id-unification-design.md.v2` | Signal ID Unification | v2 设计稿（当前最新） |
| `2026-05-12-signal-lifecycle-design.md` | Signal Lifecycle | 信号生命周期状态设计：3 种状态值 + 迁移规则 + 追踪过滤 |
| `2026-05-12-fusion-integration-design.md` | Fusion Integration | 融合层决策接入 build_signal 设计：置信度阈值 0.2 + fusion→signal 映射 |
| `2026-05-12-fusion-activation-design.md` | Fusion Activation | 将 `FUSION_LOG_ONLY` 默认值从 true 改为 false，激活融合层 |
| `2026-05-12-pool-fusion-design.md` | Pool Fusion | 选股池融合层集成设计：pool.json 新增 fusion 字段 + show/compare 展示 |
| `2026-05-06-portfolio-allocation-and-market-filter-design.md` | Portfolio Allocation + Market Filter | Score 占比分配 + ATR Cap + 大盘环境过滤设计 |

## Reviews

| 文件名 | 对应计划 | 审查结论 | 关键问题 |
|--------|---------|---------|---------|
| `2026-05-12-signal-id-unification-review.json` | Signal ID Unification | NEEDS_REVISION | signal_results 迁移 ID 重算未定义日期规范化；3-key/4-key 未调用 `_norm_date()`；`fill()` 新旧 ID 双查逻辑不完整 |

---

## 依赖关系图

```
Signal ID Unification (A-3) ←── 基础设施，无前置依赖
├── Signal ID Phases 3-4        ←── 依赖 Unification Phase 1-2 完成
├── Signal Lifecycle            ←── 依赖 Unification（ID 统一后才能定义状态迁移）
├── T0 Enhancement              ←── 依赖 Unification（信号追踪需要统一 ID）
└── Tracking Fusion Breakdown   ←── 依赖 Unification + Fusion Integration

Fusion Activation               ←── 独立，将 FUSION_LOG_ONLY 改为 false
└── Fusion Integration          ←── 依赖 Activation（融合层生效后才能接入 build_signal）
    └── Pool Fusion             ←── 依赖 Fusion Integration（融合数据可用后才能存入池）

Portfolio Allocation + Market Filter ←── 独立，无前置依赖
```

核心路径：Signal ID Unification 是最多计划的前置依赖（4 个下游），应优先实施。Fusion 系列形成 Activation → Integration → Pool 的线性链。Portfolio Allocation 完全独立，可并行推进。
