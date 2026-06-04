# 修复缠论二类买点误报 + 承接存在条件过宽

## 背景
南网科技从60跌到51，连续下跌，但系统仍标记"二类买"并给出看涨方向。实际是下跌中继，不应算买点。

## 问题分析

### 问题1：`_check_macd_for_2nd_buy` 条件太松
**文件**：`02-共享模块-shared/trader_shared/chan_core.py` 第255-303行

当前函数已有 MACD 检查，但条件太松：
- 条件A：最近5根K线 MACD 柱状线最小值比前面5根高就行（哪怕只高一点点）
- 条件B：最后3根K线 MACD 柱状线从负值回升就行

**修复方案**：在 `return condition_a or condition_b` 之前，加趋势过滤：
- 取最后5根K线的收盘价
- 检查是否全部低于 MA5、MA10、MA20（空头排列）
- 如果是空头排列，返回 False（不触发二类买）

### 问题2：`承接存在` 条件太宽
**文件**：`02-共享模块-shared/trader_shared/decision_core.py` 第375行

当前代码：`if below_ma_count >= 1 and current > support:`
只要低于1条均线且价格高于支撑就标记"承接存在"。

**修复方案**：改为 `below_ma_count >= 3`，至少低于3条均线才算"承接存在"。

## 验收标准
1. 南网科技不再被标记为二类买（或 confidence 显著降低）
2. "承接存在" 只在真正有承接时触发
3. 所有现有测试通过
4. `python3 scripts/final_report.py --target 南网科技` 输出正确
