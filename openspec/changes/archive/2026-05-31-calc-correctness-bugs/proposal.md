## Why

计算模块存在 19 个数学正确性 bug，其中 4 个严重错误导致整个分析链路输出错误结果。HMM 大势检测器 Bear/Range 标签互换导致所有下游参数缩放反向；缠论 MACD 返回值被丢弃导致背驰检测和一买信号变成死代码；T0 的 ADX Wilder 平滑公式写错导致趋势强度完全失真。这些 bug 不是边缘场景，而是影响每一笔分析的核心数学错误。

## What Changes

修复全部 19 个计算正确性 bug，按严重程度分三批：

**第一批：严重（数学错误，影响所有决策）**
- `hmm_regime.py:24-25` — Bear/Range 标签互换，排序后 index 1=Range 但标签写成 Bear
- `chan_core.py:375` — `_calc_macd(bars)` 返回值被丢弃，MACD 从未写回 bars
- `indicators.py:357-359` — ADX Wilder 平滑公式 `smooth - smooth/n + raw` 应为 `(smooth*(n-1) + raw)/n`
- `indicators.py:370-378` — ADX 从 DX 计算时用固定 SMA 基准而非递推平滑

**第二批：中等（逻辑错误，影响部分场景）**
- `wyckoff_core.py:47` — Spring 阈值支撑位下方 8%，经典 Wyckoff 只需 1-3%
- `wyckoff_core.py:49` — Spring 收盘价不需要回到支撑上方，应该要求
- `momentum_core.py:105-107` — ADX 初始种子 off-by-one，包含 tr[0]=0
- `fusion_core.py:355` — 动量 65 分触发超买权重分配
- `fusion_core.py:354` — 缠论买点信号绕过 pos_pct 位置检查
- `chan_core.py:286-292` — 二买用全局最高价而非局部上涨笔高点
- `chan_core.py:268-276` — 一买只比两根 MACD 柱而非段面积
- `wyckoff_core.py:79-82` — Upthrust 回收阈值太远（阻力下方 2%）
- `hmm_regime.py:103-137` — 收敛检查 off-by-one

**第三批：低（边缘场景/设计选择）**
- `momentum_core.py:34` — RSI gains=losses=0 时返回 100 而非 50
- `hmm_regime.py:179` — 最少 10 个观测拟合 HMM，应为 30+
- `fusion_core.py:360` — 文档说 80% momentum at high，实际 55%
- `chan_core.py:225-252` — 中枢用三笔交集，比标准缠论更严格
- `wyckoff_core.py:108-115` — 量价背离用单根最大量柱，易被异常值干扰
- `volume_profile.py:87-92` — 量能均分到重叠 bin 而非按价格比例

## Capabilities

### New Capabilities

- `calc-safety`: 统一的计算正确性规范 — 定义 Wilder 平滑、HMM 状态标签、缠论 MACD 透传等核心数学模式的正确实现方式

### Modified Capabilities

（无现有 spec 需修改）

## Impact

受影响文件：
- `02-共享模块-shared/trader_shared/hmm_regime.py` — HMM 大势检测（影响全局）
- `02-共享模块-shared/trader_shared/chan_core.py` — 缠论分析（影响 trader + review）
- `01-功能包-packages/t0/scripts/indicators.py` — T0 技术指标（影响 t0）
- `02-共享模块-shared/trader_shared/momentum_core.py` — 动量分析（影响 trader + review）
- `02-共享模块-shared/trader_shared/wyckoff_core.py` — 威科夫分析（影响 trader + review）
- `02-共享模块-shared/trader_shared/fusion_core.py` — 决策融合（影响全局）
- `02-共享模块-shared/trader_shared/bayesian_fusion.py` — 贝叶斯融合（影响全局）
- `02-共享模块-shared/trader_shared/volume_profile.py` — 量价分析（影响 trader）

HMM 标签修复是最关键的变更，会影响所有使用 `hmm_regime_en` 的下游模块。无 API 变更，无 breaking change，全部为内部数学修正。
