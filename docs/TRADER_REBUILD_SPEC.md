# Trader Rebuild Spec

本文档用于把当前 Trader 仓库的架构、取数、计算、业务串联、分析指标和输出面板契约一次性讲清楚。目标是让另一个 agent 不读旧代码，也能重新实现一套行为等价的系统。

当前日期语境：2026-05-01。系统面向 A 股，输出是交易辅助，不是自动下单系统。

## 1. 总体定位

Trader 是一组给 Hermes / OpenClaw / WorkBuddy / Codex 使用的 A 股交易辅助 skills。它不是券商交易系统，不提交订单，不读取真实账户成交，只做：

- 实时/盘后行情取数。
- 单票结构分析。
- 盘中 T0 观察和触发卡。
- 多股候选排序。
- 组合仓位轮动。
- 选股池管理。
- 午间/盘后复盘。
- 机器可读信号输出。

核心原则：

- 默认输出 Markdown 面板，给人看。
- 显式请求 JSON 时输出结构化数据，给 agent / monitor 消费。
- 所有“买/卖/低吸/高抛”都是条件触发建议，不代表已经下单。
- T0 只在已有底仓内做，不增加隔夜仓位。
- 观察价不是执行价；只有触发确认后才生成执行价。

## 2. 目录架构

源码区：

```text
01-功能包-packages/
  01-单票分析-trader/
  02-盘中T0-t0-trader/
  03-多股比较-trader-compare/
  04-仓位轮动-trader-portfolio/
  05-盘后复盘-review-trader/
  06-选股池-trader-pool/

02-共享模块-shared/
  01-行情数据-market-data/
    light_data.py
  02-候选逻辑-candidate/
    trader_candidate_core.py
    t0_candidate_core.py
  03-输出校验-contracts/
    signal_contract.py
    signal_store.py

03-安装包-dist/
  *.zip
```

功能包分工：


| 包                | 作用                           | 主入口                                                       |
| ---------------- | ---------------------------- | --------------------------------------------------------- |
| trader           | 单票手机端分析报告，判断状态、关键价、行动卡、风险    | `scripts/final_report.py` / `scripts/run_analysis.py`     |
| t0-trader        | 盘中 T0 精细执行卡，低吸/高抛观察价、触发价、失效价 | `scripts/final_t0.py` / `scripts/t0_run.py`               |
| trader-compare   | 多股行动比较，当前属于兼容入口              | `scripts/final_compare.py` / `scripts/compare_run.py`     |
| trader-portfolio | 2-3 只股票仓位分配和高切低轮动            | `scripts/final_portfolio.py` / `scripts/portfolio_run.py` |
| review-trader    | 午间/盘后复盘，单票或多股复盘              | `scripts/final_review.py`                                 |
| trader-pool      | 主日常入口：入池、排序、计划、复盘、归档         | `scripts/final_pool.py`                                   |


推荐工作流：

```text
新票验票 -> trader
确认跟踪 -> trader-pool add
池内优先级 -> trader-pool rank
明日计划 -> trader-pool plan
盘中执行 -> t0-trader
盘后复盘 -> review-trader / trader-pool review
仓位轮动 -> trader-portfolio
```

## 3. 行情取数规格

共享行情模块应提供 `light_data.py`。

### 3.1 股票解析

输入支持：

- 股票名称映射，例如 `南网科技 -> 688248`。
- 6 位代码，例如 `688248`。
- 带市场代码，例如 `688248.SH`。
- 前缀格式，例如 `SH688248`、`SZ300750`。

解析规则：

- 若输入在 `NAME_MAP`，先映射到代码。
- 若包含 `.`，按 `code.market` 拆分。
- 若以 `SH/SZ/BJ` 开头，前两位为 market，剩余为 code。
- 否则提取数字，取最后 6 位，不足补 0。
- 未显式市场时：
  - `6/688/689` 开头 -> `SH`
  - `8/4` 开头 -> `BJ`
  - 其他 -> `SZ`

输出 `Security`：

```python
{
  "code": "688248",
  "market": "SH",
  "name": "南网科技",
  "ts_code": "688248.SH",
  "qq_symbol": "sh688248"
}
```

### 3.2 HTTP 客户端

仅依赖 Python 标准库：

- `urllib.request`
- `ssl._create_unverified_context()`
- timeout = 12 秒
- 最大重试 = 3 次
- 重试退避 = `0.08 * 2**attempt + random(0, 0.02)`

### 3.3 Quote 取数

接口：

```text
https://qt.gtimg.cn/q=<qq_symbol>
```

编码：`gbk`。

解析字段：


| 字段                 | 位置  | 含义    |
| ------------------ | --- | ----- |
| name               | 1   | 股票名   |
| current_price      | 3   | 现价    |
| pre_close          | 4   | 昨收    |
| open               | 5   | 今开    |
| current_change_pct | 32  | 当前涨跌幅 |
| high               | 33  | 今日高   |
| low                | 34  | 今日低   |
| volume             | 36  | 成交量   |
| amount             | 37  | 成交额   |
| turnover_rate      | 38  | 换手率   |


日期时间：

- 从 quote 字段倒序扫描。
- `YYYYMMDD` -> `YYYY-MM-DD`
- `YYYY-MM-DD` 直接使用。
- `HH:MM:SS` 为 `trade_time`。
- 找不到日期时用系统日期。

Quote 标准输出：

