# T0 增强改造计划

> 目标：补全 t0-trader 信号准确性缺失的指标、数据源和风控逻辑，不影响现有输出格式，不损害实时性能。
> 影响文件：indicators.py、price_point_engine.py、config.py
> **不修改文件**：t0_core.py、final_t0.py、t0_run.py、monitor.py
> 数据源说明：所有改造只使用当前已有免费 API（腾讯日线 + 新浪 5m/15m/30m 分钟线），不引入外部付费数据。

---

## 一、当前已有 vs 缺失清单

### 1.1 已有数据源

| 数据 | 来源 | 周期 | 字段 |
|---|---|---|---|
| 实时快照 | 腾讯行情 | 实时 | 现价/昨收/今开/最高/最低/成交量/成交额/换手率/涨跌幅 |
| 前复权日线 | 腾讯行情 | 日线（30 天默认） | open/close/high/low/volume + 自动计算 atr7/atr14/atr_ratio |
| 5 分钟线 | 新浪 | 5m（60 根默认） | day/open/high/low/close/volume |
| 15 分钟线 | 新浪 | 15m（60 根默认） | 同上 |
| 30 分钟线 | 新浪 | 30m（60 根默认） | 同上 |

### 1.2 缺失数据源（不在这个计划中的，因为本计划不做）

本计划**不做**以下需求，因为需要付费数据源：

| 缺失数据 | 为什么需要 | 获取方式 | 本计划处理 |
|---|---|---|---|
| Level 2 逐笔/十档 | 买卖盘口深度 | 付费接口（万得/同花顺 iFinD） | **不做。计划不涉及 Level 2。** |
| 交易所精确 VWAP | 当前用典型价 `(o+h+l+c)/4 * vol` 近似 | 交易所 Level 1 分时数据 | **替代：布林带通道 + VWAP 联合使用** |
| 昨日 5m 高低点 | 日内重要参考位 | 新浪 5m 只返回当日数据 | **替代：日线 20 日高低点 + 5m 12 根高低点代理** |
| 精确量比（过去 5 日每分钟） | 更精确量能判断 | 每日分钟级成交额历史 | **替代：已有 volume_ratio = 最近 6 根均量 : 前 12 根均量，语义等价** |

> **结论**：不缺关键数据。本计划全部基于现有数据源做增强。

### 1.3 已有指标 vs 缺失指标

| 已有指标（indicators.py） | 缺失指标 |
|---|---|
| SMA / EMA | **布林带（Bollinger Bands）** |
| MACD(12,26,9) | **KDJ/随机指标** |
| RSI(14) | **RSI 背离检测** |
| VWAP | **OBV（能量潮）** |
| 量比(recent/prior) | **ADX（趋势强度）** |
| 上影线/下影线检测 | **K 线形态库（十字星/锤子/吞没/倒锤）** |
| 新最低/新最高检测 | **ATR 动态止损价** |

---

## 二、性能评估：不影响操盘

### 2.1 计算量测算

| 操作 | 数据量 | 复杂度 | 预估耗时 |
|---|---|---|---|
| 原始 5m/RSI/MACD/VWAP/量比（已有） | 60-120 根 bar | O(n) | ~5ms |
| + 布林带(20 周期) | 60-120 次窗口运算 | O(20n) | ~3ms |
| + RSI 背离(找极值 + 分背离) | 60-120 次遍历 | O(n) | ~1ms |
| + KDJ(9 周期) | 60-120 次 EMA | O(n) | ~2ms |
| + OBV | 60-120 次累加 | O(n) | ~1ms |
| + 5 个 K 线形态检测 | 2-3 根 bar | O(1) | <1ms |
| + ADX(14 周期) | 60-120 次 WDI/DI | O(n) | ~5ms |
| + ATR 动态止损 | 1 次计算 | O(1) | <1ms |
| **合计** | | | **~18ms** |

> **结论**：全部新增指标算完约 **18 毫秒**，而你等新浪 API 返回 5m 数据就要 **200-500 毫秒**。计算时间不到网络延迟的 10%，**可以忽略不计**。

### 2.2 内存占用

60 根 5m bar，每根 bar 计算：
- RSI 序列：60 floats
- MACD 序列：60×3 = 180 floats
- 布林带：60 × 5 字段 = 300 floats
- KDJ：60×3 = 180 floats
- OBV：60×2 = 120 floats

**合计约 1320 个浮点数，占用约 10KB**。对比 5m bar 本身数据（每根 ~200 字节 × 60 = 12KB），指标数据量可忽略。

### 2.3 实际场景

用户触发 `t0-trader` 分析一只股票的时间线：

```
用户请求 → 腾讯行情快照 (~100ms) → 新浪 5m 数据 (~300ms) → 
布林带(3ms) + RSI背离(1ms) + KDJ(2ms) + OBV(1ms) + 形态(<1ms) + ADX(5ms) + ATR止损(<1ms) → 
构建信号 → Markdown 渲染 (~5ms) → 返回结果

总耗时: ~420ms （瓶颈是网络，不是计算）
```

**结论：不阻塞交易、不增加感知延迟。**

---

## 三、指标打架解决方案（分层架构）

### 3.1 现状问题

当前 `detect_buy_trigger()` 和 `detect_sell_trigger()` 有 **8 个平权条件**，满足 4 个 + 至少 1 个核心条件即触发。

**问题**：
- 上影线检测（辅助级）和 RSI 背离（决策级）平权计数，不对
- 10 个指标全放一个池子，用户分不清哪个信号更可信
- 没有考虑市场环境——强趋势中的 RSI 超卖和震荡市的 RSI 超卖意义完全不同

### 3.2 分层架构（改为 4 层）

