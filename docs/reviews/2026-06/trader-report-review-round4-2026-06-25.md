# Trader 报告四轮体检 — 代码级 bug、功能空壳、配置失效

体检时间：2026-06-25 02:05
累计发现：三轮 65 项 + 本轮 22 项 = 87 项

本轮重点：trailing_stop 的 import 导致永远 None、自校准器参数全是 1.0、缓存普遍过期、测试覆盖严重不足、AGENTS.md 中 5 项功能宣称未实际生效。

---

## N. 代码级 bug（运行时静默失败，不报错但功能废了）

### N1. trailing_stop 永远 None — import 路径错误导致 ENABLE_TRAILING_STOP=False ⚠️ P0 必修

**现象**：所有股票的 `trailing_stop` 都是 None，包括南网科技（浮盈 69.9% 应触发紧止损）。

**根因**（已定位到代码）：

`structure_core.py` 第 496 行：
```python
try:
    from config import ENABLE_TRAILING_STOP, TRAILING_STOP_ATR_MULTIPLE
except (ImportError, AttributeError):
    ENABLE_TRAILING_STOP = False
```

`config` 是 `trader_shared` 包的子模块，不能用 `from config import`，正确写法是 `from trader_shared.config import`。当运行环境通过 `pip install -e .` 安装时，`from config import` 必然失败，导致 `ENABLE_TRAILING_STOP=False`，后续所有移动止损计算被跳过。

**同样受影响的文件**：
- `structure_core.py:395` — `from config import THEORY_ADJUST_LOG_ONLY`
- `t0_candidate_core.py:105-107` — `from config import MIN_ZONE_WIDTH_PCT ...`

**修复**：全部改为 `from trader_shared.config import ...` 或 `from .config import ...`。

---

### N2. 自校准器参数全是 1.0，等于从未生效 ⚠️ P0 必修

**现象**：`calibrated_params.json` 所有参数完全相同：

```json
{
  "global": {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 1.0},
  "bull":   {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 1.0},
  "bear":   {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 1.0},
  "range":  {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 1.0}
}
```

AGENTS.md 宣称"基于 HMM regime 对历史信号分桶搜优（bull/bear/range/global），引入盈亏比加权胜率模型仿真打分"，但四个 regime 全部相同参数。等于自校准器输出了初始值后就从未被实际优化过。

**可能根因**：
- 分层搜索收敛到全局最优，没有出现 regime 间差异
- 所有 regime 的信号样本数不够，导致搜优跳过了分桶
- `self_calibration.py` 的仿真打分函数有 bug

**修复**：
1. 排查 `scripts/self_calibration.py` 的分桶搜优逻辑
2. 检查是否每个 regime 的信号样本 >= 20
3. 样本不足时应在 calibrated_params.json 中标注"样本不足，使用全局参数"

---

### N3. api_limits.json 限流计数器时间戳全是 2026-05-23 ⚠️ 必修

**现象**：

```json
{"calls": [1779608638.840808, 1779608638.843328, 1779608638.8497138]}
```

3 个时间戳全是 2026-05-23（一个月前），此后没有任何新的 API 调用被记录。说明限流计数器只在某个特定路径被调用，大多数 API 请求绕过了它。

**修复**：统一 API 调用入口，所有数据请求都经过限流计数器。

---

## O. 功能空壳（AGENTS.md 宣称已实现，实际未生效）

### O1. ATR 移动止损 — 宣称已实现，但全部 None（根因 N1）

AGENTS.md：「ATR 移动止损已实现，trailing_stop = highest_close × (1 - ATR% × 3.0)」

实际：所有股票的 trailing_stop 都是 None。根因见 N1。

---

### O2. 斐波那契黄金挂单位 — 宣称已实现，但 fib_retrace 全 None ⚠️ 必修

AGENTS.md：「斐波那契黄金挂单位 (Golden Bid)：structure_core.py 自动从缠论笔中计算 38.2%/50%/61.8% 黄金分割回调价」

实际：

```json
fib_retrace: {swing_high: null, swing_low: null, retrace_382: null, golden_bid: null}
fib_ext_1382: null, fib_ext_1618: null
```

所有字段 None，markdown 报告里完全没有黄金分割信息。`structure_core.py` 的 swing_high/swing_low 从缠论笔中提取失败。

---

### O3. Volume Profile (POC/Value Area) — 宣称已嵌入，但报告无任何痕迹 ⚠️ 必修

AGENTS.md：「volume_profile.py 计算 POC 控制节点与 Value Area 70% 成交量密集区，已嵌入 decision_core.py 的 _check_theory_breakout」

实际：江西铜业 JSON 报告里没有任何 `poc`/`value_area`/`volume_profile` 相关字段。POC 控制节点和 Value Area 虽然可能在内部计算了，但完全没暴露到报告层，等于没做。

---

