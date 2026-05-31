## ADDED Requirements

### Requirement: Unified signal read path

`signal_store._read_store()` MUST 成为唯一的信号读取路径，`DataManager.load_signals()` MUST 委托给它。

#### Scenario: DataManager reads signals
- **WHEN** 调用 `DataManager.load_signals()`
- **THEN** MUST 内部调用 `signal_store._read_store()`，返回格式一致

#### Scenario: Bad line observability
- **WHEN** `signals.jsonl` 包含损坏行
- **THEN** 两个读取路径 MUST 都能通过 `signal_store.get_bad_line_stats()` 获取坏行计数和原因

### Requirement: Signal file rotation

`signals.jsonl` 超过 10MB 时 MUST 自动归档。

#### Scenario: File exceeds 10MB on append
- **WHEN** `append_signal()` 检测到 `signals.jsonl` 文件大小 > 10MB
- **THEN** MUST 将当前文件 rename 为 `signals-archive-YYYYQ#.jsonl`（按当前季度），然后创建新文件

#### Scenario: Archive file already exists
- **WHEN** 同一季度多次触发归档
- **THEN** MUST 追加到已有的 `signals-archive-YYYYQ#.jsonl`（不覆盖）

#### Scenario: Normal operation under 10MB
- **WHEN** `signals.jsonl` 文件大小 < 10MB
- **THEN** 行为不变，直接追加

### Requirement: Bad line diagnostics

信号读取 MUST 提供统一的坏行诊断接口。

#### Scenario: Corrupted line in signals.jsonl
- **WHEN** 文件第 42 行包含无效 JSON
- **THEN** `signal_store.get_bad_line_stats()` MUST 返回 `{"count": 1, "last_line": 42, "last_reason": "Expecting value: line 1 column 1", "last_path": "~/.trader/signals.jsonl"}`

#### Scenario: Multiple bad lines
- **WHEN** 文件有 3 个坏行
- **THEN** `count` MUST 为 3，`last_line` / `last_reason` 记录最后一次