```
┌────────────────────────────────────────────────────────────┐
│  Layer 1: 否决层 (Blocking)                                 │
│  出现任一条件 → 本侧信号直接取消，不参与信号匹配              │
│  - 5m 持续创新高/新低 → 不逆势交易                          │
│  - MACD 柱状图继续放大（单边趋势）→ 趋势未衰竭                │
│  - 放量跌破主支撑 / 放量突破主阻力 → 真突破，不反向交易        │
│  - VWAP 上行 + 放量突破主阻力 → 强势突破，不急于高抛          │
│  - ADX > 25（强趋势）+ 逆势信号 → 辅助条件不计数（但不阻断）  │
├────────────────────────────────────────────────────────────┤
│  Layer 2: 核心条件 (Core) 需 ≥2 个同时满足                   │
│  按信号权重从高到低排列：                                    │
│  - RSI 背离（最高权重，+1 core）                             │
│  - MACD 柱状图收缩（+1 core）                               │
│  - 量能收缩（+1 core）                                      │
│  - 站回/跌破 VWAP（+1 core）                                │
│  - 布林带触及上/下轨 + 极值和背离共振（+1 core）              │
├────────────────────────────────────────────────────────────┤
│  Layer 3: 辅助条件 (Auxiliary) 加分但不核心                   │
│  - KDJ 超卖金叉 / 超买死叉                                  │
│  - K 线形态（锤子线/十字星/吞没）                            │
│  - OBV 价量背离                                             │
│  - RSI 极值转向（已有 rsi_turning_up/down）                  │
├────────────────────────────────────────────────────────────┤
│  Layer 4: 方向过滤器 (Direction Filter)                      │
│  - 震荡市(ADX<20)：辅助条件正常计数 + RSI 极值信号权重提升     │
│  - 趋势市(ADX>25)：只做顺势回调/冲高衰竭，不做超买超卖均值回归 │
│  - 中性市(ADX 20-25)：按现有逻辑，不做加权                    │
└────────────────────────────────────────────────────────────┘
```

### 3.3 信号判定规则

```python
# ===== 低吸信号判定 =====
def evaluate_buy_signal(state, bars, zones):
    matched_core = []
    matched_aux = []
    blocked = []
    adx = state.get("adx", 0) or 0
    is_strong_trend = adx > 25

    # [Block] 否决层
    if is_new_low_recent(bars):
        blocked.append("5m持续创新低")
    if macd_green_expanding(state):
        blocked.append("MACD绿柱继续放大")
    if current < support and volume_expanded:
        blocked.append("放量跌破主支撑")
    if is_strong_trend:
        pass  # 强趋势下不做辅助辅助辅助
    if blocked:
        return "被阻断", blocked

    # [Core] 核心层
    if state.get("bullish_divergence"):
        matched_core.append("RSI底背离")  # 最高权重
    if macd_green_shrinking(state):
        matched_core.append("MACD绿柱缩短")
    if state.get("volume_ratio", 1) < VOLUME_SHRINK_RATIO:
        matched_core.append("量能收缩")
    if current >= vwap:
        matched_core.append("站回VWAP")
    # 布林带下轨 + RSI 极值共振
    if state.get("pct_b") is not None and state.get("pct_b") < 0 and state.get("last_rsi") and state.get("last_rsi") < 30:
        matched_core.append("布林下轨+RSI超卖共振")

    # [Aux] 辅助层
    if state.get("kdj_oversold") and state.get("kdj_golden_cross"):
        matched_aux.append("KDJ超卖金叉")
    if state.get("hammer") or state.get("bullish_engulfing"):
        matched_aux.append("锤子线/看涨吞没")
    if state.get("doji"):
        matched_aux.append("十字星（变盘信号）")
    if _is_obv_divergence_up(state, bars):
        matched_aux.append("OBV价平量升")
    if rsi_turning_up(state):
        matched_aux.append("RSI低位拐头")

    # [Filter] 方向过滤器
    if is_strong_trend:
        # 强趋势下，只做核心条件
        matched_aux = []  # 辅助条件清零

    # [Decide] 判定
    if len(matched_core) >= 2:
        confidence = "high" if len(matched_core) >= 3 else "medium"
    elif len(matched_core) == 1 and len(matched_aux) >= 2:
        confidence = "medium"
    elif len(matched_core) == 0 and len(matched_aux) >= 3:
        confidence = "low"  # 仅辅助条件，低置信
    else:
        confidence = "none"

    return (
        "已触发" if confidence != "none" else "观察中",
        {"core": matched_core, "aux": matched_aux, "confidence": confidence}
    )
```

### 3.4 高抛信号判定（对称逻辑）

```python
# ===== 高抛信号判定 =====
def evaluate_sell_signal(state, bars, zones):
    matched_core = []
    matched_aux = []
    blocked = []
    adx = state.get("adx", 0) or 0
    is_strong_trend = adx > 25

    # [Block] 否决层
    if is_new_high_recent(bars):
        blocked.append("5m持续创新高")
    if macd_red_expanding(state):
        blocked.append("MACD红柱继续放大")
    if vwap_up and volume_expanded and current > resistance:
        blocked.append("VWAP上行且放量突破主压力")
    if is_strong_trend:
        pass  # 强趋势下辅助条件清零
    if blocked:
        return "被阻断", blocked

    # [Core] 核心层
    if state.get("bearish_divergence"):
        matched_core.append("RSI顶背离")
    if macd_red_shrinking(state):
        matched_core.append("MACD红柱缩短")
    if state.get("volume_ratio", 1) <= 1.0:
        matched_core.append("冲高未放量")
    if current <= vwap:
        matched_core.append("跌回VWAP")
    if state.get("pct_b") is not None and state.get("pct_b") > 1 and state.get("last_rsi") and state.get("last_rsi") > 70:
        matched_core.append("布林上轨+RSI超买共振")

    # [Aux] 辅助层
    if state.get("kdj_overbought") and state.get("kdj_death_cross"):
        matched_aux.append("KDJ超买死叉")
    if state.get("inverted_hammer") or state.get("bearish_engulfing"):
        matched_aux.append("倒锤线/看跌吞没")
    if _is_obv_divergence_down(state, bars):
        matched_aux.append("OBV价升量缩")
    if rsi_turning_down(state):
        matched_aux.append("RSI高位拐头")

    # [Filter] 方向过滤器
    if is_strong_trend:
        matched_aux = []

    # [Decide]
    confidence = "high" if len(matched_core) >= 3 else \
                 "medium" if len(matched_core) >= 2 or (len(matched_core) == 1 and len(matched_aux) >= 2) else \
                 "low" if len(matched_aux) >= 3 else "none"

    return ("已触发" if confidence != "none" else "观察中",
            {"core": matched_core, "aux": matched_aux, "confidence": confidence})
```

