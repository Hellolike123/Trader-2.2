# 威科夫 Spring / ST / 阶段机语义纠偏 — Agent Handoff

> **status**: impl_done（2026-03-22；pytest test_wyckoff_tr + test_wyckoff_core 220 passed）  
> **日期**: 2026-03-22  
> **产品法源**: `docs/audit/wyckoff-original-concept-inventory.md` §三/§九；`config.py` Spring/UT 注释  
> **范围**: 事件分级、ST 锚、阶段 premature、LPS thrust、打分对称；**不改** fusion / decision_view / major_stage

---

## 0. 30 秒摘要

| ID | 问题 | 必须行为 |
|----|------|----------|
| **P0-1** | 缩量 Spring 被标 `weak` 且打分减半，与「供应耗尽可靠」矛盾 | `low_vol_confirm` **不得**因缩量 alone 标 weak；深度+缩量+收回中轴 → **strong**；weak 仅浅刺穿等噪音 |
| **P0-2** | `acc_b_ctx_idx = max(sc,ar,comp)` 使 **Spring 后 compression** 把真 Spring 判 premature | B 背景只认 **事件索引严格早于 Spring/UT** 的路径；之后出现的 compression 不参与 |
| **P1-1** | `_detect_st` 用山寨刺穿条件锚 Spring | ST 必须经 `_detect_spring`（同闸）找到锚点后，再查 3–15 根缩量回测 |
| **P1-2** | LPS 只手写 climb SOS | LPS 锚点须认 `_detect_sos_at_tip`（climb **或** thrust） |
| **P1-3** | 裸 UT（有 B）标 `distribution_a` | 改为 **`distribution_c`（测试：UT）**，对称裸 Spring→C |
| **P1-4** | UT `weak` 不降权 | 与 Spring weak 对称：`upthrust_strength=="weak"` → UT 分减半 |
| **P2-1** | 量价背离可双亮 | 极值须落在窗口后半；双亮时只保留更近极值一侧 |

**延期（本单不做）**：放量 Spring 硬过滤改软信号（`high_vol_warning` 打分死分支）——保持 signal=False + 透传审计字段。

---

## 1. 禁止项

- 禁止改 fusion / 出手 / major_stage / 池分道公式（除消费已有 wyckoff 字段的既有降权文案）
- 禁止软确认 ST（`secondary_test_sc` 合同不变）
- 禁止把 merge 挪到 decision_view 之后
- 禁止凭感觉抬 phase（仅纠标签/premature 索引）

---

## 2. 可改文件

| 文件 | 改动 |
|------|------|
| `trader_shared/wyckoff_events.py` | Spring 分级；ST 锚；LPS tip SOS；背离 |
| `trader_shared/wyckoff_phase.py` | premature B 索引；裸 UT→C |
| `trader_shared/wyckoff_core.py` | UT weak 打分；Spring weak 文案（若需） |
| `trader_shared/config.py` | 仅注释对齐（阈值常量可不改） |
| `tests/test_wyckoff_tr.py` / `test_wyckoff_core.py` | 改期望 + 新测 |

---

## 3. Spring 分级合同（P0-1）

前提：已通过刺穿、收回支撑、2 根窗、非放量 hard filter、`reclaim_ratio >= 0.5`。

| strength | 条件 |
|----------|------|
| **strong** | `depth_pct >= STRONG_DEPTH` **且** `reclaim_ratio >= STRONG_RECLAIM` **且**（`vol_class==low_vol_confirm` **或**（`normal` 且 `vol_ratio >= 1.0`）） |
| **weak** | `depth_pct < WEAK_DEPTH`（浅刺穿噪音） |
| **ordinary** | 其余（含：缩量但深度未达 strong；正常量未齐 strong 三维） |
| **failure** | 不变（未收回 / 放量 hard filter） |

文案：

- strong + low_vol：`深度震仓+缩量供应耗尽+坚决收回中轴，吸筹最强确认`
- strong + normal 量配：`深度震仓+量能配合+坚决收回中轴，吸筹最强确认`
- weak：`刺穿过浅，噪音风险`
- ordinary + low_vol：`缩量洗盘（供应耗尽），标准可靠弹簧`

打分：`spring_strength=="weak"` 仍减半；**low_vol ordinary/strong 全分**。  
测例 `test_weak_spring_grading`：**缩量深刺** → 不得 weak（strong 或 ordinary 按深度）。

---

## 4. premature 合同（P0-2）

对 `spring_idx >= 0`：

```
prior_b = []
if sc_idx>=0 and ar_idx>=0 and sc_idx < spring_idx and ar_idx < spring_idx:
    prior_b.append(max(sc_idx, ar_idx))
if comp_idx>=0 and comp_idx < spring_idx:
    prior_b.append(comp_idx)
if prior_b: premature=False
elif acc_b_ctx and sc_idx<0 and ar_idx<0 and comp_idx<0:
    # 仅 signals 布尔、无扫描索引 → 承认 B（兼容注入测）
    premature=False
else:
    premature=True
```

UT 对称：`bc/are` 均 `< ut_idx`，或 `comp_idx < ut_idx`。

---

## 5. 验收表

| # | 验收 | 测 |
|---|------|-----|
| A | 缩量+深刺+收回中轴 → strong；文案含供应耗尽 | `test_strong_low_vol_spring` / 改 weak 测 |
| B | 浅刺穿 → weak + 打分减半 | `test_weak_spring_*` |
| C | SC→AR→Spring→后 compression → premature=False | 新 phase 测 |
| D | ST 不认「未过 _detect_spring」的假刺穿 | 新 ST 测 |
| E | thrust SOS 后缩量回调可 LPS | 新 LPS 测 |
| F | 裸 UT+B → phase distribution_c | 改/新 phase 测 |
| G | UT weak 打分绝对值减半 | 新 score 测 |
| H | 背离不同时 bullish+bearish | 单元测 |

```bash
python3 -m pytest 02-共享模块-shared/tests/test_wyckoff_tr.py \
  02-共享模块-shared/tests/test_wyckoff_core.py -q --tb=line
```

---

## 6. 查 Agent 对照

- [x] 缩量不再映射 weak  
- [x] premature 不用全局 max(comp)  
- [x] ST 调 `_detect_spring`  
- [x] LPS climb 原窗 + thrust tip  
- [x] 裸 UT=C（压缩 B）  
- [x] UT weak 降权  
- [x] 未碰 fusion/出手  
- [x] 门禁相关：`test_wyckoff_tr.py` + `test_wyckoff_core.py` 220 passed  
