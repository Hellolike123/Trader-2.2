# 威科夫 Ghost ST / 过期 SOS / 裸阶段 D — Agent Handoff

> **status**: impl_done（2026-03-22；test_wyckoff_tr+core 224 passed）  
> **日期**: 2026-03-22  
> **承接**: `wyckoff-spring-st-phase-bugfix-handoff.md`  
> **范围**: 误识别收口；**不改** fusion / decision_view / major_stage / 池分道公式

---

## 0. 问题

| ID | 现象 | 误识别 |
|----|------|--------|
| **G1 Ghost ST** | Spring+ST 后破位多日，`st_signal` 仍 True | 假「Spring确认」、阶段 C→D 虚抬、+8 分 |
| **G2 Stale SOS** | 突破后连跌，`lookback_tips=30` 仍亮 SOS | 假强势、bias 偏多、+15 分 |
| **G3 裸 D** | 仅 TrendPullback/TrendRally → `accumulation_d` / `distribution_d` | 均线回踩冒充威科夫 D |

---

## 1. 必须行为

### G1 ST

在既有「真 Spring 锚 + 3–15 根缩量回测」上追加：

1. **近端**：命中的 ST bar 索引 `i` 须满足 `len(bars)-1-i <= WYCKOFF_ST_FRESH_BARS`（默认 **8**）  
2. **未失效**：ST bar 之后至末日，不得出现 `close < support * 0.99`（有效收盘破支撑则整段 ST 灭）

禁止：再引入软确认（价格从未回测仍亮）。

### G2 SOS

主路径 `_detect_sos(..., lookback_tips=RECENT)`：

1. tip 命中：不变  
2. 回扫命中（age>0）额外闸：  
   - 若有 `tr_upper`：末日 `close >= tr_upper * WYCKOFF_SOS_STALE_HOLD_RATIO`（默认 **0.98**）  
   - 若无 `tr_upper`：`age <= WYCKOFF_SOS_STALE_MAX_AGE_NO_TR`（默认 **8**）  
3. 不满足 → 当作未命中，继续往更近 tip 找；全无则 false

`lookback_tips` 默认值可保持 30（搜索窗）；**亮灯**靠 hold/age 闸，不必强砍窗宽。

簇/BU 内 tip-only 不变。

### G3 阶段机裸 D

| 信号 | 有积累/派发背景时 | 无背景时 |
|------|-------------------|----------|
| TrendPullback | 可与 Spring 等组合进 D（既有） | **禁止**单独 `accumulation_d`；`phase=none` 或保持更前命中 |
| TrendRally | 可与 UT 等组合进 D（既有） | **禁止**单独 `distribution_d` |

「有背景」定义（保守）：

- 积累侧：`sc_found or ar_found or (not spring_premature and spring) or compression`（与既有 acc 链一致即可）  
- 派发侧：`bc_found or are_found or (not upthrust_premature and ut_found) or sow_found or compression`

裸 compression → accumulation_b **本单不改**（下轮）。

---

## 2. 可改文件

- `trader_shared/config.py` — 新常量  
- `trader_shared/wyckoff_events.py` — ST / SOS  
- `trader_shared/wyckoff_phase.py` — 裸 TPB/TRL  
- `tests/test_wyckoff_tr.py` / `test_wyckoff_core.py`

---

## 3. 验收

| # | 测 |
|---|-----|
| A | Spring+ST 后破位 → st=False |
| B | ST 在近端且未破 → st=True（回归） |
| C | SOS 20 根前 + 现价远离上沿 → sos=False |
| D | SOS 近端 tip → 仍 True |
| E | 仅 trend_pullback → phase≠accumulation_d |
| F | 仅 trend_rally → phase≠distribution_d |
| G | Spring+B+TPB → 仍可 accumulation_d |
| H | UT+B+TRL → 仍可 distribution_d |

```bash
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_wyckoff_tr.py \
  02-共享模块-shared/tests/test_wyckoff_core.py -q --tb=line
```

---

## 4. 禁止

- 改 fusion / 出手 / major_stage  
- ST 软确认  
- 把 merge 挪到 decision_view 后  
