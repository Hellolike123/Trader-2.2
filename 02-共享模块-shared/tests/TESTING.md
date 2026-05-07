# signal_tracker.py 测试文档

## 测试文件总览

| 文件 | 测试数 | Bug 覆盖 | 类型 |
|------|--------|----------|------|
| `test_signal_tracker.py` | 17 | BUG-001/002/003/004/005/006/009/010/011/012 + 性能优化 | 核心修复回归 |
| `test_signal_tracker_backfill.py` | 6 | BUG-007/067 | 已知缺陷 + 功能待实现 |
| `test_signal_tracker_trading_day.py` | 6 | BUG-008/013/066 | 交易日偏移 + 坏行可观测 |
| `test_signal_tracker_schema.py` | 4 | BUG-014/054 | schema_version 兼容性 |
| `test_signal_tracker_e2e.py` | 4 | BUG-067/068/069 | 端到端全链路 |

## 运行命令

```bash
# 单文件快速回归
python3 -m pytest 02-共享模块-shared/tests/test_signal_tracker.py -v

# 全量回归
python3 -m pytest 02-共享模块-shared/tests/ -q

# 包含 calibrator 的完整套件
python3 -m pytest 02-共享模块-shared/tests/ -q -k "signal_tracker or calibrator"

# E2E 专项（含 mock 网络请求）
python3 -m pytest 02-共享模块-shared/tests/test_signal_tracker_e2e.py -v
```

## 修复 Bug 测试覆盖矩阵

### P0 - 数据安全性

| Bug | 测试文件 | 测试方法 | 验证内容 |
|-----|---------|---------|----------|
| 001 | `test_signal_tracker.py` | `TestFillByTargetPreservesBadLines::test_preserves_bad_line` | 重写文件时不丢弃损坏行 |
| 001 | `test_signal_tracker.py` | `TestExplicitExceptHandling::test_fill_by_target_preserves_bad_line` | 同上，独立测试类 |
| 002 | `test_signal_tracker.py` 中通过源码验证 `tuple[str, str, str]` 去重key |
| 006 | `test_signal_tracker.py` | `TestAtomicWriteAndFsync::test_fill_by_target_uses_fsync_and_replace` | `os.fsync` + `os.replace` 被调用 |

### P1 - 稳定性/正确性

| Bug | 测试文件 | 测试方法 | 验证内容 |
|-----|---------|---------|----------|
| 003 | `test_signal_tracker.py` | `TestUpdateSubcommandExists::test_update_calls_check_recent` | update 子命令调用 `check_recent` |
| 005 | `test_signal_tracker.py` | `TestExplicitExceptHandling::test_compute_results_uses_explicit_valueerror` | `except ValueError` 替代裸 `except` |
| 006 | `test_signal_tracker.py` | `TestAtomicWriteAndFsync` | RESULT_PATH 写也使用 fsync+replace |
| 009 | `test_signal_tracker.py` | `TestExplicitExceptHandling::test_check_recent_uses_explicit_except` | `json.JSONDecodeError, ValueError` |
| 010 | `test_signal_tracker.py` | `TestNormalizeSymbol::*` (5 个) | 数值代码→.SH/.SZ 推断，已有后缀不改写 |
| 011 | `test_signal_tracker.py` | `TestSignalTypeDefault` | `signal_type` 默认空串不是 `"None"` |
| 012 | `test_signal_tracker.py` | `TestShowSingleSortByResultTime` | 按 `result_time` 排序而非行顺序 |

### P2 - 可观测性/兼容性

| Bug | 测试文件 | 测试方法 | 验证内容 |
|-----|---------|---------|----------|
| 007 | `test_signal_tracker_backfill.py` | `TestBackfillRequires::*` | 截止边界正确，backfill 待实现 |
| 008 | `test_signal_tracker_trading_day.py` | `TestTradingDayOffset::*` | 跨周末/长假 scan 逻辑 |
| 013 | `test_signal_tracker_trading_day.py` | `TestBadLineObservability::*` | 坏行静默跳过（已知行为），utf-8 编码 |
| 014 | `test_signal_tracker_schema.py` | `TestSchemaVersion::*` | 新记录含 `schema_version`，旧记录兼容读取 |
| 067 | `test_signal_tracker_e2e.py` | `TestCliExitCodes` | CLI exit code 待实现 |
| 068 | `test_signal_tracker_e2e.py` | `TestEndToEndPipeline::test_full_pipeline` | 全链路：信号→计算→结果→面板 |

### 性能优化

| 优化 | 测试方法 | 验证内容 |
|------|---------|----------|
| scan 循环复用 `sig_dt` 避免 42 次重复 `strptime` | `TestNoRepeatedStrptime::test_reuses_sig_dt` | `sig_dt + timedelta` 存在 |

## 已知尚未实现的功能（pending tests）

| Bug | 文件 | 说明 |
|-----|-----|------|
| 007 (backfill) | `test_signal_tracker_backfill.py` | `test_backfill_not_yet_implemented` 标记为已知限制 |
| 067 (CLI exit code) | `test_signal_tracker_e2e.py` | `test_no_exit_code_defined` 确认当前 always return 0 |

## 测试覆盖率统计

```
总计: 123 测试全部通过
├── signal_tracker 系列: 37 测试
│   ├── 核心修复回归: 17 测试
│   ├── backfill/cutoff: 6 测试
│   ├── 交易日偏移 + 坏行: 6 测试
│   ├── schema_version: 4 测试
│   └── E2E 全链路: 4 测试
├── 原有: 88 测试 (calibrator/chan/wyckoff/momentum/v2_infra)
└── 新增 __init__.py: 1 文件
```

## CI 建议

```yaml
# GitHub Actions 示例
- name: Run signal_tracker tests
  run: |
    cd 02-共享模块-shared
    python3 -m pytest tests/ -q --tb=short
    # E2E 专项
    python3 -m pytest tests/test_signal_tracker_e2e.py -v
```