```python
{
  "name": "...",
  "symbol": "688248.SH",
  "trade_date": "2026-05-01",
  "trade_time": "14:55:00",
  "current_price": 57.60,
  "pre_close": 56.00,
  "open": 56.20,
  "high": 58.30,
  "low": 55.80,
  "volume": 12345678.0,
  "amount": 123456789.0,
  "turnover_rate": 3.21,
  "current_change_pct": 2.86
}
```

### 3.4 前复权日 K

接口：

```text
https://web.ifzq.gtimg.cn/appstock/app/fqkline/get
```

参数：

```python
{
  "_var": "kline_dayhfq",
  "param": f"{qq_symbol},day,,,{max(days, 20)},qfq"
}
```

输出日 K：

```python
{"date": "2026-04-30", "open": 55.1, "close": 57.6, "high": 58.3, "low": 54.9, "volume": 123456.0}
```

没有 bars 时抛错。

### 3.5 分钟 K

接口：

```text
https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData
```

参数：

```python
{"symbol": qq_symbol, "scale": "5|15|30", "ma": "no", "datalen": "60"}
```

分钟 K 取不到时返回空列表，不抛错。标准字段：

```python
{
  "time": "...",
  "date": "...",
  "open": 57.1,
  "high": 57.8,
  "low": 56.9,
  "close": 57.5,
  "volume": 12345.0,
  "amount": 1234567.0
}
```

### 3.6 通用数值函数

`to_float(value)`：

- `None`, `""`, `"-"`, `"--"`, `"null"`, `"None"` -> `None`
- 去掉逗号后转 float。
- NaN / Infinity -> `None`

`pct_change(start, end)`：

```python
((end / start) - 1.0) * 100
```

若 `start == 0`，返回 0。

## 4. 单票候选逻辑 trader_candidate_core

用于 `trader` 和 `trader-pool`。它偏向“单票是否值得跟踪/低吸/转强”的结构判断。

默认参数：

```python
LOOKBACK_DAYS = 30
RECENT_WINDOW = 5
STRUCTURE_WINDOW = 20
TAKE_PROFIT_BUFFER = 1.06
MA_PERIODS = (5, 10, 20, 30)
MIN_ZONE_WIDTH_PCT = 0.005
MAX_ZONE_WIDTH_PCT = 0.012
MIN_STOP_BUFFER_PCT = 0.008
MAX_STOP_BUFFER_PCT = 0.025
MIN_CONFIRM_SPACE_PCT = 0.008
MAX_REASONABLE_MA_DISTANCE_PCT = 0.12
```

### 4.1 支撑/压力候选

输入：

- `current`
- `bars`: 日 K
- `change_pct`
- `quote`

计算：

```python
recent5 = bars[-5:]
recent20 = bars[-20:]
ma5/ma10/ma20/ma30 = 各周期收盘均线
```

支撑候选：


| 来源    | 值                             | 权重   |
| ----- | ----------------------------- | ---- |
| 5日低点  | `min(recent5.low)`            | 1.00 |
| 今日低点  | `quote.low`                   | 0.95 |
| 20日低点 | `min(recent20.low)`           | 0.85 |
| MA5   | 若 `MA5 <= current` 且距离不超过 12% | 0.78 |
| MA10  | 同上                            | 0.76 |
| MA20  | 同上                            | 0.72 |
| MA30  | 同上                            | 0.70 |


压力候选：


| 来源    | 值                             | 权重   |
| ----- | ----------------------------- | ---- |
| 5日高点  | `max(recent5.high)`           | 1.00 |
| 今日高点  | `quote.high`                  | 0.95 |
| 20日高点 | `max(recent20.high)`          | 0.85 |
| MA5   | 若 `MA5 >= current` 且距离不超过 12% | 0.78 |
| MA10  | 同上                            | 0.76 |
| MA20  | 同上                            | 0.72 |
| MA30  | 同上                            | 0.70 |


选择规则：

```python
directional = 支撑取 <= current，压力取 >= current
如果 directional 为空，取离 current 最近的 3 个
排序 key = (distance / max(weight, 0.1), distance)
distance = abs(price - current) / max(current, 1)
```

### 4.2 观察区和止损

平均振幅：

```python
avg_amplitude_pct = average((high - low) / close) over recent20 valid bars
default = 0.02
```

观察区宽度：

```python
zone_width_pct = clamp(avg_amplitude_pct * 0.28, 0.005, 0.012)
low_zone_lower = support
low_zone_upper = support * (1 + zone_width_pct)
```

止损缓冲：

```python
stop_buffer_pct = clamp(avg_amplitude_pct * 0.45, 0.008, 0.025)
hard_stop = support * (1 - stop_buffer_pct)
```

止盈/减仓：

```python
take = max(confirm, current) * 1.06
```

空间位置：

```python
position_ratio = clamp((current - support) / max(confirm - support, current * 0.01), 0, 1)
pressure_space_pct = (confirm - current) / current
```

### 4.3 状态判定

状态枚举：

- `低吸观察`
- `等转强`
- `防守观察`
- `冲高减仓`
- `空间不足`
- `暂不碰`
- `数据失败`

规则顺序：

