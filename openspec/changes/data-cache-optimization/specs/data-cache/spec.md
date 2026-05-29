## ADDED Requirements

### Requirement: 日线K线文件缓存

系统 SHALL 将日线K线数据写入文件缓存 `~/.trader/cache/daily/{code}.json`，盘中分析时读取缓存并追加当日实时 bar 合并为完整 K 线序列。

#### Scenario: 盘中分析读取日线缓存
- **WHEN** 盘中（9:30-15:00）执行单票分析，且缓存文件存在且未过期（TTL 24小时）
- **THEN** 系统读取缓存的历史日线，将当日实时 quote 合并为一根 bar 追加到末尾，返回完整的 K 线序列

#### Scenario: 缓存不存在时 fallback
- **WHEN** 缓存文件不存在或已过期
- **THEN** 系统自动 fallback 到实时抓取，行为与当前完全一致

#### Scenario: 缓存写入校验
- **WHEN** 系统尝试写入日线缓存
- **THEN** 必须校验：bar 数量 >= 200、每根 bar 的 close > 0、日期单调递增。校验失败时不写入缓存

### Requirement: 扩展数据文件缓存

系统 SHALL 将扩展数据（股东户数、机构EPS、解禁信息、题材归因）写入文件缓存 `~/.trader/cache/enrich/{code}.json`，TTL 12小时。

#### Scenario: 盘中读取扩展数据缓存
- **WHEN** 盘中执行单票分析，且扩展数据缓存存在且未过期
- **THEN** 系统直接读取缓存，跳过 4 路外部 API 调用

#### Scenario: 扩展数据缓存过期
- **WHEN** 扩展数据缓存已过期（超过 12 小时）
- **THEN** 系统重新抓取扩展数据并更新缓存

### Requirement: 大盘环境文件缓存

系统 SHALL 将大盘环境数据（指数行情、90日K线、HMM regime 结果）写入文件缓存 `~/.trader/cache/market_env.json`，盘中读取缓存并追加当日实时指数。

#### Scenario: 盘中读取大盘环境缓存
- **WHEN** 盘中执行分析，且大盘环境缓存存在且未过期
- **THEN** 系统读取缓存的指数历史数据，追加当日实时指数价格，重新计算 HMM regime（或使用缓存的 regime）

#### Scenario: 大盘环境缓存不存在
- **WHEN** 大盘环境缓存不存在或已过期
- **THEN** 系统 fallback 到实时抓取，行为与当前一致

### Requirement: 缓存写入原子性

系统 SHALL 使用 tmp+rename 模式写入缓存文件，确保多进程并发安全。

#### Scenario: 并发写入安全
- **WHEN** 两个进程同时写入同一缓存文件
- **THEN** 使用 tmp+rename 原子操作，不会产生文件损坏

#### Scenario: 写入过程中进程崩溃
- **WHEN** 缓存写入过程中进程异常终止
- **THEN** 原缓存文件不受影响（tmp 文件未 rename）

### Requirement: 手动清缓存命令

系统 SHALL 提供 `trader.py cache clear` 命令清空所有缓存。

#### Scenario: 清空全部缓存
- **WHEN** 用户执行 `trader.py cache clear`
- **THEN** 删除 `~/.trader/cache/` 下所有文件，下次分析重新抓取

#### Scenario: 清空指定类型缓存
- **WHEN** 用户执行 `trader.py cache clear --type daily`
- **THEN** 只删除 `~/.trader/cache/daily/` 下的文件