### O4. Bayesian Fusion — 默认关闭但 HMM 数据已污染 ⚠️ 必修

AGENTS.md：「bayesian_fusion.py 用乘积规则融合三路专家后验概率。通过设置 BAYESIAN_FUSION=true 激活」

实际：`BAYESIAN_FUSION` 环境变量未设置，功能关闭。但更严重的是：
- 传统融合层的 regime 判断依赖 market_env.HMM，而 HMM 数据已被污染（见第三轮 G1/G2）
- 即使激活 Bayesian Fusion，也会基于被污染的 HMM 数据计算先验概率

---

### O5. 主力行为五阶段识别 — 宣称已实现，但始终 0/15 "无数据" ⚠️ 必修

AGENTS.md：「main_force.py 基于资金流向特征、价格数据和筹码信息，识别吸筹/试盘/拉升/派发/砸盘」

实际：所有股票 `main_force_score = {total_score: 0, label: "🔴无数据"}`。

最新 commit (db0fcaf) 增加了 `calc_fund_flow_features_from_bars` 作为 fallback，但实际运行中仍然 0/15，说明 bars 推导的 fallback 也没生效。

---

## P. 缓存与数据新鲜度系统性失效

### P1. 10/30 daily 缓存的数据停在 5/29-6/18，过期 7-27 天 ⚠️ 必修

**现象**：

| 文件 | 最后日期 | 过期天数 |
|------|----------|----------|
| 002050.json | 2026-05-29 | 27 天 |
| 688248.json | 2026-05-29 | 27 天 |
| 600703.json | 2026-06-22 | 3 天 |
| 002460.json | 2026-06-12 | 13 天 |
| 601899.json | 2026-06-12 | 13 天 |

**问题**：单票分析优先读缓存，缓存过期后分析的 K 线数据就少了最新的 N 天，导致所有技术指标（MA/ATR/EXPMA）基于过期数据计算。

**修复**：
1. 缓存超过 1 个交易日自动刷新
2. `trader.py cache warm` 应支持时间范围参数，默认刷新所有缓存
3. 读取缓存时检查 `last_date < today - 1`，自动触发刷新

---

### P2. fund_flow 缓存全部停在 6/12-6/15，过期 10-13 天 ⚠️ 必修

**现象**：赣锋锂业 fund_flow 最后日期 2026-06-12，今天是 6/25。

**问题**：这就是主力行为"无数据"的直接原因——资金流向数据 13 天没更新，`main_force.py` 没有可用的资金数据。

**修复**：fund_flow 缓存过期时，自动调用东方财富 API 刷新，或 fallback 到 bars 推导。

---

### P3. pipeline_state 大盘环境 8 天未更新，27 只 stock 中 23 只超 5 天 ⚠️ 必修

**现象**：

```
market.updated: 2026-06-17 17:43 （8 天前）
stocks 更新分布:
  2026-06-15: 1 只
  2026-06-18: 1 只
  2026-06-22: 2 只
  2026-06-23: 1 只
  2026-06-25: 1 只
  更早: 23 只（85%）
```

**问题**：pipeline_state 是为了批量分析时避免重复计算，但 85% 的股票状态超过 5 天，意味着批量分析时绝大多数票需要重新计算——pipeline 缓存形同虚设。

**修复**：添加定时 cron 任务自动刷新 pipeline_state，或降低缓存 TTL。

---

## Q. 测试覆盖严重不足（10/16 关键问题无测试）

### Q1. 16 个关键系统中 10 个完全没有测试 ⚠️ 必修

| 功能 | 有无测试 |
|------|----------|
| 移动止损 (trailing_stop) | ✗ |
| 筹码当前价以上占比 | ✗ |
| 筹码中位数 | ✗ |
| 信号 ID 唯一性 | ✗ |
| 信号结果回填 (outcome) | ✗ |
| 市场环境数据 (market_env) | ✗ |
| 1R 目标价 | ✗ |
| 高抛区下沿 | ✗ |
| 持仓状态 | ✗ |
| 黄金分割 (fib_retrace) | ✗ |
| 融合加权分 | ✓ |
| 看空信号 | ✓ |
| 风险回报比 | ✓ |
| 低吸区上沿 | ✓ |
| 数据状态 | ✓ |
| 数据新鲜度 | ✗ |

**问题**：90 个测试全部通过，但 10/16 关键功能没有测试覆盖。说明测试只覆盖了"容易测的"，没覆盖"容易出错的"。

**修复**：在 test_contract.py 或新建 test_internal_consistency.py 中增加：
1. trailing_stop 非 None 验证（有持仓时）
2. chip_current_pct 与 chip_mid_price 数学一致性
3. signal_id 唯一性验证
4. outcome 非 unknown 验证（completed 信号）
5. market_env.bars close 范围合理性（4000-10000）

---

## R. 配置与初始化陷阱

### R1. 持仓文件与单票分析完全脱节 ⚠️ 必修

