# Trader 报告三轮体检 — 深层数据污染与契约违反

体检时间：2026-06-25 01:42
前提：上两轮 40 项问题已交给其他 agent 修复中，本轮继续深挖新问题。
本轮重点：JSON 报告内部字段一致性、信号生命周期、状态文件污染、数据通道错乱。

样本：江西铜业/三花智控/赣锋锂业 单票 JSON 完整字段 + signals.jsonl（102 条）+ review_state.json + stage_state.json + market_env 字段。

---

## G. 数据通道严重污染（影响整个系统可信度）

### G1. market_env.bars 同时塞了指数数据和个股数据 ⚠️ P0 必修

**现象**：江西铜业 JSON 的 `market_env` 字段：

```
market_env.current: 8793.49    ← 报告的"大盘指数"
market_env.bars: 101 条
  - 11 条指数数据（close 4932-4959，2026-05-05 至 2026-05-04，无 open 字段）
  - 90 条个股数据（close 5.86-9.08，2026-01-12 至 2026-05-29，有 open/high/low/volume）
```

**问题**：
1. `current=8793.49` 与 bars 里的指数数据（最高 4959）差 80%，根本对不上
2. bars 里同时混入了指数数据和某只个股（7-8 元）的 K 线数据
3. 个股 K 线日期（2026-01-12 起）早于指数数据日期（2026-05-05 起），数据源混乱
4. 个股 K 线的 `data_source='tencent-http'`、`data_status='full'`，被当成"市场环境"参与计算

**根因**：`market_env.py` 抓指数时，缓存键冲突或返回数据被错误合并，把个股日线数据塞进了 market_env 的 bars 字段。

**修复**：
1. `market_env.py` 抓取指数时严格校验返回的 close 范围（中证1000 应在 4000-10000 区间）
2. bars 字段只保留指数数据，过滤掉任何带 `open/high/low/volume` 的项
3. 当 bars 的 close 范围跨度过大（如 5-9000）时直接报错，不进入 HMM 计算

---

### G2. HMM confidence=1.0 基于污染数据 ⚠️ P0 必修

**现象**：

```
market_env.hmm_regime_label: 低波上涨
market_env.hmm_confidence: 1.0    ← 100% 置信度
market_env.bars: 混合污染数据（指数+个股）
```

**问题**：HMM 状态机基于混合污染数据算出 100% 置信度，这个"牛市"判断直接进入下游：
- `position_info.market_env='牛市'`
- `fusion.regime='正常'`
- `fusion.hmm_regime='bull'`
- 影响 zone_width / confirm_buffer / stop_buffer 的 Regime Multipliers 缩放

**修复**：
1. HMM 计算前校验输入数据方差，方差过大（指数+个股混合）时拒绝计算
2. confidence=1.0 时应触发二次校验，正常 HMM 不会给出 100% 置信度
3. data_freshness='stale' 时，HMM 结果应降级为"参考"，不进入 Regime Multipliers

---

### G3. market_env.data_freshness='stale' 但仍被使用 ⚠️ 必修

**现象**：

```
market_env.data_status: full
market_env.data_freshness: stale    ← 数据已过期
market_env.level: 正常              ← 仍给出"正常"判定
```

**问题**：数据已过期（stale），但 status 仍是 full，level 仍是"正常"。`stale` 与 `full` 矛盾。

**修复**：data_freshness='stale' 时，data_status 应自动降级为 'partial' 或 'degraded'，level 标注"⚠️ 数据过期"。

---

## H. JSON 报告内部数学矛盾（同一份报告自相矛盾）

### H1. 低吸区上沿 > 高抛区下沿，两区间重叠 ⚠️ 必修

**现象**：江西铜业：

```
low_zone:  46.88-47.82  （低吸区上沿 47.82）
high_zone: 46.81-47.77  （高抛区下沿 46.81）
current:   47.33
```

低吸区上沿 47.82 > 高抛区下沿 46.81，两区间重叠 2.13%。

**问题**：低吸和高抛区域重叠，等于同一价位既"低吸"又"高抛"，逻辑自相矛盾。

**修复**：渲染前 assert `low_zone_upper < high_zone_lower`，违反时报警。

---

### H2. fusion.weighted_score=0.0 与手动计算不符 ⚠️ 必修

**现象**：江西铜业 fusion：

