# BUSINESS.md — Trader3.0 业务逻辑

> **最后更新**：2026-07-31 | **标杆**：`trader_shared/` 代码 + `formulas.md` + `output-template.md`  
> 冲突时：以本文 **§2.0 岗位合同** 与代码为准；算法细则以 `formulas.md` 为准，再回写本文。

---

## 1. 业务流程总览

### 1.1 单票分析（核心流程）

```
输入股票代码 → 数据获取 → 策略分析 → 融合仪表 → 结构/筹码/阶段 → 纪律门控 → decision_view → 结论 → 报告
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
入池分析 → 软门槛分道 → 入池 → 排序 → 作战表 → 盯盘 → 复盘 → 淘汰归档
```

---

## 2. 策略业务规则

### 2.0 岗位 × 时框合同（产品法源）

> 后续改代码 / 写 Agent 规则 **必须先满足本小节**。算法细节见各 § 与 `formulas.md`。

| 岗位 | 理论 | 时框 | 回答的问题 | 不做什么 |
|------|------|------|------------|----------|
| **中线状态** | 威科夫 | **仅周线** | 现在处在什么阶段/背景？能不能谈试探？ | 不定短线买卖价；日线不得冒充中线状态 |
| **短线交易** | 缠论 | **日线**（可加 30m/5m 区间套确认） | 位到了没有？何时何价可扳机？ | 不定中线阶段；不覆盖威科夫背景 |
| **短线参考** | 动量 / VPF | 日线 | 动能/价量是否拆台或顺风？ | 不改威科夫阶段；不单独构成开仓理由 |

**铁律**：

1. 中线「现在什么阶段」**只听周线威科夫**；周线不足 → `timeframe=insufficient` → **不参与定论**，禁止日线回退定中线。
2. 短线「何时何价出手」听**日线缠论**买卖点；须中线背景允许（威科夫未否决试探）才可推荐新开。
3. 动量 / VPF 只做确认或否决；同向加信心，反向推迟；**不得**改写阶段或单独开仓。
4. Fusion `weighted_score` **仅仪表**；出手听 `decision_view`（共振 ∧ 策略可执行 ∧ 纪律）。
5. 报告中线「缠论：」行为**结构副读**，不得覆盖威科夫状态定论（见 §2.1）。

与岗位共振对齐：`docs/designs/resonance-and-orchestration.md`（background=周线威科夫，structure=日线缠论，momentum=确认/否决）。

### 2.1 缠论（Chanlun）— 短线交易扳机

**角色**：短线交易岗（位到了没有）。算法权威：`formulas.md`。

**核心概念**：分型 → 笔 → 线段 → 中枢 → 买卖点 → 背驰。

**买卖点类型**（权威：`formulas.md` §6）：
- 一类买点：≥2 个严格不重叠同向中枢 + 离开段背驰 + 末两段同向笔新低 + MACD 面积减弱
- 二类买点：回调不破前低，且前置一类为**时间轴历史结构**
- 三类买点：中枢上方回踩不破
- 卖点对称
- 执行优先认正式「一/二/三类」；「类一/类二」为观察档，不进强扳机
- 一类买优先配合小级别确认（区间套 `30m✓` 等）；背驰生产默认 `legacy`，严格 b/c 见 `CHAN_DIVERGENCE_BC=strict`

**短线（日线）**：
- `chanlun_strategy` 跑日线 → fusion / 短线专家 / 出手扳机
- 段数只调 `structure_confidence`，不把主状态改成「线段不足」

**中线「缠论：」行（结构副读，方案 A）**：
- 周线默认根数：`WEEKLY_LOOKBACK_BARS=260`（`config.py`；`data_provider` / `light_data` 统一默认）
- `chanlun_strategy_midline`：**优先周 K**；周线不足且日线够 → `timeframe=daily_fallback`，展示追加「（日线）」
- **允许**日线回退作结构展示；**禁止**该结果参与中线阶段/定论（中线状态只认周线威科夫，§2.0 / §2.2）
- 中线关键价仍只认周线引擎（`mid_key_prices`）；`daily_fallback` 笔段**不得**进中线价主路径