```python
change = to_float(change_pct) or 0
below_ma_count = count(current < ma for ma in [ma5, ma10, ma20, ma30])
above_ma5_ma10 = current >= ma5 and current >= ma10

if current <= hard_stop or current < support * 0.995:
    status = "暂不碰"
elif change <= -7 and current > low_zone_upper:
    status = "暂不碰"
elif current <= low_zone_upper:
    status = "低吸观察"
elif current >= confirm:
    status = "冲高减仓" if change >= 3 else "等转强"
elif 0 <= pressure_space_pct < 0.008:
    status = "空间不足"
elif above_ma5_ma10 and position_ratio >= 0.60:
    status = "等转强"
elif below_ma_count >= 3:
    status = "防守观察"
elif position_ratio >= 0.72:
    status = "等转强"
else:
    status = "防守观察"
```

### 4.4 单票评分

基础分：

```python
STATUS_SCORE = {
  "低吸观察": 80,
  "等转强": 70,
  "防守观察": 60,
  "冲高减仓": 55,
  "空间不足": 45,
  "暂不碰": 20,
  "数据失败": 0,
}
```

调整：

```python
if status != "暂不碰" and current <= low_zone_upper: +10
if status != "暂不碰" and current >= confirm: +8
if current <= hard_stop: -40
if abs(pct_change(current, hard_stop)) < 1.0: -8
if change <= -5 and status != "低吸观察": -8
if change >= 5 and position_ratio >= 0.65: -10
if pct_change(current, confirm) > 2: +5 else -4
if low_zone and confirm_price: +5
```

## 5. T0 候选逻辑 t0_candidate_core

用于多股比较和组合轮动里的 T0 倾向粗判，不等同 `t0-trader` 的精细执行价。

默认参数：

```python
CONFIRM_BUFFER = 0.02
RECENT_WINDOW = 5
STOP_BUFFER = 0.98
TAKE_PROFIT_BUFFER = 1.06
T0_MIN_SPACE_PCT = 1.5
```

计算：

```python
support = min(recent.low)
resistance = max(recent.high)
confirm = max(resistance, current * 1.02)
hard_stop = support * 0.98
low_zone = support 到 support * 1.01
take = max(confirm, current) * 1.06
position_ratio = clamp((current - support) / max(confirm - support, current * 0.01), 0, 1)
```

状态：

```python
if current <= hard_stop or current < support * 0.995: 暂不碰
elif change <= -7 and current > low_zone_upper: 暂不碰
elif current <= low_zone_upper: 低吸观察
elif current >= confirm: 冲高减仓 if change >= 3 else 等转强
elif position_ratio >= 0.72: 等转强
else: 防守观察
```

T0 倾向：

```python
width_pct = (confirm - support) / current * 100
if status in {"暂不碰", "数据失败"} or current <= 0 or width_pct < 1.5:
    "不做"
elif status in {"低吸观察", "防守观察"} and position_ratio <= 0.45:
    "等待低吸触发"
elif status in {"等转强", "冲高减仓"} or position_ratio >= 0.55 or change >= 3:
    "等待高抛触发"
else:
    "不做"
```

## 6. trader 单票分析

入口：

```bash
python3 scripts/final_report.py --target 南网科技
python3 scripts/run_analysis.py --target 南网科技 --output markdown|json|signal-json
```

### 6.1 数据流

```text
target
 -> resolve_security
 -> fetch_quote
 -> fetch_qfq_daily(days=LOOKBACK_DAYS)
 -> fetch_5m
 -> current = quote.current_price or last daily close
 -> trader_candidate_core.build_candidate_levels(current, daily, change_pct, quote)
 -> 结构/量能/动能二次加工
 -> Markdown 面板 / JSON / signal-json
```

### 6.2 派生指标

阶段 `stage`：

```python
weekly_close = bars[-1].close
monthly_close = bars[-20].close if len(bars) >= 20 else bars[0].close

if current > weekly_close > monthly_close: "走强"
elif current >= weekly_close and weekly_close <= monthly_close: "修复"
elif current >= monthly_close * 0.98: "震荡"
else: "转弱"
```

结构回放：

- 取最近 20 根日 K。
- 每 5 根切一段。
- 段涨跌幅 `pct_change(first.close, last.close)`。
- 标签：
  - `>= 4%`: 拉升窗口
  - `<= -4%`: 下跌窗口
  - `>= 1%`: 反弹窗口
  - `<= -1%`: 回踩窗口
  - 其他：震荡窗口

量能观察：

- 若 5m bars >= 12：
  - `recent_avg = avg(last 6 volume)`
  - `prior_avg = avg(previous 12 volume)`
  - `recent_avg / prior_avg >= 1.3`: 分时量能放大
  - `<= 0.75`: 分时量能收缩
- 否则使用最近 20 日最大量能日，判断当天收涨/收跌。

动能观察：

```python
width = max(confirm - support, current * 0.02)
if current >= confirm:
    "有启动迹象，但还要看放量站稳后的延续"
elif stage == "转弱":
    "启动条件不足"
elif current >= confirm - width * 0.25:
    "预备启动，等待放量确认"
else:
    "动能仍是弱修复"
```

### 6.3 Markdown 面板

必须输出这些区块，顺序固定：

```text
分析报告 — {name}（{code}）
现价：...
MA5 / MA10 / MA20 / MA30

✅ 结论概述
🎯 今日交易计划
📏 仓位管理
🧭 简化分析逻辑
⚠️ 风险管理
📌 交易指导卡
👉 一句话
```

今日交易计划固定 4 行角色：

- 空仓：等低吸观察区止跌，或确认位放量站稳后再看。
- 有底仓：不补仓摊平；反弹到确认位附近但量能不足，可减 10%-20%。
- 加仓：只有放量站上确认位且回踩不破，才重新评估。
- 止错：收盘跌破止错价，停止低吸，不再补仓。

