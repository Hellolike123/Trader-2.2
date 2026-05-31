## 1. stage_positioning.py 测试

- [x] 1.1 新建 `02-共享模块-shared/tests/test_stage_positioning.py`
- [x] 1.2 编写 `_assess_volume_price()` 测试 — 蓄势/主升/派发/衰退四种量价场景
- [x] 1.3 编写 `_detect_major_stage()` 测试 — 综合量价+MA+ATR 判定，含冲突场景
- [x] 1.4 编写 `_detect_short_term_momentum()` 测试 — 走强/修复/震荡/转弱四种场景
- [x] 1.5 编写 `assess_stage()` 测试 — 主入口，验证返回 dict 包含 major_stage + momentum + confidence
- [x] 1.6 编写 `compute_position_with_env()` 测试 — 阶段×大盘仓位上限，含亏损禁止加仓
- [x] 1.7 编写 `compute_stop_losses()` 测试 — 三层止损（技术/阶段/时间）

## 2. decision_core.py 测试

- [x] 2.1 检查 `02-共享模块-shared/tests/` 是否已有 test_decision_core.py，有则补充，无则新建
- [x] 2.2 编写 `status_layers()` 测试 — 暂不碰/低吸观察/冲高减仓/等转强/突破确认/数据不足
- [x] 2.3 编写 `score_for()` 测试 — 各状态对应的分数范围
- [x] 2.4 编写 `atr_volatility_level()` 测试 — 低/中/高波动率分级
- [x] 2.5 编写 `base_weight()` 测试 — 各波动率级别的仓位上限

## 3. structure_core.py 测试

- [x] 3.1 检查 `02-共享模块-shared/tests/` 是否已有 test_structure_core.py，有则补充，无则新建
- [x] 3.2 编写 `build_structure_context()` 测试 — 正常数据 + 数据不足场景
- [x] 3.3 编写 `moving_average()` 测试 — 充足数据 + 不足数据
- [x] 3.4 编写 `choose_level()` 测试 — 多个支撑/阻力位选择 + 空列表
- [x] 3.5 编写 `average_atr_pct()` 测试 — 正常 bars + 全零 bars

## 4. 验证

- [x] 4.1 跑全量测试确认无回归：`python3 -m pytest 02-共享模块-shared/tests/ -q`（570 passed）
- [x] 4.2 确认新增测试全部通过（48 个新测试全部通过）