**报告波段标签**（`conclusion_block._build_wave_label`）：
| 条件 | 文案 |
|------|------|
| strokes &lt; 3 | `笔数不足 · 先观望` |
| segments == 1 且 strokes ≥ 3 | 笔级/结构叙事 + `线段偏少`（如 `拉升趋势中 · 线段偏少`） |
| segments == 0 且 strokes ≥ 3 有结构/浪型 | 笔级/结构叙事 + `线段未成型` |
| segments == 0 且 strokes ≥ 3 无结构 | `中枢未成型 · 先观望` |
| segments ≥ 2 | 按走势分类 / 买卖点 overlay |

**禁止**：写「线段不足」或「无法判断」当主结论。段少也要给立场：有结构用结构，没有就「先观望」。

**MACD 与背驰**（`formulas.md` §5.1）：
- `histogram = DIF − DEA`（×1，非通达信 2×）
- 预热不足写 `None`，禁止 `0.0` 占位；面积跳过 `None` 与反号柱

**评分权重**（选股池）：chanlun_score max 45

### 2.2 威科夫（Wyckoff）— 中线状态岗

**角色**：中线状态岗（阶段/背景能不能谈试探）。**不定**短线买卖价。

**阶段状态机**：吸筹 → 试盘 → 拉升 → 派发 → 砸盘（另有 Markup/Markdown 与原典事件 PS/PSY/BU/UTAD 等）

**时框与窗口（中线）**：
- **仅周线**；`wyckoff_strategy_midline` 周线独占，**禁止**日线回退
- 取数：`WEEKLY_LOOKBACK_BARS=260`（约 5 年周 K 背景）
- 开口：≥ `WYCKOFF_MIN_BARS=15` 根周 K；不足 → `timeframe=insufficient` →「周线不足 · 不参与定论」
- 阶段叙事：约近 **12 根周 K**（`WYCKOFF_PHASE_LOOKBACK=60` × 周线缩比 0.2）
- 读法：优先 `phase` + 事件链（如「还差 SOS」）+ `WyckoffStateView`；**不以**单事件亮灯或打分均值当状态
- **Phase A 区间边界**（原典）：TR 种子由 **SC/ST 低点 + AR 高点**钉定；`WYCKOFF_CLIMAX_ANCHOR_BARS` 仅作搜索/超时。`forming`=有 SC；`established`=SC+AR（检测态，**≠**成熟箱体）。规格：`docs/plans/wyckoff-phase-a-range-handoff.md`
- **箱体/量度成熟度 L0–L3**（展示合同）：L0 无 SC；L1=SC 或 SC+AR **无成功 ST** → 只写**雏形**、**禁止**「箱体」与量度；L2=真 ST（回测 SC 区+缩量，**禁止软确认**）→ 可写 `箱体 lo-hi`；L3=L2+宽度 → 可量度。仅分位 TR 不得量度。规格：`docs/plans/wyckoff-tr-maturity-l0l3-handoff.md`
- **箱体人话（中短线共用）**：L2/L3 → `箱体 {lo:.2f}-{hi:.2f}`；L1 → `雏形 …（待 ST）` / 箱体未成形；旧词「区间未钉」仅兼容。实现：`_phase_a_box_phrase` + `tr_maturity`
- **中线面板结构**：`威科夫：阶段 · [箱体] · 事件 · 含义`（`format_wyckoff_midline_light`；有箱体则插入，无则跳过箱体槽）
- **日线威科夫（短线展示双轨）**：
  - 短线 `威科夫：` ← 日线跑**同一套**种子箱/事件机，**只给人看**（与中线点名同构；**禁止**面板写「日线阶段：」；无箱体诚实写「无 / 箱体未成形 / 暂定不出」；有箱同写 `箱体 lo-hi`）
  - 短线 `事件：` ← 事件灯（`format_wyckoff_event_light` / `format_event_display`）
  - **不进**中线定论、**不进** fusion、**不进**共振背景岗、**不单独开仓**

**约束**：
- 日线威科夫**已退出**短线 fusion（第三席为 VPF）；日线结果不得写入中线定论
- 主消费：中线「威科夫：」一行 + 选股池/复盘吸筹链排序；背景岗共振**只读周线**威科夫；短线「威科夫：」仅对照阅读