仓位管理固定：

- 观察中：不动。
- 低吸确认：最多 1 成仓。
- 有底仓做差价：单次最多动底仓的 10%-20%。
- 转强确认：最多加到 3 成仓。

### 6.4 trader_signal_v1 映射

`trader` 输出信号时：

```python
if stage == "转弱":
    signal_type="defensive", direction="bearish_lean", action="wait", confidence="low"
elif scene == "冲高减仓":
    signal_type="reduce", direction="neutral", action="reduce", confidence="medium"
elif current >= confirm or scene in {"突破确认", "等转强"}:
    signal_type="track", direction="bullish", action="track", confidence="medium"
elif scene in {"低吸观察", "防守观察", "空间不足"}:
    signal_type="wait_for_confirmation", direction="bullish_lean", action="observe", confidence="medium"
else:
    signal_type="observe", direction="neutral", action="observe", confidence="low"
```

信号触发条件：

- `trigger.type = price_confirm`
- `trigger.price = confirm`
- `trigger.text = "{confirm}元 放量站稳并回踩不破后再评估"`

失效条件：

- `invalidation.type = price_break`
- `invalidation.price = stop`
- `invalidation.text = "跌破 {stop}元 后停止低吸"`

仓位：

- `track`: max_total_pct = 30
- `reduce`: max_total_pct = 20
- `defensive`: max_total_pct = 0
- 其他：max_total_pct = 30
- max_single_move_pct = 10

风险 flags：

- `stage == 转弱` -> `structure_weak`
- `scene == 空间不足` -> `limited_upside_space`
- `volume_text` 包含 `不足` -> `volume_confirmation_missing`

## 7. t0-trader 盘中执行

入口：

```bash
python3 scripts/final_t0.py --target 南网科技
python3 scripts/t0_run.py --target 南网科技 --output markdown|json|signal-json
```

### 7.1 数据流

```text
target
 -> quote + qfq daily + 5m + 15m + 30m
 -> current = quote.current_price or last daily close
 -> build_price_point_model(report_data)
 -> T0 Markdown / JSON / trader_signal_v1
```

### 7.2 数据状态

只使用已完成 5m K 做触发。

已完成 5m K：

- 若 bar 日期早于今天，视为完成。
- 若 `bar_time + 5 minutes <= now`，视为完成。

数据状态：

```python
if not quote or not daily or len(completed_5m) < 20:
    "insufficient"
elif 非交易时段:
    "non_trading"
elif last_5m_date != today:
    "delayed"
elif now - last_5m <= 12 minutes:
    "fresh"
else:
    "delayed"
```

交易时段：

- 工作日 09:30-11:30
- 工作日 13:00-15:00

### 7.3 关键位

支撑候选：

- 5日低点，权重 1.0
- 今日低点，权重 0.9
- 20日低点，权重 0.8
- 最近 12 根 5m 低点，权重 0.7
- 最近 8 根 15m 低点，权重 0.7
- 最近 8 根 30m 低点，权重 0.8
- VWAP，权重 0.6

压力候选：

- 5日高点，权重 1.0
- 今日高点，权重 0.9
- 20日高点，权重 0.8
- 最近 12 根 5m 高点，权重 0.7
- 最近 8 根 15m 高点，权重 0.7
- 最近 8 根 30m 高点，权重 0.8
- VWAP * 1.01，权重 0.6

选择规则：

- 支撑只优先取 `<= current`，压力只优先取 `>= current`。
- 先选权重 >= 0.7 且不是 VWAP 的 primary 候选。
- 如果 VWAP 离现价 <= 0.8%，且 primary 离现价 >= 8%，则用 VWAP。
- 否则按距离近、权重大排序。

### 7.4 T0 区间

日内振幅：

```python
amplitude_pct = (quote.high - quote.low) / quote.pre_close
```

振幅状态：

- `< 1.5%`: `too_small`
- `< 3.0%`: `normal`
- `>= 3.0%`: `good`

区间宽度：

```python
width_pct = min(0.006, amplitude_pct * 0.15) if amplitude_pct else 0.005
buy_zone = support * (1 - width_pct) 到 support * (1 + width_pct)
sell_zone = resistance * (1 - width_pct) 到 resistance * (1 + width_pct)
```

净空间：

```python
t0_net_space_pct = (sell_zone.lower - buy_zone.upper) / buy_zone.upper
sell_net_space_pct = (sell_zone.lower - current) / current
```

若 `t0_net_space_pct < 0.006`，低吸和高抛都无效。
若 `sell_net_space_pct < 0.004`，高抛无效。

### 7.5 技术指标

基于完成的 5m K：

- VWAP：`sum(((high+low+close)/3)*volume) / sum(volume)`
- volume_ratio：最近 6 根均量 / 之前 12 根均量。
- MACD：EMA12、EMA26、DEA9，hist = `(dif - dea) * 2`。
- RSI：14 周期。
- 上影线：上影 >= max(实体*1.2, 全振幅*0.25)。
- 下影线：下影 >= max(实体*1.2, 全振幅*0.25)。
- 最近创新低：最近 6 根最后一根 low <= 前面 low 最小值。
- 最近创新高：最近 6 根最后一根 high >= 前面 high 最大值。

### 7.6 ICT-Lite 执行辅助

ICT 只辅助执行，不单独决定方向。

扫流动性：

- 在最近窗口内，若某根 K 的 low 跌破前 lookback 低点，且 close 收回该低点 -> `downside_sweep`。
- 若 high 突破前 lookback 高点，且 close 跌回该高点下方 -> `upside_sweep`。

