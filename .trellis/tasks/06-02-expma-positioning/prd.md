# 加减仓策略重构计划 (Position Strategy Remodel & Golden Bid Resonance)

本次更新旨在解决当前代码中“买入条件严苛/自相矛盾”的问题，将理论中的**四阶段模型**与最新的 **EXPMA 战法**深度结合，重构系统盘中/盘后的加减仓建议。同时引入高级的“黄金共振验证”。

## 发现的现状 (Background)
经审查，目前的加减仓动作直接来自 `_DECISION_MATRIX`，而矩阵的行、列依赖于“阶段 (Stage)”和“短期动能 (Momentum)”。
底层代码 `_detect_short_term_momentum` 仅使用普通 `ma5` 和 `ma10` 来打分，且未与 EXPMA(10/20) 绑定。此外，高级工具“斐波那契黄金挂单位 (Golden Bid)” 仅计算并未参与决策。

## Proposed Changes

### 1. 改造短期动能检测 (`_detect_short_term_momentum`)
文件：`02-共享模块-shared/trader_shared/stage_positioning.py`

将函数的入参扩展，引入 `expma10` 和 `expma20`。重写“走强/修复/震荡/转弱”的判定规则，使其完全基于 EXPMA(10/20) 的生命线法则：
- **走强 (Strong)**：现价站上 EXPMA(10) 且 EXPMA(10) > EXPMA(20)（多头排列，强势主升）。
- **修复 (Recovery)**：现价在 EXPMA(10) 与 EXPMA(20) 之间（回踩生命线，绝佳低吸/加仓点）。
- **震荡 (Ranging)**：现价跌破 EXPMA(20) 但距离不远，或者均线处于粘合状态。
- **转弱 (Weak)**：现价跌破 EXPMA(20) 且放量下跌（死叉破位）。

### 2. 重写决策矩阵 (`_DECISION_MATRIX`)
在矩阵中为每个阶段赋予正确的实战操盘指导，调整买点（加仓）和卖点（减仓）的平衡：

- **蓄势 (Accumulation)**
  - 走强 → ("低吸试盘", 20%)
  - 修复 → ("回调低吸", 15%)
  - 震荡/转弱 → ("观望等待", 0%)
- **主升 (Markup)**
  - 走强 → ("顺势加仓", 50%-70%)
  - 修复 → ("回踩加仓", 40%)
  - 震荡 → ("底仓持有", 20%)
  - 转弱 → ("跌破防线减仓", 20%)
- **派发 / 衰退**
  - 所有状态大多输出 ("减仓"/"清仓"/"空仓规避", 0%-20%)

### 3. 引入“黄金坑验证” (Golden Resonance Add)
文件：`01-功能包-packages/trader/scripts/run_analysis.py` 和 `02-共享模块-shared/trader_shared/stage_positioning.py`

- **逻辑注入**：修改 `assess_stage` 函数签名，接收 `fib_retrace` 字典（由 `build_structure_context` 计算得出）。在 `run_analysis.py` 等外层调用处，将 `levels.get("fib_retrace")` 传给 `assess_stage`。
- **判断逻辑**：在得出基础的 `action` 建议（例如“回踩加仓” 40%）后，增加一步拦截判断。
  - 如果 `fib_retrace` 中的 `golden_bid` 不为空，且当前的 **EXPMA(10) 或 EXPMA(20)** 的价格与 `golden_bid` 价位非常接近（例如误差在 $\pm 2\%$ 甚至 $\pm 1.5\%$ 以内），这说明均线支撑与缠论黄金分割点发生重合，形成强力共振。
  - 此时，将输出动作 `action` 动态升级为 **"🌟黄金共振加仓"**，并且将最大建议仓位强行拔高至 **80%**。

### 4. 清理冗余的遗留代码
移除从未被外部调用的遗留函数 `check_position_actions`，保持 `stage_positioning.py` 代码纯净。
