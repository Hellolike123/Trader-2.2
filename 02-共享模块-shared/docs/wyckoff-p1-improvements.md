# 威科夫模块 P1 改进文档

## 背景

对比 [WyckoffTradingAgent](https://github.com/YoungCan-Wang/WyckoffTradingAgent) 后，发现 3 个精度改进点。

## 改动

### 1. Spring 一字板过滤 (`_is_frozen_board`)

**问题**：A 股涨跌停制度下，一字板（开=高=低=收）几乎没有真实换手，"放量"和"收盘收回"在物理上不具备意义，不能作为有效 Spring 支撑测试。

**改法**：在 `_detect_spring` 入口检查当前 K 线和前一日 K 线是否为一字板（日振幅 ≤ 1% 且开收差 ≤ 1%），是则跳过。

**函数**：`_is_frozen_board(bar) -> bool`

### 2. 涨跌停板量能缩放 (`_board_vol_scale`)

**问题**：20% 涨跌停板块（创业板/科创板）的日常波动率更高，"放量"更容易被正常噪音触发。用同一套绝对阈值会导致这些板块假信号过多。

**改法**：按股票代码判断板块，20% 板块量能阈值放大 `sqrt(20/10) = 1.41` 倍。在 `_detect_spring` 的量能分级中使用缩放后的阈值。

**函数**：`_board_vol_scale(symbol) -> float`

**判断规则**：
- 300xxx / 301xxx（创业板）→ 1.41
- 688xxx / 689xxx（科创板）→ 1.41
- 其他 → 1.0

### 3. 交易区间检查 (`_is_trading_range`)

**问题**：Spring 应该发生在合理的交易区间（TR）内。如果整体振幅过大（如从 50 涨到 200），说明不是区间震荡，而是趋势行情，Spring 信号不可靠。

**改法**：计算近 20 日的 ATR 和整体振幅，要求振幅不超过 `max(ATR% × 4, 30%)`。

**函数**：`_is_trading_range(bars, lookback=20) -> bool`

## API 变更

- `wyckoff_analysis(bars, symbol="")` — 新增可选 `symbol` 参数
- `wyckoff_strategy(..., symbol="")` — 新增可选 `symbol` 参数

向后兼容：不传 symbol 时行为不变。

## 测试覆盖

新增 14 个测试用例：
- `TestIsFrozenBoard`: 4 个（一字板/正常/小范围/缺数据）
- `TestBoardVolScale`: 5 个（创业板/科创板/主板/北交所/无后缀）
- `TestIsTradingRange`: 3 个（正常/极端/短数据）
- `TestSpringWithFrozenBoard`: 2 个（一字板跳过/科创板量能缩放）

## 验证

```bash
python3 -m pytest 02-共享模块-shared/tests/test_wyckoff_core.py -v
```
