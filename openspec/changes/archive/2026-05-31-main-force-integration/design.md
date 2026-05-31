## Context

主力引擎已实现（main_force.py 208 行 + main_force_output.py 97 行 + fund_flow_data.py 221 行），fusion_core.py 已有 `_apply_main_force_weights()` 和 `_MAIN_FORCE_WEIGHT_ADJUSTMENTS`，但 `run_analysis.py` 从未调用主力引擎。需要在分析流程中接入。

## Goals / Non-Goals

**Goals:**
- 在 `run_analysis.py` 的 `build_report()` 中接入主力引擎
- 将 `main_force_env` 传入 `merge_decisions()`
- 在报告输出中增加主力行为段落
- 在复盘输出中增加主力行为段落

**Non-Goals:**
- 不修改主力引擎逻辑（只接入）
- 不新增东方财富 API 的其他数据（只用资金流向）

## Decisions

### 1. 接入位置：build_report() 内部 vs 外部

**问题**：主力引擎应该在 `build_report()` 内部调用还是外部？

**决策**：在 `build_report()` 内部调用，与 chanlun/wyckoff/momentum 并行。

**理由**：
- 主力引擎依赖 bars 和 quote，与现有策略相同
- 并行执行可以减少总耗时
- 替代方案：在 `build_report()` 外部调用，但需要传递更多参数

### 2. 缓存策略：每次实时获取 vs 使用缓存

**问题**：`fetch_fund_flow()` 调用东方财富 API，是否每次都实时获取？

**决策**：使用 `cache_utils.fetch_fund_flow_cached()`，TTL 24 小时。

**理由**：
- 资金流向数据每天收盘后更新，24 小时 TTL 合理
- 减少 API 调用频率
- 替代方案：每次实时获取，但增加 API 负担

### 3. 错误处理：API 失败时的行为

**问题**：东方财富 API 失败时怎么办？

**决策**：`main_force_env` 设为 `"unknown"`，不影响其他分析。

**理由**：
- 主力引擎是辅助因子，不应阻断主分析流程
- `"unknown"` 在 `_apply_main_force_weights()` 中不触发任何调整

## Risks / Trade-offs

**风险 1**：东方财富 API 可能不稳定
→ 缓解：缓存 + 错误降级为 unknown

**风险 2**：新增 API 调用增加分析耗时
→ 缓解：并行执行 + 缓存，增量耗时 < 0.5s
