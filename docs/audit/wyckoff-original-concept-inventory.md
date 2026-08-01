# 威科夫原典概念完整盘点 — 代码落地状态一览

> 整理自：Wyckoff《Studies in Tape Reading》、SMI 经典五阶段教学体系、Ruben Villahermosa《The Wyckoff Methodology in Depth》
> 
> 标注：✅ 已实现  ⚠️ 部分实现/有差距  ❌ 未实现
>
> 审计日期：2026-07-16（同日二次更新：互斥打分 + 原典缺口补齐；2026-08-01：P&F 水平计数落地；同日：箱体/量度 L0–L3 成熟度门禁定稿；同日：JAC/止跌量/CM/AR P2-C 有界落地）

---

## 一、三大定律 (Three Laws)

| 概念 | 状态 | 代码落点 |
|------|------|---------|
| 供求律 (Supply & Demand) | ✅ | SC/BC/Spring/Upthrust/量比检测 |
| 因果律 (Cause & Effect) | ✅ | P&F 水平计数 + **L3 展示门禁**（`tr_maturity`）；L1/分位禁止量度。计数：`wyckoff-pnf-handoff.md`；门禁：`wyckoff-tr-maturity-l0l3-handoff.md` |
| 努力结果律 (Effort vs Result) | ✅ | `_detect_effort_vs_result` (VSA) |

---

## 二、市场循环五阶段 (Five-Phase Market Cycle)

| 概念 | 状态 | 代码落点 |
|------|------|---------|
| Accumulation A-E | ✅ | `wyckoff_phase._detect_phase` |
| Distribution A-E | ✅ | `wyckoff_phase._detect_phase` |
| **Markup（上升趋势阶段）** | ✅ | `phase=markup`（BU 或 SOS+站上 TR 上沿） |
| **Markdown（下降趋势阶段）** | ✅ | `phase=markdown`（UTAD 或 UT+SOW+破 TR 下沿） |

---

## 三、积累事件链 (Accumulation Sequence)

| 事件 | 状态 | 说明 |
|------|------|------|
| **PS (Preliminary Support 初步止跌)** | ✅ | `_detect_preliminary_support`；与 SC 互斥让位 |
| SC (Selling Climax 卖力高潮) | ✅ | |
| AR (Automatic Rally 自动反弹) | ✅ | P1 锚点 + P2-C 量能：`WYCKOFF_AR_PREFER_WEAK_VS_SC`（默认开）多候选 prefer 弱于 SC；`ar_volume_soft`=量能偏强/非原典弱量；`REQUIRE` 默认关。落点 `_detect_ar` / `config.py` |
| ST (Secondary Test 二次测试) | ✅ | 广义 ST + L2/L3 门禁；**禁止软确认**；A 股参数放宽（量比/窗/邻近/刺穿）。`st_*`=Spring 确认，与 `secondary_test_sc_*` 分离。规格：`wyckoff-tr-maturity-l0l3-handoff.md` |
| Spring (弹簧/震仓) | ✅ | |
| Test of Spring (Spring 后确认测试) | ✅ | `spring_test_*` 与 `st_*` 双写（`_spring_test_fields_from_st`）；阶段机 C→D 认 Test |
| SOS (Sign of Strength 强势信号) | ✅ | |
| **BU (Back Up 回调买入)** | ✅ | `_detect_backup`（SOS 后缩量回踩） |
| LPS (Last Point of Support 最后支撑点) | ✅ | 与 LPSY 打分互斥 + LPSY 分析层门控 |
| **Jump Across the Creek (跳溪)** | ✅ | `_detect_jump_across_creek` → `jac_signal`/`jac_reason`/`jac_price`；SOS/Markup/BU 附近越过溪站稳；展示灯，不进 fusion |

---

## 四、派发事件链 (Distribution Sequence)

| 事件 | 状态 | 说明 |
|------|------|------|
| **Preliminary Supply (PSY 初步供应)** | ✅ | `_detect_preliminary_supply` |
| BC (Buying Climax 购买高潮) | ✅ | |
| ARE (Automatic Reaction 自动回落) | ✅ | `_detect_are`（BC 后放量回落，对称 AR） |
| **UTAD (Upthrust After Distribution)** | ✅ | `_detect_utad`（须 BC/SOW 背景 + UT） |
| SOW (Sign of Weakness 弱势信号) | ✅ | |
| LPSY (Last Point of Supply 最后供应点) | ✅ | 分析层+打分层派发背景门控；与 LPS 互斥 |
| **Stopping Volume (止跌量)** | ✅ | `_detect_stopping_volume` → `stopping_volume_*`；可与 SC 同亮，打分防双计；展示「止跌量」 |

---

## 五、交易区间（TR）分析

