# 高阶防御与预警系统建设 (Advanced Trading Features)

基于系统当前成熟的四阶段模型与数据底座，本次实施将引入三大高阶实战功能：**浮盈动态保护伞**、**量能真空区预警**、以及**个股股性透视卡**。

## Proposed Changes

### 1. 浮盈阶梯动态保护伞 (Dynamic ATR Trailing Stop)
文件：`02-共享模块-shared/trader_shared/structure_core.py`

- **逻辑注入**：在 `build_structure_context` 中新增可选参数 `pnl_pct: float | None = None` (当前浮盈比例)。
- **动态乘数计算**：
  - 默认乘数：`3.0` (浮盈 `< 20%` 或亏损时，给足洗盘空间)
  - 利润保护一阶：当浮盈 `≥ 20%` 时，ATR 乘数缩紧至 `2.0`。
  - 利润保护二阶：当浮盈 `≥ 30%` 时，ATR 乘数缩紧至 `1.5`。
  - 利润保护三阶：当浮盈 `≥ 40%` 时，ATR 乘数极限收缩至 `1.2`。
- **输出**：计算出的 `trailing_stop`（移动止损价）将紧紧贴合最高价，随时保护利润底线。

### 2. 量能真空区跌破预警 (Volume Vacuum Warning)
文件：`01-功能包-packages/t0/scripts/final_t0.py` (动态盯盘) & `01-功能包-packages/trader/scripts/final_report.py` (静态分析)

- **逻辑注入**：计算日内的 `VolumeProfile`。
- **真空判定**：如果现价不仅跌破均线支撑，并且跌破了 **POC (筹码控制节点)**，同时下方价格区间对应的成交量不足 POC 处峰值的 10%。
- **动作**：
  - 在 T0 盯盘模块触发一次性强烈级别预警，输出 `⚠️ 警告：已跌破 POC 密集区，下方为量能真空，极易发生加速杀跌，建议立刻清仓！`。
  - 在 Trader 静态分析报告面板（如 `✨ 亮点与风险` 下）中同样加入此预警。

### 3. 个股历史“股性”透视卡 (Historical Win-Rate Dashboard)
文件：`01-功能包-packages/trader/scripts/final_report.py`

- **逻辑注入**：读取底座历史文件 `~/.trader/signal_results.jsonl`（包含该股历史交易的胜率、盈亏比等数据）。
- **展示优化**：在分析报告底部 `✨ 亮点与风险` 下方新增一栏 `📊 股性与历史回测`，直观打印出系统在该股历史上的交易成绩。