### 3.5 用户终端展示（核心/辅助分离）

现有输出只展示 `matched_conditions` 平铺列表，改为分层展示：

```
🎯 T0 — 南网科技（688248）｜现价 4.35（+1.23%）

🔍 扫描
当前：低吸
买入：已触发（置信度高）
卖出：未触发

📊 低吸信号分析
核心条件（3个）：
  ✓ RSI底背离（价格新低 RSI 未新低）
  ✓ MACD绿柱缩短（空头动能衰竭）
  ✓ 量能收缩（抛压减轻）
辅助条件（2个）：
  ✓ KDJ超卖金叉
  ✓ 锤子线
置信度：高（核心≥2）

📊 高抛信号分析
核心条件（0个）：
  （空，未触发）
辅助条件（1个）：
  ◦ 冲高未放量
置信度：无

🚩 关键价位
低吸观察：4.32以下 → 执行 4.33 → 可接受 4.34
高抛观察：4.42附近
止损：4.20（ATR×2动态）

💰 仓位管控
触发后：底仓的 20%-30%
```

> **关键改动**：用户一眼看到核心条件有几个、辅助条件有几个、置信度几档。不再从一长串混合条件里自己判断可信度。

### 3.6 不同市场环境下的判定差异

| 市场状态 | ADX 值 | 低吸条件 | 高抛条件 | 说明 |
|---|---|---|---|---|
| **强趋势上涨** | > 25 | 只做核心条件，辅助条件清零 | 高抛辅助条件正常计数 | 趋势中不做超卖抄底，但可以做冲高衰竭高抛 |
| **强趋势下跌** | > 25 | 低吸辅助条件正常计数 | 只做核心条件，辅助条件清零 | 跌势中不做超买高抛，但可以做止跌低吸 |
| **震荡市** | < 20 | 核心1 + 辅助2 即可触发 | 核心1 + 辅助2 即可触发 | 均值回归有效，辅助条件权重提升 |
| **中性市** | 20-25 | 核心2 或 核心1 + 辅助2 | 同上 | 现有逻辑，不做加权 |

> **注意**：ADX 的方向（+DI vs -DI 谁大）需要额外判断趋势方向。当前只实现 ADX 数值，+DI/-DI 方向判断放在未来迭代（不阻塞本计划）。

---

## 四、实施方案（按优先级排序）

### P0-1：ATR 动态止损

**现状问题**：止损价 = `main_support * 0.995`（固定 0.5%），在 ATR14=0.15（高波动天）时止损太窄容易穿仓，在 ATR14=0.001（低波动天）时止损太宽不够灵敏。

**方案**：

```python
# config.py 新增常量
ATR_STOP_FACTOR: float = 2.0          # 止损距离 = ATR14 × N
ATR_STOP_MIN_PCT: float = 0.005       # 止损最小距离（占现价百分比），兜底
ATR_STOP_MAX_PCT: float = 0.025       # 止损最大距离（占现价百分比），封顶
```

```python
# price_point_engine.py 新增函数
def compute_atr_dynamic_stop(current: float, atr14: float, atr_ratio: float) -> float | None:
    """计算 ATR 动态止损价。"""
    if atr14 <= 0 or current <= 0:
        return None
    atr_distance = atr14 * ATR_STOP_FACTOR
    pct_distance = current * ATR_STOP_MIN_PCT  # 兜底最小
    atr_distance = max(atr_distance, pct_distance)
    pct_max = current * ATR_STOP_MAX_PCT
    if atr_distance > pct_max:
        atr_distance = pct_max
    return round_price(current - atr_distance)
```

**改动范围**：
- `config.py`：新增 3 个常量
- `price_point_engine.py`：新增 `compute_atr_dynamic_stop()` 函数，在 `build_price_point_model()` 末尾用 ATR 止损价覆盖 `buy_model["invalid_price"]`
- `t0_core.py`：无需改动（`invalid_price` 字段已有消费逻辑）

**现有 ATR 数据**：`light_data.py:253-286` 的 `_compute_atr_fields()` 已在日线 bar 上计算了 `atr14`、`atr7`、`atr_ratio`，`price_point_engine.py:671-679` 已读取 `atr14` 和 `atr_ratio`，数据已就绪。

---

### P0-2：RSI 背离检测

**现状问题**：只判断 RSI 是否转向（`turning_up`/`turning_down`），没有检测价格与 RSI 的背离——这是 5m 级别最强的 T0 信号之一，P0 级。

**方案**：在 `indicators.py` 新增背离检测函数。

```python
def detect_bullish_divergence(bars: list[dict[str, Any]], rsi_series: list[float | None], lookback: int = 12) -> bool:
    """
    底背离（看涨）：最近 2 个低点中，价格创新低但 RSI 不回创新低。
    lookback: 搜索窗口，默认 12 根 5m 线（1 个小时）。
    """
    lows_in_window = []
    for i in range(len(bars) - lookback, len(bars)):
        close = float(bars[i].get("close", 0))
        rsi_val = rsi_series[i]
        if rsi_val is not None and close > 0:
            lows_in_window.append((close, rsi_val, i))
    if len(lows_in_window) < 2:
        return False
    lows_in_window.sort(key=lambda x: x[1])
    rsi_min_1 = lows_in_window[0]
    rsi_min_2 = lows_in_window[1]
    return rsi_min_1[0] < rsi_min_2[0]


def detect_bearish_divergence(bars: list[dict[str, Any]], rsi_series: list[float | None], lookback: int = 12) -> bool:
    """
    顶背离（看跌）：最近 2 个高点中，价格创新高但 RSI 不回创新高。
    """
    highs_in_window = []
    for i in range(len(bars) - lookback, len(bars)):
        close = float(bars[i].get("close", 0))
        rsi_val = rsi_series[i]
        if rsi_val is not None and close > 0:
            highs_in_window.append((close, rsi_val, i))
    if len(highs_in_window) < 2:
        return False
    highs_in_window.sort(key=lambda x: x[1], reverse=True)
    rsi_max_1 = highs_in_window[0]
    rsi_max_2 = highs_in_window[1]
    return rsi_max_1[0] < rsi_max_2[0]
```