```
signals_detail:
  chan:       direction=1, confidence=0.4
  momentum:   direction=0, confidence=0.44
  wyckoff:    direction=0, confidence=0.2
weights_used:
  chan: 0.3, momentum: 0.45, wyckoff: 0.25
weighted_score: 0.0
```

**手动计算**：
```
加权分 = (1×0.4×0.3) + (0×0.44×0.45) + (0×0.2×0.25) = 0.12
```

但报告 weighted_score=0.0，差 0.12。

**修复**：检查 `fusion_core.py` 的加权分计算，chan direction=1 的正贡献被错误归零。

---

### H3. momentum direction=0 但 reason="MACD柱为正(偏多)" ⚠️ 必修

**现象**：

```
momentum:
  direction: 0      ← 0=中性
  confidence: 0.44
  reason: MACD柱为正(偏多)   ← 文案说偏多
```

**问题**：direction=中性，但 reason 说"偏多"——同一字段内部自相矛盾。

**修复**：MACD 柱为正时 direction 应为 1（偏多），不能文案说偏多但 direction 标中性。

---

### H4. exit_plan.risk_r=1.17 与实际风险回报比 0.44 不符 ⚠️ 必修

**现象**：江西铜业：

```
exit_plan.risk_r: 1.17
exit_plan.target_1r: 48.05
current: 47.33
stop: 45.71
```

**手动计算**：
```
1R = current - stop = 47.33 - 45.71 = 1.62
target_1r 应 = current + 1R = 47.33 + 1.62 = 48.95
实际 target_1r = 48.05
实际风险回报比 = (target-current)/(current-stop) = 0.72/1.62 = 0.44
报告 risk_r = 1.17
```

risk_r 字段（1.17）与实际计算（0.44）差 2.6 倍。

**修复**：检查 `exit_plan` 的 risk_r 计算公式，应该是 `(target-current)/(current-stop)`。

---

### H5. exit_plan 列表 4 项但 already_exited 只 3 项 ⚠️ 必修

**现象**：

```
exit_plan.exit_plan: 4 项（BC信号/阻力位/1R目标/派发清仓）
exit_plan.already_exited: [False, False, False]  ← 只有 3 个
```

**问题**：退出计划 4 项，已退出标记只有 3 个，长度不匹配。第 4 项（派发清仓）永远无法被标记为已退出。

**修复**：already_exited 长度必须等于 exit_plan 长度。

---

### H6. target_1r 低于现价，等于止盈目标已经错过 ⚠️ 必修

**现象**：

| 票 | current | target_1r | 关系 |
|----|---------|-----------|------|
| 三花智控 | 43.90 | 43.77 | target 低于 current 0.30% |
| 赣锋锂业 | 71.62 | 71.78 | target 高于 current 仅 0.22% |
| 江西铜业 | 47.33 | 48.05 | target 高于 current 1.52% |

**问题**：
- 三花智控的止盈目标 43.77 < 现价 43.90，等于"止盈目标已经在脚下"，报告却让用户"等触达"
- 赣锋锂业 target_1r 距现价仅 0.22%，开盘一个跳动就到

**修复**：target_1r 必须 > current × 1.02，否则视为"目标已错过"， fusion action 降级。

---

### H7. position_state.stop_price 与报告 stop 完全不同（4 套止损）⚠️ 必修

**现象**：江西铜业同一报告内 4 套止损价：

```
报告 stop:                  45.71
stage_stop.price:           39.59    （蓄势区间下沿）
position_state.stop_price:  41.96
t0_ref.stop:                45.71
trailing_stop:              None     （AGENTS.md 说有移动止损，实际是 None）
```

**问题**：同一报告 4 套止损价（45.71 / 39.59 / 41.96），最大差距 6.12 元（13%）。`trailing_stop` 还是 None，但 AGENTS.md 明确说"ATR 移动止损"已实现。

**修复**：
1. 报告内只暴露一个"有效止损"= max(stop, trailing_stop, position_state.stop_price)
2. trailing_stop 不能为 None，必须基于 highest_close × (1 - ATR% × 3.0) 计算
3. stage_stop 和 position_state.stop_price 应该一致，或明确说明差异

---

### H8. position_state.position_pct=10 vs position_info.suggested_pct=15 ⚠️ 必修

**现象**：江西铜业同一报告：

```
position_state.position_pct: 10
position_info.suggested_pct: 15
```

**问题**：同一报告两个仓位建议 10% vs 15%，差 50%。操盘手不知道用哪个。

