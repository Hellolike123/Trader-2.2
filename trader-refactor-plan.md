# Trader 全家桶改造计划 v1.0

> 本计划用于指导 Skill Agent 依据 Livermore×ATR 仓位管理框架改造 Trader 全家桶。
> 改造原则：不破坏现有脚本输出格式，在计算层嵌入 ATR 逻辑，对外接口保持不变。

---

## 一、改造背景与目标

### 1.1 现有问题


| 问题     | 描述                                                  |
| ------ | --------------------------------------------------- |
| 仓位固定档位 | trader-portfolio 的仓位上限（1成/3成）不随市场波动率调整，高波动市场下风险暴露过大 |
| 止损静态化  | 止损依赖"关键价位"，不计算价格到止损位的实际幅度（ATR）                      |
| 无波动率感知 | 各 skill 均不输出/使用 ATR，投资决策缺乏弹性                        |
| 加仓节奏粗糙 | 金字塔加仓仅靠"浮盈加仓"描述，无具体递减幅度规则                           |


### 1.2 改造目标

- 在各 skill 关键计算节点嵌入 ATR 计算逻辑
- 仓位输出从"固定档位"升级为"ATR感知动态仓位"
- 止损输出增加 ATR 基准供参考
- 对外接口（命令参数、输出格式）保持向后兼容
- 内部数据层增加 `atr14`、`atr7`、`atr_ratio` 字段

---

## 二、通用数据层改造

### 2.1 新增数据字段（各 skill light_data.py）

在所有获取日线数据的函数返回值中，增加以下字段：

```python
{
    "date": "2026-04-30",
    "open": 55.52,
    "close": 54.91,
    "high": 55.99,
    "low": 52.73,
    "volume": 6885482.0,
    # --- 新增 ATR 字段 ---
    "tr14": 2.660,       # 14日 True Range 均值
    "atr7": 2.667,       # 7日 ATR
    "atr14": 2.660,      # 14日 ATR
    "atr_ratio": 0.0484  # atr14 / close
}
```

### 2.2 ATR 计算标准

```
TR = max(H-L, |H-PC|, |L-PC|)  # PC = 前一日收盘
ATR14 = SUM(TR, 14) / 14
ATR7 = SUM(TR, 7) / 7
ATR_ratio = ATR14 / close
```

### 2.3 波动率档位划分


| ATR_ratio | 档位   | 首仓上限   | 说明     |
| --------- | ---- | ------ | ------ |
| < 0.01    | 低波动  | 15-20% | 可用上限仓位 |
| 0.01-0.02 | 正常波动 | 10%    | 标准仓位   |
| 0.02-0.03 | 高波动  | 5-7%   | 压低仓位   |
| > 0.03    | 极端波动 | ≤5%    | 观望或不做  |


---

## 三、trader skill 改造

### 3.1 改造范围

文件：`scripts/final_report.py`
依赖：`scripts/light_data.py`

### 3.2 改动点

**① light_data.py（与 review-trader 共用）**

在 `fetch_qfq_daily` 返回的每条数据中附加 ATR 字段：

```python
def fetch_qfq_daily(sec: Security, http: HttpClient, days: int = 40) -> list[dict]:
    # 现有逻辑不变
    bars = _fetch_raw(...)
    # 新增：计算并附加 ATR
    for i, bar in enumerate(bars):
        if i == 0:
            tr = bar['high'] - bar['low']
        else:
            prev_close = bars[i-1]['close']
            tr = max(bar['high']-bar['low'],
                     abs(bar['high']-prev_close),
                     abs(bar['low']-prev_close))
        bar['tr'] = tr
    # 计算 ATR14/ATR7
    trs = [b['tr'] for b in bars]
    bars[-1]['atr7'] = sum(trs[-7:]) / 7
    bars[-1]['atr14'] = sum(trs[-14:]) / 14
    bars[-1]['atr_ratio'] = bars[-1]['atr14'] / bars[-1]['close']
    return bars
```

**② final_report.py**

新增输出区块 `📊 ATR 仓位参数`，放在现有 `📏 仓位管理` 之后或整合进仓位管理区块内：

```
📊 ATR 仓位参数（收盘后更新）
14日ATR：2.66元（ATR/价格=4.84%）
波动档位：高波动（建议首仓≤7%）
止损幅度（2×ATR）：5.32元
参考止损价（买入价-ATR×2）：实时计算
```

新增/修改 `📏 仓位管理` 输出：

```
📏 仓位管理
建议首仓：5-7%（波动档位限制）
最大加仓：分两次（+5%、+2-3%）
总仓位上限：30%
止损参考：ATR×2，跌破即执行
```

### 3.3 兼容性要求

