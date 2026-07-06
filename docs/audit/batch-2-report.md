# 第 2 批算法模块审查与修复报告

> **审查日期**：2026-07-07
> **审查分支**：`audit-batch-2-algorithms`（main 保持干净作为安全网）
> **协作模式**：双 Reviewer 并行审查（理论派 + 工程派）→ Arbitrator 裁决+执行
> **审查范围**：6 个算法模块（bayesian_fusion / hmm_regime / main_force / wyckoff_core / chip_distribution / volume_profile）
> **前置依赖**：已包含第 1 批 11 项修复（fund_flow 单位 / None 防御 / 阈值边界 / cache 竞态等）

---

## 一、审查概览

| 维度 | 理论派 Reviewer | 工程派 Reviewer | 交叉验证 |
|------|----------------|----------------|---------|
| P0 | 1 | 2 | 0 |
| P1 | 2 | 2 | 0 |
| P2 | 1 | 4 | 0 |
| 合计 | 4 | 8 | 0 |

**最终裁决**：ACCEPT 6 项 · DEFER 6 项 · REJECT 0 项

两派视角无交叉重叠——理论派聚焦算法正确性（乘积规则/常数广播/背离语义/契约偏离），工程派聚焦边界鲁棒性（None/NaN/KeyError/除零）。互补关系与第 1 批一致。

---

## 二、裁决矩阵

| # | 模块 | 行号 | 原始发现 | 来源 | 原级 | 裁决 | 理由 |
|---|------|------|---------|------|------|------|------|
| 1 | bayesian_fusion.py | 165 | `merge()` 贝叶斯乘积规则缺先验除法，三路 likelihood 均含同一 regime 先验，相乘放大先验 3 次方 | 理论派 | P0 | **DEFER** | 读代码确认 `_expert_likelihood` 返回 `confidence·P(action\|dir,regime) + (1-confidence)·uniform`（条件后验）而非纯似然。正确修复需引入边际先验 P(action)（未存储），属设计变更；且 BAYESIAN_FUSION 默认关闭，风险低。详见关键裁决说明 |
| 2 | chip_distribution.py | 173-178 | 空间过滤自适应阈值（2%/3%/4%）偏离 AGENTS.md 契约固定 4% | 理论派 | P1 | **DEFER** | AGENTS.md L24 明确写"间距 ≥ 4% 且 ≥ 4 bins"。自适应阈值对低价股是合理增强，但偏离契约。改回固定 4% 影响低价股检测，需用户决定改代码还是改契约 |
| 3 | hmm_regime.py | 248-251 | `fit()` 2D 输入 `np.full(len(returns), float(volume_ratio))` 将标量广播为常数序列，第二维度无时序变化 | 理论派 | P1 | **DEFER** | 确认 `volume_ratio: float \| None` 是标量，`np.full` 生成常数序列，2D 退化为 1.5D。修复需改上游传入每日 volume_ratio 序列，属接口设计变更 |
| 4 | wyckoff_core.py | 305-307 | `_detect_volume_divergence` 看多/看空背离用相同量能条件（后半段量萎缩） | 理论派 | P2 | **DEFER** | 涉及算法语义：看多背离的"抛压枯竭"与看空背离的"量能萎缩"用同一条件缺乏区分度，但具体修法需交易理论验证 |
| 5 | main_force.py | 67-73 | `.get(key, 0)` 在值为 None 时返回 None，`cum_5 > 0` 等比较抛 TypeError | 工程派 | P0 | **ACCEPT** | 与第 1 批 fund_flow 同类问题。读代码确认 7 处 `.get(key, default)` 需改为 `.get(key) or default` |
| 6 | hmm_regime.py | 249/254/294/298/331/335 | `np.array(returns, dtype=float)` 遇 None 在 numpy 2.x 抛 ValueError；NaN 透传致 argmax 未定义 | 工程派 | P0 | **ACCEPT** | 确认 6 处 `np.array(returns, dtype=float)` 无 None/NaN 清洗。加 `_clean_floats()` helper 在入口过滤 |
| 7 | wyckoff_core.py | 160/216/256/467/492/516 | 6 处 `b["low"]`/`b["high"]` 直接索引，缺 key 时 KeyError（同文件 L622 却用 `.get()`） | 工程派 | P1 | **ACCEPT** | 读代码确认 6 处不一致。`to_float()` 已处理 None，改 `.get()` 即可 |
| 8 | bayesian_fusion.py | 114-115 | confidence 为 NaN 时 `np.clip(nan,...)` 不处理，posterior 全 NaN，argmax 误选索引 0 | 工程派 | P1 | **ACCEPT** | 确认 NaN 经 clip/blended/weighted 全链路透传，argmax 返回 0（"空仓/止损"）。加 `np.isfinite` 检查 fallback 0.3 |
| 9 | chip_distribution.py | 245 | `current_price=0` 时 `abs(price-current_price)/current_price` 除零 | 工程派 | P2 | **ACCEPT** | 确认 `current_price = valid[-1]["close"]`，close=0 时 ZeroDivisionError。加 `current_price <= 0` 守卫 |
| 10 | bayesian_fusion.py | 126-128 | 大 weight（>20）时 `exp(log·weight)` 数值下溢 | 工程派 | P2 | **DEFER** | 默认权重 1.0/1.5/0.8 不触发；BAYESIAN_FUSION 默认关闭。正确修复应改用 log-sum-exp，非本批范围 |
| 11 | volume_profile.py | 293-295 | `vp["poc"]` 直接索引缺 key 时 KeyError | 工程派 | P2 | **ACCEPT** | 防御性修复，改 `vp.get("poc", 0.0)` 等，低成本 |
| 12 | volume_profile.py | fit 失败 | poc=0.0 而非 None，可能被误认为真实价格 | 工程派 | P2 | **DEFER** | `_fitted` 标志已存在且下游 `assess_vp_breakout` 已检查；改 poc=None 涉及类型契约变更，收益低 |

