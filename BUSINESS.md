# BUSINESS.md — Trader3.0 业务逻辑

> **最后更新**：2026-07-14 | **基于**：代码级分析

---

## 1. 业务流程总览

### 1.1 单票分析（核心流程）

```
输入股票代码 → 数据获取 → 策略分析 → 融合决策 → 结构/筹码/阶段 → 纪律门控 → 结论 → 报告
```

**耗时**：网络数据获取 ~3-10s（取决于数据源），本地计算 ~1s。

### 1.2 七步流水线

| 步骤 | 模块 | 输入 | 输出 |
|------|------|------|------|
| 1. 数据获取 | data_provider | stock code | Security + Quote + Bars + FundFlow |
| 2. 策略分析 | PluginRegistry | daily_bars, weekly_bars | chan/momentum/wyckoff results |
| 3. 融合决策 | fusion_core | 三路信号 + regime | weighted_score + action + confidence |
| 4. 结构筹码阶段 | structure/chip/stage | daily_bars, fund_flow | support/resistance/stage/chips |
| 5. 纪律门控 | mistery_gate + chan_discipline | fusion + structure | allow_new_entry/action/cap/invalidation |
| 6. 结论构建 | conclusion_block | 以上全部 | 中线看法/短线看法/出手/原因 |
| 7. 报告渲染 | report_core | report dict | Markdown |

### 1.3 选股池管理

```
入池分析 → 三关筛选 → 入池 → 排序 → 作战表 → 盯盘 → 复盘 → 淘汰归档
```

---

## 2. 策略业务规则

### 2.1 缠论（Chanlun）

**核心概念**：分型 → 笔 → 线段 → 中枢 → 买卖点 → 背驰。

**买卖点类型**：
- 一类买点：下跌趋势背驰后的底分型
- 二类买点：回调不破前低
- 三类买点：中枢上方回踩不破
- 一类卖点：上涨趋势背驰后的顶分型
- 二类卖点：反弹不破前高
- 三类卖点：中枢下方反弹不破

**约束**（D4 修复后）：
- 背驰必须发生在"离开段"（末笔在中枢之后）——不再被静默禁用
- 周线缠论独立运行，不回退日线

**评分权重**（选股池）：chanlun_score max 45（阶段 bonus + 场景 bonus + 确认位距离 + 买点类型 + 数据充分性）

### 2.2 威科夫（Wyckoff）

**阶段状态机**：吸筹(A/B/C) → 试盘 → 拉升 → 派发(A/B/C) → 砸盘

**事件检测**（10+ 种）：
- Spring（弹簧）：下跌末端快速拉回
- Upthrust（上冲回落）：上涨末端冲高回落
- SOS（强势信号）：放量突破
- SOW（弱势信号）：放量跌破
- BC（买入高潮）：天量天价
- AR（自动反弹）
- ST（二次测试）
- LPS（最后供应点）

**约束**：
- 日线威科夫已退出短线融合（VPF 替代）
- 周线威科夫独占中线分析，不回退日线
- Phase 持久化：反向翻转基于 phase order 符号（D4 修复），不再排除 distribution 阶段

### 2.3 动量（Momentum）

**综合评分**：MACD + RSI + OBV + 价格位置

**方向判定**：
- `direction = +1`：多方（MACD 金叉 + RSI > 50 + OBV 上升）
- `direction = 0`：中性
- `direction = -1`：空方

**评分权重**（选股池）：momentum_score max 20

### 2.4 价量资金（VPF — 融合第三席）

**替代**：日线威科夫在短线融合中的位置。

**信号类型**：
- 主力净流出警告（近 N 日累计）
- 天量滞涨
- 放量下跌
- 缩量上涨（虚假突破）

**信号层级**：`vpf_bearish_warning`（唯一的生产级 warning 层级）

**权重**：正常 0.25 / 偏弱 0.35 / 很差 0

---

## 3. 融合决策规则

### 3.1 加权公式

```
weighted_score = Σ(direction_i × confidence_i × weight_i) / Σ(weight_i)
```

其中：
- `direction_i` ∈ {+1, 0, -1}（来自各专家信号标准化）
- `confidence_i` ∈ [0, 1]（来自各专家置信度）
- `weight_i` ∈ [0, 1]（来自 regime 权重矩阵）

### 3.2 Regime 权重矩阵

| Regime | 缠论 | 动量 | VPF |
|--------|------|------|------|
| 正常 | 0.45 | 0.30 | 0.25 |
| 偏弱 | 0.50 | 0.15 | 0.35 |
| 很差 | 0 | 0 | 0（默认偏空） |