**现象**：

```
positions.json: 南网科技 2000 股 @ 35.99 / 中国铝业 2000 股 @ 11.50
单票分析南网科技 has_position: False（不带 --cost 参数时）
单票分析南网科技 has_position: True（带 --cost 35.99 时）
```

**问题**：用户已有持仓记录在 `positions.json`，但单票分析不会自动读取。必须每次手动传 `--cost` 参数才能让系统知道你有持仓。南网科技浮盈 69.9%，如果不手动传 --cost，系统会认为你没持仓，给出"试探买"而不是"移动止盈"建议。

**修复**：单票分析时自动从 `positions.json` 读取匹配的持仓记录，优先使用。

---

### R2. pipeline_state.positions 永远是空字典 ⚠️ 必修

**现象**：

```json
pipeline_state.positions: {}
positions.json: 2 笔持仓
```

**问题**：pipeline_state 的 positions 字段永远为空，持仓信息从未被同步到 pipeline。

---

### R3. 融合层只有 3 路信号，主力/筹码/量能未接入 ⚠️ 必修

**现象**：

```
fusion.signals_detail: ['chan', 'momentum', 'wyckoff']
未接入: main_force, chip, volume
```

AGENTS.md 说五维体系（威科夫+缠论+筹码+动量+融合信号），但融合层实际只接入了 3 维。主力行为和筹码变化没有作为信号通道参与加权投票。

**修复**：将 main_force 和 chip_migration 作为独立的专家通道接入 fusion_core，丰富 weighted_score 的输入维度。

---

## S. 其他发现

### S1. stage_state.json 16 个股票全是空字典 ⚠️

**现象**：`stage_state.json` 有 16 个 key 但全部是 `{}`，阶段状态从未被持久化。每次分析都重新计算 major_stage，浪费性能且无法追踪阶段切换历史。

---

### S2. chip_history.json 同时用两种 key 格式，同票最多 11 条无上限 ⚠️

**现象**：55 个 key，20 个是 "002460" 格式，35 个是 "002466_2026-06-02" 格式。天齐锂业(002466)有 11 条记录从 6/2 到 6/12，但之后就没有新增了——说明最近分析时 key 用了不同格式或没写入。

---

### S3. review_state.json 有"票A/票B"测试数据 + 南网科技 2 次重复 ⚠️

**现象**：7 条 reviews 中，2 条是测试数据（票A 000001.SZ / 票B 000002.SZ），1 条是南网科技 5/29 的重叠复盘。

---

### S4. pipeline_state.json.lock 文件大小为 0 ⚠️

**现象**：lock 文件大小为 0 字节——说明 lock 机制正常释放了，但 lock 文件没被删除。这是一种文件系统污染，长期累积会产生大量 0 字节的 `.lock` 文件。

---

## T. 改进优先级（本轮的 5 个 P0）

| 优先级 | 改进项 | 成本 | 操盘价值 |
|--------|--------|------|----------|
| P0 | N1 trailing_stop=None — import 路径 bug | 极低（3 处改一行） | ⭐⭐⭐⭐⭐ |
| P0 | N2 自校准器参数全是 1.0 | 中 | ⭐⭐⭐⭐⭐ |
| P0 | O1-O5 五项功能宣称已实现但实际未生效 | 中 | ⭐⭐⭐⭐⭐ |
| P0 | P1 缓存普遍过期 7-27 天 | 低 | ⭐⭐⭐⭐⭐ |
| P0 | R1 持仓文件与单票分析脱节 | 低 | ⭐⭐⭐⭐⭐ |
| P1 | Q1 10/16 关键功能无测试 | 中 | ⭐⭐⭐⭐ |
| P1 | R3 融合层只有 3 路信号 | 中 | ⭐⭐⭐⭐ |
| P1 | P3 pipeline_state 85% 过期 | 低 | ⭐⭐⭐⭐ |
| P2 | N3 api_limits 一个月未更新 | 低 | ⭐⭐⭐ |
| P2 | R2 pipeline positions 永远为空 | 低 | ⭐⭐⭐ |
| P2 | S1-S4 状态文件污染 | 低 | ⭐⭐ |

---

## U. 给修复 agent 的优先建议

1. **N1（10 分钟）**：改 3 处 `from config import` 为 `from trader_shared.config import`，trailing_stop 立刻恢复
2. **R1（30 分钟）**：单票分析自动读 positions.json，解决持仓脱节
3. **P1（1 小时）**：缓存过期自动刷新机制
4. **O1-O5（3 小时）**：逐一修复 fib_retrace/golden_bid/Volume Profile/Bayesian/main_force 空壳
5. **N2（2 小时）**：排查自校准器，修复参数差异化

四轮累计 87 项问题。修完本轮的 5 个 P0 后，系统的"功能完整性"才能匹配 AGENTS.md 的宣称。
