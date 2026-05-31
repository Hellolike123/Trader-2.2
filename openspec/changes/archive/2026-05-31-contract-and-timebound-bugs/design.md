## Context

跨模块契约和时间边界审计发现 16 个问题。时间边界问题的根因是系统没有中国股市节假日日历，`is_trading_time()` 只查周末不查节假日。跨模块契约问题主要是降级安装时 fusion override 映射为空。

## Goals / Non-Goals

**Goals:**
- 新增中国股市节假日日历，修复节假日假告警
- 非交易时段数据标记为 stale，下游可感知
- current_price=0 时返回"数据不足"而非"风险回避"
- T0 monitor 收盘后进入长休眠
- 降级 T0 安装时 fusion override 正常工作

**Non-Goals:**
- 不改变现有分析逻辑
- 不新增功能（除了节假日日历）
- 不清理 structure_core 的未消费 key（低优先级，不影响功能）

## Decisions

### 1. 节假日日历：硬编码 vs 动态获取

**问题**：系统没有节假日日历，`is_trading_time()` 在节假日误判。

**决策**：硬编码 2025-2027 年已知节假日，存储为 set。

**理由**：
- 中国股市节假日每年由证监会提前公布，变化不大
- 硬编码零依赖，不需要网络请求
- 替代方案：调用第三方 API，但增加外部依赖和网络开销
- 每年底更新一次即可

### 2. data_freshness：新增字段 vs 修改 data_status

**问题**：非交易时段返回过期数据但 data_status 仍为 "full"。

**决策**：新增 `data_freshness` 字段（live/stale），不修改现有 `data_status`。

**理由**：
- `data_status` 已有完整语义（full/partial/degraded/failed），不应混入时间维度
- 新字段向后兼容，现有消费者不受影响
- 替代方案：扩展 data_status 增加 "stale_full" 等状态，但会破坏现有契约

### 3. current=0 处理：前置拦截 vs 修改状态映射

**问题**：current_price=0 时 status_layers 返回"风险回避"，语义错误。

**决策**：在 status_layers 入口增加 `if current <= 0` 前置检查，返回"数据不足"。

**理由**：
- 最小改动，在函数入口拦截
- "数据不足"是现有状态，语义正确
- 替代方案：修改所有下游状态映射，但改动范围过大

### 4. T0 monitor 收盘后行为：退出 vs 长休眠

**问题**：run_monitor() 收盘后持续空转。

**决策**：收盘后 sleep 到下一个交易时段（次日 9:25）。

**理由**：
- 保持进程存活，适合 cron/daemon 场景
- 不浪费 CPU 和网络
- 替代方案：直接退出，但需要外部调度器重启

## Risks / Trade-offs

**风险 1**：硬编码节假日需要每年更新
→ 缓解：config.py 中加注释提醒年底更新。如果漏更新，最坏情况是节假日多跑几轮空检查。

**风险 2**：data_freshness 新字段可能被忽略
→ 缓解：在关键路径（T0 monitor、market_env）主动检查此字段。

**风险 3**：current=0 前置检查可能拦截合法的极低价股
→ 缓解：A 股最低价格 > 1 元，current=0 只在停牌/盘前出现。