来源：`trader_shared/config/fusion_regime_weights.yaml`

### 3.3 决策映射

```
weighted_score  →  action
  > 0.4         →  增持/半仓试
  (0.15, 0.4]   →  持股观望
  (-0.15, 0.15] →  观望等待
  (-0.4, -0.15] →  减仓
  < -0.4        →  空仓
```

### 3.4 风控否决链（优先级从高到低）

1. `regime = "很差"` → 一票否决：输出「暂不碰」
2. 限售解禁 → 空仓
3. `major_stage = 衰退` → 不参与
4. `major_stage = 派发` → 不加仓
5. 资金流出 veto（VPF bearish + continuous）
6. 天量天价 → 减仓

### 3.5 冲突消解

当 `disagreement > 1`（即三路信号中至少有 2 路方向不同）：
- confidence 降级
- 输出标注「信号有分歧，建议谨慎」

---

## 4. 阶段判定规则

### 4.1 四阶段模型

| 阶段 | 特征 | 操作建议 |
|------|------|----------|
| **蓄势** | 价格在支撑区横盘 | 可轻仓试探 |
| **主升** | 价格突破确认位持续新高 | 趋势明确，持有/增持 |
| **派发** | 高位放量滞涨 | 诱多，逐步退出 |
| **衰退** | 跌破生命线持续新低 | 不参与 |

### 4.2 选股池三关筛选

**第一关 — 阶段筛选**：
- 衰退期 → 直接拒绝

**第二关 — 评分门槛**：
- 按 `major_stage` 查表 `ADMISSION_SCORE_EXECUTE / OBSERVE`
- 总分 ≥ execute 阈值 → 可入池执行
- 总分 ≥ observe 阈值 → 可入池观察
- 总分 < observe 阈值 → 拒绝

**第三关 — 风控检查**：
- 现价跌破止损 → 拒绝

---

## 5. 报告业务规则

### 5.1 输出模板（短中线双轨）

```
分析报告 — {name}（{code}）｜短中线

现价 {price}（{change_pct}）｜MA20 {ma20}｜MA250 {ma250}{ma250_warning}
  综合动能 {momentum} ｜ 大盘 {regime}
  ...行业/量比/换手...
  ⚠️ 股价在年线下方运行（如适用）

🧭 中线
  阶段：{major_stage} · {momentum_direction}
  定论：{midline_conclusion}
  威科夫：{wyckoff_midline}
  缠论：{chanlun_midline}
  筹码：{chip_summary}
  关键价（中线）：...

⚡ 短线
  出手：{execution} · 分仓{pct}%
  缠论：{chan_signal}
  动能：{momentum_signal}
  价量资金：{vpf_signal}
  失效：{invalidation}
  关键价（短线）：...

✅ 亮点：...
⚠️ 风险：...
```

### 5.2 关键价规则

**中线关键价**：生命线 → 回踩区 → 压力/目标位 → MA250 参考 → MA20 参考

**短线关键价**：止损 → 低吸区 → 现价 → 止盈区 → 前高/止盈 → MA20 压力

### 5.3 纪律规则

| 规则 | 来源 | 效果 |
|------|------|------|
| 出手条件 | mistery_gate | 确认位以上 + 放量 → 允许出手 |
| 仓位上限 | mistery_gate + chan_discipline | merge 取两者更紧 |
| 失效条件 | chan_discipline | 收盘跌破 MA20 反抽不回 / 跌破止损 |
| regime 否决 | fusion_core | "很差" → 全部否决 |

---

## 6. 计算规则（部分关键公式）

### 6.1 ATR（平均真实波幅）

```
ATR14 = SMA(TR, 14)
TR = max(H-L, |H-C_prev|, |L-C_prev|)
```

### 6.2 盈亏比

```
R:R = (target - current) / (current - stop)
IDEAL: ≥ 2.0
MIN: ≥ 1.2（低于此值拒绝）
```

### 6.3 筹码获利比例

```
profit_ratio = 当前价以上的筹码量 / 总筹码量
> 80% → 高获利盘（抛压风险）
< 20% → 深套盘（反弹阻力小）
```

### 6.4 Supertrend

```
Upper Band = (H+L)/2 + multiplier × ATR
Lower Band = (H+L)/2 - multiplier × ATR
方向 = Upper Band < 前值 → 上升趋势
```

---

*此文档基于 2026-07-14 代码状态。任何业务规则变更必须同步更新。*
