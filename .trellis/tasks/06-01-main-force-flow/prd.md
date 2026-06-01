# 主力资金进出分析 — 三端输出集成

## Goal

在 trader/t0/review 三个 skill 的输出中增加主力资金进出分析段落，让用户一眼看到"主力在干什么"。

## 背景

现有模块已实现：
- `main_force.py` — 五阶段识别（吸筹/试盘/拉升/派发/砸盘）
- `main_force_output.py` — 格式化输出
- `fund_flow_data.py` — **日线级**资金流向（超大单/大单/中单/小单），从东方财富 API 获取
- `big_order.py` — **分钟级**大单异动分析（从5分钟K线推算）
- `fusion_core.py` — 主力阶段修正信号权重

数据模块都有了，缺的是**集成到三端输出**：
- trader 有主力阶段但没有超大单/大单细分
- t0 完全没有资金异动段落
- review 最完整（有主力阶段+大单回溯）

## 一、trader 分析报告

### 位置

在 `🧭 阶段判断` 之后，`📍 决策` 之前，新增 `💰 主力资金` 段落。

### 输出格式

```
💰 主力资金
阶段：吸筹期（置信度 0.7）
近5日：+3200万（↑↑↑↓↑）连续3日净流入
今日：+800万（超大单 +500万｜大单 +300万）
价资关系：量价配合，资金在低位吸筹
提示：连续3日净流入，关注是否放量突破
```

### 字段说明

| 字段 | 来源 | 说明 |
|------|------|------|
| 阶段 | `main_force.py` → `stage` | 吸筹/试盘/拉升/派发/砸盘 |
| 置信度 | `main_force.py` → `confidence` | 0-1 |
| 近5日累计 | `fund_flow_data.py` → `cum_flow_5d_wan` | 万元 |
| 趋势 | `fund_flow_data.py` → `daily_flow_5d` | ↑↓→ 符号 |
| 连续天数 | `fund_flow_data.py` → `consecutive_inflow/outflow_days` | 天 |
| 今日净流入 | `fund_flow_data.py` → `daily_flow_5d[-1]` | 万元 |
| 超大单/大单 | `fund_flow_data.py` → 需新增字段 | 万元 |
| 价资关系 | `main_force.py` → `flow_price_relation` | 文字 |
| 提示 | `main_force_output.py` → `_build_hint()` | 文字 |

### 代码改动

1. `fund_flow_data.py` — 新增 `super_large_wan` 和 `large_wan` 字段到 features
2. `run_analysis.py` — 在 `_fetch_fund_flow()` 中获取超大单/大单数据
3. `run_analysis.py` — 输出段落增加 `💰 主力资金` 段落

### 与现有段落的联动

- `✨ 亮点` 段落：如果主力吸筹期 + 连续净流入，加入"主力在吸筹"
- `⚠️ 风险` 段落：如果主力派发/砸盘期，加入"主力资金持续流出"
- `👉 一句话` 段落：根据主力阶段调整措辞

## 二、t0 盯盘

### 位置

在 `🔍 扫描` 之后，`📋 盘中动态` 之前，新增 `💰 资金异动` 段落。

### 输出格式

```
💰 资金异动
14:35 超大单买入 +500万（主力进场）
10:20 大单卖出 -200万（试探抛压）
09:35 大单买入 +300万（开盘吸筹）
今日净流入：+600万 ｜ 超大单：+500万
```

### 字段说明

| 字段 | 来源 | 说明 |
|------|------|------|
| 时间 | 分钟线数据 | HH:MM |
| 方向 | 主动买入/卖出 | 买入/卖出 |
| 金额 | 大单金额 | 万元 |
| 类型 | 超大单/大单 | 根据金额阈值判断 |
| 今日净流入 | 汇总 | 万元 |
| 超大单汇总 | 汇总 | 万元 |

### 代码改动

1. `t0/scripts/t0_core.py` — 新增大单异动分析函数
2. `t0/scripts/final_t0.py` — 输出段落增加 `💰 资金异动` 段落

### 大单阈值

```
超大单：单笔 ≥ 500万
大单：单笔 ≥ 100万
中单：单笔 ≥ 20万
小单：单笔 < 20万
```

## 三、review 复盘

### 位置

在 `🧭 阶段与结论` 之后，`📊 关键价位` 之前，新增 `💰 主力资金复盘` 段落。

### 输出格式

```
💰 主力资金复盘
阶段：吸筹期（置信度 0.7）
今日大单回溯：
  14:35 超大单买入 +500万（主力进场）
  09:35 大单买入 +300万（开盘吸筹）
  10:20 大单卖出 -200万（试探抛压）
回溯总结：买方更强，主力在低位吸筹
近5日累计：+3200万（↑↑↑↓↑）
价资关系：量价配合
```

### 代码改动

1. `review/scripts/review_core.py` — `_get_main_force()` 增加大单明细
2. `review/scripts/review_render.py` — 输出段落增加 `💰 主力资金复盘` 段落

