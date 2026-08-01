# 威科夫箱体 / 量度成熟度 L0–L3 — Agent Handoff

> **status**: impl_done（Gate+ST+测例绿；面板 view 已接 measure_allowed）  
> **日期**: 2026-08-01  
> **产品法源**: Wyckoff Analytics TR 边界句（SC+ST lows + AR high）；Villahermosa（无 ST 则结构存疑；Phase B 在 ST 后）；A 股适配只放宽**检测参数**、不砍回测语义  
> **对照论证**: 南网科技（SC+AR 种子误标箱体+量度）；上证指数（有回踩无成功 ST → 应停 L1；现系统分位箱能量度 → 违规）；科创50（日线破位新低合理无箱；周线分位箱能量度 → 违规）  
> **读者**: 实现 Agent（只读本文 + 下列代码锚点即可动手）  
> **关联**: `wyckoff-phase-a-range-handoff.md`（P1/P2 种子）；`wyckoff-pnf-handoff.md`（P&F 计数本身不变，**何时允许量度**由本文闸）

---

## 0. 30 秒摘要

1. **问题**：`phase_a_status=established`（仅 SC+AR）被当成成熟「箱体」，并立刻跑 P&F/1:1 量度；分位 TR 无 Phase A/ST 也能量度。  
2. **分层**：L0 无 Phase A → L1 雏形（SC 或 SC+AR，**无成功 ST**）→ L2 可写「箱体」（**真 ST**）→ L3 可量度（L2 + Phase B 宽度）。  
3. **禁止软确认**：「价格仍在 SC 之上 / 未破位」**不得**当 ST，不得抬 L2。  
4. **A 股适配**：只调 ST/SC 的量比、刺穿、等待窗等常量；**保留**回测 SC 区 + 供给变弱。  
5. **不改**：fusion / 出手 / 池分道 / P&F 建图公式；Spring Test（`st_*`）与广义 ST（`secondary_test_sc_*`）继续分离。

---

## 1. 成熟度合同

| 级别 | 字段值 `tr_maturity` | 含义 | 面板箱体 | 量度目标 |
|------|----------------------|------|----------|----------|
| **L0** | `L0` | 无有效 SC（无 Phase A） | 不写箱体/雏形价 | **禁止** |
| **L1** | `L1` | 有 SC，或 SC+AR，但 **无** `secondary_test_sc_signal` | **雏形/候选**（可写下沿/上下沿数字）；**禁止**「箱体 lo-hi」成熟叙事 | **禁止**（清空 `cause_effect_*` 目标或 note 写明未达 L3） |
| **L2** | `L2` | **成功广义 ST**（回测 SC 区 + 量/波幅弱于 SC；未有效破新低） | 可写 **`箱体 lo-hi`**（下沿=`min(sc_low, st_sc_low)`，上沿=`ar_high`；无 AR 则不上沿成熟箱，见下） | **仍禁止**（缺宽度） |
| **L3** | `L3` | L2 **且** Phase B 宽度足够（见 §3） | 同 L2 | **允许** P&F / 显式 1:1 fallback（标签诚实） |

### 1.1 与旧 `phase_a_status` 关系（兼容）

| `phase_a_status` | 典型 `tr_maturity` | 说明 |
|------------------|--------------------|------|
| `none` | `L0` | 无 SC |
| `forming`（仅 SC） | `L1` | 上沿未出；无 ST 更不能 L2 |
| `established`（SC+AR）且无 ST | `L1` | **打破旧语义**：established ≠ 可写成熟箱体 / 可量度 |
| `established` + 成功 ST | `L2` 或 `L3` | 有宽度 → L3 |

**硬规则**：`phase_a_status=established` **不再**单独授权「箱体」文案与 `cause_effect` 数字。

### 1.2 L2 与 AR

原典完整边界：SC/ST lows + AR high。  
- **推荐 L2**：`secondary_test_sc_signal` **且** 有效 `ar_high`。  
- 仅有 ST、无 AR：保持 L1（或透出「下沿已测、上沿未钉」），**禁止**成熟「箱体 lo-hi」，**禁止**量度。

### 1.3 禁止软确认（否决清单）

下列 **一律不算** ST，不得抬 L2：

