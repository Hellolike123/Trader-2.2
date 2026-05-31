## Context

当前代码库中 None/空序列/类型转换的处理方式散落在各模块，写法不一致，导致 25+ 个同类 bug。时间感知逻辑也散落在 4 个文件中，节假日判断缺失。需要在架构层面提供统一的安全原语和时间感知层。

## Goals / Non-Goals

**Goals:**
- 提供 5 个安全原语函数，覆盖所有 None/空序列/类型转换场景
- 提供集中式时间感知层，统一节假日、交易时段、数据新鲜度判断
- 全局替换所有脆弱写法（约 25 处）
- 确保安全原语有完整测试覆盖

**Non-Goals:**
- 不重构现有模块架构
- 不改变外部 API
- 不修复数学公式错误（已在 calc-correctness-bugs 处理）
- 不引入新的外部依赖

## Decisions

### 1. safe_float 语义：None→default，0.0→0.0

**问题**：`float(dict.get("key", 0))` 值为 None 时崩溃，`to_float(x) or 0.0` 吞合法 0.0。

**决策**：`safe_float(d, key, default=0.0)` — key 存在但值为 None 时返回 default，值为 0.0 时返回 0.0。

**理由**：
- 区分"值缺失"和"值为零"，两者语义不同
- 替代方案：用 `if x is not None` 逐处检查，但代码冗长且容易遗漏

### 2. safe_dict 语义：None→{}，保证返回 dict

**问题**：`dict.get("key", {})` 值为 None 时返回 None 而非 {}，后续 `.get()` 崩溃。

**决策**：`safe_dict(d, key)` — key 存在但值为 None/非 dict 时返回 {}。

**理由**：
- 保证返回值一定是 dict，下游可以安全调用 `.get()`
- 替代方案：`d.get("key") or {}`，但会吞空 dict（虽然空 dict 和 None 对 .get() 行为一致）

### 3. safe_max 语义：空序列返回 None，不用哨兵值

**问题**：`max(keys, default=-1)` 空 dict 时返回 -1，后续 `dict.get(-1)` 返回空 dict，语义错误。

**决策**：`safe_max(iterable, default=None)` — 空序列返回 default（默认 None）。

**理由**：
- 调用方需要区分"最大值是 -1"和"序列为空"两种情况
- 替代方案：`max(keys) if keys else None`，但每个调用点都要写 if/else

### 4. trading_context 集中式 vs 分散式

**问题**：`is_trading_time()` 在 light_data.py 中只查周末不查节假日，market_env 和 monitor 各自手动检查。

**决策**：新建 `trading_context.py`，集中管理所有时间/状态判断，原 `is_trading_time()` 改为调用新模块。

**理由**：
- 单一职责，所有时间逻辑在一个地方
- 节假日日历更新只需改一处
- 替代方案：在各文件中各自增加节假日检查，但会导致多处重复维护

### 5. 节假日数据：硬编码 2025-2027 vs 动态获取

**问题**：中国股市节假日每年由证监会公布，没有公开 API。

**决策**：硬编码 2025-2027 年已知节假日，存储为 frozenset。

**理由**：
- 零外部依赖，不需要网络请求
- 每年底更新一次，维护成本低
- 替代方案：调用第三方 API（如 tushare），但增加外部依赖

## Risks / Trade-offs

**风险 1**：全局替换可能引入回归
→ 缓解：每个替换点有对应测试，替换后跑全量测试

**风险 2**：安全原语的性能开销（额外函数调用）
→ 缓解：函数体极简（3-5 行），开销可忽略

**风险 3**：硬编码节假日需要每年更新
→ 缓解：config.py 加注释提醒。如果漏更新，最坏情况是节假日多跑几轮空检查