**在 `latest_indicator_state()` 中增加背离计算**：

```python
def _find_local_extremes(values: list[float | None], window: int = 3) -> list[tuple[str, int, float]]:
    """找局部极值点索引（左 window 个和右 window 个都比它小/大）"""
    extremes: list[tuple[str, int, float]] = []
    for i in range(window, len(values) - window):
        v = values[i]
        if v is None:
            continue
        is_low = all(v <= values[i+k] for k in range(-window, window+1) if k != 0 and values[i+k] is not None)
        is_high = all(v >= values[i+k] for k in range(-window, window+1) if k != 0 and values[i+k] is not None)
        if is_low:
            extremes.append(("low", i, v))
        if is_high:
            extremes.append(("high", i, v))
    return extremes
```

**在信号匹配中使用**（P0-2 与 P0-3 布林带结合为"共振"核心条件）：

```python
# detect_buy_trigger() 核心条件层
core_count = 0
matched_core = []
matched_aux = []

if state.get("bullish_divergence"):
    matched_core.append("RSI底背离（价格新低RSI未新低）")
    core_count += 1

if macd_green_shrinking(state):
    matched_core.append("MACD绿柱缩短")
    core_count += 1

if (state.get("volume_ratio") or 1) < VOLUME_SHRINK_RATIO:
    matched_core.append("量能收缩")
    core_count += 1

if state.get("vwap") is not None and current >= float(state["vwap"]):
    matched_core.append("站回VWAP")
    core_count += 1

# 布林带下轨 + RSI 超卖共振（P0-3 布林 + P0-2 背离结合）
if (state.get("pct_b") is not None and state.get("pct_b") < 0 and
    state.get("last_rsi") is not None and state.get("last_rsi") < 30):
    matched_core.append("布林下轨+RSI超卖共振")
    core_count += 1
```

**卖出对称**：

```python
if state.get("bearish_divergence"):
    matched_core.append("RSI顶背离（价格新高RSI未新高）")
    core_count += 1
if macd_red_shrinking(state):
    matched_core.append("MACD红柱缩短")
    core_count += 1
if state.get("volume_ratio", 1) <= 1.0:
    matched_core.append("冲高未放量")
    core_count += 1
if state.get("vwap") is not None and current <= float(state["vwap"]):
    matched_core.append("跌回VWAP")
    core_count += 1
if (state.get("pct_b") is not None and state.get("pct_b") > 1 and
    state.get("last_rsi") is not None and state.get("last_rsi") > 70):
    matched_core.append("布林上轨+RSI超买共振")
    core_count += 1
```

**辅助条件层**（低吸）：

```python
if state.get("kdj_oversold") and state.get("kdj_golden_cross"):
    matched_aux.append("KDJ超卖金叉")
if state.get("hammer") or state.get("bullish_engulfing"):
    matched_aux.append("锤子线/看涨吞没")
if state.get("doji"):
    matched_aux.append("十字星（变盘信号））
if _is_obv_divergence_up(state, bars):
    matched_aux.append("OBV价平量升")
if rsi_turning_up(state):
    matched_aux.append("RSI低位拐头")
```

**判定层**：

```python
# 方向过滤器：ADX 判断
adx = state.get("adx", 0) or 0
is_strong_trend = adx > 25

# 强趋势下，辅助条件清零（不做逆势均值回归）
if is_strong_trend:
    matched_aux = []

# 判定
is_triggered = False
confidence = "none"

if core_count >= 2:
    is_triggered = True
    confidence = "high" if core_count >= 3 else "medium"
elif core_count == 1 and len(matched_aux) >= 2:
    is_triggered = True
    confidence = "medium"
elif len(matched_aux) >= 3:
    is_triggered = True
    confidence = "low"
```

**判定结果**存入 `plan["buy"]["signal_quality"]`，供 `t0_core.py.render_markdown()` 展示：

```python
buy_model["signal_quality"] = {
    "core": matched_core,
    "aux": matched_aux,
    "confidence": confidence,
}
```

**改动范围**：
- `indicators.py`：新增 `detect_bullish_divergence()`、`detect_bearish_divergence()`、`_find_local_extremes()`（3 个函数）
- `price_point_engine.py`：重构 `detect_buy_trigger()` 和 `detect_sell_trigger()` 为分层架构；在 `latest_indicator_state()` 增加背离、布林、KDJ 等字段
- `config.py`：可选新增 `RSI_DIVERGENCE_LOOKBACK: int = 12`
- **`t0_core.py`**：需要在 `render_markdown()` 中消费新的 `signal_quality` 字段，分层展示 core/aux

---

### P0-3：布林带

**现状问题**：支撑/阻力区是静态区间（main_support ± width_pct），没有动态波动率带。布林带的上下轨是天然是动态支撑阻力。

**方案**：

