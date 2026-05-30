## Why

基于 2026-05-30 讨论结果，需要将四阶段定位模型落地到仓位管理、选股池规则和入池流程中。当前利弗莫尔框架已废弃但代码仍在，选股池规则与四阶段脱节，入池需要两步操作。

## What Changes

- 清理利弗莫尔框架（livermore_rules.yml、modifier_rule_engine.py 中的利弗莫尔函数、portfolio_core.py 中的 livermore_tier）
- 实现四阶段仓位管理规则（蓄势0-30%、主升50-80%、派发0-30%、衰退0%）
- 硬规则：持仓亏损时禁止加仓
- 选股池命令精简为 3 种（list/plan/add+remove）
- 选股池输出显示阶段信息（大阶段+短期动能）
- 入池规则改为四阶段挂钩（阶段筛选→评分门槛→风控检查）
- 入池流程优化为一步操作（回复 1 入池）

## Capabilities

### New Capabilities
- `stage-position-sizing`: 四阶段仓位管理规则，持仓亏损禁止加仓

### Modified Capabilities
- `trader`: 选股池精简、阶段显示、入池规则挂钩、一步入池流程

## Impact

- 修改文件：portfolio_core.py、portfolio_run.py、final_pool.py、modifier_rule_engine.py
- 删除文件：livermore_rules.yml
- 向后兼容：选股池数据格式不变
