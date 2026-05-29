# ATR 移动止损 + 假跌破确认 + 分阶段退出 — 规格

> 来源：commit c4a3289
> 状态：已实现，本文档为补写

---

## 功能概述

三个相互协作的风险控制机制，共同构成退出策略体系：

1. **ATR 移动止损** — 止损价随股价上涨动态上移
2. **假跌破确认** — 跌破止损后观察是否为假跌破
3. **分阶段退出** — 根据与止损的距离分级响应

---

## 1. ATR 移动止损

### 公式

```
trailing_stop = highest_close × (1 - atr_pct × TRAILING_STOP_ATR_MULTIPLE)
```

- `highest_close`：分析窗口内所有K线的最高收盘价
- `atr_pct`：ATR 百分比（来自 `average_atr_pct()`）
- `TRAILING_STOP_ATR_MULTIPLE`：默认 3.0

### 安全约束

```
trailing_stop = max(trailing_stop, hard_stop)
```

止损价只紧不松，永远不低于原始硬止损。

### 示例

```
股价从 10 涨到 15，ATR% = 3%
trailing_stop = 15 × (1 - 0.03 × 3.0) = 15 × 0.91 = 13.65
若 hard_stop = 14.0 → trailing_stop = max(13.65, 14.0) = 14.0
若 hard_stop = 12.0 → trailing_stop = max(13.65, 12.0) = 13.65
```

### 实现位置

| 文件 | 位置 | 作用 |
|------|------|------|
| `structure_core.py` | `build_structure_context()` 末尾 | 计算 trailing_stop |
| `config.py` | `ENABLE_TRAILING_STOP = True` | 开关 |
| `config.py` | `TRAILING_STOP_ATR_MULTIPLE = 3.0` | ATR 倍数 |
| `run_analysis.py` | `render_markdown()` | 显示"移动止损（ATR）" |

---

## 2. 假跌破确认

### 判定逻辑

```
触发条件: current_price ≤ hard_stop
确认条件: 近 PULLBACK_CONFIRM_DAYS (默认3) 日内
          任一日收盘价 ≥ support
结果: _fake_break = True
```

### 状态映射

| 条件 | base_status | theory_status |
|------|-------------|---------------|
| 跌破止损 + 假跌破确认 | "防守观察" | "防守观察" |
| 跌破止损 + 无假跌破 | "风险回避" | "暂不碰" |

### 注意

- "任一日"条件较宽松，单日反弹即可触发
- 假跌破状态下不触发全面退出，转为观察

### 实现位置

| 文件 | 位置 |
|------|------|
| `decision_core.py` | `status_layers()` 中 `_fake_break` 逻辑块 |
| `config.py` | `PULLBACK_CONFIRM_DAYS = 3` |

---

## 3. 分阶段退出

### 三级升级

```
┌──────────────────────────────────────────────────────┐
│  Level 1: 价格距止损 < 2×ATR                         │
│  → base_status = "冲高减仓"                           │
│  → 策略：逢高减仓，不追空                              │
├──────────────────────────────────────────────────────┤
│  Level 2: 价格跌破 hard_stop（无假跌破）               │
│  → base_status = "风险回避"                           │
│  → theory_status = "暂不碰"                           │
│  → 策略：全面退出                                     │
├──────────────────────────────────────────────────────┤
│  Level 3: 价格跌破 hard_stop + 假跌破确认              │
│  → base_status = "防守观察"                           │
│  → 策略：持有观察，不急于退出                           │
└──────────────────────────────────────────────────────┘
```

### ATR 估算

分阶段退出中的 ATR 近似值：

```python
atr_est = abs(hard_stop - support) / 2  # 或 0.01 取下限
```

注意：这是简化估算，不使用实际 `atr_pct`。

### 实现位置

| 文件 | 位置 |
|------|------|
| `decision_core.py` | `status_layers()` 中 `_near_stop` 逻辑块 |
| `config.py` | `EXIT_PHASED_ENABLED = True` |

---

## 配置项汇总

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `ENABLE_TRAILING_STOP` | bool | True | 移动止损开关 |
| `TRAILING_STOP_ATR_MULTIPLE` | float | 3.0 | ATR 倍数 |
| `PULLBACK_CONFIRM_DAYS` | int | 3 | 假跌破确认回溯天数 |
| `EXIT_PHASED_ENABLED` | bool | True | 分阶段退出开关 |
