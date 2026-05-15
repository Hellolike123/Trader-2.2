# 左侧化改造计划 - 执行版

## 确认结果

| # | 问题 | 决定 |
|---|------|------|
| 1 | 止损系数 | **保持 0.40**，不收紧 |
| 2 | t0 触发标签 | **C：买 10% / 买 13%** |
| 3 | 跌破支撑 | **C：提示"跌破 XX，继续等待；放量跌破则阻断"** |
| 4 | 有底仓止损 | **改**，补充"跌破 XX 止损" |
| 5 | 熔断面板 | **B：买入：熔断中（止损 X 次触发，当日暂停）** |
| 6 | 熔断时间 | **A：自然日** |
| 7 | 触发条件 | **1 核心 + 1 辅助**（不是 1 个条件） |

## 改动清单（6 个文件）

### 1. t0/config.py — 新增 4 个左侧参数
```python
LEFT_TRIGGER_CORE: int = 1                # 核心条件数
LEFT_TRIGGER_AUX: int = 1                 # 辅助条件数
LEFT_NO_SUPPORT_BLOCK: bool = True        # 跌破主支撑不阻断
LEFT_FUSE_THRESHOLD: int = 2              # 熔断阈值
```

### 2. t0/price_point_engine.py — 4 处改动

**改 2a: 去掉"跌破主支撑"阻断**
```python
# 改前（line ~469-477）:
if current < zone["main_support"] and current < (num(last.get("close")) or current):
    blocked.append("跌破主支撑后未收回")
if (state.get("volume_ratio") or 0) > VOLUME_EXPAND_RATIO and current < zone["main_support"]:
    blocked.append("放量跌破主支撑")
if blocked:
    return trigger_result("被阻断", None, [], blocked)

# 改后:
# 非放量跌破不阻断，降级为提示
# 放量跌破仍阻断
if LEFT_NO_SUPPORT_BLOCK:
    if (state.get("volume_ratio") or 0) > VOLUME_EXPAND_RATIO and current < zone["main_support"]:
        blocked.append("放量跌破主支撑")
    # 不阻断，继续等条件
else:
    # 原逻辑保留
    if current < zone["main_support"] and current < (num(last.get("close")) or current):
        blocked.append("跌破主支撑后未收回")
    if (state.get("volume_ratio") or 0) > VOLUME_EXPAND_RATIO and current < zone["main_support"]:
        blocked.append("放量跌破主支撑")
    if blocked:
        return trigger_result("被阻断", None, [], blocked)
```

**改 2b: 降低触发门槛**
```python
# 改前（line ~515-518）:
if state.get("weak_trend"):
    status = "已触发" if (core_count >= 1 and effective_total >= MIN_TRIGGER_MATCHES - 1) else "观察中"
else:
    status = "已触发" if effective_total >= MIN_TRIGGER_MATCHES and core_count >= 1 else "观察中"

# 改后:
if LEFT_NO_SUPPORT_BLOCK:  # 左侧模式
    status = "已触发" if (core_count >= LEFT_TRIGGER_CORE and aux_count >= LEFT_TRIGGER_AUX) else "观察中"
elif state.get("weak_trend"):
    status = "已触发" if (core_count >= 1 and effective_total >= MIN_TRIGGER_MATCHES - 1) else "观察中"
else:
    status = "已触发" if effective_total >= MIN_TRIGGER_MATCHES and core_count >= 1 else "观察中"
```

**改 2c: AUX 在强趋势下不全清零**
```python
# 改前（line ~513）:
effective_aux = 0 if (state.get("strong_trend") and state.get("di_downtrend")) else aux_count

# 改后（仅左侧模式下）:
if LEFT_NO_SUPPORT_BLOCK and state.get("strong_trend") and state.get("di_downtrend"):
    effective_aux = aux_count  # 左侧模式下 AUX 保留全值（不清零）
else:
    effective_aux = 0 if (state.get("strong_trend") and state.get("di_downtrend")) else aux_count
```

**改 2d: 状态显示优化**
```python
# 触发后状态标签改:
# "已触发" → 根据条件数显示"买 10%"或"买 23%"
if status == "已触发":
    if effective_total >= STRONG_TRIGGER_MATCHES:
        status = "买 23%"   # 强信号，仓位更大
    else:
        status = "买 10%"   # 普通信号
elif LEFT_NO_SUPPORT_BLOCK and blocked_reasons:
    # 有阻断原因但非放量跌破
    if any("跌破主支撑" in b and "放量" not in b for b in blocked_reasons):
        # 降级为提示
        status = "观察中"  # 继续观察
```

### 3. t0/t0_core.py — 改面板标签
```python
# 把面板上的"已触发"改成"买 10%"或"买 23%"
# 根据有效匹配数量决定显示
```

### 4. t0/monitor.py — 熔断告警

```python
# 在 monitor 中:
# 1. 检测熔断条件: 当日止损次数 >= LEFT_FUSE_THRESHOLD
# 2. 输出: "买入：熔断中（止损 X 次触发，当日暂停）"
```

### 5. trader/run_analysis.py — 改决策输出

**改 5a: 决策输出（line 485-489）**
```python
# 改前:
f"状态：{status_text}"
f"  · 空仓 → 在 {low_zone} 止跌确认才试，最多 {position_cap}% 仓位"
f"  · 有底仓 → 反弹 {confirm:.2f} 冲不动就减 10-20%"
f"  · 加仓 → 放量站稳 {confirm:.2f} 且回踩不破，才评估",

# 改后:
f"状态：{status_text}"
f"  · 空仓 → 在 {low_zone} 试探买 {position_cap}%, 止损 {hard_stop:.2f}"
f"  · 有底仓 → 反弹 {confirm:.2f} 冲不动就减 10-20%, 跌破 {hard_stop:.2f} 止损"
f"  · 加仓 → 放量站稳 {confirm:.2f} 且回踩不破，才评估"
```

**改 5b: current_action_text（line 725-734）**
```python
def current_action_text(stage: str, scene: str, hard_stop: float | None = None) -> str:
    if stage == "转弱":
        return "暂不碰"
    if scene == "低吸观察":
        return f"在支撑区试探 {position_cap}%, 跌破 {hard_stop} 止损" if hard_stop else "在支撑区试探"
    if scene == "空间不足":
        return "等待，不追"
    if scene in {"突破确认", "等转强", "冲高减仓"}:
        return "持有观察，不急卖"
    return "等待，不主动追"
```

### 6. decision_core.py — 不需要改动

## 回退测试

跑完所有改动后:
```bash
python3 -m pytest 01-功能包-packages/02-盘中T0-t0-trader/tests/test_indicators_comprehensive.py -q
python3 -m pytest 02-共享模块-shared/tests/ -q
```

## 预期结果

- 测试通过率不变（343 passed）
- 5 个预置失败不变
- 41 个新测试继续通过