- 价格仍在 `sc_low` 之上、从未回测 SC 区  
- 「弹上去后横着」但 low 未进入 proximity / 允许刺穿带  
- 回测时量能仍 ≥ SC × `WYCKOFF_ST_SC_VOL_RATIO`（未明显缩量）  
- 有效跌破 SC 且收盘不收回（新低延续 → 失败 Phase A / 仍 L0–L1）

---

## 2. 字段合同（新增 / 行为变更）

### 2.1 分析层透出

```text
tr_maturity: "L0" | "L1" | "L2" | "L3"
tr_maturity_reason: str          # 人话/调试：为何停在本级
measure_allowed: bool            # == (tr_maturity == "L3")
box_display_mode: "none" | "proto" | "box"
  # none=L0；proto=L1；box=L2/L3
```

`phase_a_range` 可附带同名字段，或仅顶栏透出（实现二选一，**顶栏必有** `tr_maturity`）。

### 2.2 种子 overlay / 量度输入

| 场景 | `tr_seed_source` / overlay | `cause_effect_*` |
|------|----------------------------|------------------|
| L0 | 可有分位 TR（事件容器） | **清空目标**；note：`未达 L3（无 Phase A）` |
| L1（含 SC+AR 无 ST） | **可**保留候选 `sc_low`/`ar_high` 供展示雏形；**不得**因种子或分位跑出可展示量度 | **清空目标**；note：`未达 L3（缺成功 ST / 仍为雏形）` |
| L2 | 种子边界 overlay（ST refine 下沿）供箱体与阶段；`tr_seed_source=phase_a_seed` | **清空目标**；note：`未达 L3（箱体已立、宽度不足）` |
| L3 | 同 L2 + 有效 TR 窗 | 正常 `_cause_effect_targets` / P&F |
| 仅分位 TR、无成功 ST | `percentile` | **清空目标**（上证/科创周线对照结论） |

实现要点（`wyckoff_core.wyckoff_analysis`）：

1. 算 `st_sc` → 定 `tr_maturity`。  
2. **仅 L2/L3** 用种子箱做「成熟 TR」overlay（或 L1 overlay 仅标 `proto` 且 `measure_allowed=False`）。  
3. 调用 `_cause_effect_targets` 之后：若 `not measure_allowed`，强制 `cause_effect_up/down_target=None`，保留诚实 note（或根本不调用计数）。  
4. **禁止**静默用分位箱在 L0/L1 出上下目标。

### 2.3 面板文案

| mode | `_phase_a_box_phrase` / 短中线 | `format_cause_effect_display` |
|------|-------------------------------|-------------------------------|
| none | 空或不写箱体段 | 空串 |
| proto | `雏形 下沿 x（上沿未出）` 或 `雏形 x-y（待 ST）`；**禁用**「箱体」一词；中短线**即使**分位 TR 被闸（no_tr/low_quality）也须提示雏形 | 空串 |
| box | `箱体 lo-hi`（仅 L2/L3） | 仅 L3：`量度目标：上 x｜下 y（P&F，非出手）`；若 `pnf_method=height_1to1_fallback` → `（高度1:1，非出手）` 勿冒充 P&F |

短线「仅对照」后缀规则不变。

---

## 3. L3 宽度门槛

在 L2 前提下，满足任一即可进 L3（常量进 `config.py`，可 env）：

| 条件 | 建议默认 | 说明 |
|------|----------|------|
| TR 窗根数 | `WYCKOFF_MEASURE_MIN_BARS=8` | `tr_end - tr_start + 1`（种子窗：SC/ST 起至最新） |
| 或 P&F 水平列 | ≥ `WYCKOFF_PNF_MIN_COLUMNS` | 计数成功且 method=`horizontal` 可直接认宽度 |

若宽度不足：保持 L2，箱体可写、量度清空。

---

## 4. ST 检测（A 股放宽参数，不砍语义）

检测器仍为 `_detect_secondary_test_sc`（`wyckoff_events.py`）。

