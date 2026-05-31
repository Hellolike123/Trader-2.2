## Why

5 个核心模块零测试覆盖：`stage_positioning.py`（856 行，四阶段定位模型）、`decision_core.py`（状态判定）、`structure_core.py`（结构分析）、`candidate_core.py`（re-export 存根）、`rule_engine.py`（规则引擎）。这些模块被三个 skill（trader/t0/review）共同依赖，任何回归都会影响全链路。

## What Changes

为以下模块编写单元测试：

**P0：stage_positioning.py（856 行，零覆盖）**
- `_assess_volume_price()` — 量价关系判定
- `_detect_major_stage()` — 大阶段判定（蓄势/主升/派发/衰退）
- `_detect_short_term_momentum()` — 短期动能（走强/修复/震荡/转弱）
- `assess_stage()` — 主入口
- `compute_position_with_env()` — 仓位计算
- `compute_stop_losses()` — 止损计算

**P0：decision_core.py（核心判定逻辑）**
- `status_layers()` — 状态判定主函数
- `score_for()` — 评分计算
- `atr_volatility_level()` — ATR 波动率分级

**P1：structure_core.py（结构分析）**
- `build_structure_context()` — 结构上下文构建
- `moving_average()` — 均线计算
- `choose_level()` — 关键价位选择

## Capabilities

### New Capabilities

- `stage-positioning-tests`: 四阶段定位模型测试覆盖
- `decision-core-tests`: 决策核心测试覆盖
- `structure-core-tests`: 结构分析测试覆盖

### Modified Capabilities

（无）

## Impact

新增测试文件：
- `02-共享模块-shared/tests/test_stage_positioning.py`
- `02-共享模块-shared/tests/test_decision_core.py`（可能已有部分，需补充）
- `02-共享模块-shared/tests/test_structure_core.py`

无代码变更，仅新增测试。