**修复**：position_state 和 position_info 的仓位建议必须一致，或明确分工（一个"建议"、一个"上限"）。

---

### H9. has_position=False 但 position_state 给出加仓建议 ⚠️ 必修

**现象**：

```
has_position: False
position_state.state: 初始建仓
position_state.action: 到达支撑位+短期走强，试探买10%
position_state.position_pct: 10
```

**问题**：没持仓的人，position_state 却给"加仓 10%"建议——语义错误。

**修复**：has_position=False 时，position_state.action 应为"暂无持仓，建议..."，不能是"加仓"。

---

### H10. position_state.conditions 三个互斥状态全 True ⚠️ 必修

**现象**：

```
current: 47.33, support: 46.88, resistance: 47.77
at_support:    True   ← 现价在支撑位
at_resistance: True   ← 现价在阻力位
in_high_zone:  True   ← 现价在高抛区
```

**问题**：现价同时处于"支撑位"、"阻力位"、"高抛区"——三个互斥状态全 True。

**根因**：判定阈值过宽，support ±2% 和 resistance ±2% 区间重叠（46.88-48.37 与 47.39-48.75 重叠）。

**修复**：
1. at_support 阈值收紧到 ±0.5%
2. at_support 和 at_resistance 互斥，不能同时 True
3. in_high_zone 阈值收紧到 high_zone_lower ±1%

---

### H11. fib_retrace 黄金分割全部 None ⚠️ 必修

**现象**：

```
fib_retrace: {
  swing_high: None, swing_low: None,
  retrace_382: None, retrace_500: None, retrace_618: None,
  golden_bid: None
}
```

**问题**：AGENTS.md 明确说"斐波那契黄金挂单位已实现"，但实际所有字段都是 None。

**修复**：检查 `structure_core.py` 的 fib_retrace 计算，swing_high/swing_low 从缠论笔中提取的逻辑可能失效。

---

### H12. exit_plan 第一项 price=None 永远不会触发 ⚠️ 必修

**现象**：

```
exit_plan[0]: {price: None, condition: 'BC 信号出现', triggered: False}
wyckoff_signals.bc_signal: False
wyckoff_signals.bc_reason: '未检测到购买高潮'
```

**问题**：BC 信号未出现，退出计划第一项 price=None——这个退出项永远不会触发，等于死项。

**修复**：bc_signal=False 时，exit_plan 第一项应从列表中移除，或标注"未激活"不参与退出。

---

### H13. win_rate_data=None 但 rank 报告显示回测数据 ⚠️ 必修

**现象**：

```
单票 JSON: win_rate_data: None
rank 报告: "本月已验证 3 次，对了 1 次，准确率 33%"
```

**问题**：单票分析的 win_rate_data 是 None，但 rank 报告却有回测数据——数据来源不一致。

**修复**：单票分析应从 signals.jsonl 加载 win_rate_data，与 rank 共用同一数据源。

---

## I. 信号生命周期严重问题（影响回测可信度）

### I1. signal_id 重复 9 次，违反 Signal Contract v2 ⚠️ P0 必修

**现象**：signals.jsonl 共 102 条，9 个 signal_id 重复：

```
signal_id 7324b9baab5899e3: 重复 9 次（全是南网科技 2025-01-15 observe completed）
signal_id 0b3894e00048b4c5: 重复 9 次
signal_id ae7776866a721328: 重复 5 次
```

**问题**：AGENTS.md 明确承诺"基于 SHA256 deterministic hash 的 16 位 Hex 强一致 UUID，严格规避重复结算"。实际 9 个 ID 重复，最严重的重复 9 次。

**根因**：`normalize_signal_id` 的 hash 输入可能只用了 (name, action)，没包含 trade_date，导致同股同动作的信号 hash 相同。

**修复**：
1. hash 输入必须包含 (name, symbol, trade_date, action, trigger_price)
2. 写入前查重，已存在的 signal_id 拒绝写入
3. 历史重复数据需要去重迁移

---

### I2. 102 条信号全部 direction=bullish/neutral，0 条 bearish ⚠️ P0 必修

**现象**：

```
direction 分布:
  bullish:      48 (47%)
  bullish_lean: 33 (32%)
  neutral:      20 (20%)
  bearish:       0 (0%)
  bearish_lean:  1 (1%)
```

**问题**：系统从不发看空信号。下跌行情中完全失明，等于只在牛市有用。

