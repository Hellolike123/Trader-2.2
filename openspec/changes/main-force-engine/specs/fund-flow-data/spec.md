## ADDED Requirements

### Requirement: 个股资金流向数据采集
系统 SHALL 通过东方财富HTTP API获取个股日线级资金流向数据，包含超大单净流入、大单净流入、中单净流入、小单净流入（单位：万元）。

#### Scenario: 成功获取资金流向数据
- **WHEN** 调用 `fetch_fund_flow(sec)` 传入有效股票代码
- **THEN** 返回近30日每日资金流向数据列表，每条记录包含 date、super_large_wan、large_wan、medium_wan、small_wan、net_flow_wan 字段

#### Scenario: API不可用时降级
- **WHEN** 东方财富API因网络问题无法访问
- **THEN** 返回空列表，不抛异常，不影响其他模块运行

### Requirement: 资金流向特征工程
系统 SHALL 基于原始资金流向数据计算衍生特征，包括累计净流入、连续流入/流出天数、净流入占比、价资关系。

#### Scenario: 计算5日和10日累计净流入
- **WHEN** 有至少10日资金流向数据
- **THEN** 返回 cum_flow_5d_wan（近5日累计）和 cum_flow_10d_wan（近10日累计），单位万元

#### Scenario: 计算连续流入天数
- **WHEN** 最近N日的 net_flow_wan 均大于0
- **THEN** 返回 consecutive_inflow_days = N

#### Scenario: 计算连续流出天数
- **WHEN** 最近N日的 net_flow_wan 均小于0
- **THEN** 返回 consecutive_outflow_days = N

#### Scenario: 判断价资关系
- **WHEN** 价格涨跌方向与资金流向方向不一致
- **THEN** 返回对应描述：价涨资出、价跌资入、价平资入、价平资出、价涨资入、价跌资出

### Requirement: 资金流向数据缓存
系统 SHALL 将资金流向数据缓存到 `~/.trader/cache/fund_flow/{股票代码}.json`，TTL 为 86400 秒（24小时）。

#### Scenario: 缓存命中时直接返回
- **WHEN** 缓存文件存在且未过期（st_mtime + TTL > 当前时间）
- **THEN** 直接读取缓存返回，不调用API

#### Scenario: 缓存未命中时调用API并写入
- **WHEN** 缓存文件不存在或已过期
- **THEN** 调用东方财富API获取数据，计算特征后写入缓存

#### Scenario: 与 warm_pool_cache 集成
- **WHEN** 执行 `trader.py cache warm`
- **THEN** 遍历选股池所有活跃股票，预缓存其资金流向数据

### Requirement: 资金流向缓存管理
系统 SHALL 支持通过现有缓存管理命令操作 fund_flow 缓存。

#### Scenario: 清理资金流向缓存
- **WHEN** 执行 `trader.py cache clear --type fund_flow`
- **THEN** 删除 `~/.trader/cache/fund_flow/` 下所有文件

#### Scenario: 清理全部缓存时包含资金流向
- **WHEN** 执行 `trader.py cache clear`
- **THEN** fund_flow 目录下的缓存文件也被清理
