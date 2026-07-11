# 威科夫模块 P2/P3 改进文档

## 背景

参考 WyckoffTradingAgent 的 Layer 4 信号，新增 Compression（压缩蓄势）和 Trend Pullback（趋势回踩）两个检测器。

## P2: Compression 压缩蓄势

**含义**：价格振幅收窄 + 量能萎缩 = 蓄势待发（Wyckoff Phase B 末期 / Creek 前夜）

**检测条件**：
1. 近 20 日 ATR 分位数 < 20%（振幅压缩）
2. 近 20 日均量 / 参考均量（60日） < 0.6（量能枯竭）
3. 非下降结构（防止阴跌缩量误判）

**新增函数**：`_detect_compression(bars) -> dict`

**报告显示**：
```
威科夫：压缩蓄势·偏多（振幅收窄+量能枯竭，突破在即）
```

**分数权重**：`WYCKOFF_SCORE_COMPRESSION = +10`

**阶段分类**：触发时标记为 `accumulation_b`（压缩蓄力）

## P3: Trend Pullback 趋势回踩

**含义**：上升趋势中的回踩不破关键均线 = 买点（Wyckoff LPS 变体）

**检测条件**：
1. 近 10 日有回撤（5-20%）
2. 回落段缩量（量比 < 0.6）
3. 收盘站稳 MA20 附近（±2%）
4. MA20 仍在上升

**新增函数**：`_detect_trend_pullback(bars) -> dict`

**报告显示**：
```
威科夫：趋势回踩·偏多（回踩不破均线，趋势延续）
```

**分数权重**：`WYCKOFF_SCORE_TREND_PB = +8`

**阶段分类**：触发时增强 `accumulation_d` 的置信度（+0.08）

## 信号优先级链

```
Spring > SOS > UT > BC > SOW > AR > ST > LPS > Compression > TrendPullback > 背离 > 无信号
```

## API 变更

无新增参数。所有新信号通过 `wyckoff_analysis()` 返回值中的 `*_signal` / `*_reason` / `*_price` 字段暴露。

## 配置常量

| 常量 | 值 | 含义 |
|------|-----|------|
| `WYCKOFF_COMPRESSION_LOOKBACK` | 20 | 压缩检测回溯窗口 |
| `WYCKOFF_COMPRESSION_ATR_QUANTILE` | 0.20 | ATR 分位数阈值 |
| `WYCKOFF_COMPRESSION_VOL_RATIO` | 0.60 | 量能萎缩比例 |
| `WYCKOFF_COMPRESSION_VOL_REF_WINDOW` | 60 | 量能参考窗口 |
| `WYCKOFF_TREND_PB_LOOKBACK` | 10 | 回踩检测回溯窗口 |
| `WYCKOFF_TREND_PB_MIN_PULLBACK` | 5.0 | 最小回撤 % |
| `WYCKOFF_TREND_PB_MAX_PULLBACK` | 20.0 | 最大回撤 % |
| `WYCKOFF_TREND_PB_VOL_SHRINK` | 0.60 | 缩量比例 |
| `WYCKOFF_TREND_PB_MA_WINDOW` | 20 | 均线窗口 |
| `WYCKOFF_SCORE_COMPRESSION` | 10 | 分数权重 |
| `WYCKOFF_SCORE_TREND_PB` | 8 | 分数权重 |

## 测试覆盖

新增 9 个测试用例：
- `TestCompression`: 3 个（检测/高量不触发/短数据）
- `TestTrendPullback`: 3 个（检测/无回撤/短数据）
- `TestCompressionInAnalysis`: 1 个（完整管线输出）
- `TestFormatOnelineCompression`: 2 个（报告格式化）

## 验证

```bash
python3 -m pytest 02-共享模块-shared/tests/test_wyckoff_core.py -v
```
