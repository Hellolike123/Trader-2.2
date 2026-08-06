# 威科夫 SOS 单日爆发型（Thrust）— Agent Handoff

> **status**: impl_done（南网日线 SOS●45.50 实证；溪内量基线 + SC 后回扫）  
> **日期**: 2026-08-04  
> **SOP 计划**: `workflows/sos-single-day-fix/plans/2026-08-04-wyckoff-sos-single-day.md`  
> **外部交接**: WorkBuddy `wyckoff-sos-修复交接说明.md`（南网科技 688248）  
> **产品/原典**: `docs/audit/wyckoff-original-concept-inventory.md` §三 SOS  
> **读者**: 实现 / 查 Agent（只读本文 + 代码锚点）

---

## 0. 30 秒摘要

1. **问题**：`_detect_sos` 只认近 5 根 ≥4 阳「爬坡型」，漏掉「单日放量大阳 + 收盘站上 TR 上沿」。  
2. **修法**：climb **OR** thrust；climb 阈值不动。  
3. **v1 thrust 必须有 creek**（优先 `ar_high`，否则 `tr_upper`）；二者皆无 **不做** thrust。  
4. **透出** `sos_kind`: `"climb" | "thrust" | None`。  
5. 主分析近端回扫：有 SC 则 SC→今（≤120），须 `min_tip_idx=sc`；簇/BU 滑窗 tip-only=1。  
6. thrust 量基线 = **溪内**（close≤creek）tip 前中位数（勿用含突破日的整段 tr_baseline）。  
7. **不改** fusion / 出手 / 池分道 / JAC 公式 / major_stage。

---

## 1. 必须 / 禁止

### 必须

| # | 合同 |
|---|------|
| M1 | climb：既有 ≥4/5 阳 + 抬高 + 均量×1.2 + 累计涨≥2% 行为不变 |
| M2 | climb 未命中时评估 thrust |
| M3 | thrust AND：阳线 ∧ `close > creek` ∧ `max(开收,昨收涨幅)` ≥5% ∧ `round(量/baseline,2)`≥1.8；creek 优先 `ar_high` 否则 `tr_upper` |
| M4 | **climb** baseline：`tr_baseline_volume` 或前窗均量；**thrust** baseline：溪内 tip 前中位数（`tr_start` 起、close≤creek）；不足 3 根再 fallback robust/均量 |
| M5 | 命中时 `sos_signal=True`，`sos_price=末日 close`，`sos_kind` 正确，`sos_reason` 可区分形态 |
| M6 | 有 pytest 边界矩阵（箱内/涨幅/量比/无 upper/climb 回归） |
| M7 | 引擎只改 `02-共享模块-shared/trader_shared/` |

### 禁止

| # | 合同 |
|---|------|
| P1 | 无 `tr_upper` 时用大阳+放量判 thrust |
| P2 | 降低 climb 的 4/5 阳门槛冒充修复 |
| P3 | 改 fusion / decision_view / 池 / short_midline 主结构 |
| P4 | 在 packages shim 或 skill 解压目录复制引擎正文 |
| P5 | 软确认 ST / 抬 tr_maturity / 改 P&F |
| P6 | 把 SOS 写成可执行开仓指令 |

---

## 2. 字段合同

```text
sos_signal: bool
sos_reason: str
sos_price: float | None
sos_kind: "climb" | "thrust" | None   # 未命中为 None
```

未命中时仍返回三键 + `sos_kind=None`（或省略时分析层视为 None；**实现须显式带 `sos_kind`** 便于测）。

---

## 3. 可改文件白名单

| 文件 | 动作 |
|------|------|
| `docs/plans/wyckoff-sos-single-day-handoff.md` | 本文 |
| `02-共享模块-shared/trader_shared/config.py` | `WYCKOFF_SOS_THRUST_MIN_GAIN` / `WYCKOFF_SOS_THRUST_VOL_RATIO` |
| `02-共享模块-shared/trader_shared/wyckoff_events.py` | `_detect_sos` + import/fallback |
| `02-共享模块-shared/tests/test_wyckoff_core.py` | `TestDetectSosThrust` 等 |
| `docs/audit/wyckoff-original-concept-inventory.md` | SOS 行补 climb+thrust 一句 |

`wyckoff_core` **若**已 `**sos` 展开则无需改；若白名单外透传丢字段再最小补丁。

---

## 4. 验收表

| ID | 场景 | 期望 |
|----|------|------|
| A1 | 箱上 thrust 构造 | SOS● thrust |
| A2 | 箱内大阳 | SOS○ |
| A3 | 涨幅 4.9% / 5.1% | False / True |
| A4 | 量比 1.7 / 1.8+ | False / True |
| A5 | 无 tr_upper | 不 thrust |
| A6 | 旧 climb 4/5 阳 | 仍● climb |
| A7 | thrust 后缩量回踩 | BU 可锚（可选集成） |

---

## 5. 回归调用点（只验证、不改逻辑）

- `wyckoff_core`：`_detect_sos(bars, tr_ctx=event_tr_ctx)`
- `_detect_event_cluster` → `_scan_last_event(..., _detect_sos)`
- `_detect_backup` 近窗回扫 `_detect_sos`
- JAC：SOS 亮后背景门可开（不改 JAC 码）

---

## 6. 回滚

`git revert` 实现 commit；或临时把 `WYCKOFF_SOS_THRUST_MIN_GAIN=0.99`。
