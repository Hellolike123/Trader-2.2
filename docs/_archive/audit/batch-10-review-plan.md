# Batch-10 审查计划：支撑/压力位同类问题三 Agent 独立复核

> 时间：2026-07-08
> 触发：用户发现 📍买卖点中短/中/长线压力三档同值，另一 agent 误判为「算法设计问题非 bug」；上一轮已对称修复支撑+压力两侧。本次用「业务 agent + 代码 agent 并行 → 裁决 agent 出计划」独立复核。

## 一、核心结论

**支撑位确有与压力位同类的「序列用反」bug——且上一轮已经对称修复，当前无 P0 残留。**

代码 agent 实测当前 `structure_core.py` 证据：
- L899 `source = window_lows if find_support else window_highs`（方向正确）
- L935-939 支撑：`if min(window_lows) >= price * 0.97`（用最低价序列判跌破，正确）
- L940-944 阻力：`if max(window_highs) <= price * 1.03`（用最高价序列判突破，正确）
- 两分支对称，无反用；`test_structure_core.py` 30 passed（含专门验证阻力突破修复的 `test_broken_resistance_falls_back_to_window_high`）

## 二、三 Agent 发现

### 业务 Agent（业务合理性视角）
1. 有效支撑/压力应要求「≥2 次触碰 + 截至最新 K 未破」；当前只验证窗口内、不验证窗口外历史突破，且短档(10日)完全不参与验证。
2. 短档支撑/压力只取 trailing 极值、不走 touched 验证，与中长线口径不一致；fallback 到裸极值会重新引入「已破位仍当有效位」。
3. 用户症状（98.04 三档同压）是「单一价位被三档回声放大成三重确认」的虚假压力；支撑侧对称存在。
4. 渲染去重(1.5%)提升可读性，但**掩盖「三档同源」问题**——用户看到一行却以为是三周期共振，应标注来源而非静默合并（业务上信息丢失）。
5. 其他：有效位排序偏好「距现价最近」而非「触碰次数最多」；3% 突破阈值偏松。

### 代码 Agent（实现正确性视角）
- P0 序列用反 bug **当前代码已修复**（证据见上），无需改动。
- 渲染去重已存在且正确（L1977 支撑 / L1990 压力 / L2005 退出计划，容差 1.5%）。
- 测试 30 passed。
- 残留 P2（非 bug）：
  - `structure_core.py:900` `opposite = window_highs if find_support else window_lows` 已成**死代码**（突破判定已不引用），易误导维护者。
  - 缺少对称的「支撑被跌破→fallback 周期最低」回归测试。
  - 跨模块 `t0/scripts/price_point_engine.py:150` 另有一份独立 `find_key_levels`（签名不同），需确认是否含同款历史 bug。

### 裁决 Agent（综合 + 亲自核查）
- 亲自核查 `price_point_engine.py:150`：为**独立实现**，根本不含突破验证逻辑，故**无序列用反历史 bug**；但其「裸极值无条件入位」写法与业务 agent 指出的同款业务弱点一致（P2）。
- `opposite` 确为死代码（全仓 grep 仅 L900 定义 + L933 注释引用，无实际调用）。
- 去重掩盖三档同源、短档不验证、排序偏好、阈值偏松均为**业务设计改进建议(P2/P3)**，非 bug，需用户决策是否纳入范围。

## 三、分级行动计划

| 级别 | 标题 | 文件:函数(line) | 改动意图 | 验证 / 双装 |
|---|---|---|---|---|
| **P0** | 无真 bug | — | 已修复，勿重复劳动 | 仅回归 `pytest` 保绿 |
| **P2** | 删死代码 `opposite` | `structure_core.py:900` | 删除未被引用的 `opposite` 变量 | pytest；改共享模块→需打包双装 |
| **P2** | 补对称回归测试 | `tests/test_structure_core.py` | 新增「支撑已被跌破→fallback 周期最低」用例 | pytest 新增用例通过 |
| **P2** | t0 破位过滤 | `price_point_engine.py:150-217` | `add_level` 前加「已破位则降权/剔除」或复用 `structure_core.find_key_levels` | 加 t0 单测；改 t0→需打包双装 |
| **P2** | 渲染去重标注来源 | `run_analysis.py:1977/1990/2005` | 三周期命中同价位时标注「三线共振」而非静默合并 | 手动渲染核对 |
| **P3** | 排序偏好调优 | `choose_level` `price_point_engine.py:220` | 优先「触碰次数最多」而非「距现价最近」 | 单测 |
| **P3** | 突破阈值收紧 | `structure_core.py:935/941` 3% | 评估收紧至 1.5%~2% | 回归测试 |

## 四、建议执行顺序与提交策略

1. **P0 确认**：跑 `cd 02-共享模块-shared && python -m pytest tests/test_structure_core.py -q`，确认 30 passed 作为基线。
2. **P2 第一批（低风险整洁）**：删 `opposite`(L900) + 补对称支撑测试 → 单独 commit。
3. **P2 第二批（跨模块）**：`price_point_engine.py` 破位过滤 + `run_analysis.py` 同源性标注 → 单独 commit。触及共享模块与 t0，须 `pack && install` 双目录（`~/.workbuddy/skills/` + `~/.hermes/skills/`）同步。
4. **P3 调优**：排序/阈值作为独立 commit，便于回滚。
5. **提交策略**：每级独立 commit；涉及共享模块/t0 的改动必须双装并在说明注明；业务类改进项（去重标注、阈值）建议先与用户确认范围再落地。

## 五、待用户决策
- 是否执行 P2 第一批（删死代码 + 补测试）？风险极低，建议做。
- 是否将 P2/P3 业务改进项（破位过滤、去重标注、排序/阈值）纳入本次范围？这些会改变报告呈现口径，需你确认。