**统一出口 View（A 档，2026-07）**：
- 契约：`docs/designs/wyckoff-state-view.md`
- 代码：`to_wyckoff_state_view(analysis)` → `WyckoffStateView`（`trader_shared/wyckoff_view.py`）
- 从现有 `wyckoff_analysis` 大 dict **薄适配**，不重跑检测
- 字段：`phase` / `active_events` / `bias` / `confidence` / `summary_oneline` / `tr` / `invalidation_hint` 等
- **生产主路径**（报告渲染）优先读 View；旧 dict 仅兼容
- 非目标：View 不直接下单；不替换 fusion；未做特征/原子事件大重构

**状态准确度演进**：
1. 个股 vs **所属板块对照指数**相对强弱（RS）（**已落地**；对照指数 SSOT = `resolve_board_index`；规格见 `docs/plans/wyckoff-rs-phase-handoff.md`）  
   - 周线阶段机：仅置信修正，**不抬** `phase`  
   - 选股池：同道排序（lane→共振→链→RS→可碰→分）；弱 RS 可盯→等齐「慎跟」；模块 `wyckoff_rs.py`，开关 `WYCKOFF_RS_ENABLED`
2. Spring 后确认测试与 ST 语义分离 → **已落地**（`spring_test_*` 双写 + 阶段 C/D；规格见 `docs/plans/wyckoff-phase-accuracy-handoff-2026-07-31.md` §2）
3. 低质量 TR 不进阶段机 → **已落地**（`WYCKOFF_PHASE_MIN_TR_QUALITY` + `phase_tr_gated`；同上 handoff §3）
4. Phase A 边界 SC/AR 钉 TR 种子 → **P1 已落地**（`phase_a_range`/`forming`/`established`）；**P2 已落地**（种子箱门控 + 广义 ST → `docs/plans/wyckoff-phase-a-range-handoff.md` §4）
5. 完整 P&F 因果目标 → **计数已落地**；**展示须 L3**（真 ST+宽度；L1/分位禁止量度；1:1 勿冒充 P&F）。短/中分轨；周线禁止日线箱体冒充。规格：`wyckoff-pnf-handoff.md` + `wyckoff-tr-maturity-l0l3-handoff.md`

原典落地盘点：`docs/audit/wyckoff-original-concept-inventory.md`。

### 2.3 动量（Momentum）— 短线确认/否决

**角色**：短线参考岗；**不是**学说原典体系。同向加信心，反向推迟；**不得**改写威科夫阶段，**不得**单独构成开仓理由。

**综合评分**：MACD + RSI + ADX + 布林 + Supertrend 确认等（见 `momentum_core` / 审计文档）

**数据不足**：`insufficient` + `score=None`（与真中性 score=50 分离）

**评分权重**（选股池）：momentum_score max 20

### 2.4 价量资金（VPF — 融合第三席）

**角色**：短线参考岗（与动量同属确认/否决侧）；**不定**中线状态。

**替代**：日线威科夫在短线融合中的位置。

**信号类型**：主力净流出警告、天量滞涨、放量下跌等。

**权重**：正常 0.25 / 偏弱 0.35 / 很差 0

**合成口径（P0 冻结，与代码一致）**：资金 `fund_quality=full` 且 `confidence≥0.55` 时**资金方向优先**于价量，可不归中性；天量空 + 资金流入是否强制观望 **另开任务**（见 `docs/designs/analysis-opinion-cards.md` §9）。

### 2.5 单日跌幅硬熔断

`decision_core.status_layers`：`change_pct <= -7.0`（百分比）触发「风险回避」（满 7% 即熔断，与 `HARD_STOP_SINGLE_DAY_DROP` 一致）。

### 2.6 分析意见卡（策略匹配输入）

策略层只读意见卡，不扫原始大 dict。契约与构建：`docs/designs/analysis-opinion-cards.md`、`trader_shared/analysis_cards.py`。

### 2.7 Fusion 输入路径（Arch C）

短线三席（缠/动量/VPF）**生产默认 cards**（意见卡 → `fusion_card_signals`；不足则 **warning 后**回退 classic）。