**修复**：fusion_core 在 weighted_score < -0.2 时应生成 bearish 信号，包括"减仓/清仓/做空观察"动作。

---

### I3. completed 信号 outcome 100% 为 unknown ⚠️ P0 必修

**现象**：

```
completed 信号: 79 条
  outcome=unknown: 79 条 (100%)
  outcome=win/loss: 0 条
```

**问题**：所有"已完成"信号的 outcome 都是 unknown，等于回测数据完全失真。rank 报告显示"准确率 33%"是基于什么算的？

**修复**：
1. 信号 completed 时必须回填 outcome（基于 trade_date 后 N 日的价格变化）
2. outcome_pnl_pct 不能永远是 0.0
3. rank 的"准确率"统计应基于 outcome 字段，不是基于 status

---

### I4. 79 条 completed 信号 outcome_days=1，回测窗口太短 ⚠️ 必修

**现象**：所有 completed 信号的 outcome_days=1。

**问题**：1 天回测窗口太短，无法验证信号有效性。蓄势期信号可能需要 5-10 天才能验证。

**修复**：outcome_days 应根据 signal_type 动态设置：
- observe: 5 天
- low_buy: 3 天
- defensive_watch: 5 天
- track: 10 天

---

## J. 状态文件污染

### J1. review_state.json 残留"票A/票B"测试数据 ⚠️ 必修

**现象**：

```
review_state.json reviews 数组:
  票A 000001.SZ date=2026-05-01 close=10.0  ← 测试数据
  票B 000002.SZ date=2026-05-01 close=20.0  ← 测试数据
  南网科技 ...（真实数据）
```

**问题**：测试数据没清理，污染了 review_state，会被复盘报告读取。

**修复**：
1. 立即清理 review_state.json 中的"票A/票B"
2. 写入时校验 name 不为"票A/票B/test_*"等测试名

---

### J2. stage_state.json 16 个股票全是空字典 {} ⚠️ 必修

**现象**：

```json
{
  "002466.SZ": {},
  "002192.SZ": {},
  ...
}
```

**问题**：16 个股票的 stage_state 全是空字典，等于阶段状态从未被记录。但报告里 major_stage 字段有值（"蓄势"），说明阶段计算每次都重新算，没用到缓存。

**修复**：stage_state 应缓存最近一次的 major_stage / momentum / 计算时间，避免重复计算。

---

### J3. chip_history.json key 命名混乱（两种格式并存）⚠️ 必修

**现象**：

```
55 个 key:
  - 普通格式（如 002460）: 20 个
  - 带日期格式（如 002466_2026-06-02）: 35 个

同一股票多条记录:
  002466: 11 条（002466_2026-06-02 到 002466_2026-06-12）
  002812: 11 条
  002192: 11 条
```

**问题**：key 命名两种格式并存，同一股票最多 11 条历史记录但没清理机制。文件会无限增长。

**修复**：
1. 统一 key 格式为 `{code}_{date}`
2. 每只股票只保留最近 5 条历史
3. 提供清理命令 `trader.py cache clear-chip-history`

---

## K. fusion 层逻辑断层

### K1. fusion.regime='正常' 但 hmm_regime='bull' ⚠️ 必修

**现象**：

```
fusion.regime: 正常
fusion.hmm_regime: bull
market_env.level: 正常
market_env.hmm_regime_label: 低波上涨
```

**问题**：HMM 说"bull/低波上涨"，fusion.regime 却是"正常"——两个 regime 字段不一致。

**修复**：fusion.regime 应直接继承 market_env 的 HMM 判定，不能两个 regime 各算各的。

---

### K2. fusion.disagreement=1 但 confidence=0.093 ⚠️ 必修

**现象**：

```
fusion.disagreement: 1    ← 信号分歧度=1（满分分歧）
fusion.confidence: 0.093  ← 置信度 9.3%
fusion.action: 等转强观察
```

**问题**：disagreement=1 表示信号严重分歧，confidence=9.3% 表示几乎没信心——但 action 仍是"等转强观察"而不是"暂不介入"。

**修复**：disagreement=1 且 confidence<0.15 时，action 应为"信号冲突，暂不介入"，不能是"等转强观察"。

---

### K3. t0_ref 只是单票报告字段的简单复制 ⚠️ 必修

**现象**：