| 常量 | 现状默认 | A 股建议方向 | 语义红线 |
|------|----------|--------------|----------|
| `WYCKOFF_ST_SC_VOL_RATIO` | 0.60 | 可略放宽至 ~0.70–0.75 | 仍须明显弱于 SC |
| `WYCKOFF_ST_SC_MAX_BARS` | 15 | 可 → 20–25（慢回测） | 仍须发生回测 |
| `WYCKOFF_ST_SC_PROXIMITY` | 0.02 | 可 → 0.03 | 仍须进入 SC 区 |
| `WYCKOFF_ST_SC_MAX_PIERCE` | 0.005 | 可 → 0.01–0.015 | 刺穿须收回；有效破位不算 |

**SC low SSOT**：`sc_low` / ST 回测锚必须是 SC 棒**最低价**（及 refine 后更低的成功 ST low）；禁止用偏高的局部低点当谷底（南网真谷 vs 系统偏高种子对照）。

指数/大盘：SC 量比难达个股阈值 → 可在 `_sc_detector_params` 对 index 放宽 SC，**不是**用软 ST 绕过。

---

## 5. 验收用例（必须有测）

| ID | 用例 | 期望 |
|----|------|------|
| M-R1 | 仅 SC，无 AR/ST | `tr_maturity=L1`；文案雏形/未成形；无量度 |
| M-R2 | SC+AR，无 ST（南网类） | `L1`；**禁止**「箱体 lo-hi」；无量度 |
| M-R3 | SC+AR+缩量回测 ST | ≥`L2`；可「箱体 lo-hi」 |
| M-R4 | M-R3 且窗宽 ≥ MIN_BARS | `L3`；有量度数字 |
| M-R5 | 仅分位 TR、无 SC/ST | `L0`；无量度（即使分位宽很好） |
| M-R6 | 「软确认」：AR 后价格一直高于 sc_low×(1+prox)，无回测 | **无** ST；`L1` |
| M-R7 | `pnf_method=height_1to1_fallback` 且 L3 | 面板不写「P&F」冒充 |
| M-R8 | 现有 wyckoff / pnf 回归 | 门禁相关子集绿；不改 fusion |

---

## 6. 实现顺序与白名单（并行切分）

```text
Agent-Doc（本会话）: 本文 + inventory / pnf-handoff / phase-a-handoff 交叉引用
Agent-Gate:  wyckoff_core.py — tr_maturity、overlay/量度闸、_phase_a_box_phrase
Agent-ST:    config.py + wyckoff_events.py — ST 参数、SC low 锚、禁止软确认（测例 M-R6）
Agent-Render: wyckoff_view.format_cause_effect_display + tests/test_wyckoff_*.py（M-R1…R8）
```

**可改**：`config.py`、`wyckoff_core.py`、`wyckoff_events.py`、`wyckoff_view.py`、相关 tests、本文档族。  
**勿改**：`fusion_core`、池分道、出手、`_detect_st` Spring 语义、P&F 建图主公式（除非 L3 门前短路）。

自测：

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest 02-共享模块-shared/tests/test_wyckoff_core.py 02-共享模块-shared/tests/test_wyckoff_pnf.py 02-共享模块-shared/tests/test_wyckoff_tr.py -q
```

---

## 7. 对照结论（为何改）

| 标的 | 手工分层 | 旧系统问题 | 本文要求 |
|------|----------|------------|----------|
| 南网科技 | SC+AR，无真 ST → L1 | established 种子箱 + 量度 | L1，无箱体词、无量度 |
| 上证指数 | 回踩偏弱 → L1 | 无 SC 却分位箱+量度且跌破下沿 | L0/L1，无量度 |
| 科创50 日线 | 破位新低 → L0/L1 | 日线无箱（碰巧对） | 保持严 |
| 科创50 周线 | 无 ST | 分位箱+量度 | L0，无量度 |

---

## 8. DoD

- [x] `tr_maturity` 透出；M-R1…R8 绿  
- [x] SC+AR 无 ST → 不出现「箱体 lo-hi」、无量度数字  
- [x] 仅分位 TR → 无量度  
- [x] 无软确认路径  
- [x] inventory / pnf-handoff / phase-a-handoff 已指向本文  
- [x] 不扩大 scope 到 fusion / 出手  

验收：`test_cause_effect_display` + `test_wyckoff_tr_maturity` + core/pnf/tr/state_view/report_optimization → **266 passed**（2026-08-01）。 