---

## 三、关键裁决说明

### ★ bayesian_fusion 乘积规则（理论派 P0 → DEFER）

**发现**：`merge()` L165 `posterior = l_chan * l_mom * l_wyk`，三路 likelihood 来自 `_expert_likelihood()`，返回 `confidence·P(action|dir,regime) + (1-confidence)·uniform` 经 log 加权后的归一化向量。这是**条件后验**而非纯似然，乘积放大了共享的 regime 先验。

**裁决 DEFER 的理由**：

1. **正确修复需引入边际先验 P(action)**：标准贝叶斯独立证据融合 `P(A|e1,e2,e3) ∝ P(e1|A)·P(e2|A)·P(e3|A)·P(A)`。若每路返回的是含先验的条件后验 `P(A|ei)`，则乘积含 `P(A)^3`，需除以 `P(A)^(n-1)=P(A)^2`。但代码未存储 P(action) 边际先验，需从 `prior_matrix` 按方向均匀分布计算 `P(action) = mean(prior_matrix, axis=0)`——属设计变更。

2. **朴素修复语义不明确**：`posterior / (prior^(n-1))` 中的 "prior" 若取均匀分布（1/5），则 `uniform^2` 是常数，归一化后不影响 argmax，修复无效；若取某一行条件先验，则各专家方向不同无法选取。必须用边际先验才有意义。

3. **默认关闭风险低**：`BAYESIAN_FUSION = os.environ.get("BAYESIAN_FUSION", "false")`，默认关闭，保持 Trader 2.2 场景优先级权重行为。当前无实际触发路径。

**建议修复方向（供后续批次）**：
```python
# 在 _build_prior 中预计算边际先验
marginal = np.mean(np.vstack([bull, bear, rang]), axis=0)  # 或按 regime 分别计算
# 在 merge 中：
prior_action = self._marginal[regime_state]
posterior = l_chan * l_mom * l_wyk / (prior_action ** 2 + 1e-10)
posterior /= posterior.sum()
```

### hmm_regime 2D 常数广播（理论派 P1 → DEFER）

**发现**：`fit()` L248-251 `obs = np.column_stack([np.array(returns), np.full(len(returns), float(volume_ratio))])`。`volume_ratio` 参数类型是 `float | None`（标量），`np.full` 生成常数序列，第二维度零方差，2D HMM 退化为 1.5D。

**裁决 DEFER 的理由**：这是接口设计问题——`volume_ratio` 语义是"近 5 日均成交额/前 5 日均成交额"的单一标量比率，而非每日时序序列。正确修复需：
1. 上游调用方传入每日 volume_ratio 序列（如 60 日的逐日比率）
2. `fit/predict/fit_predict` 签名改为 `volume_ratios: List[float] | None`
3. 缓存 key 计算同步调整

涉及 `detect_regime` 便捷函数及上游所有调用方（`fusion_core` / `market_env` 等），属跨模块接口变更，非本批范围。

### chip_distribution 自适应阈值（理论派 P1 → DEFER）

**发现**：L173-178 按 `avg_price` 自适应 `min_gap_pct`（<10 用 2%，<50 用 3%，≥50 用 4%），偏离 AGENTS.md L24 契约"间距 ≥ 4% 且 ≥ 4 bins"。