结构确认：

- downside_sweep 后，后续 close 突破 sweep 前 lookback 高点 -> `bullish_bos`。
- upside_sweep 后，后续 close 跌破 sweep 前 lookback 低点 -> `bearish_choch`。

信号：

- downside_sweep + bullish_bos -> `buy_confirmed`
- upside_sweep + bearish_choch -> `sell_confirmed`

强度：

- reclaim >= 0.25 且 wick >= 0.35 -> strong
- 满足一个 -> medium
- 否则 weak

### 7.7 低吸触发

阻断：

```python
if data_status in {"insufficient", "non_trading"} or len(5m) < 20: 数据不足
if space_state == "too_small": 被阻断（日内振幅不足）
if t0_net_space_pct < 0.006: 被阻断（T0净空间不足）
if current > buy_zone.upper: 未进入候选区
```

进入候选区后，阻断理由：

- 最近 5m 持续创新低。
- MACD 绿柱继续放大。
- 跌破主支撑后未收回。
- 放量跌破主支撑。
- ICT 反向高抛确认。

触发条件候选，满足数量 >= 4 即 `已触发`：

- 5m 不再创新低。
- 量能收缩。
- MACD 绿柱缩短。
- RSI 低位拐头。
- 站回 VWAP。
- 出现下影线。
- 支撑位收回。
- ICT 下扫后转强。

触发价：

```python
execution = trigger_close * BUY_CONFIRM_FACTOR  # 1.002
acceptable = execution * BUY_ACCEPT_FACTOR      # 1.003
```

若当前价 > acceptable，状态改为 `触发过期`，不输出 execution。

低吸失效价：

```python
invalid = main_support * 0.995
```

### 7.8 高抛触发

阻断：

```python
if data_status in {"insufficient", "non_trading"} or len(5m) < 20: 数据不足
if space_state == "too_small": 被阻断（日内振幅不足）
if t0_net_space_pct < 0.006: 被阻断（T0净空间不足）
if sell_net_space_pct < 0.004: 被阻断（卖出空间不足）
if current < sell_zone.lower: 未进入候选区
```

进入候选区后，阻断理由：

- 最近 5m 持续创新高。
- MACD 红柱继续放大。
- VWAP 上行且放量突破主压力。
- ICT 反向低吸确认。

触发条件候选，满足数量 >= 4 即 `已触发`：

- 冲高没有继续放量。
- 放量滞涨或缩量上攻。
- MACD 红柱缩短。
- RSI 高位拐头。
- 跌回 VWAP。
- 出现上影线。
- 压力位回落。
- ICT 上扫后转弱。

触发价：

```python
execution = trigger_close * SELL_CONFIRM_FACTOR  # 0.998
acceptable = execution * SELL_ACCEPT_FACTOR      # 0.997
```

若当前价 < acceptable，状态改为 `触发过期`，不输出 execution。

高抛取消价：

```python
invalid = main_resistance * 1.005
```

### 7.9 今日动作和仓位

今日动作：

```python
if data_status in {"non_trading", "insufficient"}: 等待，不主动操作
elif 任一侧触发过期: 等待下一次触发
elif buy 已触发 且 sell 未触发: 低吸优先
elif sell 已触发 且 buy 未触发: 高抛优先
elif 双侧已触发: 选择现价更接近的区间
else: 等待，不主动操作
```

仓位：

```python
if action not in {"低吸优先", "高抛优先"}: 不动
elif model.status != "已触发": 不动
elif space_state == "too_small": 不动
elif data_status == "fresh" and space_state == "good" and matched_count >= 5:
    底仓的 20%-30%
else:
    底仓的 10%-20%
```

### 7.10 Markdown 面板

当前实现输出：

```text
T0 盯盘助理
{name}（{symbol}）｜现价 ...（涨跌幅）

📍 当前结论
🎯 今日关键点
📜 今日回顾
📊 盘中走势
📦 仓位建议
🔭 下一步只盯
```

关键展示字段：

- 当前：低吸 / 高抛 / 不动。
- 提醒级别：可执行 / 轻仓做 / 别犯错 / 无。
- 买入状态：可执行 / 已错过 / 被阻断 / 数据不足 / 未触发。
- 卖出状态：同上。
- 低吸观察价。
- 高抛观察价。
- 低吸失效价。
- 高抛取消价。
- 今日回顾最近 3 条 monitor history。
- 盘中走势最多 3 段：开盘段 / 中段 / 最近。
- 仓位建议：当前、触发后。
- 下一步只盯：低吸、高抛、停止条件。

## 8. trader-compare 多股比较

入口：

```bash
python3 scripts/final_compare.py --targets 南网科技 中国铝业
```

定位：兼容入口。日常推荐改用 `trader-pool rank`。

数据流：

```text
targets
 -> 对每只股票 analyze_target
 -> t0_candidate_core.build_candidate_levels
 -> score_for
 -> sort_candidates(score desc)
 -> pick_empty_position
 -> pick_holding_t0
 -> Markdown
```

排序：按 `score` 降序。

空仓优先：

```python
第一个 status in {"低吸观察", "等转强", "防守观察"} 且 not chase_risk
chase_risk = change >= 5 and position_ratio >= 0.65
```

有底仓做 T：

```python
第一个 t0_action in {"等待低吸触发", "等待高抛触发"} 且 status not in {"暂不碰", "数据失败"}
```