> TR 识别层已落地。阶段机读 `WYCKOFF_PHASE_MIN_TR_QUALITY`；P1/P2 种子箱门控见 `wyckoff-phase-a-range-handoff.md`。  
> **2026-08-01 修正**：`established`（仅 SC+AR）≠ 成熟箱体 / ≠ 可量度。产品分层 **L0–L3**（`tr_maturity`）：无成功 ST 停 L1（雏形）；真 ST → L2 可写「箱体」；L2+宽度 → L3 可量度。分位 TR alone 禁止量度。规格：`docs/plans/wyckoff-tr-maturity-l0l3-handoff.md`。RS 见 §七（已落地）。

| 概念 | 状态 | 说明 |
|------|------|------|
| TR 识别（成交密集区判定） | ✅ | `_detect_trading_range` 宽度/振幅/质量 |
| TR 上下沿计算 | ⚠️ | 分位与 `phase_a_range` 并存；**成熟箱**须 L2（SC+AR+ST）；L1 仅雏形价 |
| TR 量能基线 | ✅ | `tr_baseline_volume` |
| TR 质量门控阶段 | ✅ | `_detect_phase` 读 `MIN_TR_QUALITY`；透出 `phase_tr_gated` |
| TR 种子箱门控（Phase A） | ✅ | P2 阶段门控 + L0–L3 展示/量度门禁（SC+AR 无 ST → 雏形、无量度） |
| TR 成熟度 L0–L3 | ✅ | `tr_maturity` / `measure_allowed` / `box_display_mode`；规格 `wyckoff-tr-maturity-l0l3-handoff.md` |
| TR 持续时间（因果律的基础） | ✅ | `tr_width` + P&F 列数；量度须 L3（`WYCKOFF_MEASURE_MIN_BARS`） |

---

## 六、点数图（Point & Figure）

> **计数已落地**（2026-08-01）；**展示授权**须 L3（同日定稿）。面板仅在 `measure_allowed` 时贴量度行；1:1 fallback 不得冒充「P&F」。规格：计数 `wyckoff-pnf-handoff.md`；门禁 `wyckoff-tr-maturity-l0l3-handoff.md`。

| 概念 | 状态 | 说明 |
|------|------|------|
| P&F 点数图绘制 | ✅ | `wyckoff_pnf.build_pnf_columns`（High-Low + 默认 3 格转向） |
| 垂直计数 (Vertical Count) | ✅ | 水平列不足时的降级：`pnf_method=vertical` |
| 水平计数 (Horizontal Count) | ✅ | 主路径：`pnf_method=horizontal` |
| 量度展示门禁 | ✅ | 仅 `tr_maturity=L3`；禁止 L1/分位箱出目标；1:1 勿冒充 P&F |

---

## 七、相对强弱 (Relative Strength)

| 概念 | 状态 | 说明 |
|------|------|------|
| 个股 vs 对照指数价量对比（RS） | ✅ | 周线阶段**置信修正**（非新阶段）+ **选股池同道排序/弱 RS 慎跟**；对照指数 = `resolve_board_index`；`WYCKOFF_RS_ENABLED`；规格 `docs/plans/wyckoff-rs-phase-handoff.md` |

---

## 八、复合人（Composite Operator）

| 概念 | 状态 | 说明 |
|------|------|------|
| CM 视角 | ✅ | `_classify_cm_mode` → `cm_mode`/`cm_note`（六模式+none）；只读 phase+事件灯映射，不改 phase/fusion |

---

## 九、量价分析 VSA（Volume Spread Analysis）

| 概念 | 状态 | 说明 |
|------|------|------|
| Effort vs Result | ✅ | |
| No Supply（供应耗尽） | ✅ | |
| **No Demand（无需求）** | ⚠️ | 高位缩量滞涨可部分由 PSY/BC 覆盖，未独立命名 |
| Stopping Volume | ✅ | 同 §四；独立专名灯 + 打分防双计 |
| Ultimate Climax | ⚠️ | 与 SC/BC 重叠，未独立命名 |

---

## 十、缺失概念优先级建议（按对当前代码准确度的影响）

| 优先级 | 概念 | 影响 |
|--------|------|------|
| **P0** | TR 识别 + 边界计算 | 所有事件检测的基石（P0-3） |
| **P1** | Markup / Markdown 阶段标签 | 五阶段循环不完整 |
| **P1** | BU (Back Up) | SOS 确认后缺失最后一个买点信号 |
| **P2（已落地）** | P&F 计数（目标价） | ✅ 水平计数主路径 + L3 展示门禁；见 `docs/plans/wyckoff-pnf-handoff.md` |
| **P2（已落地）** | RS 相对强弱 vs 对照指数 | ✅ 已落地（见 §七）；阶段置信 + 池排序/慎跟 |
| **P3（已落地）** | Stopping Volume 专名 | ✅ 独立灯 + 与 SC 防双计；见 §四 |
| **P3（已落地）** | CM 行为模式轻量映射 | ✅ `cm_mode`/`cm_note`；不改阶段/量度 |
| **P3（已落地）** | Jump Across the Creek / AR P2-C | ✅ JAC 专名灯；AR prefer 弱于 SC（REQUIRE 默认关） |
| **P3 余** | UTAD / PS / PSY（已有检测）完整度打磨、Ultimate Climax / No Demand 专名 | 增强完整度 |
