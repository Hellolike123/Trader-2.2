## 1. 严重数学错误修复

- [x] 1.1 `hmm_regime.py:24-25` — 将 `REGIME_LABELS` 和 `REGIME_EN` 的 index 1/2 互换：1=Range, 2=Bear
- [x] 1.2 `chan_core.py:375` — 将 `_calc_macd(bars)` 改为 `bars = _calc_macd(bars)`
- [x] 1.3 `indicators.py:357-359` — 将 `smooth_tr = smooth_tr - (smooth_tr / period) + tr[i]` 改为 `smooth_tr = (smooth_tr * (period - 1) + tr[i]) / period`（smooth_up, smooth_down 同理）
- [x] 1.4 `indicators.py:370-378` — 将 ADX 计算改为 `adx[i] = (adx[i-1] * (period - 1) + dx_val) / period`，删除固定 SMA 基准逻辑
- [x] 1.5 `hmm_regime.py` — 为标签修复添加测试：验证 bear/range 场景下 `detect_regime()` 返回正确的 `state_en`
- [x] 1.6 `chan_core.py` — 为 MACD 透传添加测试：验证 `chanlun_analysis()` 返回的 bars 包含 `macd_histogram`

## 2. 中等逻辑错误修复

- [x] 2.1 `wyckoff_core.py:47` — 将 `WYCKOFF_SPRING_RECLAIM_RATIO` 从 0.92 改为 0.97
- [x] 2.2 `wyckoff_core.py:49` — 增加收盘价回到支撑上方的检查：`current_close >= support`
- [x] 2.3 `momentum_core.py:105-107` — 将 `sum(tr[:period])` 改为 `sum(tr[1:period+1])`（pdi_s, mdi_s 同理）
- [x] 2.4 `fusion_core.py:355` — 将 `mom_score >= 65` 改为 `mom_score >= 80 and pos_pct >= 0.7`
- [x] 2.5 `fusion_core.py:354` — 为 `is_breakout_or_bottom` 增加 `pos_pct <= 0.3` 约束（当 strong_bullish_chan/wyk 为 True 时）
- [x] 2.6 `chan_core.py:286-292` — 二买 `up_high` 改为用 `down_strokes[-2]` 和 `down_strokes[-1]` 之间的那个上涨笔的高点
- [x] 2.7 `wyckoff_core.py:79-82` — 将 Upthrust `reclaim_level` 从 `resistance * 0.98` 改为 `resistance * 0.995`
- [x] 2.8 `hmm_regime.py:103-137` — 将收敛检查移到参数更新之后，或在循环末尾额外计算一次 log-likelihood
- [x] 2.9 为上述修复添加对应测试用例（更新了 spring/upthrust/fusion 测试）

## 3. 低优先级修复

- [x] 3.1 `momentum_core.py:34` — 将 `100.0 if avg_l == 0` 改为 `50.0 if avg_l == 0 and avg_g == 0 else 100.0 if avg_l == 0`
- [x] 3.2 `hmm_regime.py:179` — 将最小数据阈值从 10 改为 30
- [x] 3.3 `fusion_core.py:360` — 更新注释说明实际权重分配（55% momentum）与文档"80%"的差异，或更新 AGENTS_DEEP.md
- [x] 3.4 `wyckoff_core.py:108-115` — 量价背离改为比较前半段 vs 后半段平均量，而非单根最大量柱
- [x] 3.5 `volume_profile.py:87-92` — 量能分配改为按价格区间重叠比例分配，而非均分
- [x] 3.6 为上述修复添加对应测试用例
