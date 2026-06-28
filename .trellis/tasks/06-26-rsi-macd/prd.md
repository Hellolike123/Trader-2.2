# 增强支撑位模型：趋势线 + 布林带 + RSI/MACD 背离

## Goal

在 `structure_core.py` 的支撑位体系中新增三类信号源，使 `support_levels` 列表涵盖趋势线、布林下轨、RSI/MACD 底背离，提高支撑位覆盖度和可信度。

## Requirements

- 新增趋势线支撑：从缠论笔或日线摆动低点中找有效上升趋势线（≥2 低点连线，斜率向上，≥3 次触碰有效）
- 新增布林下轨支撑：基于 20 日收盘价 ± 2σ，下轨作为支撑候选
- 新增 RSI 底背离支撑：价格创更低低点但 RSI 未创新低 → 支撑信号
- 新增 MACD 底背离支撑：价格创更低低点但 MACD 柱未创新低 → 支撑信号
- 所有新信号源以 `{name, price, weight}` 格式追加到 `support_levels` 列表
- 权重策略：趋势线 0.85、布林下轨 0.80、RSI 背离 0.75、MACD 背离 0.75
- 只在 `build_structure_context()` 内实现，不新增外部依赖
- 所有新功能在数据不足时静默跳过（不抛异常）
- 下游消费者（report 输出、决策层）零改动

## Acceptance Criteria

- [ ] 趋势线：在 300 天数据 + 明显上升趋势的股票上能计算出趋势线价格
- [ ] 布林下轨：在所有有 20+ 日数据的股票上都能计算出
- [ ] RSI 背离：在有明显下跌 + 反弹的股票上能检测到底背离
- [ ] MACD 背离：同上
- [ ] 数据不足时（<20 bars）所有新信号跳过，不抛异常
- [ ] `support_levels` 列表长度增加，原有支撑位不受影响
- [ ] 现有 718 个测试全通过

## Definition of Done

- [ ] 代码变更完成，所有测试通过
- [ ] 用南网科技跑一次验证输出中支撑位包含新来源
- [ ] 不修改 `structure_core.py` 以外核心文件

## Technical Approach

所有逻辑集中在 `structure_core.py` 的 `build_structure_context()` 函数内，在现有 `support_levels` 扩展段追加 4 个新块：

### 趋势线

```
1. 从 bars 提取 60 天内摆动低点（n日最低价 + 左右各 2 根更低）
2. 取最近 2 个上升的摆动低点，计算斜率
3. 斜率 > 0 且投影到今日的价格低于现价 → 趋势线支撑
4. 检查该趋势线在过去是否被至少触碰过 3 次（价格最低价 ≤ 趋势线价 × 1.02）
5. 通过则纳入 support_levels
```

### 布林下轨

```
1. 取最近 20 日收盘价
2. 计算 SMA(20) 和标准差 σ
3. lower = SMA(20) - 2 × σ
4. close < lower 时作为阻力线处理（反之作为支撑）
```

### RSI 底背离

```
1. 取最近 60 日收盘价计算 RSI(14)
2. 找最近 2 个价格摆动低点（窗口 5 天最低价）
3. 找对应位置的 RSI 值
4. 如果 price_low1 > price_low2 且 rsi_low1 < rsi_low2 → 底背离
5. 用第二个摆动低点的 RSI 差值线性映射到价格修正
```

### MACD 底背离

```
1. 计算 EMA12 - EMA26 作为 MACD 柱
2. 同样比较最近 2 个价格摆动低点的 MACD 柱值
3. price_low1 > price_low2 且 macd_low1 < macd_low2 → 底背离
4. 背离强度 = min(现价, 前低) 作为支撑参考价
```

## Out of Scope

- 顶背离检测（阻力位增强不是本次目标）
- 趋势线用于阻力位
- 布林上轨辅助压力位
- 修改现有支撑位权重
- 修改 fusion_core、decision_core 等消费模块
- 新增配置文件选项

## Technical Notes

- 当前 `build_structure_context()` 在 `structure_core.py:341`，已有 support_levels 构建段在 L353-362
- 现有 choose_level 逻辑按 weight 排序选最优，新信号 weight 已设合理值
- 缠论笔数据在 `chan_result` 参数中传入，可通过 `chan_result.get("bi_list")` 获取
- RSI 计算在 `momentum_core.py` 中已有 `calc_rsi()` 函数
- 布林带需自实现（无现有函数），约 5 行
- MACD 计算需自实现 EMA（或复用 expma），约 10 行
- 所有新函数加 `_trendline_support`, `_bollinger_support`, `_rsi_divergence_support`, `_macd_divergence_support` 前缀
