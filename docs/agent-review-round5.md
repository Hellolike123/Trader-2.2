# 第 5 轮 Agent 审查报告（agent 审 agent）

**审查日期**: 2026-06-28
**审查范围**: trader_shared 计算模块（4 组并行 agent 审查）
**基线 commit**: 3f720c7（第四轮修复后）
**共发现 12 个 bug**：P0 × 2、P1 × 4、P2 × 6

---

## P0 严重 bug（崩溃 / 错误结果，2 个）

### P0-1: 东方财富资金流向 API 字段映射全部错位
- **文件**: `02-共享模块-shared/trader_shared/fund_flow_data.py:163-175`
- **问题**: 代码假设字段顺序为 `[主力, 超大, 大, 中, 小]`，但实际 API 顺序为 `parts[1]=主力净流入, parts[2]=小单, parts[3]=中单, parts[4]=大单, parts[5]=超大单`。
  - agent 用贵州茅台实时数据验证：`parts[4]+parts[5] = 71M+194M = 265M = parts[1]`，证实 parts[1]=主力(=超大+大)、parts[5]=超大单。
  - 当前代码把 parts[5](超大单) 赋给 `net_flow_wan`，把 parts[1](主力) 赋给 `super_large_wan`，全部错位。
- **影响**: 全系统资金流向数据（`net_flow_wan`/`cum_flow_5d_wan`/`consecutive_inflow_days`/`flow_price_relation`）全部基于错误字段，主力行为识别引擎输入失真。
- **建议修复**:
  ```python
  net_flow   = float(parts[1]) if parts[1] != "-" else super_large + large
  small      = float(parts[2]) if parts[2] != "-" else 0.0
  medium     = float(parts[3]) if parts[3] != "-" else 0.0
  large      = float(parts[4]) if parts[4] != "-" else 0.0
  super_large= float(parts[5]) if parts[5] != "-" else 0.0
  ```

### P0-2: 缠论二类卖点误用底部背离标志作为确认条件
- **文件**: `02-共享模块-shared/trader_shared/chan_core.py:536-539`
- **问题**: `macd_divergence_ok` 由 `_check_macd_for_2nd_buy` 计算（只检测**底部背离**：MACD 为负且回升），但同一变量被传给 `detect_sell_points` 作为二类卖的确认条件。二类卖出现在上涨末端（需**顶部背离**：MACD 为正且走弱），此时 `macd_divergence_ok` 几乎必然为 False，导致二类卖点几乎永不触发。
- **影响**: 缠论卖点检测核心逻辑错误，二类卖（重要卖出信号）失效。
- **建议修复**: 新增 `_check_macd_for_2nd_sell`（检测顶部背离），在 `detect_sell_points` 中使用该结果。

---

## P1 高优先 bug（边界条件错误，4 个）

### P1-1: 跳空日检测死代码，base_idx 永远返回 0
- **文件**: `02-共享模块-shared/trader_shared/stage_positioning.py:149-166`
- **问题**: `gap_indices` 循环排除了 `i==0` 和 `i==len-1`；随后 `base_idx` 循环找"第一个不在 gap_indices 中的索引"，永远返回 0。跳空日检测逻辑被完全旁路，注释声称的"涨停后横盘 4 天不被误判主升"未生效。
- **影响**: 5 日内中间某天涨停后横盘，仍可能误判为"主升"。
- **建议修复**: `base_idx = min(gap_indices) - 1`（若 gap_indices 非空）。

### P1-2: ATR 窗口首根 K 线遗漏前一日收盘价
- **文件**: `02-共享模块-shared/trader_shared/structure_core.py:128-131`
- **问题**: `average_atr_pct` 遍历 `bars[-period:]`，首根 K 线因 `prev_close is None` 退化为 `tr = high - low`，忽略跳空缺口。但当 `len(bars) > period` 时，`bars[-period-1].close` 可用。True Range 定义为 `max(high-low, |high-prev_close|, |low-prev_close|)`，跳空日 TR 被严重低估。
- **影响**: 跳空日的 ATR 被低估，影响 zone_width/stop_buffer 等下游参数。
- **建议修复**: 循环前初始化 `if len(bars) > period: prev_close = to_float(bars[-period-1].get("close"))`。

### P1-3: regime="很差" 时 pattern 权重未归零，违反全员空仓设计
- **文件**: `02-共享模块-shared/trader_shared/fusion_core.py:478-484, 515`
- **问题**: regime="很差" 时 `weights = regime_weights`（无 "pattern" 键），但第 515 行 `weights.get("pattern", 0.10)` 的默认值 0.10 把 pattern 偷偷加回。注释明写"很差 regime pattern 也不加"，实际仍参与加权。
- **影响**: "很差"大盘风控场景下可能给出偏乐观的"等转强观察"动作，而非设计意图的"持股观望"(score=0)。
- **建议修复**: 第 515 行改用 `weights.get("pattern", 0.0)`，或第 479 行显式设 `weights["pattern"] = 0.0`。

