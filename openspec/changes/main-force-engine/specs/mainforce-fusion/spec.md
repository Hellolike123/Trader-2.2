## ADDED Requirements

### Requirement: 主力行为作为融合层环境因子
fusion_core.py 的 `merge_decisions()` SHALL 接受可选参数 `main_force_env`，其值为主力行为阶段字符串（"accumulation"/"testing"/"markup"/"distribution"/"markdown"/"unknown"）。

#### Scenario: 传入main_force_env参数
- **WHEN** 调用 `merge_decisions()` 时传入 main_force_env = "accumulation"
- **THEN** 融合层在计算权重时应用吸筹期的权重修正规则

#### Scenario: 不传入main_force_env时行为不变
- **WHEN** 调用 `merge_decisions()` 时不传入 main_force_env 或传入 None
- **THEN** 融合层行为与当前完全一致，无任何变化

### Requirement: 主力行为权重修正规则
系统 SHALL 根据 main_force_env 阶段对三路信号权重进行修正，修正幅度保守（±5%~15%），修正后重新归一化。

#### Scenario: 吸筹期权重修正
- **WHEN** main_force_env = "accumulation"
- **THEN** wyckoff 权重 +10%，momentum 权重 -10%，chan 不变；修正后归一化

#### Scenario: 拉升期权重修正
- **WHEN** main_force_env = "markup"
- **THEN** momentum 权重 +10%，chan 权重 -5%，wyckoff 不变；修正后归一化

#### Scenario: 派发期权重修正
- **WHEN** main_force_env = "distribution"
- **THEN** wyckoff 权重 +10%，chan 权重 -10%，momentum 权重 -5%；修正后归一化

#### Scenario: 砸盘期权重修正
- **WHEN** main_force_env = "markdown"
- **THEN** 三路权重均下调（chan -15%，wyckoff -10%，momentum -10%），整体偏向保守

#### Scenario: unknown阶段不修正
- **WHEN** main_force_env = "unknown"
- **THEN** 权重不修正，与无 main_force_env 时一致

### Requirement: 融合结果包含主力行为信息
merge_decisions() 的返回结果 SHALL 包含 main_force_env 字段，便于下游模块引用。

#### Scenario: 返回结果包含main_force_env
- **WHEN** 调用 merge_decisions() 并传入 main_force_env
- **THEN** 返回 dict 中包含 "main_force_env" 键，值为传入的阶段字符串

#### Scenario: 融合日志包含main_force_env
- **WHEN** FUSION_LOG_ONLY=true 且融合过程被记录
- **THEN** 日志输出中包含 main_force_env 字段