- `final_report.py --target xxx` 命令参数不变
- 输出文本格式不变（保留原有 headings）
- ATR 参数作为新增区块追加，不改变现有表格结构
- 若数据不足无法计算 ATR（如新股），输出 `ATR：数据不足` 并回退到原仓位逻辑

---

## 四、trader-portfolio skill 改造

### 4.1 改造范围

文件：`scripts/final_portfolio.py`
依赖：`scripts/light_data.py`

### 4.2 改动点

**① 加仓规则改造**

原输出：

```
🔁 加仓规则
...等确认后再加仓...
```

改为：

```
🔁 加仓规则
首次加仓：浮盈 + 回踩不破前低 → 按 ATR 计算加仓5%
二次加仓：再次确认 → 按 ATR 计算加仓2-3%
每次加仓前必须重新计算 ATR，调整加仓股数
总仓位不超过30%（ATR极端波动时主动降至20%）
```

**② 止损逻辑改造**

在 `⚠️ 风险控制` 中增加：

```
止损：跌破关键支撑即执行，不以ATR为唯一标准
ATR辅助：止损幅度不得超过持仓市值的10%
若ATR计算的止损幅度 > 持仓市值10%，降仓处理
```

**③ 新增波动率感知区块**

在输出末尾（`⚠️ 风险控制` 后）追加：

```
📊 组合波动率监控
南网科技：ATR=2.66元（4.84%）｜高波动
中国铝业：ATR=0.xx元（x.xx%）｜正常/低波动
...
组合加权ATR比率：待计算
建议：当前组合整体偏向高波动，总仓位不超过组合上限的60%
```

### 4.3 兼容性要求

- `final_portfolio.py --targets xxx yyy` 命令参数不变
- 输出 headings 顺序不变
- ATR 相关内容作为新增区块，不删除或修改现有区块内容
- 若某只股票 ATR 计算失败，标注 `ATR：数据不足`，其他股票正常输出

---

## 五、t0-trader skill 改造

### 5.1 改造范围

文件：`scripts/final_t0.py`
依赖：`scripts/light_data.py`、`scripts/price_point_engine.py`

### 5.2 改动点

**① 低吸/高抛触发条件（补充ATR维度）**

原逻辑：价格跌到观察价以下 → 触发低吸
改造后：

```
低吸触发条件（双重确认）：
1. 价格条件：跌到观察价以下
2. ATR条件：当前价格相对观察价的距离 ≤ ATR×2
   （即：如果价格跌幅超过 ATR×2，不追，等止跌确认）
```

**② 输出区块新增 ATR 参数**

在 `🎯 今日关键点` 中增加：

```
ATR参考（14日）：2.66元
低吸安全区：观察价以下 ATR×1 以内
低吸警戒线：跌破观察价超过 ATR×2 → 停止低吸
```

在 `📦 仓位建议` 中修改：

```
单次最多动底仓的 10%-20%
ATR参考：当前波动档位 [高/正常/低]
若为高波动档位，优先选择 10% 而非 20%
```

### 5.3 兼容性要求

- `final_t0.py --target xxx` 命令参数不变
- 输出格式（Heading 结构）不变
- ATR 内容作为新增行追加进现有区块
- 若 ATR 数据不足，降级到原有仓位建议（不报错）

---

## 六、review-trader skill 改造

### 6.1 改造范围

文件：`scripts/final_review.py`
依赖：`scripts/light_data.py`

### 6.2 改动点

**① `📈 走势结构` 区块（追加波动率信息）**

在现有结构描述后追加：

```
ATR分析：
近7日TR均值：2.67元
近14日ATR：2.66元
ATR/价格：4.84%（高波动档位）
注：高波动档位下，首仓建议压至5-7%，止损幅度约5.3元
```

**② `🎯 明日关键价位`（增加 ATR 止损参考）**

在支撑/压力列表后追加：

```
ATR止损参考（14日ATR=2.66元）：
做多止损：买入价 - ATR×2 = 买入价 - 5.32元
若止损幅度超过持仓市值10%，降低买入仓位
```

**③ `🧭 明日应对`（增加波动率条件）**

在强势/震荡/回落三个分支的动作中，增加条件：

```
强势（站上58.30）：
ATR参考判断：若此时ATR_ratio仍>3%，即便站上也只轻仓（≤10%），
不加仓，等ATR降到2%以下再正常操作
```

### 6.3 兼容性要求

- `final_review.py --target xxx` 命令参数不变
- 输出格式（Heading 顺序）不变
- ATR 内容作为追加描述，不修改现有行
- 若 ATR 数据不足，输出 `ATR：数据不足（新股/停牌）`，隐藏相关段落

---

## 七、trader-compare skill 改造

### 7.1 改造范围

