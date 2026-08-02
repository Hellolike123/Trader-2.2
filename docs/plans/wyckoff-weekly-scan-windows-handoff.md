# 威科夫周线扫描窗缩放 — Agent Handoff（S1 + S3）

> **状态**: 规格冻结（用户 2026-08-02 确认修软债 S1+S3）  
> **产品法源**: `BUSINESS.md` §2.2；AR 半幅先例见 `wyckoff-structure-anchor-handoff.md` §2.2  
> **非目标**: 不改 fusion / decision_view / 池分道；不改 SC 冷启动 90/39；不改 Spring/SOS/compression/cluster 全面缩放（软债 S4 另案）；不改 `WIDTH_REF`（S2 另案）

---

## 0. 30 秒摘要

1. **S1**：周线阶段机叙事窗≈12 根，但滑窗仍用日线 `window=15` → `_scan_last_event` 在 `n<window` 直接失败。周线滑窗/max_lookback **半幅缩放**（同 AR），且短序列须整段回退。  
2. **S3**：`WYCKOFF_ST_SC_MAX_BARS`（默认 22）周线不缩 ≈5 个月过松。周线 **半幅**（`max(8, ceil(N/2))`，22→11）。  
3. 日线行为不变。

---

## 1. 必须

### 1.1 S1 — 阶段机滑窗周线半幅

| 项 | 日线（现行） | 周线（新） |
|----|--------------|------------|
| `_phase_lookback` / `wide_bars` | 60 | 既有 `max(10, int(60×0.2))=12`（不改） |
| `_scan_for_signal` / `_scan_last_event` 的 `window` | 15 / 16 / 18 / 20 等 | `max(6, ceil(daily_window/2))` |
| `max_lookback_bars` | 30 / 40 | `max(window, ceil(daily_mlb/2))` |
| `_scan_last_event` 短序列 | `n < window` → `(-1, None)` | **须**与 `_scan_for_signal` 一致：整段 `scan_bars` 试探一次；命中则索引=`len-1` |

缩放入口：`wyckoff_phase._tf_scan_params(timeframe, window, max_lookback_bars)`（或等价）；`_detect_phase` 全部滑窗调用经此函数。`timeframe` 已透传（W-01），勿回退默认日线窗。

### 1.2 S3 — 广义 ST 扫描窗周线半幅

| 项 | 日线 | 周线 |
|----|------|------|
| `WYCKOFF_ST_SC_MAX_BARS` 有效值 | config 默认 **22** | `max(8, ceil(22/2))` = **11** |
| 刺穿 / 量比 / 邻近 | 不改 | 不改 |

实现：`_detect_secondary_test_sc` 内按 `timeframe` 算 `st_max`，用于 `st_scan_end` 与 `fail_scan_end` 上沿（破位扫描仍从 SC+1，语义不砍）。

半幅公式与 AR（`WYCKOFF_AR_MAX_BARS` 周线 `max(2, int(N*0.5))`）同族：周线用 **一半根数**，下限防过短。

---

## 2. 禁止

1. 周线阶段机继续用未缩放的 `window=15` 导致叙事窗 12 根时索引序系统性失效。  
2. 用改文档迁就坏代码（禁止删「≈12 周叙事」来回避缩窗）。  
3. 把 SC 冷启动 CAP / Path A 钉住改成「缩窗替代」。  
4. 顺手改 S2（`WIDTH_REF`）/ S4（全事件窗）/ 出手 / fusion。  
5. 日线 `ST_SC_MAX_BARS` / 日线 phase 滑窗数值被周线逻辑改写。

---

## 3. 可改文件白名单

| 文件 | 改什么 |
|------|--------|
| `trader_shared/wyckoff_phase.py` | `_tf_scan_params`；`_detect_phase` 全部滑窗经缩放 |
| `trader_shared/wyckoff_events.py` | `_scan_last_event` 短序列回退；`_st_sc_max_bars_for_tf`；`_detect_secondary_test_sc` 周线 `st_max` |
| `BUSINESS.md` §2.2 | 补「阶段滑窗半幅」「ST 周线半幅」一行 |
| `docs/plans/wyckoff-structure-anchor-handoff.md` §2.2 | 表内交叉引用本文（阶段短窗周线半幅） |
| `docs/plans/wyckoff-tr-maturity-l0l3-handoff.md` §4 | `ST_SC_MAX_BARS` 注明周线半幅 |
| `tests/test_wyckoff_phase_timeframe.py`（或新测） | S1 验收 |
| `tests/test_wyckoff_tr_maturity.py` 或新测 | S3 验收 |

---

## 4. 验收测例（必须有测）

| ID | 用例 | 期望 |
|----|------|------|
| **W-S1a** | `timeframe=weekly` 时 `_tf_scan_params(15, 30)` | `window==8`（ceil 15/2）、`max_lookback_bars==15` |
| **W-S1b** | `_scan_last_event`：`len(bars)=12`、`window=15`、detector 在整段上亮信号 | **不得**恒为 `(-1, None)`；短序列回退后能返回命中索引 |
| **W-S1c** | `_detect_phase(..., timeframe="weekly")` 滑窗调用 | 实际传入 detector 的子窗长度 ≤ 半幅后的 window（可用 spy / 记录）或等价：weekly 路径 `window` 参数经缩放 |
| **W-S3a** | 合成周线：合格 ST 落在 SC/AR 后第 **12** 根（日线窗内、周线半幅外） | `timeframe=weekly` → **不认** ST；`timeframe=daily` 同序列 → **可认**（若其它 ST 条件满足） |
| **W-S3b** | 合成周线：合格 ST 落在半幅内（如 AR 后第 5 根） | `timeframe=weekly` → 可认 ST |

回归：既有 `test_wyckoff_phase_timeframe`（W-01）、`test_wyckoff_tr_maturity` M-R*、structure-anchor 日/周冷启动 **不得**因本改误红（日线夹具不传 weekly）。

---

## 5. 收益 / 风险（验收对照）

| | |
|--|--|
| 收益 | 周线阶段顺序校验重新可用；周线 ST/L2 不再五个月远射 |
| 风险 | 部分票周线 `phase` 换词；慢回测周线 ST 变严（L2 更少） |
| 非目标 | 不追求与日线事件密度一致；不修 WIDTH_REF |

---

## 6. PR 对照清单

- [ ] S1 半幅 + `_scan_last_event` 短序列回退  
- [ ] S3 周线 `st_max` 半幅  
- [ ] BUSINESS §2.2 + 两份既有 handoff 交叉引用  
- [ ] W-S1* / W-S3* 测绿  
- [ ] 日线 M-R* / W-01 回归绿  
