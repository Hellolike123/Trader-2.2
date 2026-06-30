# 入场盈亏比过滤 + Kelly仓位 + 输出增强

## Goal

在入场决策层加入盈亏比过滤器，防止低质量交易信号被输出；同时用 Kelly 公式动态调整仓位，用形态目标修正盈利预期，并在选股池排名页展示盈亏比。

## Requirements

### R1: 入场盈亏比过滤（Plan B）

- `config.py`: 新增 `ENABLE_RISK_REWARD_FILTER`, `RISK_REWARD_THRESHOLDS`
- `run_analysis.py`: 在现有盈亏比计算行（~L1592）后增加场景感知过滤闸门
  - `base_status` 为 "突破确认"/"突破观察" → 跳过过滤
  - 否则按 `market_env_level` → `RISK_REWARD_THRESHOLDS` 取阈值
  - 低于阈值 → 不生成买入价行，显示 "盈亏比 X.XR ✗ 需胜率≥XX%，低于大环境下限 X.X"
  - 高于阈值 → 显示 "盈亏比 X.XR ✓ 需胜率≥XX%"

### R2: Kelly 公式仓位叠加

- 读取 `~/.trader/signal_results.jsonl` 按当前 `market_env` 分桶的历史胜率
- Kelly% = (win_rate × R - (1-win_rate)) / R
- `position_cap = min(stage_positioning_cap, Kelly% × 2 × total_cap)`
- 如果无历史数据或样本<10 → 回退到纯阶段仓位

### R3: Pattern target 修正盈亏比

- 如果 `pattern_result` 存在且 `target > take` → 用 `target` 取代 `take` 计算盈亏比
- 输出显示 "形态目标 XXX.XX元"

### R4: 排序页/计划页显示盈亏比

- `final_pool.py` 在 rank/plan 输出中显示每只票的盈亏比
- 格式：`南网科技 评分76 盈亏比 2.1R ✓ 仓位10%`
- 排序参考分 = 评分 × (1 + min(盈亏比-1, 2) × 0.1)，即有理有据提权

## Acceptance Criteria

- [ ] 低盈亏比场景下买入价被正确过滤，显示拒绝原因
- [ ] 突破确认场景下不过滤
- [ ] 不同 market_env 使用不同阈值（熊市 1.2 / 震荡 1.5 / 牛市 2.0）
- [ ] Kelly 公式正确计算仓位，有历史数据时 < 阶段仓位
- [ ] Pattern target 修正生效，形态检测结果 > take 时用目标价
- [ ] plan/rank 输出显示盈亏比 + 通过/拒绝标记
- [ ] 全量测试通过，0 回归

## Out of Scope

- 不改动 `decision_core.py` / `structure_core.py` — 盈亏比是入场纪律，不是结构定位
- 不改 `review` / `t0` 技能输出（那些是事后分析）
- 不修改 `self_calibration.py` 的离线评分

## Technical Approach

### 修改点清单

| 文件 | 改动量 | 说明 |
|------|--------|------|
| `trader_shared/config.py` | +5 行 | 新增配置项 |
| `run_analysis.py` | ~+50 行 | 过滤闸门 + Kelly + pattern target 修正 |
| `final_pool.py` | ~+20 行 | plan/rank 排序页显示盈亏比 |

### 核心逻辑（run_analysis.py）

```python
# 在 risk_reward_val 计算之后（~L1598）:

# R3: Pattern target 修正
pattern = r.get("pattern_result") or {}
if pattern and pattern.get("target", 0) > take_price:
    take_price = pattern["target"]
    # 重新计算 risk_reward_val
    risk_reward_val = round((take_price - low_price) / downside, 1)

# R1: 场景感知过滤
base_status = r.get("base_status", "")
if base_status in ("突破确认", "突破观察"):
    pass  # 不过滤
elif risk_reward_val is not None and risk_reward_available:
    market_env_level = market_env_data.get("level", "正常")
    threshold = RISK_REWARD_THRESHOLDS.get(market_env_level, 1.5)
    if risk_reward_val < threshold:
        # 过滤：不生成买入行
    else:
        # 通过：生成买入行 + ✓ + 最低胜率

# R2: Kelly 仓位
if risk_reward_available and risk_reward_val > 0:
    from trader_shared.signal_tracker import load_historical_win_rate
    win_rate = load_historical_win_rate(market_env_level)
    if win_rate and win_rate > 0:
        R = risk_reward_val
        kelly = (win_rate * R - (1 - win_rate)) / R
        kelly = max(0, min(kelly, 1))
        kelly_cap = int(kelly * 2 * total_cap)
        position_cap = min(position_cap, kelly_cap)
```

### 测试

- 新加测试在 `02-共享模块-shared/tests/accuracy/` 或 `tests/`
- 验证场景感知过滤逻辑
- 验证 Kelly 公式计算
- 验证 pattern target 修正
- 不破坏已有 760+ 个测试
