# 威科夫 LPSY 背景闸 + 阶段确认事件近端 — Agent Handoff

> **status**: impl_done（2026-03-22；test_wyckoff_tr+core 230 passed）  
> **日期**: 2026-03-22  
> **承接**: `wyckoff-comp-sow-phase-tip-handoff.md`  
> **范围**: 误识别续收口；**不改** fusion / decision_view / major_stage

---

## 0. 问题

| ID | 现象 | 必须 |
|----|------|------|
| **G7** | 阶段机对 Spring/UT/SOS/LPS 全窗滑扫，历史事件可把阶段钉在 C/D，而 tip 灯已灭 | 确认类事件（Spring/UT/SOS/LPS）滑窗 **max_lookback ≤ FRESH**（默认 **12**）；SC/AR/BC/ARE 结构锚保持长窗 |
| **G8** | `_detect_lpsy` 本体无派发背景，仅 analysis 层门控 | 检测器内建背景闸（BC/UT/SOW；可弱扫 BC/UT/SOW），与 UTAD 同构；analysis 层门控可保留双保险 |

---

## 1. 常量

```python
WYCKOFF_PHASE_CONFIRM_FRESH_BARS = 12  # 阶段机确认事件近端
```

---

## 2. 可改

- `config.py`
- `wyckoff_phase.py` — spring/ut/sos/lps scan fresh
- `wyckoff_events.py` — `_detect_lpsy` 背景
- `wyckoff_core.py` — 调用 LPSY 透传背景（可选）
- tests

---

## 3. 验收

| # | 测 |
|---|-----|
| A | LPSY 无 BC/UT/SOW → detector false（gated reason） |
| B | LPSY + tip UT/BC/SOW → 可 true |
| C | Spring 仅在 30 根前、tip 无 → phase 不因长窗扫到而 accumulation_c（signals 不注入 spring） |
| D | 近端 Spring+B → 仍 accumulation_c |

禁止改 fusion/出手。
