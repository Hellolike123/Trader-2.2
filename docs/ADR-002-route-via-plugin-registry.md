# ADR-002: `build_report` 改走 `PluginRegistry`（中线不丢、日线等价）

- **Status**: Deferred（待插件接口扩展 + 等价性验证；**本次未实现**，避免静默回归）
- **Branch**: `refactor/trader-architecture`
- **前置**: ADR-001（真库）、ADR-003（逻辑已进 `report_builder.py`）

---

## Context（问题动机）

架构评审指出 `build_report` 绕过组合点：它直接 `pool.submit(chanlun_strategy, ...)` 调策略函数，
没走 `PluginRegistry.analyze_all()`，导致"可组合"被架空。ADR-002 的目标：让 `build_report`
统一经 `PluginRegistry` 组合分析，使插件成为真实组合点。

## 实测发现的两个致命陷阱（为什么不能盲做）

| # | 陷阱 | 后果 | golden 能否抓到 |
|---|------|------|----------------|
| 1 | `PluginRegistry.analyze_all(current, bars, change_pct, quote)` **只有日线，无中线概念**；插件也只注册 `chan/wyck/momentum`（日线） | 天真路由会**丢掉中线分析**（`chanlun_strategy_midline` / `wyckoff_strategy_midline`） | ✅ 能（golden 有 5 策略调用计数断言） |
| 2 | `ChanlunPlugin.analyze` 调 `chanlun_strategy(current, bars, change_pct, quote)` **不传 `weekly_bars`**；但 `build_report` 的日线调用**传 `weekly_bars`** | 路由后**日线 chan 结果静默漂移**（缺周线上下文） | ❌ **抓不到**（golden 仅对 `weighted_score` 做范围断言 `-1..1`，漂移后仍在区间内） |

陷阱 2 是真正危险的点：**golden 守门测试无法发现日线 chan 的等价性退化**，会变成无人察觉的静默回归。

## Decision（决策：推迟）

**本次不实现 ADR-002。** 理由：

1. 当前 golden 测试只能验证"形状 + 范围 + 中线 key 存在 + 5 策略被调用"，
   **无法验证日线 chan 结果逐字段等价**——而陷阱 2 恰恰落在 golden 的盲区。
2. 用户授权条款含"每个任务完成后需简要汇报、**遇到阻塞/无法验证需立即反馈**"。
   ADR-002 属于"无法在不引入静默回归风险的前提下安全验证"的任务，故按该条款停下、先文档化。

## 安全实现路径（待执行）

要做到**行为等价**的 ADR-002，必须先补插件接口，使 `analyze_all` 能 1:1 复刻 `build_report` 当前的 5 次调用：

1. **插件接口扩展**：`IndicatorPlugin.analyze` 增加 `weekly_bars` 关键字参数；
   `ChanlunPlugin`/`WyckoffPlugin`/`MomentumPlugin` 把 `weekly_bars` 透传给对应 `*_strategy`。
2. **中线插件**：注册 `chanlun_midline` / `wyckoff_midline` 插件（包装 `*_strategy_midline`），
   或给 `analyze_all` 增加 `midline=True` 分支，使其产出中线结果。
3. **`build_report` 改走 registry**：用 `registry.analyze_all(daily_bars, weekly_bars, current, change_pct, quote)`
   取回 `{chan_d, chan_mid, wyk_d, wyk_mid, mom}` 结果喂融合层，删掉直调策略函数。
4. **等价性验证（关键闸门）**：在 golden 测试中**增加"前后报告逐字段 diff"**——
   对比 ADR-002 前后 `fusion.weighted_score` / 各策略 `direction` / `confidence` / 中线 key 的**精确值**（而非范围）。
   只有逐字段一致（或差异 < 浮点 epsilon）才允许通过。

## Consequences（若执行）

- ✅ 插件成为真实组合点，新增指标走 `plugins/` 即被 `build_report` 自动纳入
- ✅ 消除 `build_report` 内联策略调用，符合"可组合"架构意图
- ⚠️ 需先扩展插件接口 + 加中线插件，工作量约 2–3h，且必须配逐字段等价验证

## 与 ADR-001/003 的关系

ADR-001（真库）+ ADR-003（逻辑进 `report_builder`）已为 ADR-002 铺好地基：
`build_report` 现在在 `trader_shared` 内、可独立测试。届时 ADR-002 的改动落在
`report_builder.py` 内，等价性验证可直接复用 `tests/test_build_report_golden.py` 扩展。
