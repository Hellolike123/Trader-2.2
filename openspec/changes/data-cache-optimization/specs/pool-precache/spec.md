## ADDED Requirements

### Requirement: 选股盘后预缓存

系统 SHALL 在每日收盘后（15:00）自动为选股池 `~/.trader/pool.json` 中的所有活跃股票预抓取全量数据并写入文件缓存。

#### Scenario: 收盘后自动预缓存
- **WHEN** 每日 15:00 定时任务触发
- **THEN** 系统读取 `~/.trader/pool.json`，对每只状态非"淘汰"/"已退出"的股票执行：
  1. `load_market_snapshot()` → 写入日线缓存
  2. `_enrich_snapshot()` → 写入扩展数据缓存
  3. `market_env.assess()` → 写入大盘环境缓存

#### Scenario: 预缓存部分失败
- **WHEN** 预缓存过程中某只股票的 API 调用失败
- **THEN** 跳过该股票，继续处理下一只，不影响其他股票的缓存

#### Scenario: 选股池为空
- **WHEN** 选股池中没有活跃股票
- **THEN** 只预缓存大盘环境数据，不报错

### Requirement: 预缓存触发方式

系统 SHALL 支持通过现有 `t0_cron.py` 定时任务和手动命令两种方式触发预缓存。

#### Scenario: 定时任务触发
- **WHEN** `t0_cron.py` 的收盘后流程执行
- **THEN** 自动调用预缓存函数

#### Scenario: 手动触发
- **WHEN** 用户执行 `trader.py cache warm`
- **THEN** 立即为选股池所有活跃股票执行预缓存

### Requirement: 预缓存数据完整性

预缓存写入的数据 MUST 与实时抓取的数据完全一致，不得丢失或修改任何字段。

#### Scenario: 缓存数据与实时数据一致
- **WHEN** 预缓存完成后，用户执行 `trader script --target {code}`
- **THEN** 分析结果与直接实时抓取的结果在数值上一致（允许 1 秒内的价格波动差异）
