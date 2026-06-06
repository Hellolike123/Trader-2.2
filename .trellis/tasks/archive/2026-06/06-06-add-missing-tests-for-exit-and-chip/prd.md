# 为退出策略和筹码回填补测试

## Goal

为两个已实现但缺少专项测试的功能补单元测试，把归档的旧任务真正关掉。

## What I already know

### 退出策略（Exit Strategy）
- `decision_core.py:311-340` — `_fake_break` 假跌破检测（回看 PULLBACK_CONFIRM_DAYS=3 天是否曾有收盘 ≥ hard_stop）、`_near_stop` 分阶段退出（距止损 < 2×ATR → 冲高减仓）
- `structure_core.py:485-494` — `trailing_stop = max(highest_close × (1 - atr_pct × 3.0), hard_stop)`，含 PnL 浮盈动态缩放
- `config.py` — 6 个配置项：`ENABLE_TRAILING_STOP`, `TRAILING_STOP_ATR_MULTIPLE`, `PULLBACK_CONFIRM_DAYS`, `EXIT_PHASED_ENABLED`, `FUSION_OVERRIDE_ENABLED`, `FUSION_CONFIDENCE_THRESHOLD`
- 已有 `test_main_force.py:test_trailing_5_only` 但不直接测试 trailing_stop

### 筹码回填（Chip History Backfill）
- `chip_migration_monitor.py` 完整 333 行：`save_chip_snapshot()`、`backfill_history()`、`check_chip_migration()`
- 三角形非重：回填前 10 个交易日、原子写入、文件存在（9553 bytes）
- 无现有测试文件

## Test Patterns（已有参考）
- `/02-共享模块-shared/tests/` 使用 pytest，按模块组织 test_xxx.py
- 使用 `trader_shared.xxx` import，无 mock 框架依赖（大部分测试传构造数据）
- `test_decision_core.py` 直接用构造数据调用 `status_layers()`
- `test_structure_core.py` 已有，可直接追加
- `test_chip_distribution_bugs.py` 存在，可新建 `test_chip_migration_monitor.py`

## Open Questions

* 无——范围清晰，可直接实施

## Requirements

- [x] `test_decision_core.py` 追加 `TestFakeBreakAndPhasedExit` 测试类
  - `test_fake_break_detected`: current <= hard_stop 且近3日有收盘≥hard_stop → base/theory_status = "防守观察"
  - `test_fake_break_not_detected`: 跌破止损且近3日无收盘≥hard_stop → base_status="风险回避", theory_status="暂不碰"
  - `test_near_stop_triggers`: current > hard_stop 且距止损 < 2×ATR → "冲高减仓"
  - `test_near_stop_not_triggers`: 距止损远 → 正常状态判定
  - `test_exit_phased_disabled`: `EXIT_PHASED_ENABLED=False`（通过 monkeypatch）→ 不触发 _near_stop
- [x] `test_structure_core.py` 追加 `TestTrailingStop` 测试类
  - `test_trailing_stop_basic`: ATR trailing_stop 计算正确
  - `test_trailing_stop_not_below_hard_stop`: trailing_stop ≥ hard_stop
  - `test_trailing_stop_disabled`: `ENABLE_TRAILING_STOP=False` → trailing_stop = None
  - `test_trailing_stop_pnl_scaling`: 浮盈 20%/30%/40% → 对应倍数紧缩
- [x] `test_chip_migration_monitor.py` 新建文件
  - `test_save_and_load_history`: 保存快照后能正确读取
  - `test_backfill_history_skips_when_exists`: 已有昨日数据 → 跳过
  - `test_backfill_history_skips_when_insufficient_bars`: bars < 60 → 跳过
  - `test_check_migration_no_history`: 无历史数据 → has_history=False
  - `test_check_migration_stable`: 底部筹码稳定 → 无警告
  - `test_check_migration_warning`: 底部减少 > 40% → warning
  - `test_check_migration_critical`: 底部减少 > 50% → critical
  - `test_check_migration_support_loss`: 支撑完全消失 → migration_pct=100%

## Acceptance Criteria

- [ ] `python3 -m pytest 02-共享模块-shared/tests/test_decision_core.py -x -v --tb=short` 通过
- [ ] `python3 -m pytest 02-共享模块-shared/tests/test_structure_core.py -x -v --tb=short` 通过
- [ ] `python3 -m pytest 02-共享模块-shared/tests/test_chip_migration_monitor.py -x -v --tb=short` 通过
- [ ] `python3 -m pytest 02-共享模块-shared/tests/ -x --tb=short` 不因本次改动产生回归

## Out of Scope

- 集成测试（需要真实 K 线数据）
- 性能测试
- 信号追踪/结算相关测试（已有覆盖）