```python
import math

def calculate_bollinger_bands(
    closes: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> dict[int, dict[str, float | None]]:
    """
    返回每个位置的布林带值。
    返回 dict[index -> {middle, upper, lower, bandwidth, pct_b}]
    """
    result: dict[int, dict[str, float | None]] = {}
    for i in range(len(closes)):
        if i + 1 < period:
            continue
        window = closes[i + 1 - period : i + 1]
        middle = sum(window) / period
        variance = sum((x - middle) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper = middle + num_std * std
        lower = middle - num_std * std
        bandwidth = (upper - lower) / middle if middle > 0 else None
        pct_b = (closes[i] - lower) / (upper - lower) if (upper - lower) > 0 else None
        result[i] = {
            "middle": round(middle, 4),
            "upper": round(upper, 4),
            "lower": round(lower, 4),
            "bandwidth": round(bandwidth, 6) if bandwidth is not None else None,
            "pct_b": round(pct_b, 4) if pct_b is not None else None,
        }
    return result
```

**在 `find_key_levels()` 中增加布林带作为支撑/阻力级别**：

```python
bb = calculate_bollinger_bands(closes, period=20, num_std=2.0)
if bb and len(bb) > 0:
    last_idx = max(bb.keys())
    bb_last = bb[last_idx]
    add_level(support, "布林下轨(20,2σ)", bb_last["lower"], 0.85)
    add_level(resistance, "布林上轨(20,2σ)", bb_last["upper"], 0.85)
    add_level(support, "布林中轨", bb_last["middle"], 0.75)
    add_level(resistance, "布林中轨", bb_last["middle"], 0.75)
```

**在 `latest_indicator_state()` 中增加布林状态**：

```python
bb = calculate_bollinger_bands(closes, period=20, num_std=2.0)
bb_last = bb.get(max(bb.keys(), default=-1), {})
result["bb"] = bb_last
result["pct_b"] = bb_last.get("pct_b")  # pct_b < 0 靠近下轨, pct_b > 1 靠近上轨
result["bb_squeeze"] = (bb_last.get("bandwidth") or 999) < 0.03  # 收口 = 即将变盘
```

**改动范围**：
- `indicators.py`：新增 `calculate_bollinger_bands()`（1 个函数，需 import math）
- `price_point_engine.py`：在 `find_key_levels()` 调用布林带增加级别；在 `latest_indicator_state()` 增加 `bb`、`pct_b`、`bb_squeeze`

---

### P1-1：KDJ 随机指标

**现状问题**：A 股 T0 交易者最常用的指标之一是 KDJ，比 RSI 反应更快。

**方案**：

```python
def calculate_kdj(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 9,
    fast_k: int = 3,
    slow_k: int = 3,
    slow_d: int = 3,
) -> dict[str, list[float | None]]:
    """
    KDJ 指标。
    RSV = (close - low_N) / (high_N - low_N) * 100
    K = SMA(RSV, fast_k)
    D = SMA(K, slow_d)
    J = 3*K - 2*D
    """
    n = len(closes)
    rsv_values: list[float | None] = [None] * n
    
    for i in range(period - 1, n):
        low_n = min(lows[i - period + 1 : i + 1])
        high_n = max(highs[i - period + 1 : i + 1])
        denom = high_n - low_n
        if denom == 0:
            rsv_values[i] = 50.0
        else:
            rsv_values[i] = (closes[i] - low_n) / denom * 100
    
    k_values = calculate_ema([v if v is not None else 50.0 for v in rsv_values], fast_k)
    d_values = calculate_ema([v if v is not None else 50.0 for v in k_values], slow_d)
    j_values: list[float | None] = []
    for k, d in zip(k_values, d_values):
        if k is not None and d is not None:
            j_values.append(round(3 * k - 2 * d, 2))
        else:
            j_values.append(None)
    
    return {"k": k_values, "d": d_values, "j": j_values}
```

**在 `latest_indicator_state()` 中增加 KDJ**：

```python
kjd = calculate_kdj(highs, lows, closes)
result["kdj"] = kjd
result["last_k"] = kjd["k"][-1] if kjd["k"] else None
result["last_d"] = kjd["d"][-1] if kjd["d"] else None
result["last_j"] = kjd["j"][-1] if kjd["j"] else None
result["kdj_golden_cross"] = (
    kjd["k"][-1] is not None and kjd["d"][-1] is not None and
    kjd["k"][-1] > kjd["d"][-1] and len(kjd["k"]) >= 2 and
    kjd["k"][-2] is not None and kjd["d"][-2] is not None and
    kjd["k"][-2] <= kjd["d"][-2]
)
result["kdj_death_cross"] = (
    kjd["k"][-1] is not None and kjd["d"][-1] is not None and
    kjd["k"][-1] < kjd["d"][-1] and len(kjd["k"]) >= 2 and
    kjd["k"][-2] is not None and kjd["d"][-2] is not None and
    kjd["k"][-2] >= kjd["d"][-2]
)
result["kdj_oversold"] = (kjd["j"][-1] is not None and kjd["j"][-1] < 20)
result["kdj_overbought"] = (kjd["j"][-1] is not None and kjd["j"][-1] > 80)
```

**作为辅助条件使用**（不阻塞本计划核心逻辑，作为 P1）：

```python
# detect_buy_trigger 辅助条件增加：
if state.get("kdj_oversold") and state.get("kdj_golden_cross"):
    matched_aux.append("KDJ超卖金叉")

# detect_sell_trigger 辅助条件增加：
if state.get("kdj_overbought") and state.get("kdj_death_cross"):
    matched_aux.append("KDJ超买死叉")
```

**改动范围**：
- `indicators.py`：新增 `calculate_kdj()` 函数
- `price_point_engine.py`：`latest_indicator_state()` 增加 KDJ 字段，信号匹配函数增加 KDJ 辅助条件

---

### P1-2：OBV 能量潮

**现状问题**：只有量比，没有量价背离判断。OBV 可以发现"价平量升"的隐蔽吸筹。

**方案**：

