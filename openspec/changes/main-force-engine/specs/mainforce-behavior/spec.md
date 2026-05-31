## ADDED Requirements

### Requirement: 主力行为五阶段识别
系统 SHALL 基于资金流向特征和价格/筹码数据，识别当前主力行为所处阶段：accumulation（吸筹）、testing（试盘）、markup（拉升）、distribution（派发）、markdown（砸盘）、unknown（无法判断）。

#### Scenario: 识别吸筹期
- **WHEN** 价格20日变化幅度 < ±5% 且 5日累计净流入 > 0 且 筹码集中度上升
- **THEN** 返回 stage = "accumulation"，confidence 根据条件满足程度在 0.4-0.8 之间

#### Scenario: 识别试盘期
- **WHEN** 单日涨幅 > 3% 且 当日主力净流入 > 500万 且 次日缩量回落超过涨幅50%
- **THEN** 返回 stage = "testing"，confidence = 0.5-0.7

#### Scenario: 识别拉升期
- **WHEN** 连续净流入天数 >= 3 且 5日累计净流入 > 1000万 且 volume_ratio > 1.3
- **THEN** 返回 stage = "markup"，confidence = 0.6-0.8

#### Scenario: 识别派发期
- **WHEN** 价格处于高位（position_ratio > 0.7）且 主力净流出或流入大幅萎缩 且 筹码松散化
- **THEN** 返回 stage = "distribution"，confidence = 0.5-0.7

#### Scenario: 识别砸盘期
- **WHEN** 连续净流出天数 >= 3 且 5日累计净流出 > 1000万 且 volume_ratio > 1.5
- **THEN** 返回 stage = "markdown"，confidence = 0.6-0.8

#### Scenario: 无法判断时返回unknown
- **WHEN** 资金流向数据不足（少于5日）或各条件均不满足
- **THEN** 返回 stage = "unknown"，confidence = 0.0

### Requirement: 主力行为信号列表
系统 SHALL 返回导致阶段判断的具体信号列表，用于展示和调试。

#### Scenario: 吸筹期包含具体信号
- **WHEN** 判断为吸筹期
- **THEN** signals 列表包含触发条件描述，如 "5日累计净流入+3200万"、"筹码集中度上升"、"价跌资入"

#### Scenario: 阶段判断为unknown时信号为空
- **WHEN** 判断为 unknown
- **THEN** signals 列表为空

### Requirement: 价资关系分析
系统 SHALL 比较价格变动方向与资金流向方向，输出价资关系描述。

#### Scenario: 价格下跌但资金净流入
- **WHEN** 近5日价格下跌且5日累计净流入 > 0
- **THEN** flow_price_relation = "价跌资入"

#### Scenario: 价格上涨但资金净流出
- **WHEN** 近5日价格上涨且5日累计净流出 > 0
- **THEN** flow_price_relation = "价涨资出"

#### Scenario: 价格横盘且资金净流入
- **WHEN** 近5日价格变化 < ±2% 且5日累计净流入 > 0
- **THEN** flow_price_relation = "价平资入"
