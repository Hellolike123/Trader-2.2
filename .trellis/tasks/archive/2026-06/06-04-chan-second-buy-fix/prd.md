# 修复缠论二类买点误报问题

## 背景

南网科技从60跌到51，连续下跌，但系统仍标记"二类买"并给出 direction=1（看涨）。实际是下跌中继，不应算买点。

## 根因分析

问题出现在两个文件：

### 文件1：chan_core.py 第284-303行

当前代码：只要 `len(strokes) >= 3` 且 `low_b > low_a` 就标记二类买，没有任何前提条件检查。

### 文件2：fusion_core.py 第103-105行

当前代码：
```python
if bp_type == "二类买":
    return {"direction": 1, "confidence": 0.6,
            "reason": "缠论二类买 (低点抬高)", "raw_key": "chan"}
```

## 修复方案

### chan_core.py 修复

在 298 行的 `if low_b > low_a and low_b < up_high:` 判断前，先检查两个前提条件：

- **条件A**：前一笔下跌必须出现底背驰（macd_hist 从负变浅，参考同文件 260-276 行的一类买判定逻辑）
- **条件B**：当前趋势不能是持续下跌，检查最后3笔的MACD是否止跌（金叉或柱状线从负收窄）

具体改法：
1. `down_strokes[-2]` 对应的 MACD 柱状线是否比更早的底更深（底背驰信号）
2. 最近5根K线的MACD柱状线是否止跌（macd_hist 从负值开始收窄）

两个条件满足一个才标记二类买，否则不标记或降低 confidence

### fusion_core.py 修复

- confidence 从 0.6 降为 0.4-0.5，因为二类买是弱信号，需要其他理论确认

## 技术分析

### 当前代码结构

1. `detect_buy_points()` 函数接收 `macd_hist_current` 和 `macd_hist_prev` 参数
2. 一类买点检测使用了 MACD 柱状线判断（底背驰）
3. 二类买点检测完全没有使用 MACD 数据，只看价格

### MACD 数据可用性

- 调用方已经传入 `macd_hist_current` 和 `macd_hist_prev`
- 但二类买点检测需要更多历史 MACD 数据来判断趋势

## 决策记录

**方案选择**：方案2 - 在调用方预计算 MACD 趋势条件

**理由**：
- 调用方已有完整 bars 数据
- 与现有的一类买点逻辑风格一致
- 接口简洁，不改函数签名

**实现方式**：
- 在调用方计算 `macd_divergence_ok` 布尔值
- 传入 `detect_buy_points()` 函数
- 二类买点需同时满足：价格抬高 + MACD条件

**Confidence 策略**：
- 满足条件A（底背驰）：confidence = 0.5
- 只满足条件B（MACD止跌）：confidence = 0.4
- 两个条件都不满足：不标记二类买

## 验证标准

1. 跑 `python3 scripts/final_report.py --target 南网科技 --output json`，fusion 的 chan signal 应该变回 direction=0（中性）或 direction=1 但 confidence ≤ 0.4
2. stage_action 应保持"观望等待"，不应变为"可买入"
3. 确认不影响其他正常二买标的

## 改动范围

只改这两个文件，不动其他模块。

## 实现总结

### 已完成的修改

1. **chan_core.py**:
   - 新增 `_check_macd_for_2nd_buy()` 函数，检查MACD底背驰或止跌信号
   - 修改 `detect_buy_points()` 函数，增加 `macd_divergence_ok` 参数
   - 二类买点标记需同时满足：价格抬高 + MACD条件
   - 调用方自动计算MACD趋势条件

2. **fusion_core.py**:
   - 二类买点confidence从0.6降为0.4

3. **test_chan_core.py**:
   - 更新测试用例以反映新的逻辑

### 测试结果

- 所有chan_core测试通过（20/20）
- 所有trader测试通过（86/86）
