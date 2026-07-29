# BUSINESS.md — Trader3.0 业务逻辑

> **最后更新**：2026-07-29 | **标杆**：`trader_shared/` 代码 + `formulas.md` + `output-template.md`  
> 冲突时以代码为准，再回写本文。

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
| 1. 数据获取 | data_provider | stock code | Security + Quote + Bars + FundFlow + **weekly_bars**（默认 `WEEKLY_LOOKBACK_BARS=260`） |
| 2. 策略分析 | PluginRegistry | daily_bars, weekly_bars | chan/momentum/wyckoff results |
| 3. 融合仪表 | fusion_core | 三路信号 + regime | weighted_score + action + confidence（**仅仪表**） |
| 4. 结构筹码阶段 | structure/chip/stage | daily_bars, fund_flow | support/resistance/stage/chips |
| 5. 纪律门控 | mistery_gate + chan_discipline | structure + 纪律 | allow_new_entry/action/cap/invalidation |
| 5b. 薄决策 | decision_view | 共振 ∧ 策略 ∧ 纪律 | allow_new_recommend（新开只收紧） |
| 6. 结论构建 | conclusion_block | 以上全部 | 中线看法/短线看法/出手/wave_label/原因 |
| 7. 报告渲染 | report_core.render_short_midline | report dict | Markdown |

### 1.3 选股池管理

```
入池分析 → 三关筛选 → 入池 → 排序 → 作战表 → 盯盘 → 复盘 → 淘汰归档
```

---

## 2. 策略业务规则

### 2.1 缠论（Chanlun）

**核心概念**：分型 → 笔 → 线段 → 中枢 → 买卖点 → 背驰。

**买卖点类型**（权威：`formulas.md` §6）：
- 一类买点：≥2 个严格不重叠同向中枢 + 离开段背驰 + 末两段同向笔新低 + MACD 面积减弱
- 二类买点：回调不破前低，且前置一类为**时间轴历史结构**
- 三类买点：中枢上方回踩不破
- 卖点对称

**中线 / 周线**：
- 周线默认根数：`WEEKLY_LOOKBACK_BARS=260`（`config.py`；`data_provider` / `light_data` 统一默认）
- 周线缠论独立运行，不回退日线
- 段数只调 `structure_confidence`，不把主状态改成「线段不足」

**报告波段标签**（`conclusion_block._build_wave_label`）：
| 条件 | 文案 |
|------|------|
| strokes &lt; 3 | `笔数不足 · 无法判断` |
| segments == 1 且有 trend/structure | 笔级叙事 + `线段偏少`（如 `拉升趋势中 · 线段偏少`） |
| segments == 0 且 strokes ≥ 3 有 trend | 笔级叙事 + `线段未成型` |
| segments ≥ 2 | 按走势分类 / 买卖点 overlay |

**禁止**：`segments < 2` 时仍写「笔数不足」（历史 bug，已修）。

**MACD 与背驰**（`formulas.md` §5.1）：
- `histogram = DIF − DEA`（×1，非通达信 2×）
- 预热不足写 `None`，禁止 `0.0` 占位；面积跳过 `None` 与反号柱

**评分权重**（选股池）：chanlun_score max 45

### 2.2 威科夫（Wyckoff）

**阶段状态机**：吸筹 → 试盘 → 拉升 → 派发 → 砸盘（另有 Markup/Markdown 与原典事件 PS/PSY/BU/UTAD 等）

**约束**：
- 日线威科夫**已退出**短线 fusion（第三席为 VPF）
- 周线威科夫独占中线，不足 → `timeframe=insufficient` →「周线不足 · 不参与定论」
- 主消费：选股池/复盘打分 + 中线「威科夫：」一行

**统一出口 View（A 档，2026-07）**：
- 契约：`docs/designs/wyckoff-state-view.md`
- 代码：`to_wyckoff_state_view(analysis)` → `WyckoffStateView`（`trader_shared/wyckoff_view.py`）
- 从现有 `wyckoff_analysis` 大 dict **薄适配**，不重跑检测
- 字段：`phase` / `active_events` / `bias` / `confidence` / `summary_oneline` / `tr` / `invalidation_hint` 等
- **生产主路径**（报告渲染、fusion）仍可读旧 dict；Agent / 后续迁移**优先读 View**
- 非目标：View 不直接下单；不替换 fusion；未做特征/原子事件大重构

### 2.3 动量（Momentum）

**综合评分**：MACD + RSI + ADX + 布林 + Supertrend 确认等（见 `momentum_core` / 审计文档）

