# Stage Detection Architecture

## Overview

`stage_positioning.py` 的核心函数 `_detect_major_stage` 输出大阶段（蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退），被 `assess_stage()` → report/plan/portfolio 全链路消费。

## Architecture: Main-Force-Driven 3-Layer

```
Layer 1 — Main Force (60%)
  main_force.detect_main_force_stage() → 吸筹/试盘/拉升/派发/砸盘
  wyckoff_core signals → Spring/Upthrust/BC/背离
  ↓
Layer 2 — Volume-Price Confirm (30%)
  _volume_price_confirm() → confirm / downgrade / upgrade
  验证主力信号真假：量价配合则确认，否则降级
  ↓
Layer 3 — Volume-Price Fallback (10%)
  _assess_volume_price() → 兜底（主力数据不可用时）
```

## Key Signatures

```python
def _detect_major_stage(
    current: float,
    ma_values: dict[str, float | None],
    bars: list[dict[str, Any]] | None = None,
    fusion_hint: dict[str, Any] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    chan_result: dict[str, Any] | None = None,
    main_force_result: dict[str, Any] | None = None,
) -> tuple[str, float, str, str]:
```

All new params default None — backward compatible.

## Main Force → Stage Mapping

| main_force stage | major_stage | confidence |
|:--|:--|:--|
| accumulation (吸筹) | 蓄势 | 60 |
| testing (试盘) | 蓄势偏强 | 55 |
| markup (拉升) | 主升 | 70 |
| distribution (派发) | 派发 | 65 |
| markdown (砸盘) | 衰退 | 60 |

## Volume-Price Confirm Rules

| main_force stage | Volume-Price Signal | Action |
|:--|:--|:--|
| markup | 放量上涨 | confirm |
| markup | 缩量/下跌 | downgrade → 蓄势偏强 |
| accumulation | 缩量筑底 | confirm |
| accumulation | 放量下跌 | downgrade → 蓄势偏弱 |
| distribution | 放量滞涨/背离 | confirm |
| distribution | 缩量横盘 | downgrade → 蓄势偏弱 |
| any | Wyckoff Spring | upgrade |
| any | Wyckoff Upthrust | confirm (if distribution) / downgrade otherwise |

## Removed Functions (2026-06-26)

- `_assess_ma_structure()` — replaced by main force + volume-price
- `_assess_atr_volatility()` — replaced by main force + volume-price

## Callers

| Caller | File | Passes main_force_result? |
|:--|:--|:--|
| `assess_stage()` | `stage_positioning.py:770` | Yes (from caller) |
| `build_report()` | `run_analysis.py:487` | Yes (`mf_result` variable) |
