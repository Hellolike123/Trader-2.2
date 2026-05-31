## Why

全量扫描 9 个核心模块发现 20 个数据消费 bug，其中 4 个会导致运行时崩溃（NameError/TypeError/ZeroDivisionError/RuntimeError），6 个导致逻辑错误（数据污染/死代码/除零），10 个为防御性缺陷。这些 bug 涵盖变量未初始化、None 值未处理、空序列未防御、死代码参数缺失等模式，影响大盘环境评估、T0 盯盘、自校准、结构分析等核心链路。

## What Changes

修复全部 20 个 bug，按严重程度分三批：

**第一批：严重（崩溃）**
- `market_env.py:72` — `current` 变量未初始化，price_part 为空时 NameError
- `t0_candidate_core.py:171` — `_FUSION_STATUS_MAP` 未定义，standalone T0 安装时 NameError
- `structure_core.py:304/319/332` — `float(dict.get("confidence", 0))` 值为 None 时 TypeError
- `self_calibration.py:120` — 收益率计算除零风险

**第二批：中等（逻辑错误）**
- `decision_core.py:276-283` — `vp_result` 从未传入 `_check_theory_breakout`，VP 过滤是死代码
- `structure_core.py:364-365` — `choose_level()` 空列表时 RuntimeError
- `self_calibration.py:77` — `return_pct=None` 时跳过 `pnl_pct` 回退
- `monitor.py:393-394` — `plan.get("buy", {})` 值为 None 时后续 `.get()` 崩溃
- `market_env.py:222-223` — `if ma5` 而非 `if ma5 is not None`，MA=0.0 误判
- `decision_core.py:269` — MA=0.0 时 `or float("inf")` 逻辑错误

**第三批：低（防御性）**
- `market_env.py` — 4 个未使用的导入
- `price_point_engine.py:296` — `default=-1` 风格不一致
- `decision_core.py:448` — `str(None)` 变成 "None" 字符串
- `self_calibration.py:86/108/109` — None 日期/非数值/缺 key
- `structure_core.py:227-262` — regime 重复计算
- `big_order.py:162` / `structure_core.py:456` — to_float 重复调用

## Capabilities

### New Capabilities

- `data-safety`: 统一的数据安全模式规范 — 定义 `or 0` / `or {}` / `float(get())` 等数据消费模式的正确用法，防止 None/falsy/空序列导致的崩溃和逻辑错误

### Modified Capabilities

（无现有 spec 需修改）

## Impact

受影响文件：
- `02-共享模块-shared/scripts/market_env.py` — 大盘环境评估
- `02-共享模块-shared/scripts/self_calibration.py` — 离线参数校准
- `02-共享模块-shared/trader_shared/structure_core.py` — 结构分析核心
- `02-共享模块-shared/trader_shared/decision_core.py` — 决策核心
- `02-共享模块-shared/trader_shared/t0_candidate_core.py` — T0 候选逻辑
- `02-共享模块-shared/trader_shared/big_order.py` — 大单分析
- `01-功能包-packages/t0/scripts/monitor.py` — T0 盯盘
- `01-功能包-packages/t0/scripts/price_point_engine.py` — 价位引擎

无 API 变更，无依赖变更，无 breaking change。全部为内部防御性修复。
