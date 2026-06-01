# 分批止盈 + 阶段止损 + 条件自动检查

## Goal

实现交易退出策略的三大模块：分批止盈（1R/阻力位/阶段退出）、三层止损（技术/阶段/时间）、加减仓条件自动检查。覆盖"买→持→加→退"全链路。

## 背景

当前系统只实现了：
- ATR 移动止损（`stage_positioning.py:815`）
- 技术止损（`structure_core.py`）
- 文字描述的加仓建议（`run_analysis.py`）

缺失：
- 分批止盈（1R 计算 + 阻力位退出 + 阶段退出）
- 阶段止损（不同阶段不同止损位）
- 时间止损（买入 N 天不涨就走）
- 条件自动检查（系统告诉用户"能不能做"）

## 一、分批止盈

### 1.1 1R 计算

```
风险 R = 买入价 - 止损价
1R 目标 = 买入价 + R

示例：
  买入 57.50，止损 56.11
  R = 57.50 - 56.11 = 1.39
  1R 目标 = 57.50 + 1.39 = 58.89
```

### 1.2 三批退出计划

| 批次 | 触发条件 | 动作 | 原因 |
|------|----------|------|------|
| 第一笔 | 价格达到 1R 目标 | 卖 1/3 | 保本，锁定部分利润 |
| 第二笔 | 价格接近阻力位（距阻力位 ≤ 2%） | 卖 1/3 | 阻力位是"天花板"，先走一部分 |
| 第三笔 | 阶段从主升转派发 | 清仓 | 趋势变了，跟着走 |

### 1.3 与四阶段的联动

```
蓄势期买入：
  1R 止盈 → 可能在蓄势期内就触发（小赚）
  阻力位止盈 → 可能在蓄势区间上沿
  阶段止盈 → 蓄势期不会转派发（除非失败）

主升期买入：
  1R 止盈 → 很快触发（趋势向上）
  阻力位止盈 → 可能在前高附近
  阶段止盈 → 主升转派发时清仓（大赚）

派发期买入：不建议买
衰退期买入：不建议买
```

### 1.4 数据结构

```python
# 返回值结构
{
    "risk_r": 1.39,                    # 风险金额
    "target_1r": 58.89,                # 1R 目标价
    "resistance_exit": 64.00,          # 阻力位退出价（取最近阻力位）
    "stage_exit": "派发",              # 阶段退出条件
    "exit_plan": [
        {"price": 58.89, "ratio": 0.33, "reason": "1R 目标，保本"},
        {"price": 64.00, "ratio": 0.33, "reason": "阻力位，锁定利润"},
        {"price": None,  "ratio": 0.34, "reason": "阶段转派发，清仓"},
    ],
    "already_exited": [False, False, False],  # 哪些已执行
}
```

### 1.5 实现位置

新建函数 `compute_exit_plan()` 在 `stage_positioning.py` 中：

```python
def compute_exit_plan(
    entry_price: float,
    stop_price: float,
    resistance_price: float | None,
    current_stage: str,
    bars: list[dict[str, Any]],
) -> dict[str, Any]:
    """计算分批止盈计划。
    
    Args:
        entry_price: 买入价
        stop_price: 止损价
        resistance_price: 最近阻力位（可选）
        current_stage: 当前阶段（蓄势/主升/派发/衰退）
        bars: K线数据（用于计算动态阻力位）
    
    Returns:
        止盈计划字典
    """
```

## 二、三层止损

### 2.1 技术止损（已实现）

```
止损位 = 关键支撑位下方 2.5%
位置：structure_core.py
```

### 2.2 阶段止损（需实现）

| 阶段 | 止损位 | 原因 |
|------|--------|------|
| 蓄势期 | 蓄势区间下沿 | 保护本金 |
| 主升期 | MA20 | 保护利润 |
| 派发期 | MA20 上方 | 锁定收益 |
| 衰退期 | 不持有 | — |

```python
def compute_stage_stop(
    stage: str,
    ma20: float,
    range_low: float | None,
    atr_pct: float,
) -> float:
    """根据阶段计算止损位。"""
    if stage == "蓄势":
        return range_low  # 蓄势区间下沿
    elif stage == "主升":
        return ma20  # MA20
    elif stage == "派发":
        return ma20 * (1 + atr_pct * 0.5)  # MA20 上方
    else:  # 衰退
        return 0  # 不持有
```

### 2.3 时间止损（需实现）

| 阶段 | 期限 | 动作 |
|------|------|------|
| 蓄势期买入 | 30 天不突破 | 走人 |
| 主升期买入 | 15 天不创新高 | 减仓 |
| 派发期买入 | 不建议 | — |

```python
def check_time_stop(
    entry_date: str,
    current_stage: str,
    days_held: int,
    made_new_high: bool,
) -> dict[str, Any]:
    """检查时间止损。
    
    Returns:
        {"triggered": bool, "action": str, "days_left": int}
    """
```

### 2.4 三层止损汇总

```python
def compute_stop_summary(
    technical_stop: float,
    stage_stop: float,
    time_stop: dict,
    current_price: float,
) -> dict[str, Any]:
    """汇总三层止损，取最近的作为最终止损。"""
    stops = {
        "技术止损": technical_stop,
        "阶段止损": stage_stop,
    }
    nearest = max(stops.values())  # 取最高的（最近的）
    return {
        "final_stop": nearest,
        "stops": stops,
        "time_stop": time_stop,
    }
```