| `FUSION_FROM_CARDS` | 行为 |
|---------------------|------|
| 缺省 / `cards` / `true` / `1` | **默认**：三席优先意见卡；失败打 warning 再 classic |
| `classic` / `false` / `0` | deprecated（仅对照）。实现上常先走 raw→现建卡→`fusion_card_signals`（`fusion_input_path=classic_via_cards`）；真 classic mappers 仅作该路径失败时的回退 |
| `compare` / `dual` | 两路都算；主结果用 cards；写入 `fusion_compare` 供对账 |

**生产默认仍是 cards**；勿把 `classic_via_cards` 当成生产主路径。  
报告路径仍会预产 `analysis_cards`（策略 📐 / ensure 用），与 fusion 默认输入解耦。  
实现：`fusion_core._fusion_input_mode` + `analysis/fusion_card_signals.py` + `merge_decisions(..., analysis_cards=...)`。  
边界与 classic/compare 回退对账：`docs/designs/analysis-strategy-boundaries.md` §5。

`FUSION_OVERRIDE_ENABLED` **默认 false**：融合分不覆盖 `theory_status`；出手听 `decision_view`。  
`decision_view` 策略亮条件：entry `executable=True`（`plan` 不算可新开）。

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

### 3.4 板块环境与「很差」实际行为

**对照指数（单票）**：环境档（正常/偏弱/很差）跟**所属板块指数**走，不是固定中证1000。

| 个股前缀 | 对照指数 | meta 短名 |
|----------|----------|-----------|
| `688` | 科创50 `000688.SH` | 科创 |
| `300`/`301` | 创业板指 `399006.SZ` | 创业板 |
| `60` | 上证指数 `000001.SH` | 上证 |
| `000`/`001`/`002`/`003` | 深证成指 `399001.SZ` | 深成 |
| 其余（含北交所） | 回退 `INDEX_CODE`（中证1000） | 中证1000 |

实现：`market_env.resolve_board_index` → `get_env_for_skill(..., index_code=)`（`context_stage`）。  
`INDEX_CODE` 仅作无映射时的宽基回退；选股池日报等无个股上下文时仍可用宽基。

**人读 meta（纯 D）**：只写板块指数涨跌 + 行业短名涨跌 + 个股涨跌；**不写**正常/偏弱、不写跑赢。环境档仍进 `market_env.level` / fusion `regime`（内部风控），面板不露。

**「很差」实际行为**（非字面「暂不碰」）— 代码路径 `fusion_core.merge_decisions` + `score_to_action`：

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

### 4.0 阶段字段词典（禁止混用）

| 字段 | 含义 | 词表 / 用途 |
|------|------|-------------|
| `midline_stage` / `conclusion.stage_line` | 周线威科夫短词 | 吸筹/主升/派发/无阶段… → **威科夫正文内展示，不单独成行** |
| `major_stage` | 日线四阶段 | 蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退 → 门控/池软信号（**不**写面板阶段行） |
| `short_term_momentum` | EXPMA 短期动能 | 走强/修复/震荡/转弱 |
| `report["stage"]` | **兼容别名** | **= `short_term_momentum`**（池/旧读方）；禁止再写轻量 `determine_stage`；禁止映射成 `major_stage` |

实现锚点：`trader_shared/stage_fields.py`；面板渲染见 `report_renderer/short_midline.py`。

### 4.1 四阶段模型（`major_stage`）

| 阶段 | 特征 | 操作建议 |
|------|------|----------|
| **蓄势**（含偏强/偏弱） | 价格在支撑区横盘 | 可轻仓试探（纪律清单全绿时） |
| **主升** | 价格突破确认位持续新高 | 趋势明确，持有/增持 |
| **派发** | 高位放量滞涨 | 诱多，逐步退出 |
| **衰退** | 跌破生命线持续新低 | 不参与 |

**方向 / 新开**听 `decision_view`（共振齐 ∧ 主策略亮 ∧ 纪律允许）；`fusion.weighted_score` **仅仪表**。不得只从阶段或融合分推断多空/宜买。

### 4.2 选股池入池（软门槛 + 分道）