```python
def calculate_obv(bars: list[dict[str, Any]]) -> dict[str, list[float | None]]:
    """
    OBV + OBV SMA(14)。
    收盘价涨，加成交量；跌，减成交量；平，不变。
    """
    closes = [float(b.get("close", 0)) for b in bars]
    volumes = [float(b.get("volume", 0)) for b in bars]
    
    obv_values: list[float | None] = [0.0]
    for i in range(1, len(closes)):
        prev = obv_values[-1] or 0.0
        vol = volumes[i]
        if closes[i] > closes[i - 1]:
            obv_values.append(round(prev + vol, 0))
        elif closes[i] < closes[i - 1]:
            obv_values.append(round(prev - vol, 0))
        else:
            obv_values.append(prev)
    
    obv_ma = calculate_ema(obv_values, 14)
    return {"obv": [float(v) for v in obv_values], "obv_ma": obv_ma}
```

**在 `latest_indicator_state()` 中增加 OBV**：

```python
obv = calculate_obv(bars)
result["obv"] = obv
result["obv_rising"] = (
    obv["obv"][-1] is not None and obv["obv"][-2] is not None and
    obv["obv"][-1] > obv["obv"][-2]
)
```

**背离判断（OBV 与价格方向相反）**，作为辅助条件：

```python
def _is_obv_divergence_up(state: dict, bars: list[dict]) -> bool:
    """价格下跌 6 根但 OBV 上升 → 隐蔽吸筹"""
    closes = values(bars, "close")
    if len(closes) < 6:
        return False
    return (closes[-1] < closes[-6] and state.get("obv_rising"))


def _is_obv_divergence_down(state: dict, bars: list[dict]) -> bool:
    """价格上涨 6 根但 OBV 下降 → 隐蔽派发"""
    closes = values(bars, "close")
    if len(closes) < 6:
        return False
    obv = state.get("obv", {}).get("obv", [])
    if len(obv) < 2:
        return False
    return (closes[-1] > closes[-6] and obv[-1] < obv[-2])
```

**辅助条件中使用**：

```python
# detect_buy_trigger 辅助条件
if _is_obv_divergence_up(state, bars):
    matched_aux.append("OBV价平量升")

# detect_sell_trigger 辅助条件
if _is_obv_divergence_down(state, bars):
    matched_aux.append("OBV价升量缩")
```

**改动范围**：
- `indicators.py`：新增 `calculate_obv()` 函数
- `price_point_engine.py`：`latest_indicator_state()` 增加 OBV，信号匹配中增加 OBV 辅助条件

---

### P1-3：K 线形态库

**现状问题**：只检测上/下影线，错过大量形态信号。

**方案**：在 `indicators.py` 新增以下检测：

```python
def detect_doji(bars: list[dict[str, Any]]) -> bool:
    """十字星：实体占全范围比例 < 10%"""
    last = bars[-1]
    o = _num(last.get("open"))
    h = _num(last.get("high"))
    l = _num(last.get("low"))
    c = _num(last.get("close"))
    if None in (o, h, l, c) or h == l:
        return False
    body = abs(c - o)
    full_range = h - l
    return body / full_range < 0.10


def detect_hammer(bars: list[dict[str, Any]]) -> bool:
    """锤子线：小实体在上部，下影线 > 实体 2 倍，上影线极短或无"""
    last = bars[-1]
    o = _num(last.get("open"))
    h = _num(last.get("high"))
    l = _num(last.get("low"))
    c = _num(last.get("close"))
    if None in (o, h, l, c) or h == l:
        return False
    body = abs(c - o)
    lower = min(o, c) - l
    upper = h - max(o, c)
    full_range = h - l
    return (lower >= max(body * 2, full_range * 0.5) and
            upper < full_range * 0.25)


def detect_inverted_hammer(bars: list[dict[str, Any]]) -> bool:
    """倒锤线：小实体在下部，上影线 > 实体 2 倍"""
    last = bars[-1]
    o = _num(last.get("open"))
    h = _num(last.get("high"))
    l = _num(last.get("low"))
    c = _num(last.get("close"))
    if None in (o, h, l, c) or h == l:
        return False
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    full_range = h - l
    return (upper >= max(body * 2, full_range * 0.5) and
            lower < full_range * 0.25)


def detect_bullish_engulfing(prev: dict, curr: dict) -> bool:
    """看涨吞没：前阴后阳，阳线实体完全包络阴线实体"""
    prev_o = _num(prev.get("open"))
    prev_c = _num(prev.get("close"))
    curr_o = _num(curr.get("open"))
    curr_c = _num(curr.get("close"))
    if None in (prev_o, prev_c, curr_o, curr_c):
        return False
    prev_bearish = prev_c < prev_o
    curr_bullish = curr_c > curr_o
    if not (prev_bearish and curr_bullish):
        return False
    return (curr_o <= prev_c and curr_c >= prev_o)


def detect_bearish_engulfing(prev: dict, curr: dict) -> bool:
    """看跌吞没：前阳后阴，阴线实体完全包络阳线实体"""
    prev_o = _num(prev.get("open"))
    prev_c = _num(prev.get("close"))
    curr_o = _num(curr.get("open"))
    curr_c = _num(curr.get("close"))
    if None in (prev_o, prev_c, curr_o, curr_c):
        return False
    prev_bullish = prev_c > prev_o
    curr_bearish = curr_c < curr_o
    if not (prev_bullish and curr_bearish):
        return False
    return (curr_o >= prev_c and curr_c <= prev_o)
```

**在 `latest_indicator_state()` 中增加形态标记**：

```python
last_bar = bars[-1]
prev_bar = bars[-2] if len(bars) >= 2 else {}
result["doji"] = detect_doji(bars)
result["hammer"] = detect_hammer(bars)
result["inverted_hammer"] = detect_inverted_hammer(bars)
result["bullish_engulfing"] = detect_bullish_engulfing(prev_bar, last_bar)
result["bearish_engulfing"] = detect_bearish_engulfing(prev_bar, last_bar)
```

**作为辅助条件使用**：