**数据不足**：`insufficient` + `score=None`（与真中性 score=50 分离）

**评分权重**（选股池）：momentum_score max 20

### 2.4 价量资金（VPF — 融合第三席）

**替代**：日线威科夫在短线融合中的位置。

**信号类型**：主力净流出警告、天量滞涨、放量下跌等。

**权重**：正常 0.25 / 偏弱 0.35 / 很差 0

**合成口径（P0 冻结，与代码一致）**：资金 `fund_quality=full` 且 `confidence≥0.55` 时**资金方向优先**于价量，可不归中性；天量空 + 资金流入是否强制观望 **另开任务**（见 `docs/designs/analysis-opinion-cards.md` §9）。

### 2.5 单日跌幅硬熔断

`decision_core.status_layers`：`change_pct < -7.0`（百分比）触发「风险回避」，**刚好 -7.0 不触发**。若产品要「满 7% 熔断」需改 `<=` 并同步测试。

### 2.6 分析意见卡（策略匹配输入）

策略层只读意见卡，不扫原始大 dict。契约与构建：`docs/designs/analysis-opinion-cards.md`、`trader_shared/analysis_cards.py`。

### 2.7 Fusion 输入路径（Arch C）

短线三席（缠/动量/VPF）**生产默认 cards**（意见卡 → `fusion_card_signals`；不足回退 classic）。

| `FUSION_FROM_CARDS` | 行为 |
|---------------------|------|
| 缺省 / `cards` / `true` / `1` | **默认**：三席优先意见卡 |
| `classic` / `false` / `0` | 强制 classic 标准化 |
| `compare` / `dual` | 两路都算；主结果用 cards；写入 `fusion_compare` 供对账 |

报告路径仍会预产 `analysis_cards`（策略 📐 / ensure 用），与 fusion 默认输入解耦。  
实现：`fusion_core._fusion_input_mode` + `analysis/fusion_card_signals.py` + `merge_decisions(..., analysis_cards=...)`。  
边界与 classic/compare 回退对账：`docs/designs/analysis-strategy-boundaries.md` §5。

---

## 3. 融合决策规则

### 3.1 加权公式

```
weighted_score = Σ(direction_i × confidence_i × weight_i)
```

权威权重源：`trader_shared/config/fusion_regime_weights.yaml`（缺失则回退 `fusion_regime._FALLBACK_REGIME_WEIGHTS`）。

### 3.2 Regime 权重矩阵（与代码一致）

| Regime | 缠论 chan | 动量 momentum | VPF |
|--------|-----------|---------------|-----|
| 正常 | **0.30** | **0.45** | 0.25 |
| 偏弱 | 0.50 | 0.15 | 0.35 |
| 很差 | 0 | 0 | 0 |
| 未知 | 同正常 | 同正常 | 同正常 |

> 正常大势：**动量占优**；偏弱：**缠论占优**。旧文档写「正常 chan=0.45 / mom=0.30」已废弃。

### 3.3 决策映射（`score_to_action`）

```
weighted_score  →  action（正常表摘要）
  ≥ 0.4         →  半仓试 (多方主导)
  ≥ 0.25        →  增持
  ≥ 0.1         →  等转强观察
  ≥ -0.05       →  持股观望
  ≥ -0.15       →  减1/3 (高位松动)
  ≥ -0.3        →  减仓
  ≥ -0.5        →  空仓/止损
```

- `disagreement > 1` → 用分歧降级表
- `regime=偏弱` → **正阈值**右移 +0.10（负阈值不改）

### 3.4 大盘「很差」实际行为（非字面「暂不碰」）

代码路径（`fusion_core.merge_decisions` + `score_to_action`）：

1. 权重全 0 → 加权分自然为 0  
2. 若 `|weighted_score| < 0.01` → **强制** `weighted_score = -0.5`  
3. 映射到 **「空仓/止损」** 一类动作  

**已移除**「regime=很差 → 动作字符串固定为暂不碰」的一票否决（见 `fusion_regime.score_to_action` 注释与 `test_fusion_core`）。  
Agent 展示层仍应：**不给买入建议**；文案对齐 fusion action / 纪律分仓，勿硬造「暂不碰」除非 `theory_status`/`status` 本身就是该词。

### 3.5 其他风控覆盖

1. 限售解禁 → 空仓侧  
2. `major_stage = 衰退` → 不参与  
3. `major_stage = 派发` → 不加仓  
4. 连续资金流出 veto（近 3 日主力净流出等）  
5. 天量天价 → 减仓  

### 3.6 冲突消解

