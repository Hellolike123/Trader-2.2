## Context

主力行为引擎刚实现（commit c78ffd5），发现 5 个 bug。核心问题是数据流断裂：`main_force.py` 的 `_result()` 不返回 `daily_flow_5d`，但 `main_force_output.py` 依赖这个字段。另一个是外部依赖不一致。

## Goals / Non-Goals

**Goals:**
- 修复全部 5 个 bug
- 确保 `requests` 依赖被移除（用 `urllib.request` 替代）
- 确保 `main_force_output.py` 能正确读到趋势数据

**Non-Goals:**
- 不重构主力引擎逻辑
- 不新增功能

## Decisions

### 1. requests → urllib.request

**问题**：`fund_flow_data.py` 用 `requests.get()`，项目其他地方全用 `urllib.request`。

**决策**：改用 `urllib.request.urlopen()` + `json.loads()`。

**理由**：
- 与项目其他 HTTP 调用一致
- 不需要额外 pip 依赖
- `light_data.py` 已有 `HttpClient` 类可复用

### 2. daily_flow_5d 传递方式

**问题**：`_result()` 不返回 `daily_flow_5d`，`main_force_output.py` 读不到。

**决策**：在 `_result()` 返回值中增加 `daily_flow_5d` 字段。

**理由**：
- 最小改动
- 与 `cum_flow_5d_wan` 等其他字段风格一致

## Risks / Trade-offs

无显著风险，纯修复。
