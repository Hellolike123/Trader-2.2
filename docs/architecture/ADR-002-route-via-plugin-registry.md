# ADR-002: `build_report` 改走 `PluginRegistry`（中线不丢、日线等价）

- **Status**: Accepted（已在 `refactor/trader-architecture` 落地，等价性闸门全绿）
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

## Decision（执行决策）

ADR-002 按安全路径完整落地。原"推迟"决策在接口扩展+等价性闸门就位后撤销，
实际实现见下方"已落地实现"章节。

### 安全实现路径（执行步骤，与下文"已落地实现"对应）

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

## Consequences（执行后果）

- ✅ 插件成为真实组合点，新增指标走 `plugins/` 即被 `build_report` 自动纳入
- ✅ 消除 `build_report` 内联策略调用，符合"可组合"架构意图
- ✅ 等价性闸门（逐字段 diff）堵住了 golden 范围断言抓不到的日线 chan 等价性退化
- ⚠️ 中线插件未注册全局（最小爆炸半径），`fusion_core`/`final_pool`/`review` 的 `analyze_all` 调用拿不到中线——有意隔离，后续如有需要可单独注册全局 midline 插件

## 与 ADR-001/003 的关系

ADR-001（真库）+ ADR-003（逻辑进 `report_builder`）已为 ADR-002 铺好地基：
`build_report` 现在在 `trader_shared` 内、可独立测试。届时 ADR-002 的改动落在
`report_builder.py` 内，等价性验证可直接复用 `tests/test_build_report_golden.py` 扩展。

---

## 已落地实现（commit 见分支 `refactor/trader-architecture`）

按"安全实现路径"逐步落地，两个陷阱均已堵住：

1. **接口扩展**：`IndicatorPlugin.analyze` 增加 `weekly_bars` 关键字参数；
   `ChanlunPlugin`/`WyckoffPlugin`/`MomentumPlugin`/`SupertrendPlugin`/`VwapPlugin`
   全部接受 `weekly_bars`（未使用者忽略）。`PluginRegistry.analyze_all` 新增
   `weekly_bars` 参数并透传给所有声明接受它的插件（`_plugin_accepts_weekly_bars`
   守卫，向后兼容未升级插件）。
2. **中线分支（最小爆炸半径方案）**：`analyze_all` 增加 `midline: bool = False`
   参数，仅当 `midline=True` 时才计算 `chanlun_strategy_midline` /
   `wyckoff_strategy_midline` 并挂到 `chanlun_midline` / `wyckoff_midline` 键。
   **不注册全局 midline 插件**——避免 `fusion_core` / `final_pool` / `review` 的
   `analyze_all` 调用被波及（那些调用不传 `midline=True`，行为与过去完全一致）。
3. **`build_report` 改走 registry**：原 5 个 `pool.submit(策略函数, ...)` 直调替换为
   单次 `registry.analyze_all(current, bars, change_pct, quote, weekly_bars=weekly_bars,
   midline=True)`，按 key 取回 `{chanlun, chanlun_midline, wyckoff, wyckoff_midline,
   momentum}`，喂融合层。删除了直调的 5 个策略 import。
4. **双重 nudge 去重**：`analyze_all` 内 `MomentumPlugin` 已做 Supertrend「只确认不否决」
   微调，故 `build_report` 移除原重复的 `apply_supertrend_nudge`（否则动量被微调两次，
   `weighted_score` 静默漂移——正是陷阱 #2 的另一种形态）。

### 等价性闸门（关键）
新增 `tests/test_build_report_adr002_equivalence.py`：
- `scripts/_capture_adr002_baseline.py` 先捕获改前 `build_report` 的精确字段
  （`weighted_score` / `confidence` / `action` / `disagreement` / 两个 `midline` 字典）
  写入 `tests/fixtures/report_baseline.json`；
- 路由后再次运行并逐字段递归 diff（float 容差 1e-6）。只有完全一致（或浮点 epsilon
  内）才通过。**这恰好堵住 golden 范围断言抓不到的日线 chan 等价性退化。**

### 验证结果
- `tests/test_imports_smoke.py` + `tests/test_build_report_golden.py`（5 策略调用计数 +
  中线 key 存活）+ `tests/test_build_report_adr002_equivalence.py`：**全绿**，
  `weighted_score=0.034` 与基线一致。
- 既有 `test_arch_refactoring.py` / `test_indicator_enhancements.py`（含 `analyze_all`
  调用）**39 passed**，无回归。

### 未做 / 后续
- 部署副本（`~/.hermes` / `~/.workbuddy`）已随 promote 由 `pack_all.py` 从仓库统一再生
- `report_builder` 的 domain/presentation 再拆已由 ADR-003b 完成（见 `report_presentation.py`）