与 AGENTS「入池软门槛」一致：**容量满才硬拒**；阶段/评分偏弱 → `lane=先别碰` 等分道，**不再**「衰退→直接拒绝」挡入库。

**评分**：按 `major_stage` 查表 `ADMISSION_SCORE_*`（软信号）。  
`total_score` = 缠 + 威 + 筹 + 动（封顶 100）。**`fusion_score` 仅仪表，不进总分、不抬/压入池门槛、不参与排序加权。**  

**排序**：`lane → 共振 → 威科夫吸筹链 → 周线 RS → 可碰 → 分`。  
风控位不清 → 待补 / 分道降权；现价跌破止损 → 分道 avoid（非一律不入库）。

---

## 5. 报告业务规则

### 5.1 输出模板（短中线双轨，与 `render_short_midline` / output-template 一致）

```
分析报告 — {name}（{code}）｜短中线

📊 价格状态
  现价 {price}（{change_pct}）｜MA20 …｜MA250 …
  综合动能 {momentum} ｜ {板块短名} ±x% ｜ {行业短名} ±x% ｜ 个股 ±x%
  量比… ｜ 换手… ｜ 调整N天 ｜ ATR14 x.xx（前/后/未复权）
  ← meta 纯 D：不写正常/偏弱/跑赢；无单独「行业：」行；ATR 并入量价行（非独立行）；映射见 §3.4

📐 理论分析
  中线
    威科夫：{wyckoff_midline}     ← 中线状态岗：仅周线；结构「阶段 · [箱体] · 事件 · 含义」（箱体 lo-hi / 箱体未成形）
    下沿 x｜上沿 y（L3）          ← 仅 tr_maturity=L3；L0-L2 省略
    量度目标：上 x｜下 y（P&F，非出手）  ← 仅 tr_maturity=L3；无数/未达 L3 则省略
    缠论：{chanlun_midline}       ← 结构副读；周不足可 daily_fallback+「（日线）」；不定阶段
    位置：…
  短线
    缠论：…（日线缠论扳机）
    买点：…（lifecycle，可选）
    威科夫：…（日线只对照；标签即威科夫，禁止「日线阶段：」；箱体 lo-hi / 箱体未成形 / 无清晰区间；不进背景岗）
    下沿 x｜上沿 y（L3）          ← 仅日线 L3；L0-L2 省略
    量度目标：上 x｜下 y（P&F，非出手）  ← 仅日线 L3；与中线分轨
    事件：…（日线威科夫事件灯；无事件可省略）
    动能：…
    资金：…

🎯 支撑阻力
  中线
    生命线 / 回踩区 / 压力 / 目标   ← mid_key_prices（周线引擎）
  短线
    止损 / 买点区 / 🌟 现价 / 卖点区 ← key_prices（日线引擎）
    {买价} 买：亏约… / 赚约…
    {现价} 追：亏约… / 赚约… → 不追?

✅ 出手
  共振：…
  新开：…
  动作：…
  原因：…
  破位看：…

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
| 决策收紧清零 | `decision_view.apply_execution_caps`（DV 之后单一出口；含 fail-closed） | 禁止新开时 `suggested_pct` / 仓位 cap 归零 |
| 失效 | chan_discipline | 跌破 MA20 反抽不回 / 跌破止损等 |
| regime 很差 | fusion_regime 权重归零 | 加权分偏中性/空仓侧动作（非固定「暂不碰」文案） |

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

人读展示：与量比/换手/调整天数同一行，形如 `ATR14 3.84（未复权）`；口径取 `atr_adjust`（qfq/hfq/none）。无有效 `atr14` 时退化为 `ATR口径 {复权标签}`。系统固定 **14 日** ATR，勿写成 ATR15。

### 6.4 盈亏比（纪律 / 出手文案）

内部可用 R:R；**报告禁止**写「2.1R」术语，改写「亏约 / 赚约」。

### 6.5 Supertrend

展示型插件（`display_only`），**不进** fusion 加权；动量侧只作确认分。

---

*此文档基于 2026-07-17 代码状态（含 WyckoffStateView A 档）。任何业务规则变更必须同步更新。*