## 四、数据结构（已有，无需新建）

### fund_flow_data.py 已有字段

```python
# fetch_fund_flow() 已返回：
{
    "date": "2026-05-26",
    "super_large_wan": 500.0,    # 超大单净流入（万元）✅ 已有
    "large_wan": 300.0,          # 大单净流入（万元）✅ 已有
    "medium_wan": -100.0,        # 中单净流入（万元）✅ 已有
    "small_wan": -200.0,         # 小单净流入（万元）✅ 已有
    "net_flow_wan": 800.0,       # 主力净流入（万元）✅ 已有
}

# calc_fund_flow_features() 已返回：
{
    "cum_flow_5d_wan": 3200.0,           # ✅ 已有
    "cum_flow_10d_wan": 5000.0,          # ✅ 已有
    "consecutive_inflow_days": 3,        # ✅ 已有
    "consecutive_outflow_days": 0,       # ✅ 已有
    "net_flow_pct": 0.05,                # ✅ 已有
    "flow_price_relation": "价涨资入",    # ✅ 已有
    "daily_flow_5d": [800, 600, 500, -200, 700],  # ✅ 已有
}
```

### big_order.py 已有数据结构

```python
# BigOrderEvent 已有：
@dataclass
class BigOrderEvent:
    time: str           # "14:35"
    side: str           # "主动买入" / "主动卖出"
    hands: float        # 手数
    amount_wan: float   # 金额（万元）
    meaning: str        # "偏试盘" / "偏试压" 等
    level: str          # "超大单" / "大单"
    near_focus: bool    # 是否在关键价位附近
```

### t0 需要的数据结构（复用现有）

```python
# 从 big_order.analyze_big_orders() 获取，无需新建
{
    "events": [BigOrderEvent(...), ...],
    "summary": "买方更强",
}
```

## 五、输出模板更新

### trader output-template.md

在 `🧭 阶段判断` 和 `📍 决策` 之间新增：

```markdown
- 💰 主力资金 includes `阶段：{stage}（置信度 {confidence}）` and `近5日：{cum_5d}万（{trend}）` and `今日：{today}万（超大单 {sl}万｜大单 {l}万）` and `价资关系：{relation}` and `提示：{hint}`.
```

### t0 output-template.md

在 `🔍 扫描` 和 `📋 盘中动态` 之间新增：

```markdown
💰 资金异动
{time} {type}{direction} {amount}万（{label}）
...
今日净流入：{net}万 ｜ 超大单：{sl_net}万
```

### review 输出

在 `🧭 阶段与结论` 和 `📊 关键价位` 之间新增 `💰 主力资金复盘` 段落。

## 六、实现步骤

### Step 1：trader 集成（改造现有输出）
- `run_analysis.py` — `_fetch_fund_flow()` 已调用 `fund_flow_data`，需在输出中增加 `💰 主力资金` 段落
- 已有数据：阶段、置信度、累计净流入、连续天数、价资关系
- 需新增：今日超大单/大单细分（从 `fund_flow_data` 的 `daily_flow[-1]` 拆分）
- 联动 `✨ 亮点`、`⚠️ 风险`、`👉 一句话`

### Step 2：t0 集成（新增资金异动段落）
- `t0_core.py` — 新增调用 `big_order.analyze_big_orders()` 获取分钟级大单异动
- `final_t0.py` — 输出增加 `💰 资金异动` 段落
- 数据来源：`big_order.py` 已有，只需调用+格式化

### Step 3：review 集成（增强现有段落）
- `review_core.py` — `_get_main_force()` 已调用，需增加超大单/大单细分
- `review_render.py` — `💰 主力资金复盘` 段落已有，需增加今日超大单/大单明细

### Step 4：模板更新
- `trader/references/output-template.md` — 增加主力资金段落
- `t0/references/output-template.md` — 增加资金异动段落

### Step 5：测试
- 单元测试：格式化函数
- 集成测试：三端输出验证

## 七、验收标准

- [ ] trader 输出包含 `💰 主力资金` 段落
- [ ] t0 输出包含 `💰 资金异动` 段落
- [ ] review 输出包含 `💰 主力资金复盘` 段落
- [ ] 超大单/大单数据正确获取
- [ ] 趋势符号（↑↓→）正确显示
- [ ] 连续流入/流出天数正确计算
- [ ] 与现有段落的联动正确（亮点/风险/一句话）
- [ ] 所有现有测试通过
- [ ] 新增函数有单元测试

## 八、关键约束

- 主力资金数据来源：腾讯资金流向 API（`fund_flow_data.py` 已有）
- 超大单/大单阈值：500万/100万（可配置）
- 数据不足时显示"资金流向数据暂不可用"
- 输出格式严格遵守 output-template.md + output-style-guide.md
- 大单异动只显示最近 3-5 条，不刷屏