输出面板：

```text
📊 多股行动比较
📌 今日优先级
🎯 行动排序
👤 空仓怎么选
📦 有底仓怎么做
⏱️ T0 倾向
🚫 今天先不碰
👉 一句话
```

每只股票必须展示：

- 名称
- 状态
- 现价
- 涨跌幅
- 动作
- 低吸观察
- 高抛观察
- 转强价
- 止错价

## 9. trader-portfolio 轮动仓位

入口：

```bash
python3 scripts/final_portfolio.py --targets 南网科技 中国铝业 三安光电
python3 scripts/final_portfolio.py --snapshot snapshot.json
```

默认参数：

```python
DEFAULT_MAX_TOTAL = 80
DEFAULT_CASH_FLOOR = 20
DEFAULT_MAIN_CAP = 50
```

### 9.1 普通 targets 模式

数据流：

```text
targets
 -> analyze_target for each
 -> sort_candidates
 -> build_roles
 -> render_markdown
 -> signal_summaries
```

角色：

- 主仓：第 1 个可交易标的。
- 副仓：第 2 个可交易标的。
- 观察：第 3 个可交易标的。
- 可交易：`status not in {"暂不碰", "数据失败"}`。

目标仓位：

```python
if status in {"暂不碰", "数据失败"}: 0
主仓:
  if current >= confirm: min(main_cap, 40)
  else: min(main_cap, 30)
副仓:
  低吸观察/等转强 -> 25
  其他 -> 20
观察:
  低吸观察/等转强/防守观察/冲高减仓 -> 10
```

若合计超过 `max_total`，按 `观察 -> 副仓 -> 主仓` 顺序削减，直到不超过组合上限。

输出面板：

```text
🧺 轮动仓位计划
规则版本：trader_portfolio_v1
📌 当前组合结论
📊 仓位分配
🔁 加仓规则
🔻 降仓规则
🎯 单票执行价位
⏱️ T0 配合
⚠️ 风险控制
```

### 9.2 snapshot 高切低模式

输入 JSON 允许字段：

```json
{
  "account": {
    "total_position_pct": 60,
    "cash_pct": 40,
    "max_move_pct": 10
  },
  "holdings": [
    {"target": "南网科技", "weight_pct": 30, "cost": 57.60}
  ],
  "candidates": [
    {"target": "中国铝业"}
  ]
}
```

轮动规则：

1. 若持仓 A 风控退出：
  - `is_risk_exit = status == 暂不碰 or current <= stop`
  - level = 风控退出
  - fraction = 1/2
  - 优先找 confirmed 候选 B 承接，否则释放仓位留现金。
2. 否则若 A 高位钝化且 B confirmed：
  - `is_high_stalled = status == 冲高减仓 or current >= take * 0.98`
  - level = 强轮动
  - fraction = 1/3
3. 否则若 A 高位钝化但 B 只 near：
  - level = 轻轮动
  - fraction = 1/6
  - 不承接，先留现金。
4. 否则若 A 接近减仓且 B near：
  - `is_near_reduce = status in {"等转强", "突破观察"} or current >= confirm`
  - level = 标准轮动
  - fraction = 1/4
5. 否则不轮动。

候选确认等级：

```python
if current >= confirm: confirmed
elif status in {"等转强", "低吸观察"} or current >= confirm * 0.97: near
else: unconfirmed
```

释放仓位：

```python
released = holding_weight_pct * fraction
if level != "风控退出":
    released = min(released, max_move_pct)
transfer = min(released, max_move_pct) if B confirmed else 0
cash_keep = released - transfer
```

snapshot 输出面板：

```text
🧺 高切低轮动面板
规则版本：trader_portfolio_rotation_v1
📌 当前结论
📊 当前仓位
🔁 轮动动作
🎯 关键价位
🛑 卖完条件
🚫 禁止动作
📈 后续复盘
👉 一句话
```

## 10. review-trader 午间/盘后复盘

入口：

```bash
python3 scripts/final_review.py --target 南网科技 --cost 57.60 --session close
python3 scripts/final_review.py --target 南网科技 --cost 57.60 --session midday
```

### 10.1 数据流

```text
target + optional cost + session
 -> quote + daily(days=40) + 5m(datalen=80)
 -> current = quote.current_price or last daily close
 -> selected_date = trade_date or daily[-1].date or quote.trade_date
 -> analyze_intraday
 -> build_levels
 -> theory_verdicts
 -> render_single
```

### 10.2 分时分析

按交易日过滤 5m K。

session = midday 时只取 09:30-11:30。

若 bars < 8：

- data_state = partial
- 分时走势降级
- 量能拆分不可用
- coverage_complete = False

正常分段：

- morning: 09:30-11:30
- open_flush: 09:30-10:00
- rebound: 10:00-11:30
- late_morning: 10:45-11:30
- afternoon: 13:00-15:00
- digestion: 13:00-14:30
- tail: 14:30-15:00

覆盖状态：

```python
coverage_complete = session == "midday" or coverage_end_time >= "14:55"
data_state = "full" if coverage_complete else "partial_close"
```

量能：

- morning_total
- afternoon_total
- total
- max_bar
- early_avg = avg(open_flush or morning[:6])
- recent_avg = avg(digestion or afternoon)
- afternoon_shrink = recent_avg < early_avg * 0.75

### 10.3 价位层

支撑：