当 `disagreement > 1`：confidence 降级；动作走分歧表；Agent 可提示「信号有分歧，建议谨慎」。

---

## 4. 阶段判定规则

### 4.1 四阶段模型

| 阶段 | 特征 | 操作建议 |
|------|------|----------|
| **蓄势**（含偏强/偏弱） | 价格在支撑区横盘 | 可轻仓试探（纪律清单全绿时） |
| **主升** | 价格突破确认位持续新高 | 趋势明确，持有/增持 |
| **派发** | 高位放量滞涨 | 诱多，逐步退出 |
| **衰退** | 跌破生命线持续新低 | 不参与 |

**方向 / 新开**听 `decision_view`（共振齐 ∧ 主策略亮 ∧ 纪律允许）；`fusion.weighted_score` **仅仪表**。不得只从阶段或融合分推断多空/宜买。

### 4.2 选股池三关筛选

**第一关 — 阶段筛选**：衰退期 → 直接拒绝  

**第二关 — 结构评分门槛**：按 `major_stage` 查表 `ADMISSION_SCORE_*`。  
`total_score` = 缠 + 威 + 筹 + 动（封顶 100）。**`fusion_score` 仅仪表，不进总分、不抬/压入池门槛、不参与排序加权。**  
入池后共振档离散收紧：冲突 / 动能拆台不得标「执行」。

**第三关 — 风控检查**：现价跌破止损 → 拒绝  

---

## 5. 报告业务规则

### 5.1 输出模板（短中线双轨，与 `render_short_midline` / output-template 一致）

```
分析报告 — {name}（{code}）｜短中线

现价 {price}（{change_pct}）
  动能 {momentum} ｜ 大盘 {regime}
  MA5：… ｜ MA20：… ｜ MA250：…
  量比… ｜ 换手…

🧭 中线
  阶段：{major_stage}
  看法：{midline_view}          ← 禁止塞阶段词
  威科夫：{wyckoff_midline}     ← 仅周线，不回退日线
  缠论：{chanlun_midline}       ← 可含「拉升趋势中 · 线段偏少」等 wave_label
  位置：…
  关键价（中线）
    生命线 / 回踩区 / 压力 / 目标   ← mid_key_prices（周线引擎）

⚡ 短线
  看法：…
  缠论 / 位置 / 动能 / 价量资金 / 裁定
  新开：否（缺：…）或 可试探（清单全绿）
  出手 / 分仓 / 失效
  关键价（短线）
    止损 / 买点区 / 🌟 现价 / 卖点区
  {买价} 买：亏约… / 赚约…
  {现价} 追：亏约… / 赚约… → 不追?

说明：…
✅ 亮点：…
⚠️ 风险：…
📌 本周只做：…
T0：…
当前池 n/m，回复 1 入池
```

权威全文：`01-功能包-packages/trader/references/output-template.md`。

### 5.2 关键价规则

**中线**：`mid_key_prices` / `midline_structure`（周线笔/段/摆动），禁止用日线 `key_levels` 冒充成功路径。

**短线**：`key_prices` — 止损 / 买点区 / 🌟 现价 / 卖点区。

### 5.3 纪律规则

| 规则 | 来源 | 效果 |
|------|------|------|
| 出手 / 新开清单 C1 | mistery_gate + chan_discipline | 五项不全绿 → 新开否 |
| 仓位上限 | merge 取更严 | 只裁 cap，不改 major_stage / fusion 分 / support / stop |
| 失效 | chan_discipline | 跌破 MA20 反抽不回 / 跌破止损等 |
| regime 很差 | fusion_core 4b | 偏空到空仓侧动作 |

报告可见面禁止 mi姐 / Mistery 品牌词。

---

## 6. 计算规则（部分关键公式）

### 6.1 日线回看

```
LOOKBACK_DAYS = 370   # 日历天，保证 MA250 足够交易日（config.py）
```

### 6.2 周线回看

```
WEEKLY_LOOKBACK_BARS = 260   # 中线缠论/威科夫成笔成段
```

### 6.3 ATR

```
ATR14 = SMA(TR, 14)
TR = max(H-L, |H-C_prev|, |L-C_prev|)
```

### 6.4 盈亏比（纪律 / 出手文案）

内部可用 R:R；**报告禁止**写「2.1R」术语，改写「亏约 / 赚约」。

### 6.5 Supertrend

展示型插件（`display_only`），**不进** fusion 加权；动量侧只作确认分。

---

*此文档基于 2026-07-17 代码状态（含 WyckoffStateView A 档）。任何业务规则变更必须同步更新。*
