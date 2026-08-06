# Trader3.0 Batch-11 实施报告：支撑压力位改进（A–E，不含阈值收紧）

> 模式：理论派 + 工程派只读分析 → Arbitrator 落地（本次因 Arbitrator 子 agent 超时，由主 agent 直接接管执行）
> 日期：2026-07-08
> 范围：用户拍板「不做阈值收紧，其他都做」

## 改动总览

| 项 | 文件 | 内容 | 状态 |
|----|------|------|------|
| A 删死代码 | `02-共享模块-shared/trader_shared/structure_core.py` | 删 L900 `opposite` 死变量，更新 L933 过时注释 | ✅ 已改，Read 复核通过 |
| E 排序主键(structure) | 同上 `_find_level_with_touches` | 选择主键 `abs(price-source[-1])` → `(-touch_count, 距离)`，优先触碰次数最多 | ✅ 已改，Read 复核通过 |
| B 对称回归测试 | `02-共享模块-shared/tests/test_structure_core.py` | 新增 `test_broken_support_falls_back_to_window_low`（镜像阻力测试） | ✅ 已加，Read 复核通过 |
| C 破位过滤(t0) | `01-功能包-packages/t0/scripts/price_point_engine.py` | `find_key_levels` 末尾加 `_filter_broken` 闭包，剔除已跌破支撑/已突破阻力（BREAK_TOL=0.015） | ✅ 已改，Read 复核通过 |
| E 排序主键(t0) | 同上 `add_level` + `choose_level` | `add_level` 累积 `touches`（近价合并+1）；`choose_level` 排序键 `(distance,-weight)` → `(-touches, distance, -weight)` | ✅ 已改，Read 复核通过 |
| D 共振标注 | `01-功能包-packages/trader/scripts/run_analysis.py` | 支撑/压力循环去重时收集命中档位，≥2 档同价标【双线共振】/【三线共振】；exit 循环保持静默去重 | ✅ 已改，Read 复核通过 |

## 关键设计决策

### E-t0 排序键兼容性（重要）
原 `choose_level` 排序键 `(distance, -weight)` 是「距离优先、weight 仅平局打破」。若直接改成 `(-weight, ...)` 会改变现有行为（L282 契约测试可能失败）。
**最终键 `(-touches, distance, -weight)`**：`touches=0` 时退化为 `(0, distance, -weight)`，与原行为**完全等价**；仅当多周期近价合并产生 `touches>0` 时才优先选被共同指向的价位。现有 `test_t0_contract.py` 不受影响（已论证，待跑测确认）。

### C-t0 破位过滤落点
采用「末尾过滤」而非「改 21 处 add_level 调用」：在 `find_key_levels` 返回前对 `support`/`resistance` 列表整体过滤，再传给 `choose_level`。改动最小、不动 `add_level` 签名、不影响其他调用者。

### D 共振标注语义
- 共振只在**支撑循环内部 / 压力循环内部**各自聚合（短/中/长同类型）。
- exit_plan 循环保持原静默去重、不标共振（exit 是不同语义）。
- 三档全同 → 【三线共振】；两档同 → 【双线共振】。

## 验证计划（待 Bash 恢复后执行）

```bash
cd /Users/like/Documents/Opencode/Trader3.0
export PYTHONPATH="02-共享模块-shared:01-功能包-packages/trader/scripts:01-功能包-packages/t0/scripts"
PY=/Users/like/.workbuddy/binaries/python/envs/default/bin/python

# 1. 语法
$PY -m py_compile \
  02-共享模块-shared/trader_shared/structure_core.py \
  01-功能包-packages/trader/scripts/run_analysis.py \
  01-功能包-packages/t0/scripts/price_point_engine.py

# 2. 主回归（期望 30→31 passed，新增 B 项支撑测试）
$PY -m pytest 02-共享模块-shared/tests/test_structure_core.py -q

# 3. t0 契约测试（期望全绿，验证 E-t0 排序键兼容）
$PY -m pytest 01-功能包-packages/t0/tests/test_t0_contract.py -q

# 4. 融合集成
$PY -m pytest 01-功能包-packages/trader/tests/test_fusion_integration.py -q
```

## 当前状态

- ✅ 5 项代码改动全部落地，已逐段 Read 复核（语法/逻辑正确）。
- ⚠️ **测试未执行**：执行当日本轮 Bash/sandbox 工具持续返回解析错误（`command expected string, received undefined`），无法运行 pytest/py_compile。待环境恢复后补跑上述验证。
- ⏸️ 未 commit / 未 pack / 未双装（需测试全绿后再 commit，按双安装位 gotcha 后续 pack + 装 workbuddy/hermes）。
