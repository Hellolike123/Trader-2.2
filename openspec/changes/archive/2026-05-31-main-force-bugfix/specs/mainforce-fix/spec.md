## ADDED Requirements

### Requirement: No external HTTP library dependency

`fund_flow_data.py` MUST 使用 `urllib.request` 而非 `requests`，与项目其他 HTTP 调用一致。

#### Scenario: Import without requests installed
- **WHEN** 环境中未安装 `requests` 库
- **THEN** `import fund_flow_data` SHALL 不抛出 ImportError

#### Scenario: API call succeeds
- **WHEN** 调用 `fetch_fund_flow("688248.SH")`
- **THEN** SHALL 返回与原 `requests.get()` 相同格式的数据

### Requirement: daily_flow_5d returned in result

`main_force.py` 的 `_result()` MUST 返回 `daily_flow_5d` 字段，使 `main_force_output.py` 能读到趋势数据。

#### Scenario: Output reads daily_flow_5d
- **WHEN** `detect_main_force_stage()` 返回结果传给 `format_main_force_section()`
- **THEN** 趋势符号 SHALL 显示实际的 ↑↓ 符号，今日净流入 SHALL 显示实际数值（非 0）

### Requirement: bars index bounds check

试盘期检测 MUST 在访问 `bars[-4]` 前检查 `len(bars) >= 4`。

#### Scenario: Only 3 bars available
- **WHEN** `bars` 只有 3 根 K 线
- **THEN** 试盘期检测 SHALL 跳过 `max_change` 计算，不抛出 IndexError

### Requirement: Correct flow direction in testing stage

试盘期"次日资金回流"条件 MUST 检查 `daily_flow_5d[-1] > 0`（流入），而非 `< 0`（流出）。

#### Scenario: Testing stage with next-day inflow
- **WHEN** 单日脉冲上涨后回落，次日资金净流入 > 0
- **THEN** SHALL 触发"次日资金回流"信号