- 今日收盘价/午间现价：守住偏强。
- 回撤第一防线：若今日低点存在且低于 current，则 `max(today_low, current*0.985)`，否则 `current*0.985`。
- 今日低点：跌破则止跌失败。
- 前一交易日低点：若与今日低点距离 <= 1%，加入双低点参考。

压力：

- 今日高点：明日/午后第一关。
- 若有 cost 且 cost > current：
  - `cost * 0.998`: 成本区前压力。
  - `cost`: 你的成本，最关键。
- 否则若近 20 日成交密集区上沿 > current，加入成交密集压力。
- 若 20 日高点 > current * 1.03，加入中期趋势压力。
- 若没有压力，使用 `current * 1.02` 短线确认压力。

成交密集区：

```python
typical = (high + low + close) / 3
center = volume weighted typical if volume exists else average typical
spread = max((max(typical)-min(typical)) * 0.18, center * 0.01)
chip_zone = center - spread 到 center + spread
```

### 10.4 五层模型评分

指标：

- 缠论结构
- 威科夫量价
- 筹码压力
- 资金行为
- 动能

布尔条件：

```python
low_close_reclaim = today_low exists and current > today_low * 1.025
double_low = today_low and previous_low distance <= 1%
lower_high = recent_high exists and current < recent_high * 0.96
above_pressure = current >= key_pressure
volume_repair = intraday usable and morning_ratio >= 0.55 and low_close_reclaim
afternoon_shrink = recent_avg < early_avg * 0.75
chip_pressure = cost and current < cost and (cost-current)/current <= 0.05
```

分数：

```python
structure_score = 50
  +15 if double_low
  +15 if low_close_reclaim
  +10 if current > prev_close
  -15 if lower_high
  +15 if above_pressure

volume_score = 50
  +20 if volume_repair
  -10 if afternoon_shrink

chip_score = 50
  -15 if chip_pressure
  +10 if cost and pnl_pct >= 0

momentum_score = 45
  +20 if above_pressure
  +10 if current > prev_close
  -10 if afternoon_shrink

total = round(structure*0.32 + volume*0.28 + chip*0.18 + momentum*0.22)
```

状态：

```python
if above_pressure and total >= 70: 转强确认
elif total >= 55: 短线止跌修复
else: 弱修复观察
```

### 10.5 输出面板

```text
📌 {股票}｜{日期}盘后复盘 / 午间复盘
结论
只看两个点
📊 今日状态 / 上午状态
量能重点
📈 走势结构 / 上午走势
理论定位
🔎 信号判断
🎯 明日关键价位 / 午后关键价位
🧭 明日应对 / 午后应对
👉 一句话
```

禁止宽表格。输出要适合微信阅读。

## 11. trader-pool 选股池

入口：

```bash
python3 scripts/final_pool.py analyze --target 南网科技
python3 scripts/final_pool.py add --target 南网科技
python3 scripts/final_pool.py show
python3 scripts/final_pool.py rank
python3 scripts/final_pool.py plan
python3 scripts/final_pool.py review
python3 scripts/final_pool.py remove --target 南网科技
python3 scripts/final_pool.py archive-exited
```

状态文件：

```text
~/.trader/pool.json
~/.trader/last_plan.json
~/.trader/pool_archive.json
```

池容量：

- 最大 10 只。
- 明日执行票最多 3 只。

### 11.1 入池评分

先调用 `trader.build_report`。实时失败时可用离线占位报告。

动能通过：

```python
near_confirm = current >= confirm * 0.985
ma_support = ma5 >= ma10 and current >= ma20
stage_ok = stage in {"走强", "修复"}
scene_ok = scene in {"等转强", "突破确认", "突破观察", "冲高减仓"}

momentum_passes = (near_confirm and ma_support) or (stage_ok and scene_ok and ma_support)
```

评分满分 100：

缠论 45：

```python
base 24
stage: 走强 +10, 修复 +7, 震荡 +3, 转弱 -10
scene: 等转强/突破确认/突破观察/冲高减仓 +7
       低吸观察/防守观察 +4
       暂不碰 -10
confirm 距离 current <=2% +4, <=5% +2
clamp 0..45
```

威科夫 30：

```python
base 15
volume_text 包含 放大/放量 +8
包含 缩量/收缩 +5
否则 +3
momentum_passes +5
clamp 0..30
```

筹码 25：

```python
base 15
current > stop +5
support <= current <= max(confirm, support) +4
take > current +3
clamp 0..25
```

总分 = 三项相加。

### 11.2 入池判定

```python
if current <= stop:
    result="拒绝", status="淘汰"
elif not confirm or not stop:
    result="待补", status="观察"
elif total_score >= 70:
    result="入池", status="执行" if momentum_passes else "观察"
elif total_score >= 55:
    result="入池", status="观察"
else:
    result="待补", status="观察"
```

记录字段：

- target
- name
- symbol
- added_at
- updated_at
- status
- admission_result
- admission_reason
- structure_summary
- trigger
- defense
- confirm
- support
- current
- momentum_state
- momentum_text
- offline
- chanlun_score
- wyckoff_score
- chip_score
- total_score

### 11.3 池内排序

排序：

```python
status_rank = {"执行": 3, "观察": 2, "淘汰": 1}
sort by (status_rank, total_score) desc
```

rank 面板：

```text
📊 池内行动排序
📌 今日优先级
🎯 行动排序
👤 空仓怎么选
📦 有底仓怎么做
⏱️ T0 倾向
🚫 今天先不碰
👉 一句话
```

rank 状态映射：

