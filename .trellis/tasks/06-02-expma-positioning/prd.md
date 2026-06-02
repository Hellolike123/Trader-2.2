# 加减仓策略重构计划 (Position Strategy Remodel)

本次更新旨在解决当前代码中“买入条件严苛/自相矛盾”的问题，将理论中的**四阶段模型**与最新的 **EXPMA 战法**深度结合，重构系统盘中/盘后的加减仓建议。

## 发现的现状 (Background)
经审查，目前的加减仓动作直接来自 `_DECISION_MATRIX`，而矩阵的行、列依赖于“阶段 (Stage)”和“短期动能 (Momentum)”。
但底层代码 `_detect_short_term_momentum` 仅使用普通 `ma5` 和 `ma10` 来打分，且过去的条件设定过于严苛，未与你的 EXPMA(10/20) 核心战略绑定，导致系统天天喊“卖”不喊“买”。

## Proposed Changes

### 1. 改造短期动能检测 (`_detect_short_term_momentum`)
文件：`02-共享模块-shared/trader_shared/stage_positioning.py`

将函数的入参扩展，引入 `expma10` 和 `expma20`。重写“走强/修复/震荡/转弱”的判定规则，使其完全基于 EXPMA(10/20) 的生命线法则：
- **走强 (Strong)**：现价站上 EXPMA(10) 且 EXPMA(10) > EXPMA(20)（多头排列，强势主升）。
- **修复 (Recovery)**：现价在 EXPMA(10) 与 EXPMA(20) 之间（回踩生命线，绝佳低吸/加仓点）。
- **震荡 (Ranging)**：现价跌破 EXPMA(20) 但距离不远，或者均线处于粘合状态。
- **转弱 (Weak)**：现价跌破 EXPMA(20) 且放量下跌（死叉破位）。

### 2. 重写决策矩阵 (`_DECISION_MATRIX`)
文件：`02-共享模块-shared/trader_shared/stage_positioning.py`

在矩阵中为每个阶段赋予正确的实战操盘指导，调整买点（加仓）和卖点（减仓）的平衡：

- **蓄势 (Accumulation)**
  - 走强 → ("低吸试盘", 20%)
  - 修复 → ("回调低吸", 15%)
  - 震荡/转弱 → ("观望等待", 0%)
- **主升 (Markup)**
  - 走强 → ("顺势加仓", 50%-70%)
  - 修复 → ("回踩加仓", 40%)  *[EXPMA防线不破就是买点]*
  - 震荡 → ("底仓持有", 20%)
  - 转弱 → ("跌破防线减仓", 20%)
- **派发 (Distribution)**
  - 走强 → ("逢高减磅", 20%)
  - 修复/震荡 → ("逢反弹减仓", 10%)
  - 转弱 → ("清仓逃命", 0%)
- **衰退 (Decline)**
  - 所有状态均输出 ("空仓规避", 0%)

### 3. 清理冗余的遗留代码
文件：`02-共享模块-shared/trader_shared/stage_positioning.py`
移除从未被调用的遗留函数 `check_position_actions`，保持 `stage_positioning.py` 代码纯净。

## Open Questions

> [!IMPORTANT]
> **请确认你的预期最大仓位**
> 上面的方案中，主升浪“走强”最高建议仓位定在 50%-70%，派发期建议逐步降低到 10%-20%。这符合你的仓位管理习惯吗？是否有需要微调的具体比例？

## Verification Plan
修改完成后，我将对真实股票（例如：南网科技等）运行 `final_report.py` 测试，观察 `action` (动作) 和 `max_position_pct` (最高仓位) 在不同技术形态下的输出是否合理，不再“永远看空”。
