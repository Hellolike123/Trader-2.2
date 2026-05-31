## ADDED Requirements

### Requirement: None-safe dict value extraction

系统在从 dict 提取数值时，SHALL 处理 key 存在但值为 None 的场景，避免 `float(None)` 崩溃。

#### Scenario: dict.get with None value and numeric default
- **WHEN** dict 包含 `{"confidence": None}`，代码执行 `float(dict.get("confidence", 0))`
- **THEN** 系统 SHALL 返回 `0.0` 而非抛出 TypeError

#### Scenario: dict.get with None value and dict default
- **WHEN** dict 包含 `{"buy": None}`，代码执行 `dict.get("buy", {}).get("tape")`
- **THEN** 系统 SHALL 返回空 dict 的 `.get()` 结果而非抛出 AttributeError

### Requirement: Empty sequence safe handling

系统在对可能为空的序列调用 max/min 时，SHALL 提前检查序列是否为空。

#### Scenario: max on empty dict keys
- **WHEN** `bb = {}`，代码执行 `bb.get(max(bb.keys()))`
- **THEN** 系统 SHALL 返回 `{}` 而非使用 `default=-1` 哨兵值

#### Scenario: choose_level on empty list
- **WHEN** `support_levels = []`，代码执行 `choose_level(support_levels, current, below=True)`
- **THEN** 系统 SHALL 返回安全默认值而非抛出 RuntimeError

### Requirement: Variable initialization before use

系统在条件分支中赋值的变量，SHALL 在分支前初始化，确保所有路径都有定义。

#### Scenario: current variable in market_env
- **WHEN** `price_part` 为空字符串，跳过 `if price_part:` 分支
- **THEN** 系统 SHALL 使用 `current = 0` 作为默认值，后续 fallback 到 `parts[3]`

#### Scenario: _FUSION_STATUS_MAP in t0_candidate_core
- **WHEN** `decision_core` 不可导入且 fusion override 开启
- **THEN** 系统 SHALL 使用本地定义的 `_FUSION_STATUS_MAP` 空 dict 而非抛出 NameError

### Requirement: Division by zero protection

系统在除法运算前，SHALL 检查除数是否为零。

#### Scenario: returns calculation in self_calibration
- **WHEN** `slice_closes[i-1]` 为 0.0
- **THEN** 系统 SHALL 跳过该收益率计算而非抛出 ZeroDivisionError

### Requirement: Dead code parameter plumbing

系统中声明了参数但从未传递的调用，SHALL 完成参数透传。

#### Scenario: vp_result passed to _check_theory_breakout
- **WHEN** `status_layers()` 被调用且有 Volume Profile 数据
- **THEN** 系统 SHALL 将 `vp_result` 透传到 `_check_theory_breakout()`，使 VP 突破过滤生效

### Requirement: Falsy-safe fallback patterns

系统在使用 `or` 运算符做 fallback 时，SHALL 区分"值缺失"和"值为合法零"。

#### Scenario: MA value of 0.0
- **WHEN** `ma5 = 0.0`（合法但极少见），代码执行 `ma5 if ma5 else None`
- **THEN** 系统 SHALL 返回 `0.0` 而非 `None`

#### Scenario: return_pct None with pnl_pct fallback
- **WHEN** record 包含 `{"return_pct": None, "pnl_pct": 5.0}`
- **THEN** 系统 SHALL 使用 `pnl_pct=5.0` 作为回退值而非返回 `0.0`

### Requirement: Unused import cleanup

系统中未使用的导入 SHALL 被移除，减少模块加载时间和依赖耦合。

#### Scenario: market_env unused imports
- **WHEN** `market_env.py` 导入了 `sys`, `Path`, `normalize_bars`, `trader_shared`
- **THEN** 系统 SHALL 移除这些未使用的导入

### Requirement: Consistent error handling patterns

系统中的错误处理模式 SHALL 保持一致，避免同一类问题使用不同写法。

#### Scenario: str(None) handling
- **WHEN** `item.get("status")` 返回 None，代码执行 `str(None)`
- **THEN** 系统 SHALL 返回空字符串 `""` 而非字符串 `"None"`
