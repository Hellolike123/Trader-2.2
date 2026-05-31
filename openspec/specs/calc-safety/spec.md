## ADDED Requirements

### Requirement: HMM state labels must match sorted order

HMM 状态检测器在按 mu 排序后，标签字典 MUST 与排序结果一致：index 0=Bull, index 1=Range, index 2=Bear。

#### Scenario: Bear market detection
- **WHEN** 大盘处于熊市（mu < 0），HMM 拟合后排序
- **THEN** `state_en` SHALL 返回 `"bear"` 而非 `"range"`

#### Scenario: Range market detection
- **WHEN** 大盘处于震荡（mu ≈ 0），HMM 拟合后排序
- **THEN** `state_en` SHALL 返回 `"range"` 而非 `"bear"`

### Requirement: Chanlun MACD must be written back to bars

缠论分析中 `_calc_macd(bars)` 的返回值 MUST 赋值回 bars 变量，确保后续的背驰检测和买点判定能读到 MACD 数据。

#### Scenario: MACD available for divergence detection
- **WHEN** 调用 `chanlun_analysis(bars)` 且 bars 中没有预计算的 `macd_histogram`
- **THEN** `detect_divergence(bars)` SHALL 能读到 `_calc_macd` 计算的 MACD 柱值

#### Scenario: MACD available for Type-1 buy point
- **WHEN** 调用 `chanlun_analysis(bars)` 且存在底背驰
- **THEN** `detect_buy_points` SHALL 能读到 `macd_hist_current` 和 `macd_hist_prev`，一买信号正常触发

### Requirement: Wilder smoothing formula correctness

ADX 计算中的 Wilder 平滑公式 MUST 使用标准形式：`new = (old * (period-1) + raw) / period`。

#### Scenario: TR smoothing with period=14
- **WHEN** `smooth_tr` 上一轮为 100，新 `tr[i]` 为 20，period=14
- **THEN** 新 `smooth_tr` SHALL 为 `(100 * 13 + 20) / 14 = 95.71`，而非 `100 - 100/14 + 20 = 112.86`

#### Scenario: ADX from DX uses running smoothed value
- **WHEN** 计算 ADX 时有前一 bar 的 ADX 值
- **THEN** 新 ADX SHALL 为 `(adx[i-1] * (period-1) + dx_val) / period`，而非基于固定 SMA 基准

### Requirement: ADX initial seed correctness

ADX 初始平滑值 MUST 从 `tr[1]` 到 `tr[period]` 计算，不包含 `tr[0]`（零初始化值）。

#### Scenario: Initial smoothed TR
- **WHEN** 计算 ADX 初始种子
- **THEN** `smooth_tr` SHALL 为 `sum(tr[1:period+1]) / period`，而非 `sum(tr[:period]) / period`

### Requirement: Wyckoff Spring threshold must be realistic

Spring 触发阈值 MUST 在支撑位下方 1-3%，收盘价 MUST 回到支撑位上方。

#### Scenario: Classic Spring detection
- **WHEN** 日内低点跌到支撑位下方 2%（如支撑=10.00，低点=9.80）
- **THEN** 系统 SHALL 检测到 Spring 信号（如果收盘价 >= 支撑位）

#### Scenario: Deep breakdown not Spring
- **WHEN** 日内低点跌到支撑位下方 8%（如支撑=10.00，低点=9.15）
- **THEN** 系统 SHALL 不触发 Spring（这是真跌破，不是假突破）

#### Scenario: Close must reclaim support
- **WHEN** 低点跌到支撑位下方 2%，但收盘价仍在支撑位下方
- **THEN** 系统 SHALL 不触发 Spring（收盘没有收回支撑）

### Requirement: Fusion weight allocation must match price position

融合层权重分配 MUST 与价格位置一致，高位不应触发低位权重，低位不应触发高位权重。

#### Scenario: Overbought weight at high price
- **WHEN** `pos_pct >= 0.7`（高位）且 `mom_score >= 80`（强动量）
- **THEN** 权重 SHALL 为动量偏斜（momentum=0.55）

#### Scenario: Breakout weight at high price with chan buy signal
- **WHEN** `pos_pct >= 0.7`（高位）且有缠论买点信号
- **THEN** 权重 SHALL 为动量偏斜（momentum=0.55），而非结构偏斜

#### Scenario: Breakout weight at low price
- **WHEN** `pos_pct <= 0.3`（低位）且有缠论买点信号
- **THEN** 权重 SHALL 为结构偏斜（chan=0.45, wyckoff=0.35）

### Requirement: Chanlun Type-2 buy uses local up-stroke high

二买判定中 `up_high` MUST 使用两个下跌笔之间的那个上涨笔的高点，而非所有上涨笔的全局最高价。

#### Scenario: Two consecutive down-strokes with local up-stroke
- **WHEN** 笔序列为 down(10) → up(18) → down(16)
- **THEN** `up_high` SHALL 为 18（局部上涨笔高点），而非 max(所有 up 笔)

### Requirement: RSI edge case when gains and losses are both zero

RSI 在 gains 和 losses 都为零时 MUST 返回 50（中性），而非 100。

#### Scenario: Flat market
- **WHEN** period 内所有价格变化恰好为 0
- **THEN** RSI SHALL 为 50.0

### Requirement: HMM minimum data threshold

HMM 拟合 MUST 至少需要 30 个观测值，少于 30 时 SHALL 返回默认参数。

#### Scenario: Insufficient data
- **WHEN** 输入只有 15 个收益率数据点
- **THEN** `fit()` SHALL 返回默认参数（不执行 EM），`detect_regime()` SHALL 返回 `"range"` with confidence 0.5
