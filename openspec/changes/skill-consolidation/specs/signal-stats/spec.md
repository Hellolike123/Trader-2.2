## ADDED Requirements

### Requirement: 信号统计分析

系统 SHALL 读取 signals.jsonl 历史数据，统计"信号说买→涨了吗？信号说卖→跌了吗？"的胜率。

#### Scenario: 统计最近 30 天信号
- **WHEN** 用户执行 `review script --tracking`
- **THEN** 输出最近 30 天的信号统计：总信号数、说买→涨的比例、说卖→跌的比例

#### Scenario: 按信号类型分组
- **WHEN** 有足够历史数据（>= 10 条信号）
- **THEN** 按 signal_type 分组显示各类型胜率

#### Scenario: 按个股分组
- **WHEN** 有足够历史数据
- **THEN** 按 symbol 分组显示各股票胜率

#### Scenario: 趋势对比
- **WHEN** 本月和上月都有数据
- **THEN** 显示"本月 xx% 上月 xx% ↑/↓ 在变好/变差"

#### Scenario: 数据不足
- **WHEN** 历史信号少于 10 条
- **THEN** 显示"数据不足，需要更多信号积累"
