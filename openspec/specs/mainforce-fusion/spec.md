## ADDED Requirements

### Requirement: Main force engine integrated into build_report

`run_analysis.py` 的 `build_report()` MUST 调用主力引擎并将 `main_force_env` 传入 `merge_decisions()`。

#### Scenario: Normal stock with fund flow data available
- **WHEN** 分析一只正常交易的股票，东方财富 API 可用
- **THEN** `merge_decisions()` 的 `main_force_env` 参数 SHALL 为 `"accumulation"` / `"testing"` / `"markup"` / `"distribution"` / `"markdown"` 之一

#### Scenario: API failure
- **WHEN** 东方财富 API 不可用或返回空数据
- **THEN** `main_force_env` SHALL 为 `"unknown"`，不影响其他分析

#### Scenario: Fund flow in report output
- **WHEN** 分析完成，生成报告
- **THEN** 报告 SHALL 包含主力行为段落（阶段、置信度、资金趋势、价资关系）

### Requirement: Main force section in review output

复盘输出 MUST 包含主力行为段落。

#### Scenario: Review with fund flow data
- **WHEN** 对一只股票进行盘后复盘
- **THEN** 复盘输出 SHALL 包含 `format_main_force_section()` 生成的段落

### Requirement: Main force weight adjustment active

`_apply_main_force_weights()` MUST 在有主力阶段数据时被调用。

#### Scenario: Accumulation stage weight adjustment
- **WHEN** 主力阶段为 "accumulation"
- **THEN** 权重 SHALL 增加 wyckoff +10%，减少 momentum -10%

#### Scenario: Markdown stage weight adjustment
- **WHEN** 主力阶段为 "markdown"
- **THEN** 权重 SHALL 减少 chan -15%，wyckoff -10%，momentum -10%
