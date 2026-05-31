## Why

主力行为引擎（main-force-engine）实现中有 5 个 bug，其中 2 个严重：`fund_flow_data.py` 引入了 `requests` 外部依赖（项目全用 `urllib.request`），`main_force_output.py` 读取的 `daily_flow_5d` key 在 `main_force.py` 的 `_result()` 中不存在导致趋势符号和今日净流入永远为空。

## What Changes

**严重修复（2 个）**
- `fund_flow_data.py` — 将 `import requests` 改为 `urllib.request`（与项目其他地方一致）
- `main_force.py` — `_result()` 返回值增加 `daily_flow_5d` 字段

**中等修复（3 个）**
- `main_force.py:101-103` — `bars[-4]` 越界保护，改为 `len(bars) >= 4`
- `main_force.py:60` — 删除未使用的 `daily_5d` 变量
- `main_force.py:119` — 试盘期"次日资金回流"条件从 `daily_5d[-1] < 0` 改为 `> 0`

## Capabilities

### New Capabilities

（无，纯 bug 修复）

### Modified Capabilities

- `mainforce-behavior`: 修复五阶段识别引擎的数据传递和边界检查

## Impact

受影响文件：
- `02-共享模块-shared/trader_shared/fund_flow_data.py` — requests → urllib
- `02-共享模块-shared/trader_shared/main_force.py` — 返回值修复 + 边界检查
- 无新增文件，无 API 变更
