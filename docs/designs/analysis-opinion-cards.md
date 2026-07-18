# 分析层意见卡契约（P0）

> **状态**：P0 冻结  
> **版本**：v0.1 · 2026-07-18  
> **代码**：`trader_shared/analysis_cards.py`（含 `ensure_report_analysis_cards`）  
> **测试**：`tests/test_analysis_opinion_cards_p0.py`（A-01～A-06）· `tests/test_arch_boundaries.py`  
> **上级**：`analysis-strategy-boundaries.md` · `strategy-layered-architecture.md` · `strategy-roadmap-and-tests.md`

---

## 1. 目的

为策略层匹配提供 **稳定、小而全的意见卡**，与报告展示解耦：

- 分析模块可继续返回大 dict  
- 策略 / Skill **只读意见卡**（或 View），不扫 K 线重算  
- 字段名变更必须 bump `schema_version` 并改测试  

---

## 2. 公共信封

每张卡均含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema_version` | str | 固定见各卡 |
| `source` | str | `chan` \| `wyckoff` \| `momentum` \| `chip` \| `vpf` |
| `role` | str | 如 `midline` / `daily` / `report` |
| `raw_available` | bool | 是否有有效分析结果 |

---

## 3. 威科夫卡 `wyckoff_card_v1`

**构建**：`build_wyckoff_card(wyckoff_raw, role=...)`  
**底层**：`resolve_wyckoff_primary` + 可选 `to_wyckoff_state_view`

| 字段 | 类型 | 说明 |
|------|------|------|
| `timeframe` | str | weekly / daily / insufficient / unknown |
| `status` | str | event \| none \| insufficient \| no_data |
| `phase` | str | 原始 phase 或空 |
| `phase_label` | str | 展示用相位文案 |
| `event_code` | str | Spring / UT / — … |
| `event_cn` | str | 弹簧 / 假突破 … |
| `direction` | int | -1 / 0 / +1 |
| `main` | str | 主句白话 |
| `note` | str | 说明 |
| `summary_line` | str | midline 或 daily 一行人话 |
| `tr_ok` | bool | 是否有 TR 上下沿 |
| `bias` | str | bull \| bear \| neutral（弱，不用于下单） |

Skill 单独问威科夫：读 `wyckoff_midline` / `wyckoff_daily` → `build_wyckoff_card`。

---

## 4. 缠论卡 `chan_card_v1`

**构建**：`build_chan_card(chan_raw, fusion_chan=None, wave_label="")`  
**底层**：`resolve_chanlun_primary` + `format_chanlun_short_light`

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | str | point \| divergence \| trend \| none |
| `type_raw` | str | 一类买 / 底背驰 … |
| `type_short` | str | 一买 / 底背驰 … |
| `direction` | int | -1 / 0 / +1 |
| `note` | str | 白话 |
| `same_level` | bool | 是否同级信号 |
| `summary_line` | str | 短线类型优先句（无「缠论：」前缀） |

---

## 5. 动量卡 `momentum_card_v1`

**构建**：`build_momentum_card(momentum_result)`  
**底层**：`momentum_strategy` / fusion `signals_detail.momentum`

| 字段 | 类型 | 说明 |
|------|------|------|
| `direction` | int | |
| `confidence` | float | 0～1 |
| `strength` | str | 可选 |
| `reason` | str | |
| `summary_line` | str | 展示用 |

---

## 6. 筹码卡 `chip_card_v1`

**构建**：`build_chip_card(current, peaks, migration, profit_pct)`  
**底层**：`format_chip_position_light` 逻辑（方案 C）

| 字段 | 类型 | 说明 |
|------|------|------|
| `has_data` | bool | 无峰且无 pct → false，不展示 |
| `support_tag` | str | 支撑弱 / 支撑价文案 |
| `resist_px` | float \| null | 上方阻力价 |
| `resist_tag` | str | 阻力弱 / 阻力 xx |
| `trapped_tag` | str | 套牢面大/中性/小 / 空 |
| `migration_tag` | str | 仅告警时非空 |
| `summary_line` | str | `筹码：…` 或 `""` |

---

## 7. VPF 卡 `vpf_card_v1`（fusion 第三席）

| 字段 | 类型 | 说明 |
|------|------|------|
| `direction` | int | |
| `confidence` | float | |
| `reason` | str | |
| `fund_direction` | int | |
| `vp_direction` | int | |
| `warning_type` | str | |
| `fund_quality` | str | full / missing / … |

---

## 8. 公共上下文卡 `context_card_v1`（策略匹配输入，非理论）

由 report 组装，不在本模块强算：

`current, change_pct, stop, support, confirm, regime, action_kind, has_position, cost, major_stage, allow_new_entry, …`

---

## 9. 口径冻结（P0 文档决策，代码可后改）

| 项 | **现行代码行为** | P0 文档口径 |
|----|------------------|-------------|
| 单日跌幅熔断 | `change_pct < -7.0` 才风险回避（**刚好 -7.0 不触发**） | **维持现状**；产品若要「满 7% 熔断」另开任务改 `<=` 与测试 |
| VPF 资金 vs 天量空 | `fund_conf>=0.55` 时资金优先，可不中性 | **维持现状**；高危 warning 一票否决另开任务 |
| 周线威无 TR | phase none，人话「周线已算 · 定不出」 | 诚实不足，非 bug |
| 日线威进 fusion | 否，第三席 VPF | 维持 |

---

## 10. 非目标（P0）

- 策略匹配引擎  
- 改 fusion 权重  
- 重写缠/威检测  

---

*字段变更：改 `analysis_cards.py` + 本文 + `test_analysis_opinion_cards_p0.py`。*