**裁决 DEFER 的理由**：自适应阈值对低价股（如 5 元股票 4%=0.2 元）是合理增强，避免低价股峰过度合并。但契约明确写 4%。二选一：① 改代码回固定 4%；② 更新 AGENTS.md 承认自适应。需用户决定。

---

## 四、修改清单

| # | 文件 | 行号 | 修改类型 | 说明 |
|---|------|------|---------|------|
| 1 | main_force.py | 67-73 | None 防御 | 7 处 `.get(k, default)` → `.get(k) or default`（cum_5/cum_10/con_in/con_out/net_pct/relation/daily_5d） |
| 2 | hmm_regime.py | 30 后新增 | None/NaN 清洗 | 新增 `_clean_floats()` helper，过滤 None/NaN/非数值 |
| 3 | hmm_regime.py | fit/predict/fit_predict/detect_regime | None/NaN 清洗 | 4 个方法入口调用 `_clean_floats(returns)`，共 7 处 |
| 4 | bayesian_fusion.py | 114-115 | NaN 防御 | confidence 加 `np.isfinite` 检查，NaN 时 fallback 0.3 |
| 5 | wyckoff_core.py | 160/216/256/467/492/516 | KeyError 防御 | 6 处 `b["low"]`/`b["high"]` → `b.get("low")`/`b.get("high")`，与 L622 一致 |
| 6 | chip_distribution.py | 245 | 除零守卫 | `current_price <= 0 or` 前置守卫 |
| 7 | volume_profile.py | 293-295 | KeyError 防御 | `vp["poc"]` 等 → `vp.get("poc", 0.0)` 等 3 处 |

**总计**：6 个文件，52 行插入，18 行删除

---

## 五、回归测试结果

### Import 验证（已通过）

```
$ python -c "from trader_shared.wyckoff_core import *;
             from trader_shared.chip_distribution import *;
             from trader_shared.hmm_regime import *;
             from trader_shared.bayesian_fusion import *;
             from trader_shared.main_force import *;
             from trader_shared.volume_profile import *;"
import OK — all 6 modified modules load successfully
```

### 功能验证（5 项关键修复 · 全部通过）

**验证 1 — main_force None 透传防御（L67-73）**

| 输入 | 返回值 | 期望 | 结果 |
|------|--------|------|------|
| features 全 None | `stage=accumulation` | 无 TypeError | ✅ PASS |

> 修复前 `cum_5 > 0`（None > 0）抛 TypeError；修复后 `cum_5 = features.get(...) or 0` → 0，正常进入 fallback 路径。

**验证 2 — hmm_regime None/NaN 清洗（fit/predict/fit_predict/detect_regime）★ 关键**

| 场景 | 输入 | 返回值 | 期望 | 结果 |
|------|------|--------|------|------|
| 含 None+NaN | `[0.01, None, -0.02, NaN, 0.005]*10` | `state=bull` | 无 ValueError | ✅ PASS |
| 全 None | `[None]*50` | `state=range` | 无崩溃 | ✅ PASS |
| 正常数据 | `[0.01,-0.02,...]*10` | `state=bull` | 正常计算 | ✅ PASS |
| _clean_floats 单元 | `[0.1, None, NaN, 0.2, 'x', 0.3]` | `[0.1, 0.2, 0.3]` | 过滤正确 | ✅ PASS |

> 修复前 `np.array([0.01, None, ...], dtype=float)` 在 numpy 2.x 抛 ValueError；修复后入口 `_clean_floats` 过滤，缓存 key 格式化也不崩溃。此验证还暴露并修复了 `detect_regime` 缓存 key 计算中 `f"{r:.6f}"` 对 None 的格式化崩溃（原计划未覆盖，验证中发现）。

**验证 3 — bayesian_fusion confidence NaN 防御（L114-115）**

| 输入 | posterior 含 NaN | action | 期望 | 结果 |
|------|-----------------|--------|------|------|
| confidence=NaN | False | 增持 | 无 NaN | ✅ PASS |
| confidence=0.8（正常） | False | 增持 | 不受影响 | ✅ PASS |

> 修复前 NaN 经 clip/blended/weighted 全链路透传，`np.argmax(all-NaN)` 返回 0（"空仓/止损"）；修复后 NaN fallback 0.3，正常计算。

**验证 4 — volume_profile vp.get 防御（L293-295）**

