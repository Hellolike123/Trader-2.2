## Context

全量扫描 9 个核心模块发现 20 个数据消费 bug。当前代码库缺乏统一的数据安全模式，各模块对 None/falsy/空序列的处理方式不一致，导致运行时崩溃和逻辑错误。

## Goals / Non-Goals

**Goals:**
- 修复全部 4 个严重崩溃 bug
- 修复全部 6 个中等逻辑错误 bug
- 修复全部 10 个防御性缺陷
- 建立统一的数据安全模式，防止同类 bug 再次出现

**Non-Goals:**
- 不重构模块架构
- 不新增功能
- 不改变外部 API 接口
- 不优化性能（本次仅修复正确性）

## Decisions

### 1. None 值处理：`or 0` vs `if x is not None`

**问题**：`float(dict.get("key", 0))` 当 key 存在但值为 None 时崩溃。`or 0` 模式会把合法的 0.0 也当作 falsy。

**决策**：对数值字段使用 `float(dict.get("key") or 0)`，对字典字段使用 `dict.get("key") or {}`。

**理由**：
- 数值场景：0.0 是合法值但极少见（股票价格不可能为 0），`or 0` 的误伤风险可接受
- 字典场景：None 和 {} 语义不同，但下游 `.get()` 调用两者行为一致
- 替代方案：`if x is not None` 更精确但代码冗长，对 20 处修改成本过高

### 2. 空序列防御：提前检查 vs 默认值

**问题**：`max(keys, default=-1)` 空 dict 时返回 -1，后续 `dict.get(-1)` 返回空 dict，语义错误。

**决策**：统一使用 `dict.get(max(keys)) if keys else {}` 模式。

**理由**：
- 与 line 202 已有模式一致
- 替代方案：`max(keys, default=-1)` + 后续检查，但增加了认知负担

### 3. Volume Profile 参数传递：扩展 status_layers 签名 vs 独立函数

**问题**：`vp_result` 从未传入 `_check_theory_breakout`，VP 过滤是死代码。

**决策**：扩展 `status_layers()` 签名，增加 `vp_result=None` 参数，透传到 `_check_theory_breakout`。

**理由**：
- 最小改动，与现有函数签名模式一致
- 替代方案：在 `_check_theory_breakout` 内部重新获取 VP 数据，但会增加重复计算

### 4. 变量初始化：前置赋值 vs else 分支

**问题**：`market_env.py` 中 `current` 在 `price_part` 为空时未初始化。

**决策**：在 `if price_part:` 前加 `current = 0`。

**理由**：
- 最小改动，与后续 `if current == 0:` 逻辑兼容
- 替代方案：改为 `if/else` 结构，但需要重构整个解析块

## Risks / Trade-offs

**风险 1**：`or 0` 模式在极端边界（价格恰好为 0.0）会误判
→ 缓解：A 股价格不可能为 0.0，指数也不可能为 0.0，实际风险为零

**风险 2**：扩展 `status_layers()` 签名可能影响调用方
→ 缓解：新参数 `vp_result=None` 是可选的，不影响现有调用

**风险 3**：修复 `_FUSION_STATUS_MAP` 需要在 t0_candidate_core.py 中定义或导入
→ 缓解：定义空 dict 作为 fallback，与 decision_core.py 中的定义保持一致
