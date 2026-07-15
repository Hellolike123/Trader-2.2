# 威科夫原典概念完整盘点 — 代码落地状态一览

> 整理自：Wyckoff《Studies in Tape Reading》、SMI 经典五阶段教学体系、Ruben Villahermosa《The Wyckoff Methodology in Depth》
> 
> 标注：✅ 已实现  ⚠️ 部分实现/有差距  ❌ 未实现
>
> 审计日期：2026-07-16

---

## 一、三大定律 (Three Laws)

| 概念 | 状态 | 代码落点 |
|------|------|---------|
| 供求律 (Supply & Demand) | ✅ | SC/BC/Spring/Upthrust/量比检测 |
| 因果律 (Cause & Effect) | ❌ | P&F 计数推算目标价：完全未实现 |
| 努力结果律 (Effort vs Result) | ✅ | `_detect_effort_vs_result` (VSA) |

---

## 二、市场循环五阶段 (Five-Phase Market Cycle)

| 概念 | 状态 | 代码落点 |
|------|------|---------|
| Accumulation A-E | ✅ | `wyckoff_phase._detect_phase` |
| Distribution A-E | ✅ | `wyckoff_phase._detect_phase` |
| **Markup（上升趋势阶段）** | ❌ | 无显式阶段标签（accumulation_d 之后没有标记） |
| **Markdown（下降趋势阶段）** | ❌ | 无显式阶段标签（distribution_d 之后没有标记） |

---

## 三、积累事件链 (Accumulation Sequence)

| 事件 | 状态 | 说明 |
|------|------|------|
| **PS (Preliminary Support 初步止跌)** | ❌ | 积累区最早信号，SC 之前的放量止跌。未独立实现 |
| SC (Selling Climax 卖力高潮) | ✅ | |
| AR (Automatic Rally 自动反弹) | ✅ | |
| ST (Secondary Test 二次测试) | ⚠️ | 支撑位是近10根最低价重算而非 Spring 记录的 support（P2-3） |
| Spring (弹簧/震仓) | ✅ | |
| Test of Spring (Spring 后确认测试) | ❌ | 代码用 ST 覆盖，但语义是"二次测试"而非"弹簧后确认" |
| SOS (Sign of Strength 强势信号) | ✅ | |
| **BU (Back Up 回调买入)** | ❌ | **SOS 突破后缩量回调不破突破位。** 与 LPS 不同：BU 在 Markup 初期，LPS 在积累期末端 |
| LPS (Last Point of Support 最后支撑点) | ⚠️ | 与 LPSY 同时触发抵消，已修（P1-1） |
| **Jump Across the Creek (跳溪)** | ❌ | 放量突破 TR 上沿启动 Markup，比 SOS 更急、更连续 |

---

## 四、派发事件链 (Distribution Sequence)

| 事件 | 状态 | 说明 |
|------|------|------|
| **Preliminary Supply (PSY 初步供应)** | ❌ | 派发区最早信号，BC 前的放量滞涨。未独立实现 |
| BC (Buying Climax 购买高潮) | ✅ | |
| AR (Automatic Rally after BC) | ✅ | |
| **UTAD (Upthrust After Distribution)** | ❌ | Upthrust 已实现但通用，UTAD（派发区末端最后假突破）需派发背景（BC/SOW 已存在）才应计数 |
| SOW (Sign of Weakness 弱势信号) | ✅ | |
| LPSY (Last Point of Supply 最后供应点) | ⚠️ | 已加派发背景门控（P1-1） |
| **Stopping Volume (止跌量)** | ❌ | 下跌末端"天量但不继续跌"的量价行为，未独立实现 |

---

## 五、交易区间（TR）分析

> **这是当前最大的功能缺口（P0-3 的基础）。**

| 概念 | 状态 | 说明 |
|------|------|------|
| TR 识别（成交密集区判定） | ❌ | `_is_trading_range` 只是波动过滤器（近20根ATR振幅≤4×ATR%），不是真正的 TR 识别 |
| TR 上下沿计算 | ❌ | 代码用局部滑动极值代替 TR 边界（P0-3） |
| TR 量能基线 | ❌ | 代码用固定窗口均量代替 TR 内的正常量能——窗口含趋势段时基线失真 |
| TR 持续时间（因果律的基础） | ❌ | 代码未将横盘宽度与目标价关联（因果律缺执行层） |

---

## 六、点数图（Point & Figure）

> 因果律的量化执行工具。原典第三大定律的实践。**完全未实现。**

| 概念 | 状态 |
|------|------|
| P&F 点数图绘制 | ❌ |
| 垂直计数 (Vertical Count) — 反弹高度1:1映射目标位 | ❌ |
| 水平计数 (Horizontal Count) — 横盘宽度×每格值算目标 | ❌ |

---

## 七、相对强弱 (Relative Strength)

| 概念 | 状态 | 说明 |
|------|------|------|
| 个股 vs 大盘价量对比 | ❌ | 原典要求始终对比个股与大盘的价量表现来判断 CM 真正意图：强于大盘=吸筹，弱于大盘=派发 |

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
| **No Demand（无需求）** | ❌ | 未作为独立信号实现 |
| Stopping Volume | ❌ | 见派发链 |
| Ultimate Climax | ❌ | 与 SC/BC 有重叠但侧重"终极量"概念 |

---

## 十、缺失概念优先级建议（按对当前代码准确度的影响）

| 优先级 | 概念 | 影响 |
|--------|------|------|
| **P0** | TR 识别 + 边界计算 | 所有事件检测的基石（P0-3） |
| **P1** | Markup / Markdown 阶段标签 | 五阶段循环不完整 |
| **P1** | BU (Back Up) | SOS 确认后缺失最后一个买点信号 |
| **P2** | P&F 计数（目标价） | 因果律执行工具，影响操作目标位 |
| **P2** | RS 相对强弱 vs 大盘 | 影响 CM 意图判断 |
| **P3** | UTAD / PS / PSY / Stopping Volume | 增强完整度 |
| **P3** | CM 行为模式显式建模 | 设计层增强 |