文件：`scripts/final_compare.py`
依赖：`scripts/light_data.py`

### 7.2 改动点

**① 新增波动率比较列**

在现有股票排序输出中，每只股票增加：

```
xxx（000000.SH）｜现价 xx.xx元
ATR14：2.66元（4.84%）｜波动档位：高
...
```

**② 排序逻辑调整**

当两只股票其他条件相近时，优先选择 **ATR_ratio 更低**（波动更小）的标的。

### 7.3 兼容性要求

- 命令参数不变
- 输出格式在 `行动排序` 每条记录中追加 ATR 行
- ATR 计算失败不影响排序，只标注 `ATR：数据不足`

---

## 八、trader-pool skill 改造

### 8.1 改造范围

文件：`scripts/final_pool.py`
依赖：`scripts/light_data.py`

### 8.2 改动点

**① 入池分析（analyze 命令）**

在现有分析报告后追加：

```
ATR仓位参数（建议入池前确认）：
ATR14：2.66元（4.84%）｜波动档位：高
建议首仓：≤7%
止损幅度：5.32元（占当前价9.7%）
若ATR_ratio>3%，该标的建议暂缓入池
```

**② 池子排序（rank 命令）**

同等条件下，ATR_ratio 更低的标的优先排序靠前。

---

## 九、通用接口规范

### 9.1 新增命令参数（可选，兼容旧接口）

```bash
# 所有支持 ATR 的脚本新增 --atr 参数
python3 final_report.py --target 南网科技 --atr
python3 final_portfolio.py --targets 南网科技 中国铝业 --atr
# --atr 可省略（默认开启），加 --no-atr 可禁用
```

### 9.2 ATR 数据来源优先级

```
1. 本地计算：light_data.py .fetch_qfq_daily() 内置 ATR
2. 降级方案：若不足14日数据，输出 ATR：数据不足
3. 旧接口兼容：无法计算时，各 skill 回退到原有逻辑，不报错
```

### 9.3 数值精度

```
ATR：保留2位小数
ATR_ratio：保留4位小数
止损幅度：保留2位小数
仓位百分比：整数（如 7%，不写 7.0%）
```

---

## 十、改造优先级


| 优先级 | Skill            | 理由                  |
| --- | ---------------- | ------------------- |
| P0  | light_data.py    | 所有 skill 公用数据层，先改这里 |
| P0  | trader-portfolio | 仓位管理的核心，直接影响持仓决策    |
| P1  | trader           | 单票分析入口，改完所有下游受益     |
| P1  | t0-trader        | 盘中执行层，ATR 影响买卖点判断   |
| P2  | review-trader    | 盘后复盘，ATR 参考信息补充     |
| P2  | trader-compare   | 多股比较，增加 ATR 列       |
| P3  | trader-pool      | 选股池，入池分析补充 ATR 建议   |


---

## 十一、改造验收标准

### 11.1 功能验收

- `python3 final_report.py --target 南网科技` 输出包含 ATR 区块
- `python3 final_portfolio.py --targets 南网科技 中国铝业` 输出包含 ATR 加仓规则
- `python3 final_t0.py --target 南网科技` 输出包含 ATR 仓位建议
- `python3 final_review.py --target 南网科技` 输出包含 ATR 分析段落
- `python3 final_compare.py --targets 南网科技 中国铝业` 每只股票标注 ATR
- 所有命令加 `--no-atr` 时行为与改造前完全一致

### 11.2 数值验收

- ATR14 计算结果与标准公式误差 < 0.01
- 止损幅度（ATR×2）保留2位小数
- 波动档位划分符合档位表定义

### 11.3 接口兼容性验收

- 原有命令参数不变
- 输出格式原有区块内容不变（只追加）
- ATR 计算失败时不报错，降级到原有逻辑

---

## 十二、参考公式汇总

```python
# True Range
TR = max(H - L, abs(H - PC), abs(L - PC))

# ATR14
ATR14 = sum(TR[-14:]) / 14

# ATR7
ATR7 = sum(TR[-7:]) / 7

# ATR Ratio
ATR_ratio = ATR14 / close

# 止损幅度
stop_distance = ATR14 * 2

# 单笔仓位（股数）
shares = (account_net_value * risk_ratio) / (ATR14 * 2)
# risk_ratio = 0.01（1%）

# 波动档位
if ATR_ratio < 0.01: 档位 = "低波动", 首仓上限 = "15-20%"
elif ATR_ratio < 0.02: 档位 = "正常波动", 首仓上限 = "10%"
elif ATR_ratio < 0.03: 档位 = "高波动", 首仓上限 = "5-7%"
else: 档位 = "极端波动", 首仓上限 = "≤5%或观望"
```