| 输入 | 返回值 | 期望 | 结果 |
|------|--------|------|------|
| `vp={'fitted': True}`（缺 poc/va_high/va_low） | `vp_signal=va_breakout` | 无 KeyError | ✅ PASS |

**验证 5 — chip_distribution current_price=0 守卫（L245）**

| 输入 | 返回值 | 期望 | 结果 |
|------|--------|------|------|
| close=0 的 120 根 bar | `peaks=3` | 无 ZeroDivisionError | ✅ PASS |

**结论**：5 项关键修复全部通过功能验证，修复语义正确。

---

## 六、遗留问题（DEFER · 需用户决定）

| # | 模块 | 问题 | 暂缓理由 | 建议 |
|---|------|------|---------|------|
| 1 | bayesian_fusion.py L165 | 乘积规则缺先验除法 | 正确修复需引入边际先验 P(action)，属设计变更；BAYESIAN_FUSION 默认关闭 | 后续批次重构 `_expert_likelihood` 返回纯似然，或预计算边际先验并除以 `P(A)^(n-1)` |
| 2 | hmm_regime.py L248-251 | 2D 输入 volume_ratio 标量广播为常数序列 | 修复需改上游传入每日序列，属跨模块接口变更 | 改 `volume_ratio: float` → `volume_ratios: List[float]`，同步改 detect_regime 及上游调用方 |
| 3 | chip_distribution.py L173-178 | 自适应阈值偏离 AGENTS.md 固定 4% | 自适应对低价股是合理增强，但偏离契约 | 二选一：① 改代码回固定 4%；② 更新 AGENTS.md 承认自适应 |
| 4 | wyckoff_core.py L305-307 | 看多/看空背离用相同量能条件 | 涉及算法语义，需交易理论验证 | 看多背离应区分"抛压枯竭"（量萎缩）与"放量吸筹"（量释放）两种场景 |
| 5 | bayesian_fusion.py L126-128 | 大 weight（>20）数值下溢 | 默认权重不触发；正确修复改用 log-sum-exp | 后续重构时统一改用 log-sum-exp 聚合 |
| 6 | volume_profile.py fit 失败 | poc=0.0 而非 None | `_fitted` 标志已存在且下游已检查 | 可选：改 poc 类型为 `float \| None`，fit 失败时设 None |

---

## 七、diff 摘要

```
 bayesian_fusion.py  |  5 +++-      confidence NaN 防御
 chip_distribution.py|  3 ++-       current_price=0 除零守卫
 hmm_regime.py       | 28 ++++++++++++++++++++++  _clean_floats helper + 4 方法入口清洗
 main_force.py       | 15 ++++++------            7 处 None 防御
 volume_profile.py   |  7 +++---    3 处 vp.get 防御
 wyckoff_core.py     | 12 +++++----- 6 处 b["low"] → b.get("low")
 6 files changed, 52 insertions(+), 18 deletions(-)
```

---

## 八、本次协作流程评估

### 视角隔离的价值

本批两派发现**零交叉重叠**，印证了视角隔离的互补性：

- **理论派**独占算法正确性维度：乘积规则缺先验除法（P0）、2D 常数广播（P1）、背离同条件（P2）、契约偏离（P1）——这些都需要从数学/算法语义层面推理，工程派视角无法覆盖。
- **工程派**独占边界鲁棒性维度：None 透传（P0）、NaN 崩溃（P0）、KeyError（P1/P2）、除零（P2）——这些需要从异常输入/边界条件层面推理，理论派视角无法覆盖。

### Arbitrator 裁决的关键判断

1. **bayesian_fusion 乘积规则**：读代码后确认 bug 存在，但判定朴素修复 `posterior/(prior^(n-1))` 语义不明确（prior 取均匀则无效，取条件则方向不同），且默认关闭，选择 DEFER 而非盲修。避免了"修了等于没修"或"引入更严重 bug"的风险。
2. **hmm NaN 清洗**：验证过程中发现 `detect_regime` 缓存 key 的 `f"{r:.6f}"` 格式化对 None 崩溃（原计划只修 np.array），Arbitrator 补充修复了入口清洗，确保全链路 None 安全。

---

## 九、下一步建议

1. **用户审阅本报告 + diff**：`git diff` 查看完整改动
2. **合并到 main**：审阅通过后 `git checkout main && git merge audit-batch-2-algorithms`
3. **DEFER 项处理**：
   - bayesian_fusion 乘积规则：是否启动算法重构（引入边际先验）
   - hmm 2D 接口：是否改为序列输入
   - chip 阈值：改代码还是改契约
4. **第 3 批启动**：本批通过后，按审查计划启动剩余模块审查