### P1-4: HMM 先验参数 mu/sigma 状态1与状态2标签错位
- **文件**: `02-共享模块-shared/trader_shared/hmm_regime.py:59-60`
- **问题**: 先验 `mu=[0.008, -0.008, 0.001]`，按标签 state1="震荡"(range)、state2="下跌"(bear)。但 mu[1]=-0.008（负=bear）却配给了 range 标签，mu[2]=0.001（近零=range）配给了 bear 标签。`fit()` 中 `argsort` 重排仅在 `len(obs)>=30` 时执行，当 3≤len<30 时直接用未重排先验跑 Viterbi，state1 被判"震荡"实为下跌。
- **影响**: 短输入（3~29 个收益率）下大势判断错误。
- **建议修复**: 先验改为 `mu=[0.008, 0.001, -0.008]`, `sigma=[0.01, 0.015, 0.02]`；或将重排逻辑移到 early return 之前。

---

## P2 低概率 bug（6 个）

### P2-1: RSI/MACD 底背离检测 bars 与指标数组索引错位
- **文件**: `structure_core.py:408-410, 475-477`
- **问题**: `closes` 预过滤 None 后 `len(_closes) < len(bars)`，导致 `rsi[-30:]` 对应的并非 `bars[-30:]`，背离判断错位。
- **触发**: bars 中存在 close=None 的 K 线（停牌/数据缺失）。

### P2-2: mom_score 获取在 momentum=None 时崩溃
- **文件**: `fusion_core.py:453`
- **问题**: `momentum_result.get("momentum", {}).get("score", 50)` 当 "momentum" 键存在但值为 None 时，`.get("momentum", {})` 返回 None，`None.get(...)` 抛 AttributeError。不在 try-except 内。
- **建议**: `mom = momentum_result.get("momentum") or {}; mom_score = mom.get("score",50) if isinstance(mom,dict) else 50`。

### P2-3: _check_theory_breakout 威科夫验证永远失效
- **文件**: `decision_core.py:292 → 188-201`
- **问题**: `signals_detail.get("wyckoff")` 取到的是标准化信号（含 direction/confidence/reason），不含原始 spring_signal 等字段，但 `_check_theory_breakout` 仍按原始结构取值，全部返回 False。对比 `structure_core.py:313` 正确用了 reason 关键词匹配。
- **建议**: 改用 `reason` 字段关键词匹配。

### P2-4: calc_adx Wilder 平滑循环 off-by-one
- **文件**: `momentum_core.py:125-132`
- **问题**: 初始化 `tr_s = sum(tr[1:period+1])/period` 已含 `tr[period]`，循环首次 `i=period` 又加权计入，双重计数。同文件 `calc_rsi` 用 `if i > period` 守卫正确规避，`calc_adx` 缺失。
- **建议**: 仿 `calc_rsi` 加 `if i > period:` 守卫。

### P2-5: HMM fit_predict 数据不足分支 state_id 与 label 不一致
- **文件**: `hmm_regime.py:232-236`
- **问题**: `len(obs)<3` 时返回 `state_id=2, state_label="宽幅震荡"`，但 `REGIME_LABELS[2]="高波下跌"`，应为 `state_id=1`。

### P2-6: HMM 缓存 key 仅取末50个收益率
- **文件**: `hmm_regime.py:283-286`
- **问题**: `data_hash` 仅用 `returns[-50:]`，无法区分不同长度/不同标的（末50日相同）的输入，可能串缓存。
- **建议**: cache key 增加 `len(returns)`。

---

## 未发现 bug 的模块
- `chan_core.py` 笔/线段/中枢计算（handle_inclusion/find_fractions/build_strokes/build_zones）✓
- `bayesian_fusion.py` 贝叶斯融合 ✓
- `fusion_regime.py` 大势参数自适应 ✓
- `main_force.py` 主力五阶段判定 ✓
- `main_force_scoring.py` 主力评分 ✓
- `chip_distribution.py` 动态衰减筹码 + 空间去重筹码峰 ✓
- `pattern_core.py` 形态识别（M头/W底/三角形）✓
- `volume_price.py` 量价分析 ✓
- `volume_profile.py` POC/Value Area ✓
- `expma_status.py` EXPMA 状态 ✓
- `multi_timeframe_resonance.py` 多周期共振 ✓
- `indicator_math.py` 指标数学 ✓

---

## 修复优先级建议
1. **立即修（P0）**: P0-1 资金流字段错位（影响全系统主力识别）、P0-2 二类卖失效
2. **尽快修（P1）**: P1-3 pattern 权重（风控场景）、P1-4 HMM 短输入、P1-2 ATR 跳空、P1-1 跳空日检测
3. **择机修（P2）**: 6 个低概率/边界 bug