```python
# detect_buy_trigger 辅助条件
if state.get("hammer") or state.get("bullish_engulfing"):
    matched_aux.append("锤子线/看涨吞没")
if state.get("doji"):
    matched_aux.append("十字星（变盘信号")

# detect_sell_trigger 辅助条件
if state.get("inverted_hammer") or state.get("bearish_engulfing"):
    matched_aux.append("倒锤线/看跌吞没")
```

**改动范围**：
- `indicators.py`：新增 5 个 K 线形态检测函数
- `price_point_engine.py`：`latest_indicator_state()` 增加形态标记，信号匹配中增加形态辅助条件

---

### P1-4：ADX 趋势强度

**现状问题**：在强趋势中均值回归策略失效，在震荡中趋势策略失效。ADX 用来区分市场环境，做方向过滤器。

**方案**：

```python
def calculate_adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:
    """
    ADX 指标（使用 Wilder smoothing）。
    返回 ADX 序列。
    """
    n = len(closes)
    if n < period * 2:
        return [None] * (n,)
    
    # True Range, +DM, -DM
    tr_list: list[float] = [0.0]
    plus_dm_list: list[float] = [0.0]
    minus_dm_list: list[float] = [0.0]
    for i in range(1, n):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_list.append(tr)
        plus_dm = max(h - highs[i - 1], 0)
        minus_dm = max(lows[i - 1] - l, 0)
        if plus_dm > minus_dm:
            plus_dm_list.append(plus_dm)
            minus_dm_list.append(0)
        else:
            plus_dm_list.append(0)
            minus_dm_list.append(minus_dm)
    
    # Wilder smoothing DI
    atr_val = sum(tr_list[:period]) / period
    plus_di_raw = sum(plus_dm_list[:period]) / atr_val * 100 if atr_val > 0 else 0
    minus_di_raw = sum(minus_dm_list[:period]) / atr_val * 100 if atr_val > 0 else 0
    
    adx_values: list[float | None] = [None] * (period * 2 - 1)
    dx_list = []
    for i in range(period, n - 1):
        atr_val = (atr_val * (period - 1) + tr_list[i]) / period
        plus_di = ((plus_di_raw * (period - 1) + plus_dm_list[i]) / atr_val * 100) if atr_val > 0 else 0
        minus_di = ((minus_di_raw * (period - 1) + minus_dm_list[i]) / atr_val * 100) if atr_val > 0 else 0
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
        dx_list.append(dx)
        plus_di_raw = plus_di
        minus_di_raw = minus_di
    
    if not dx_list:
        return adx_values
    
    smoothed = calculate_ema(dx_list, period)
    adx_values[period * 2 - 2 : period * 2 - 2 + len(smoothed)] = smoothed[:len(adx_values) - period * 2 + 2]
    
    return adx_values
```

**在 `latest_indicator_state()` 中使用**：

```python
adx_values = calculate_adx(highs, lows, closes, period=14)
adx_last = adx_values[-1] if adx_values and adx_values[-1] is not None else None
result["adx"] = adx_last
result["strong_trend"] = adx_last is not None and adx_last > 25
result["weak_trend"] = adx_last is not None and adx_last < 20
```

**作为方向过滤器**（在 `detect_buy_trigger` / `detect_sell_trigger` 中，强趋势时清空辅助辅助）：

```python
# detect_buy_trigger / detect_sell_trigger 判定之前
if state.get("strong_trend"):
    # 强趋势：辅助条件不计数，只做核心条件
    matched_aux = []
    status = "已触发" if core_count >= 2 else "观察中"
else:
    status = "已触发" if (
        core_count >= 2 or
        (core_count == 1 and len(matched_aux) >= 2) or
        len(matched_aux) >= 3
    ) else "观察中"
```

**改动范围**：
- `indicators.py`：新增 `calculate_adx()` 函数
- `price_point_engine.py`：`latest_indicator_state()` 增加 ADX 字段，信号匹配判定逻辑中使用 ADX 作为方向过滤器

---

## 五、改动汇总

| 改动 | 文件 | 新增函数/常量 | 修改现有函数 |
|---|---|---|---|
| **ATR 动态止损** | `config.py` | `ATR_STOP_FACTOR`, `ATR_STOP_MIN_PCT`, `ATR_STOP_MAX_PCT` | — |
| | `price_point_engine.py` | `compute_atr_dynamic_stop()` | `build_price_point_model()` |
| **RSI 背离** | `indicators.py` | `detect_bullish_divergence()`, `detect_bearish_divergence()`, `_find_local_extremes()` | — |
| | `price_point_engine.py` | — | `latest_indicator_state()`, `detect_buy_trigger()` (重构成分层架构), `detect_sell_trigger()` (重构成分层架构) |
| **布林带** | `indicators.py` | `calculate_bollinger_bands()` | — |
| | `price_point_engine.py` | — | `find_key_levels()`, `latest_indicator_state()` |
| **KDJ** | `indicators.py` | `calculate_kdj()` | — |
| | `price_point_engine.py` | — | `latest_indicator_state()` |
| **OBV** | `indicators.py` | `calculate_obv()` | — |
| | `price_point_engine.py` | — | `latest_indicator_state()`, 辅助信号匹配 |
| **K 线形态** | `indicators.py` | `detect_doji()`, `detect_hammer()`, `detect_inverted_hammer()`, `detect_bullish_engulfing()`, `detect_bearish_engulfing()` | — |
| | `price_point_engine.py` | — | `latest_indicator_state()`, 辅助信号匹配 |
| **ADX** | `indicators.py` | `calculate_adx()` | — |
| | `price_point_engine.py` | — | `latest_indicator_state()` |
| **信号分层架构** | `price_point_engine.py` | — | `detect_buy_trigger()` 重构为 core+aux 分层, `detect_sell_trigger()` 重构为核心辅助分层 |
| **T0 核心展示** | `t0_core.py` | — | `render_markdown()` 增加 signal_quality 分层展示 |

**`final_t0.py` / `t0_run.py`**：不修改，因为它们只是调用 `build_price_point_model()`。

**`monitor.py`**：不修改，信号状态变化检测消费的是 `build_price_point_model()` 的返回值结构。

