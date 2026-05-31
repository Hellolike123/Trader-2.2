## ADDED Requirements

### Requirement: safe_float extracts float from dict safely

`safe_float(d, key, default=0.0)` MUST 从 dict 中安全提取浮点值，None/缺失/类型错误时返回 default，合法 0.0 不被吞。

#### Scenario: Key exists with None value
- **WHEN** `d = {"confidence": None}`，调用 `safe_float(d, "confidence")`
- **THEN** SHALL 返回 `0.0`

#### Scenario: Key exists with 0.0 value
- **WHEN** `d = {"confidence": 0.0}`，调用 `safe_float(d, "confidence")`
- **THEN** SHALL 返回 `0.0`（不被 `or` 吞掉）

#### Scenario: Key exists with string value
- **WHEN** `d = {"price": "15.50"}`，调用 `safe_float(d, "price")`
- **THEN** SHALL 返回 `15.5`

#### Scenario: Key exists with non-numeric string
- **WHEN** `d = {"price": "N/A"}`，调用 `safe_float(d, "price")`
- **THEN** SHALL 返回 `0.0`

#### Scenario: Key missing
- **WHEN** `d = {}`，调用 `safe_float(d, "price")`
- **THEN** SHALL 返回 `0.0`

#### Scenario: Custom default
- **WHEN** `d = {"price": None}`，调用 `safe_float(d, "price", default=-1.0)`
- **THEN** SHALL 返回 `-1.0`

### Requirement: safe_dict extracts dict from dict safely

`safe_dict(d, key)` MUST 从 dict 中安全提取子 dict，None/缺失/非 dict 时返回 {}。

#### Scenario: Key exists with None value
- **WHEN** `d = {"buy": None}`，调用 `safe_dict(d, "buy")`
- **THEN** SHALL 返回 `{}`

#### Scenario: Key exists with dict value
- **WHEN** `d = {"buy": {"price": 10.0}}`，调用 `safe_dict(d, "buy")`
- **THEN** SHALL 返回 `{"price": 10.0}`

#### Scenario: Key missing
- **WHEN** `d = {}`，调用 `safe_dict(d, "buy")`
- **THEN** SHALL 返回 `{}`

### Requirement: safe_max returns None for empty sequences

`safe_max(iterable, default=None)` MUST 对空序列返回 default，不用哨兵值。

#### Scenario: Empty list
- **WHEN** 调用 `safe_max([])`
- **THEN** SHALL 返回 `None`

#### Scenario: Non-empty list
- **WHEN** 调用 `safe_max([3, 1, 2])`
- **THEN** SHALL 返回 `3`

#### Scenario: Empty dict keys
- **WHEN** `d = {}`，调用 `safe_max(d.keys())`
- **THEN** SHALL 返回 `None`

#### Scenario: Custom default
- **WHEN** 调用 `safe_max([], default=0)`
- **THEN** SHALL 返回 `0`

### Requirement: require_positive guards against zero/negative

`require_positive(value, name)` MUST 在 value ≤ 0 或 None 时返回 None，否则返回 float(value)。

#### Scenario: Zero value
- **WHEN** 调用 `require_positive(0, "price")`
- **THEN** SHALL 返回 `None`

#### Scenario: Positive value
- **WHEN** 调用 `require_positive(15.5, "price")`
- **THEN** SHALL 返回 `15.5`

#### Scenario: None value
- **WHEN** 调用 `require_positive(None, "price")`
- **THEN** SHALL 返回 `None`