```
t0_ref.low_buy:  46.88 = report.support
t0_ref.high_sell: 47.77 = report.resistance
t0_ref.stop:     45.71 = report.stop
```

**问题**：t0_ref 没有独立的 T0 视角，只是把单票报告的 support/resistance/stop 复制过来。T0 应该有基于分时数据的动态触发价。

**修复**：t0_ref 应基于 5m/15m 分时数据计算，与单票报告的日线 support/resistance 不同。

---

## L. 改进优先级（按操盘价值 × 修复成本）

| 优先级 | 改进项 | 成本 | 操盘价值 |
|--------|--------|------|----------|
| P0 | G1 market_env.bars 指数+个股混合污染 | 中 | ⭐⭐⭐⭐⭐ |
| P0 | G2 HMM confidence=1.0 基于污染数据 | 中 | ⭐⭐⭐⭐⭐ |
| P0 | I1 signal_id 重复 9 次，违反契约 | 低 | ⭐⭐⭐⭐⭐ |
| P0 | I2 102 条信号 0 条 bearish | 中 | ⭐⭐⭐⭐⭐ |
| P0 | I3 completed 信号 outcome 100% unknown | 中 | ⭐⭐⭐⭐⭐ |
| P0 | H2 fusion.weighted_score=0 与计算不符 | 低 | ⭐⭐⭐⭐⭐ |
| P0 | H6 target_1r 低于现价 | 低 | ⭐⭐⭐⭐⭐ |
| P0 | H7 同一报告 4 套止损价 | 中 | ⭐⭐⭐⭐⭐ |
| P1 | H1 低吸区上沿 > 高抛区下沿 | 低 | ⭐⭐⭐⭐ |
| P1 | H4 risk_r=1.17 与实际 0.44 不符 | 低 | ⭐⭐⭐⭐ |
| P1 | H8 仓位建议 10% vs 15% | 低 | ⭐⭐⭐⭐ |
| P1 | H9 has_position=False 却给加仓建议 | 低 | ⭐⭐⭐⭐ |
| P1 | H10 三个互斥状态全 True | 低 | ⭐⭐⭐⭐ |
| P1 | H11 fib_retrace 全部 None | 中 | ⭐⭐⭐⭐ |
| P1 | H13 win_rate_data=None 但 rank 有回测 | 低 | ⭐⭐⭐⭐ |
| P1 | G3 data_freshness=stale 仍被使用 | 低 | ⭐⭐⭐ |
| P1 | K1 fusion.regime 与 hmm_regime 不一致 | 低 | ⭐⭐⭐⭐ |
| P1 | K2 disagreement=1 仍"等转强观察" | 低 | ⭐⭐⭐⭐ |
| P2 | H3 momentum direction=0 但 reason 偏多 | 低 | ⭐⭐⭐ |
| P2 | H5 exit_plan 4 项 already_exited 3 项 | 极低 | ⭐⭐⭐ |
| P2 | H12 BC 信号未出现 exit_plan 含死项 | 低 | ⭐⭐⭐ |
| P2 | I4 outcome_days=1 回测窗口太短 | 低 | ⭐⭐⭐ |
| P2 | J1 review_state 残留测试数据 | 极低 | ⭐⭐⭐ |
| P2 | J2 stage_state 全是空字典 | 低 | ⭐⭐ |
| P2 | J3 chip_history key 命名混乱 | 低 | ⭐⭐ |
| P2 | K3 t0_ref 只是字段复制 | 中 | ⭐⭐⭐ |

---

## M. 给修复 agent 的优先建议

按 ROI 排序，建议先修这 5 个：

1. **G1 + G2（2 小时）**：market_env 数据污染是整个系统的"毒源"，HMM/Regime/仓位缩放全部受影响。修这个等于修半个系统。

2. **I1（30 分钟）**：signal_id 重复违反契约，修 `normalize_signal_id` 的 hash 输入，加入 trade_date。

3. **I2 + I3（2 小时）**：信号系统从不发 bearish + outcome 全 unknown，等于回测数据完全失真。这是"系统自我进化"能力的根基。

4. **H2 + H6 + H7（1 小时）**：加权分计算错误 + target_1r 低于现价 + 4 套止损，三个数学矛盾直接修。

5. **H9 + H10（30 分钟）**：has_position=False 给加仓建议 + 三个互斥状态全 True，逻辑层断言补齐。

修完这 5 项，系统的"数据可信度"和"内部一致性"才能达到操盘手敢用的水平。
