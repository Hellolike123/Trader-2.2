# 威科夫原典概念完整盘点 — 代码落地状态一览

> 整理自：Wyckoff《Studies in Tape Reading》、SMI 经典五阶段教学体系、Ruben Villahermosa《The Wyckoff Methodology in Depth》
> 
> 标注：✅ 已实现  ⚠️ 部分实现/有差距  ❌ 未实现
>
> 审计日期：2026-07-16（同日二次更新：互斥打分 + 原典缺口补齐）

---

## 一、三大定律 (Three Laws)

| 概念 | 状态 | 代码落点 |
|------|------|---------|
| 供求律 (Supply & Demand) | ✅ | SC/BC/Spring/Upthrust/量比检测 |
| 因果律 (Cause & Effect) | ⚠️ | TR 高度 1:1 投射 `cause_effect_*`（非完整 P&F 点数图） |
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
| AR (Automatic Rally 自动反弹) | ⚠️ | P1 已落地：`_find_sc_anchor` SSOT + `ar_high` 边界价 + `ar_volume_soft`（弱量仍亮）。**余缺口**：AR 后窗仍 ≤7 根（`anchor//2`），延迟 AR 可能 forming；原典「弱于 SC」量能规则 P2 再 soft 化 |
| ST (Secondary Test 二次测试) | ✅ | Phase A 广义 ST（测 SC/AR）→ 独立 `_detect_secondary_test_sc` + `secondary_test_sc_*`（§4.4）。字段 `st_*` 仍保留；语义上现为 Spring 后确认。**禁止**与 Spring Test 混名/混检 |
| Spring (弹簧/震仓) | ✅ | |
| Test of Spring (Spring 后确认测试) | ✅ | `spring_test_*` 与 `st_*` 双写（`_spring_test_fields_from_st`）；阶段机 C→D 认 Test |
| SOS (Sign of Strength 强势信号) | ✅ | |
| **BU (Back Up 回调买入)** | ✅ | `_detect_backup`（SOS 后缩量回踩） |
| LPS (Last Point of Support 最后支撑点) | ✅ | 与 LPSY 打分互斥 + LPSY 分析层门控 |
| **Jump Across the Creek (跳溪)** | ⚠️ | 未专名；强 SOS + Markup/BU 近似表达 |

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
| **Stopping Volume (止跌量)** | ⚠️ | 与 SC/VSA 部分重叠，未独立命名 |

---

## 五、交易区间（TR）分析

> TR 识别层已落地（✅）。阶段机读 `WYCKOFF_PHASE_MIN_TR_QUALITY`（默认 0.35）：低质量/无 TR 时事件可亮、阶段不抬升（`phase_tr_gated`）。**P1**：`phase_a_range`（`sc_low`/`ar_high`/`forming`|`established`）已透出；**P2 已落地**：分位 TR 与 established 种子箱挂门控（forming / 无 established 叠加 P0-B）+ 广义 ST refine 下沿。更大缺口见 §七 RS、§六 P&F。

| 概念 | 状态 | 说明 |
|------|------|------|
| TR 识别（成交密集区判定） | ✅ | `_detect_trading_range` 宽度/振幅/质量 |
| TR 上下沿计算 | ⚠️ | 分位带 tr_upper/tr_lower（刺穿毛刺过滤）与 `phase_a_range` **并存**；established 前分位 TR 不得冒充原典 TR 种子抬阶段；established 时种子 SC/AR 优先 overlay |
| TR 量能基线 | ✅ | `tr_baseline_volume` |
| TR 质量门控阶段 | ✅ | `_detect_phase` 读 `MIN_TR_QUALITY`；透出 `phase_tr_gated` |
| TR 种子箱门控（Phase A） | ✅ | `forming` / 无 `established` 叠加 P0-B；禁止借分位 TR 抬 B/C/D；established 时种子边界 overlay。规格：`wyckoff-phase-a-range-handoff.md` §4.3 |
| TR 持续时间（因果律的基础） | ⚠️ | `tr_width` 透出；目标用高度 1:1 投射，非 P&F 格数 |

---

## 六、点数图（Point & Figure）

> 完整 P&F 仍未做；用 TR 高度 1:1 投射作**工程近似**。

| 概念 | 状态 | 说明 |
|------|------|------|
| P&F 点数图绘制 | ❌ | 未实现 |
| 垂直计数 (Vertical Count) | ⚠️ | 近似：`cause_effect_up/down_target` = 边界 ± TR 高度 |
| 水平计数 (Horizontal Count) | ⚠️ | 同上（用高度而非横盘格数×box） |

---

## 七、相对强弱 (Relative Strength)

| 概念 | 状态 | 说明 |
|------|------|------|
| 个股 vs 对照指数价量对比（RS） | ✅ | 周线阶段**置信修正**（非新阶段）；对照指数 = `resolve_board_index`；`WYCKOFF_RS_ENABLED` 总开关；规格 `docs/plans/wyckoff-rs-phase-handoff.md` |

---

## 八、复合人（Composite Operator）

| 概念 | 状态 | 说明 |
|------|------|------|
| CM 视角 | ⚠️ | 作为设计原则使用，但无显式建模 CM 行为模式（打压吸筹 / 拉高吸筹 / 横盘吸筹 / 拉高派发 / 横盘派发 / 震仓派发） |

---

## 九、量价分析 VSA（Volume Spread Analysis）

| 概念 | 状态 | 说明 |
|------|------|------|
| Effort vs Result | ✅ | |
| No Supply（供应耗尽） | ✅ | |
| **No Demand（无需求）** | ⚠️ | 高位缩量滞涨可部分由 PSY/BC 覆盖，未独立命名 |
| Stopping Volume | ⚠️ | 与 SC/VSA 重叠，未独立命名 |
| Ultimate Climax | ⚠️ | 与 SC/BC 重叠，未独立命名 |

---

## 十、缺失概念优先级建议（按对当前代码准确度的影响）

| 优先级 | 概念 | 影响 |
|--------|------|------|
| **P0** | TR 识别 + 边界计算 | 所有事件检测的基石（P0-3） |
| **P1** | Markup / Markdown 阶段标签 | 五阶段循环不完整 |
| **P1** | BU (Back Up) | SOS 确认后缺失最后一个买点信号 |
| **P2** | P&F 计数（目标价） | 因果律执行工具，影响操作目标位 |
| **P2** | RS 相对强弱 vs 对照指数 | ✅ 已落地（见 §七）；影响阶段置信 / CM 意图判断 |
| **P3** | UTAD / PS / PSY / Stopping Volume | 增强完整度 |
| **P3** | CM 行为模式显式建模 | 设计层增强 |
