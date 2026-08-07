# 威科夫 裸压缩 / SOW 连续日 / 阶段 ST tip — Agent Handoff

> **status**: impl_done（2026-03-22；test_wyckoff_tr+core 228 passed）  
> **日期**: 2026-03-22  
> **承接**: `wyckoff-ghost-st-stale-sos-bare-d-handoff.md`  
> **范围**: 误识别续收口；**不改** fusion / decision_view / major_stage

---

## 0. 问题

| ID | 现象 | 必须 |
|----|------|------|
| **G4** | 裸 compression → `accumulation_b（压缩蓄力）` | 无 SC/AR 停止背景时 **不得** 正式标积累 B；可 `phase=none` + 文案点名压缩缺背景。compression **仍可**作 Spring premature 的 B 软背景 / 打分灯 |
| **G5** | SOW `consecutive>1` 时历史日仅 low 刺穿即算 | 历史确认日须 **收盘** `< support`；末日仍：放量 + 收盘破才正式 SOW（既有 ⑤B） |
| **G6** | 阶段机滑窗 ST 可在 tip 已灭时虚抬 Spring+Test→D | 阶段机对 ST/spring_test：**只读 tip**（`signals` 或 `wide_bars` 末日一次 `_detect_st`），**禁止** `_scan` 滑窗复活历史 ST |

---

## 1. 可改

- `wyckoff_phase.py` — G4、G6  
- `wyckoff_events.py` — G5  
- `tests/test_wyckoff_tr.py` / `test_wyckoff_core.py`

---

## 2. 验收

| # | 测 |
|---|-----|
| A | 仅 compression → phase ≠ accumulation_b |
| B | SC+AR+compression → 仍可积累链（A 或 B 合理） |
| C | SOW：先日仅下影刺穿 + 末日收盘破 → 不因「2 日 low」单独成立；先日收盘破 + 末日收盘破放量 → 成立 |
| D | tip ST=False（破位后）时 phase 不因滑窗 ST 进 Spring+Test D |

```bash
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_wyckoff_tr.py \
  02-共享模块-shared/tests/test_wyckoff_core.py -q --tb=line
```

---

## 3. 禁止

- 改 fusion / 出手  
- 砍 compression 打分  
- ST 软确认  
