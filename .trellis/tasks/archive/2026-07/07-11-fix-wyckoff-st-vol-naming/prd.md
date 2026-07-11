# PRD — 修复 wyckoff ST 量能基准与 volume_price 变量命名

## 目标
修复代码审查发现的 2 个确定性缺陷（非设计选择）：

### 问题 1（真 bug）：`wyckoff_core.py:793-795` ST 检测量能基准分母错误
- **位置**：`_detect_st()` 内 `spring_avg_vol` 计算
- **现状**：分母硬编码 `max(WYCKOFF_SPRING_SUPPORT_LOOKBACK, 1)` = 10
- **问题**：当 `spring_idx < 10` 时，`bars[max(0, spring_idx - 10):spring_idx]` 实际不足 10 根 K 线，分母偏大 → 均量被低估 → 缩量阈值 `spring_avg_vol * 0.8` 同步变小 → 放大 ST 误触发风险
- **修复**：分母改为实际 slice 长度 `len(...)`

### 问题 2（代码质量）：`volume_price.py:133-149` `_calc_volume_ratio` 变量名与逻辑相反
- **现状**：循环里 `recent_sum` 实际累加的是**更老**的数据，`prev_sum` 累加的是**更新**的数据，但 return 用 `avg_prev / avg_recent`（即 newer/older，数学结果正确）
- **问题**：变量名与注释（"近N日均量/前N日均量"）完全反了，后续维护者极易误改导致量比反转
- **修复**：重命名 `recent_sum→older_sum`、`prev_sum→newer_sum`、`recent_count→older_count`、`prev_count→newer_count`，保持 return `newer/older` 不变；同步更新 docstring 说明变量顺序

## 验收标准
- `spring_avg_vol` 用实际 slice 长度归一化
- `_calc_volume_ratio` 计算结果不变（仅变量重命名，行为一致）
- 现有单测通过：`pytest 02-共享模块-shared/tests/test_wyckoff_core.py 02-共享模块-shared/tests/test_volume_price*.py`

## 范围外
- 不改 Compression 下降结构检查（确认为设计选择，非 bug）
- 不改 power_volume range（确认设计选择）
- 不改 MA20 上升检查 `ma_vals[-3]`（确认防毛刺设计）
- 不改 fund_flow_data.py 的 `close * volume` fallback（精度有限，不在本次）