## 三、加仓/减仓/清仓条件自动检查

### 3.1 加仓条件

```python
ADD_POSITION_CONDITIONS = {
    "蓄势→20%": {
        "条件": ["支撑位不破", "缩量横盘3天", "MA收敛"],
        "检查函数": "check_accumulation_add",
    },
    "主升→40%": {
        "条件": ["放量突破", "幅度>3%", "MA多头", "回踩不破"],
        "检查函数": "check_markup_add",
    },
    "回踩→60%": {
        "条件": ["回踩MA20", "回踩<50%", "缩量", "企稳"],
        "检查函数": "check_pullback_add",
    },
    "创新高→80%": {
        "条件": ["放量创新高", "MA20上升"],
        "检查函数": "check_new_high_add",
    },
}
```

### 3.2 减仓条件

```python
REDUCE_CONDITIONS = {
    "派发期减仓": {
        "条件": ["连续3日跌破MA20", "放量", "MA20走平"],
    },
    "主升期转弱": {
        "条件": ["跌破MA20", "连续3日确认"],
    },
}
```

### 3.3 清仓条件

```python
CLEAR_CONDITIONS = {
    "衰退期清仓": {
        "条件": ["MA空头", "放量下跌", "移动止损触发"],
    },
}
```

### 3.4 输出格式

```python
def check_conditions(
    stage: str,
    current_price: float,
    bars: list[dict],
    position_pct: float,
) -> dict[str, Any]:
    """检查加仓/减仓/清仓条件。
    
    Returns:
        {
            "add": {
                "可行": bool,
                "目标仓位": str,
                "条件": [
                    {"name": "支撑位不破", "met": True, "detail": "58.00 未破"},
                    {"name": "缩量横盘3天", "met": False, "detail": "目前1天"},
                ],
                "结论": "⏳ 还差2天缩量横盘",
            },
            "reduce": {...},
            "clear": {...},
        }
    """
```

## 四、输出集成

### 4.1 trader 分析报告

在 `📍 决策` 段落增加：

```
📍 决策
蓄势期 + 修复 → 观察，等确认
  空仓 → 不动手，等放量站稳 62.69
  有底仓 → 持有，跌破 56.11 止损

  止盈计划（买入价 57.50）
    第一笔：58.89 卖 1/3（1R 目标）
    第二笔：64.00 卖 1/3（阻力位）
    第三笔：阶段转派发 清仓

  三层止损
    技术止损：56.11 ｜ 阶段止损：58.00 ｜ 时间止损：30天
    → 阶段止损最近，跌破 58.00 减仓

  条件检查
    加仓：⏳ 还差2天缩量横盘
    减仓：✅ 未触发
    清仓：✅ 未触发
```

### 4.2 review 复盘

在 `📍 条件检查` 段落增加止盈进度：

```
📍 条件检查
止盈进度：
  ✅ 第一笔 58.89 已执行（2026-05-20）
  ⏳ 第二笔 64.00 未触发（当前 59.33）
  ⏳ 第三笔 阶段转派发 未触发

加仓：
  ❌ 缩量横盘不足3天
减仓：
  ✅ 未触发
```

### 4.3 t0 盯盘

在 `🔍 扫描` 段落增加止盈触发价：

```
🔍 扫描
当前：持有
低吸：未触发，57.50元以下
高抛：未触发，62.69元附近
止盈：第一笔 58.89 未触发 ｜ 第二笔 64.00 未触发
止损：56.11元
```

## 五、实现步骤

### Step 1：分批止盈计算
- 在 `stage_positioning.py` 新增 `compute_exit_plan()`
- 接收：买入价、止损价、阻力位、当前阶段、K线
- 返回：三批退出计划

### Step 2：阶段止损计算
- 在 `stage_positioning.py` 新增 `compute_stage_stop()`
- 根据阶段返回不同止损位

### Step 3：时间止损检查
- 在 `stage_positioning.py` 新增 `check_time_stop()`
- 需要买入日期（从 pool.json 或 signals.jsonl 读取）

### Step 4：条件自动检查
- 在 `decision_core.py` 新增 `check_conditions()`
- 检查加仓/减仓/清仓条件，返回每条的 ✅/❌/⏳

### Step 5：输出集成
- 修改 `run_analysis.py` 的输出段落
- 修改 `review_render.py` 的输出段落
- 修改 `t0` 的输出段落

### Step 6：测试
- 单元测试：各计算函数
- 集成测试：完整输出验证

## 六、关键约束

- 止盈计划只在有持仓时计算（空仓不显示）
- 阻力位优先用筹码分布峰位，其次用缠论压力位
- 条件检查的"连续N天"需要从 K 线数据计算，不依赖外部状态
- 时间止损需要买入日期，从 pool.json 的 `entry_date` 字段读取
- 输出格式严格遵守 output-template.md + output-style-guide.md

## 七、验收标准

- [ ] `compute_exit_plan()` 返回正确的三批退出计划
- [ ] `compute_stage_stop()` 根据阶段返回不同止损位
- [ ] `check_time_stop()` 正确计算时间止损
- [ ] `check_conditions()` 返回每条条件的满足状态
- [ ] trader 输出包含止盈计划 + 三层止损 + 条件检查
- [ ] review 输出包含止盈进度
- [ ] t0 输出包含止盈触发价
- [ ] 所有现有测试通过
- [ ] 新增函数有单元测试