---

## 六、数据流验证

### 6.1 RSI 背离 + 布林带共振的数据链

```
light_data.py:fetch_5m() → 5m bars (close)
    ↓
indicators.py:calculate_rsi(closes) → rsi_series (list[float | None])
indicators.py:calculate_bollinger_bands(closes) → {index: {upper, lower, pct_b}}
indicators.py:_find_local_extremes(closes) → 极值点索引
    ↓
indicators.py:detect_bullish_divergence(bars, rsi_series) → bool
    ↓
price_point_engine.py:latest_indicator_state() → {
    "bullish_divergence": bool,
    "pct_b": float | None,
    "last_rsi": float | None,
}
    ↓
price_point_engine.py:detect_buy_trigger() → core=["布林下轨+RSI超卖共振", "RSI底背离"], aux=[...]
    ↓
build_price_point_model() → plan["buy"]["signal_quality"] = {core: [...], aux: [...], confidence: "high"}
    ↓
t0_core.py:render_markdown() → 分层展示 core/aux 条件 + 置信度
```

### 6.2 ATR 动态止损的数据链

```
light_data.py:_compute_atr_fields() → daily bars with atr14, atr_ratio
    ↓
price_point_engine.py:build_price_point_model() → reads daily[-1]["atr14"], daily[-1]["atr_ratio"]
    ↓
compute_atr_dynamic_stop(current, atr14, atr_ratio) → stop_price
    ↓
buy_model["invalid_price"] = stop_price (覆盖原 main_support * 0.995)
    ↓
t0_core.py:render_markdown() → f"止损：ATR动态{invalid_price}元"
```

---

## 七、测试要求

所有新增函数必须有对应单测，放在 `01-功能包-packages/02-盘中T0-t0-trader/tests/test_indicators_extended.py`：

```python
# 测试清单
test_calculate_bollinger_bands_basic()      # 验证：用已知 close 序列计算布林带，上下轨 > 中轨 > 下轨
test_calculate_bollinger_bands_empty()      # 验证：空列表返回空 dict
test_calculate_bollinger_bands_short()      # 验证：少于 20 根 bar 全为 None
test_calculate_bollinger_bands_pct_b()      # 验证：pct_b 在 0-1 之间 = 价格在布林带内，< 0 = 破下轨，> 1 = 破上轨
test_detect_bullish_divergence_true()       # 验证：价格新低 RSI 不新低 → True
test_detect_bullish_divergence_false()      # 验证：价格新低 RSI 也新低 → False
test_detect_bearish_divergence_true()       # 验证：价格新高 RSI 不新高 → True
test_detect_bearish_divergence_false()      # 验证：价格新高 RSI 也新高 → False
test_detect_bullish_divergence_window()     # 验证：lookback 参数控制搜索范围
test_kdj_golden_cross()                     # 验证：K 上穿 D → golden_cross = True
test_kdj_death_cross()                      # 验证：K 下穿 D → death_cross = True
test_kdj_oversold()                         # 验证：J < 20 → oversold = True
test_kdj_overbought()                       # 验证：J > 80 → overbought = True
test_calculate_obv_up()                     # 验证：连续上涨 → OBV 递增
test_calculate_obv_down()                   # 验证：连续下跌 → OBV 递减
test_obv_divergence_up()                    # 验证：价跌量升 → _is_obv_divergence_up = True
test_obv_divergence_down()                  # 验证：价升量缩 → _is_obv_divergence_down = True
test_detect_doji()                          # 验证：十字星 → True
test_detect_hammer()                        # 验证：锤子线 → True
test_detect_inverted_hammer()               # 验证：倒锤线 → True
test_detect_bullish_engulfing()             # 验证：看涨吞没 → True
test_detect_bearish_engulfing()             # 验证：看跌吞没 → True
test_calculate_adx_basic()                  # 验证：AD 值 >= 0
test_compute_atr_dynamic_stop_basic()       # 验证：ATR14 = 0.1, factor = 2 → stop = current - 0.2
test_compute_atr_dynamic_stop_min_bound()   # 验证：ATR 太小 → 用 min_pct 兜底
test_compute_atr_dynamic_stop_max_bound()   # 验证：ATR 太大 → 用 max_pct 封顶
test_signal_quality_core_aux_layering()     # 验证：2 个核心条件 → confidence = "medium"，3 个核心 → confidence = "strong"
test_signal_quality_no_core_one_aux()       # 验证：0 核 1 辅 → confidence = "none"（不触发）
test_signal_quality_strong_trend_filter()   # 验证：强趋势 + 3 辅助 → matched_aux 清零 → confidence = "none"
test_signal_quality_weak_trend_relaxed()    # 验证：震荡市 + 1 核 2 辅 → confidence = "medium"（可触发）
```

**回归测试验证**（确保重构后现有行为不受影响）：
- 所有现有 `tests/test_t0_contract.py` 通过
- `self_check.py` 全部通过（`*_OUTPUT_VALIDATOR=OK`）

---

## 八、实施顺序建议（给执行 Agent）

1. **先改 `config.py`**：增加 ATR 止损 3 个常量 + ADX 阈值 2 个常量
2. **再改 `indicators.py`**：新增所有指标函数（布林、背离、KDJ、OBV、形态、ADX），每个函数写完后立即写单测
3. **改 `price_point_engine.py` 的 `latest_indicator_state()`**：集成所有新指标的 state 字段
4. **改 `find_key_levels()`**：增加布林级别（P0-3）
5. **改 `detect_buy_trigger()` / `detect_sell_trigger()`**：重构成了核心/辅助分层架构（这是最核心的改动，必须仔细）
6. **改 `build_price_point_model()`**：增加 ATR 动态止损覆盖、signal_quality 字段
7. **改 `t0_core.py:render_markdown()`**：分层展示 core/aux 条件 + 置信度
8. **运行单测 + self_check + pytest**
9. **如果全部通过 → 完成**