```python
执行 + momentum_state 通过 -> 低吸观察
执行 + momentum_state 未通过 -> 等转强
观察 -> 防守观察
淘汰 -> 暂不碰
```

T0 倾向：

```python
淘汰 -> 不做
执行 -> 等待低吸触发
momentum_state 通过 -> 等待高抛触发
其他 -> 不做
```

### 11.4 明日计划

`plan` 输出：

```text
选股池盘后分析 — 日期
候选池容量 / 执行 / 观察 / 淘汰 / 明日只盯Top2
明日优先级
结构评分
上涨动能过滤
明日交易指导卡
待补与拒绝
仓位纪律
一句话
```

仓位纪律固定：

- 执行：首次最多 1 成。
- 确认：最多加到 3 成。
- 单票风险：不超过账户 1R。
- 总仓位：不超过 5 成。
- 盘中新票：只能走例外通道，小仓试错。

`plan` 会把执行票写入 `~/.trader/last_plan.json`，供次日 `review` 使用。

### 11.5 次日复盘

对上一份作战表的 execution_items 逐只复盘：

```python
if current <= defense:
    result = "失效"
elif current >= trigger:
    result = "命中"
else:
    result = "未触发"
```

未触发不是错误；失效则转入风险处理。

## 12. trader_signal_v1 机器可读信号

协议版本：

```python
contract = "trader_signal_v1"
```

必填字段：

```python
{
  "contract": "trader_signal_v1",
  "source_skill": "...",
  "symbol": "...",
  "name": "...",
  "trade_date": "YYYY-MM-DD",
  "analysis_time": "YYYY-MM-DD HH:MM:SS",
  "signal_type": "...",
  "direction": "...",
  "action": "...",
  "confidence": "...",
  "data_status": "...",
  "trigger": {"type": "...", "price": 0.0, "text": "..."},
  "invalidation": {"type": "...", "price": 0.0, "text": "..."},
  "position": {"max_total_pct": 30, "max_single_move_pct": 10},
  "risk_flags": [],
  "summary": "..."
}
```

允许 source_skill：

- trader
- t0-trader
- trader-compare
- trader-portfolio
- review-trader
- trader-pool

允许 signal_type：

- observe
- wait_for_confirmation
- track
- low_buy_watch
- low_buy_triggered
- high_sell_watch
- high_sell_triggered
- reduce
- defensive
- risk_stop
- trigger_expired
- blocked
- review_result

允许 direction：

- bullish
- bearish
- neutral
- bullish_lean
- bearish_lean

允许 action：

- no_action
- observe
- wait
- track
- pilot_entry
- low_buy
- high_sell
- reduce
- stop_low_buy
- stop_high_sell

允许 confidence：

- low
- medium
- high

允许 data_status：

- full
- degraded
- partial
- insufficient
- fresh
- stale
- non_trading

校验：

- `trigger` 和 `invalidation` 必须是 object。
- 若存在 `price`，必须是数字。
- `position.max_total_pct` 和 `position.max_single_move_pct` 必须在 0..100。
- triggered T0 信号 `low_buy_triggered/high_sell_triggered` 必须有 `trigger.price` 和非空 `trigger.text`。

信号持久化：

- 默认路径：`~/.trader/signals.jsonl`
- 每行一个 JSON。
- `append_signal` 先校验，再追加。
- `load_recent_signals(symbol=None, limit=20)` 倒序读取，按 symbol 可选过滤。

## 13. 输出校验和测试要求

每个功能包都必须有自己的输出校验器，校验：

- 固定标题和区块顺序。
- 禁止 agent 自行改写面板。
- 禁止旧版字段混入。
- 表格数量和格式。
- 关键状态枚举。

核心测试：

```bash
python3 02-共享模块-shared/03-输出校验-contracts/test_signal_contract.py
pytest 01-功能包-packages/01-单票分析-trader/tests/test_contract.py -q
pytest 01-功能包-packages/02-盘中T0-t0-trader/tests/test_t0_contract.py -q
pytest 01-功能包-packages/03-多股比较-trader-compare/tests/test_compare_contract.py -q
pytest 01-功能包-packages/04-仓位轮动-trader-portfolio/tests/test_portfolio_contract.py -q
pytest 01-功能包-packages/05-盘后复盘-review-trader/tests/test_review_contract.py -q
pytest 01-功能包-packages/06-选股池-trader-pool/tests/test_pool_contract.py -q
```

## 14. 重写实现的最低等价标准

另一个 agent 重写时，只要满足以下条件，就视为等价：

1. 能用腾讯 quote、腾讯 qfq daily、Sina 5m/15m/30m 获取数据，并标准化为本文字段。
2. `trader_candidate_core` 的支撑/压力、观察区、止损、状态、评分与本文一致。
3. `t0-trader` 只用完成 5m K 触发，且执行价只在 `已触发` 时出现。
4. `trader` 输出固定手机面板，并能输出 `trader_signal_v1`。
5. `trader-compare` 能按分数排序、选择空仓优先和有底仓 T0 标的。
6. `trader-portfolio` 能做普通角色分配和 snapshot 高切低轮动。
7. `review-trader` 能生成午间/盘后五层模型复盘。
8. `trader-pool` 能维护 `~/.trader/pool.json`，并完成 analyze/add/show/rank/plan/review/remove/archive-exited。
9. 所有 Markdown 面板的区块标题、顺序和核心字段与本文一致。
10. 所有 JSON 信号通过 `trader_signal_v1` 校验。

