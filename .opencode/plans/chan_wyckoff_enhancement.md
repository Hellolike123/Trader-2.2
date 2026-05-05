# 缠论 3 类买卖点 + 威科夫 Spring 信号 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Trader 2.0 项目补齐真正的缠论结构分析（分型/笔/中枢/买卖点/背驰）和威科夫 Spring 信号检测，替换当前"伪缠论"统计窗口法和"伪威科夫"单日量价观察。

**Architecture:** 在 `02-候选逻辑-candidate/` 下新建 `chan_core.py` 和 `wyckoff_core.py`，跟随现有 `strategy_protocol.py` 策略函数协定（`fn(current, bars, change_pct, quote) -> dict`），结果 merge 进现有 `levels` 字典。五层理论打分（`theory_verdicts`）中缠论分/威科夫分替换为基于现实结构的打分。选股池评分（`score_report`）同步适配。

**Tech Stack:** Pure Python 3.10+，零新增依赖，仅使用项目已有的 `light_data` 工工具函数。

---

## 背景：当前状态

| 方法 | 当前实现 | 问题 |
|------|---------|------|
| **缠论** | 5日/20日高低点统计，硬编码两行文字输出 | 伪缠论（本质是布林带变体） |
| **威科夫** | `low_close_reclaim`（收在日内低点之上2.5%）+ 早盘量占比 | Spring 误报率 >80% |

项目有缠论/威科夫标签，但**没有分型/笔/线段/中枢，没有 Spring/Upthrust/吸筹区识别**。

---

## 文件清单

### 新建文件

| 文件 | 职责 | 预估行数 |
|------|------|---------|
| `02-共享模块-shared/02-候选逻辑-candidate/chan_core.py` | 缠论核心：包含处理、分型、笔、中枢、买卖点、背驰 | ~400 |
| `02-共享模块-shared/02-候选逻辑-candidate/wyckoff_core.py` | 威科夫核心：Spring/Upthrust 检测、量价背离、吸筹/派发识别 | ~250 |
| `02-共享模块-shared/tests/test_chan_core.py` | 缠论单元测试 | ~200 |
| `02-共享模块-shared/tests/test_wyckoff_core.py` | 威科夫单元测试 | ~100 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `02-共享模块-shared/02-候选逻辑-candidate/structure_core.py` | 无需修改（通过 run_analysis.py 调用集成） |
| `01-功能包-packages/05-盘后复盘-review-trader/scripts/review_core.py` | theory_verdicts() 中缠论分/威科夫分 → 基于结构打分 |
| `01-功能包-packages/01-单票分析-trader/scripts/run_analysis.py` | build_report() 中追加缠论函数调用 + 威科夫函数调用 |
| `01-功能包-packages/03-选股池-trader-pool/scripts/final_pool.py` | score_report() 中缠论分/威科夫分适配新字段 |
| `02-共享模块-shared/trader_shared/config.py` | 新增缠论/威科夫配置常数 |
| `02-共享模块-shared/01-行情数据-market-data/models.py` | 新增 ChanlunSignal / WyckoffSignal TypedDict |

---

## Task 0: 配置常量

**Files:** Modify `02-共享模块-shared/trader_shared/config.py`

在文件末尾追加：

```python
# ---- Chan Theory (缠论) constants ----
CHANLUN_MIN_BARS: int = 20              # 最少 K 线数才计算
CHANLUN_MIN_BARS_PER_STROKE: int = 5    # 每笔最少 K 线数（含 2 个分型 + 中间最小 1 根）

# ---- Wyckoff constants ----
WYCKOFF_MIN_BARS: int = 15             # 最少 K 线数
WYCKOFF_SPRING_SUPPORT_LOOKBACK: int = 10  # Spring 支撑回看天数
WYCKOFF_SPRING_RECLAIM_RATIO: float = 0.92  # 收回阈值（跌破至 <92% 支撑 = Spring）
WYCKOFF_SPRING_BULLISH_VOL_RATIO: float = 1.3  # Spring 后 N 日量需放大 30%
WYCKOFF_DIVERGENCE_BARS: int = 5       # 量价背离回看窗口
```

---

## Task 1: chan_core.py — Step 1+2: 包含处理 + 顶底分型

**Files:** Create `02-共享模块-shared/02-候选逻辑-candidate/chan_core.py`

### 1.1 包含关系处理

连续两根 K 线如果方向相同（同向包含），需要合并。

| 场景 | 规则 |
|------|------|
| 同向上包（`high1>=high2 and low1>=low2`） | 取 `max(high)`, `max(low)` |
| 同向下包（`high1<=high2 and low1<=low2`） | 取 `min(high)`, `min(low)` |
| 反向不包含 | 不构成包含关系 |

合并后必须回退检查与前一个已合并结果是否仍构成包含。

```python
def handle_inclusion(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """处理 K 线包含关系，返回合成后的 K 线列表。"""
    if len(bars) < 2:
        return bars[:]

    bars_clean = []
    for bar in bars:
        high, low = to_float(bar.get("high")), to_float(bar.get("low"))
        if high is None or low is None:
            continue
        bars_clean.append({
            "high": high, "low": low,
            "close": to_float(bar.get("close")),
            "open": to_float(bar.get("open")),
            "volume": to_float(bar.get("volume")),
            "date": bar.get("date"),
        })

    if len(bars_clean) < 2:
        return bars_clean

    included = [bars_clean[0]]
    for i in range(1, len(bars_clean)):
        curr = bars_clean[i]
        prev = included[-1]
        # 判断是否包含
        if (curr["high"] >= prev["high"] and curr["low"] >= prev["low"]) or \
           (curr["high"] <= prev["high"] and curr["low"] <= prev["low"]):
            # 合并
            nh = max(curr["high"], prev["high"])
            nl = min(curr["low"], prev["low"])
            included[-1] = {**prev, "high": nh, "low": nl}
            # 回退检查
            while len(included) >= 2:
                p2, p1 = included[-2], included[-1]
                if (p1["high"] >= p2["high"] and p1["low"] >= p2["low"]) or \
                   (p1["high"] <= p2["high"] and p1["low"] <= p2["low"]):
                    nh = max(p1["high"], p2["high"])
                    nl = min(p1["low"], p2["low"])
                    included = included[:-2] + [{**p1, "high": nh, "low": nl}]
                else:
                    break
        else:
            included.append(curr)

    return included
```

### 1.2 顶底分型

| 分型类型 | 条件 |
|---------|------|
| 顶分型 | 中间 K 线的 `high` 最高、`low` 最高 |
| 底分型 | 中间 K 线的 `low` 最低、`high` 最低 |

```python
def find_fractions(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """找出所有顶分型和底分型。"""
    fractions = []
    for i in range(1, len(bars) - 1):
        p, c, n = bars[i-1], bars[i], bars[i+1]
        is_top = (c["high"] > p["high"] and c["high"] > n["high"] and
                  c["low"] > p["low"] and c["low"] > n["low"])
        is_bottom = (c["high"] < p["high"] and c["high"] < n["high"] and
                     c["low"] < p["low"] and c["low"] < n["low"])
        if is_top:
            fractions.append({"type": "top", "high": c["high"], "low": c["low"],
                             "index": i, "close": c["close"]})
        elif is_bottom:
            fractions.append({"type": "bottom", "high": c["high"], "low": c["low"],
                             "index": i, "close": c["close"]})
    return fractions
```

---

## Task 2: chan_core.py — Step 3: 笔

```python
def build_strokes(fractions: list[dict[str, Any]], min_bars_per_stroke: int = 5) -> list[dict[str, Any]]:
    """从分型序列构建笔。
    返回: [{"start_type": "top"/"bottom", "start_price": ...,
            "end_type": "bottom"/"top", "end_price": ..., "direction": "up"/"down"}]
    """
    if len(fractions) < 2:
        return []

    strokes = []
    current_stroke_start = fractions[0]
    current_direction = None

    for i in range(1, len(fractions)):
        frac = fractions[i]
        if frac["index"] - current_stroke_start["index"] < min_bars_per_stroke - 1:
            continue

        if current_direction is None:
            if frac["type"] == "bottom" and current_stroke_start["type"] == "top":
                strokes.append({
                    "start_type": "top", "start_price": current_stroke_start["high"],
                    "end_type": "bottom", "end_price": frac["low"], "direction": "down"
                })
                current_stroke_start, current_direction = frac, "up"
            elif frac["type"] == "top" and current_stroke_start["type"] == "bottom":
                strokes.append({
                    "start_type": "bottom", "start_price": current_stroke_start["low"],
                    "end_type": "top", "end_price": frac["high"], "direction": "up"
                })
                current_stroke_start, current_direction = frac, "down"
        else:
            if current_direction == "up" and frac["type"] == "top" and frac["high"] > current_stroke_start["low"]:
                strokes.append({
                    "start_type": "bottom", "start_price": current_stroke_start["low"],
                    "end_type": "top", "end_price": frac["high"], "direction": "up"
                })
                current_stroke_start, current_direction = frac, "down"
            elif current_direction == "down" and frac["type"] == "bottom" and frac["low"] < current_stroke_start["high"]:
                strokes.append({
                    "start_type": "top", "start_price": current_stroke_start["high"],
                    "end_type": "bottom", "end_price": frac["low"], "direction": "down"
                })
                current_stroke_start, current_direction = frac, "up"

    return strokes
```

---

## Task 3: chan_core.py — Step 4: 中枢 + 买卖点 + 背驰

### 3.1 中枢

连续 3 笔的价格重叠区域 = 中枢。中枢上沿（zg）= 三笔高点取低，中枢下沿（zd）= 三笔低点取高。zh_top > zh_bottom 则有效。

```python
def build_zones(strokes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从笔序列构建中枢。"""
    if len(strokes) < 3:
        return []

    zones = []
    for i in range(0, len(strokes) - 2, 2):
        s1, s2, s3 = strokes[i], strokes[i+1], strokes[i+2]
        all_extremes = ([s["start_price"], s["end_price"]] for s in (s1, s2, s3))
        all_extremes = [x for sublist in all_extremes for x in sublist]

        zh_top = min(max(s["start_price"], s["end_price"]) for s in (s1, s2, s3))
        zh_bottom = max(min(s["start_price"], s["end_price"]) for s in (s1, s2, s3))

        if zh_top > zh_bottom:
            zones.append({
                "zh_top": zh_top, "zh_bottom": zh_bottom,
                "zh_center": (zh_top + zh_bottom) / 2,
                "strokes": [s1, s2, s3], "valid": True
            })
        else:
            zones.append({
                "zh_top": zh_top, "zh_bottom": zh_top,  # 相等，无效
                "zh_center": zh_top, "strokes": [s1, s2, s3], "valid": False
            })

    return zones
```

### 3.2 买卖点

| 类型 | 条件 | 置信度 |
|------|------|-------|
| 一类买 | 下跌趋势 + 创新低 + MACD 底背驰 | 3 高 / 2 中 |
| 二类买 | 一买后首次回踩不破前低 | 2 中 |
| 三类买 | 突破中枢后回踩上沿不破 | 3 高 |

```python
def detect_buy_points(strokes: list[dict[str, Any]], zones: list[dict[str, Any]],
                      last_close: float, macd_hist_current: float | None,
                      macd_hist_prev: float | None) -> list[dict[str, Any]]:
    """检测买卖点。"""
    points = []

    # 一买：最后一笔是下跌笔，MACD 底背驰
    if len(strokes) >= 2:
        last, prev = strokes[-1], strokes[-2]
        if last["direction"] == "down" and prev["direction"] == "up":
            price_new_low = last["end_price"] < prev["start_price"]
            macd_div = macd_hist_current and macd_hist_prev and macd_hist_current > macd_hist_prev
            if price_new_low or macd_div:
                bp = {"type": "一类买", "price": last["end_price"],
                      "confidence": 3 if (price_new_low and macd_div) else 2}
                points.append(bp)

    # 二买：至少3笔，当前笔回踩不破前低
    if len(strokes) >= 3:
        s1, s2, s3 = strokes[-1], strokes[-2], strokes[-3]
        if s1["direction"] == "down" and s2["direction"] == "up" and s3["direction"] == "down":
            if s1["end_price"] > s3["start_price"]:
                points.append({
                    "type": "二类买", "price": s1["end_price"], "confidence": 2
                })

    # 三买：突破中枢 + 回踩上沿
    valid_zones = [z for z in zones if z.get("valid", True)]
    if valid_zones and last_close:
        latest = valid_zones[-1]
        zh_top = latest["zh_top"]
        if last_close > zh_top and last_close <= zh_top * 1.02:
            points.append({
                "type": "三类买", "price": zh_top, "confidence": 3
            })

    return points
```

### 3.3 背驰（MACD 辅助）

```python
def detect_divergence(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """检测顶/底背驰（MACD 柱辅助）。"""
    recent = bars[-10:] if len(bars) >= 10 else recent
    if len(recent) < 5:
        return {"top_divergence": False, "bottom_divergence": False, "reason": ""}

    highs = [to_float(b.get("high")) for b in recent if to_float(b.get("high"))]
    lows = [to_float(b.get("low")) for b in recent if to_float(b.get("low"))]
    macds = [to_float(b.get("macd_histogram")) for b in recent if to_float(b.get("macd_histogram"))]

    result = {"top_divergence": False, "bottom_divergence": False, "reason": ""}

    if len(highs) >= 3 and len(macds) >= 3:
        peak_h_idx = highs.index(max(highs))
        peak_m_idx = macds.index(max(macds))
        if peak_h_idx > peak_m_idx and peak_h_idx >= 2:
            result["top_divergence"] = True

    if len(lows) >= 3 and len(macds) >= 3:
        peak_h_idx = lows.index(min(lows))
        peak_m_idx = macds.index(min(macds))
        if peak_h_idx > peak_m_idx and peak_h_idx >= 2:
            result["bottom_divergence"] = True

    return result
```

### 3.4 公开 API：`chanlun_analysis()`

```python
def chanlun_analysis(bars: list[dict[str, Any]], current: float,
                     macd_hist_current: float | None = None,
                     macd_hist_prev: float | None = None) -> dict[str, Any]:
    """缠论分析主函数。返回 dict，可直接 merge 进现有 levels 字典。"""
    from config import CHANLUN_MIN_BARS, CHANLUN_MIN_BARS_PER_STROKE

    # 内置 MACD 计算（如果 bars 不含 macd_histogram）
    if not any("macd_histogram" in b for b in bars):
        bars = _calc_macd([b.copy() for b in bars])

    if len(bars) < CHANLUN_MIN_BARS:
        return {"strokes": [], "zones": [], "buy_points": [],
                "trend_label": "数据不足", "buy_point_text": "数据不足",
                "strokes_count": 0, "zones_count": 0}

    handled = handle_inclusion(bars)
    fractions = find_fractions(handled)
    strokes = build_strokes(fractions, min_bars_per_stroke=CHANLUN_MIN_BARS_PER_STROKE)
    zones = build_zones(strokes)
    buy_points = detect_buy_points(strokes, zones, current, macd_hist_current, macd_hist_prev)
    divergence = detect_divergence(bars)

    # 趋势判断
    if not strokes:
        trend_label = "数据不足"
    elif strokes[-1]["direction"] == "up":
        trend_label = "拉升段"
    else:
        trend_label = "回调段"

    # 最后有效中枢
    valid_zones = [z for z in zones if z.get("valid", True)]
    bz = valid_zones[-1] if valid_zones else None

    buy_point_text = "无买卖点"
    if buy_points:
        bp = buy_points[0]
        buy_point_text = f"有{bp['type']}信号（置信度{bp['confidence']}）"

    return {
        "strokes": [{"direction": s["direction"], "start": s["start_price"],
                     "end": s["end_price"]} for s in strokes],
        "zones": [{"zh_top": z["zh_top"], "zh_bottom": z["zh_bottom"],
                   "zh_center": z["zh_center"]} for z in valid_zones[-2:]],
        "buy_points": buy_points,
        "last_valid_zone_last_price": bz["zh_bottom"] if bz else None,
        "last_valid_zone_first_price": bz["zh_top"] if bz else None,
        "trend_label": trend_label,
        "buy_point_text": buy_point_text,
        "strokes_count": len(strokes),
        "zones_count": len(valid_zones),
        "divergence": divergence,
    }
```

---

## Task 4: wyckoff_core.py

**Files:** Create `02-共享模块-shared/02-候选逻辑-candidate/wyckoff_core.py`

### 4.1 Spring 检测

Spring = 弹簧效应 = 主力洗盘。条件：
1. 支撑位 = 近 10 天最低价
2. 当日最低价跌破支撑（<92%）
3. 收盘价收回支撑位之上（>92%）
4. 量能特征（放量恐慌 或 缩量洗盘）

### 4.2 Upthrust 检测

Upthrust = 上冲回落 = 主力派发。条件：
1. 阻力位 = 近 10 天最高价
2. 当日最高价突破阻力（>102%）
3. 收盘价回到阻力位之下

### 4.3 量价背离

| 类型 | 条件 |
|------|------|
| 顶背离（看空） | 近5日高价新高，但最大量能出现在更早位置 |
| 底背离（看多） | 近5日低价新低，但最大量能出现在更早位置 |

### 4.4 公开 API

```python
def wyckoff_analysis(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """威科夫量价信号分析。"""
    if len(bars) < 15:
        return {"spring_signal": False, "upthrust_signal": False,
                "bearish_volume_divergence": False, "bullish_volume_divergence": False,
                "wyckoff_summary": "数据不足"}

    spring = _detect_spring(bars)
    upthrust = _detect_upthrust(bars)
    bearish_div, bullish_div = _detect_volume_divergence(bars)

    signals = []
    if spring["spring_signal"]: signals.append(f"Spring：{spring['spring_reason']}")
    if upthrust["upthrust_signal"]: signals.append(f"Upthrust：{upthrust['upthrust_reason']}")
    if bearish_div: signals.append("量价背离：高价创新高但量能萎缩")
    if bullish_div: signals.append("量价背离：低价创新低但量能萎缩")

    return {
        "spring_signal": spring["spring_signal"], "spring_reason": spring["spring_reason"],
        "upthrust_signal": upthrust["upthrust_signal"], "upthrust_reason": upthrust["upthrust_reason"],
        "bearish_volume_divergence": bearish_div, "bullish_volume_divergence": bullish_div,
        "wyckoff_summary": "；".join(signals) if signals else "无明显信号",
    }
```

完整实现细节：

```python
def _detect_spring(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """检测 Spring（弹簧效应）。"""
    recent = bars[-10:]
    if len(recent) < 5:
        return {"spring_signal": False, "spring_reason": ""}

    support = min(to_float(b.get("low")) for b in recent[:-1] if to_float(b.get("low")) is not None)
    if support is None:
        return {"spring_signal": False, "spring_reason": ""}

    current = bars[-1]
    low = to_float(current.get("low"))
    close = to_float(current.get("close"))
    vol = to_float(current.get("volume")) or 0

    if low is None or close is None:
        return {"spring_signal": False, "spring_reason": ""}

    if low <= support * 0.92 and close >= support * 0.92:
        recent_vols = [to_float(b.get("volume")) or 0 for b in recent[:-1]]
        avg_vol = sum(recent_vols) / len(recent_vols) if recent_vols else 0
        vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0
        reason = f"跌破支撑{support:.2f}至{low:.2f}，收盘收回{close:.2f}"
        if vol_ratio > 1.2:
            reason += "（放量恐慌）"
        else:
            reason += "（缩量洗盘）"
        return {"spring_signal": True, "spring_price": support, "spring_reason": reason}

    return {"spring_signal": False, "spring_reason": ""}


def _detect_upthrust(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """检测 Upthrust（上冲回落）。"""
    recent = bars[-10:]
    if len(recent) < 5:
        return {"upthrust_signal": False, "upthrust_reason": ""}

    resistance = max(to_float(b.get("high")) for b in recent[:-1] if to_float(b.get("high")) is not None)
    if resistance is None:
        return {"upthrust_signal": False, "upthrust_reason": ""}

    current = bars[-1]
    high = to_float(current.get("high"))
    close = to_float(current.get("close"))

    if high is None or close is None:
        return {"upthrust_signal": False, "upthrust_reason": ""}

    if high >= resistance * 1.02 and close < resistance * 0.98:
        reason = f"冲破阻力{resistance:.2f}至{high:.2f}，收盘回到{close:.2f}之下"
        return {"upthrust_signal": True, "upthrust_price": resistance, "upthrust_reason": reason}

    return {"upthrust_signal": False, "upthrust_reason": ""}


def _detect_volume_divergence(bars: list[dict[str, Any]]) -> tuple[bool, bool]:
    """量价背离：价格创新高/低但量能不配合。"""
    recent = bars[-5:]
    if len(recent) < 3:
        return False, False

    highs = [to_float(b.get("high")) for b in recent if to_float(b.get("high"))]
    lows = [to_float(b.get("low")) for b in recent if to_float(b.get("low"))]
    vols = [to_float(b.get("volume")) or 0 for b in recent if to_float(b.get("volume")) is not None]

    bearish = False
    bullish = False

    if len(highs) >= 2 and len(vols) >= 2:
        if highs[-1] > highs[-2]:
            max_vol_index = vols.index(max(vols))
            if max_vol_index < len(vols) - 2:
                bearish = True

    if len(lows) >= 2 and len(vols) >= 2:
        if lows[-1] < lows[-2]:
            max_vol_index = vols.index(max(vols))
            if max_vol_index < len(vols) - 2:
                bullish = True

    return bearish, bullish
```

---

## Task 5: MACD 辅助（内置于 chan_core.py）

```python
def _calc_macd(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """计算 MACD 并写入 bars 中的 macd_histogram 字段。"""
    if len(bars) < 26:
        return bars

    closes = [to_float(b.get("close")) for b in bars if to_float(b.get("close")) is not None]
    fast_alpha, slow_alpha, signal_alpha = 2.0/13.0, 2.0/27.0, 2.0/10.0
    ema12, ema26 = sum(closes[:12])/12.0, sum(closes[:26])/26.0
    dea_values = []

    for i in range(12, len(bars)):
        c = closes[i]
        ema12 = ema12 * fast_alpha + c * (1.0 - fast_alpha)
        if i >= 26:
            ema26 = ema26 * slow_alpha + c * (1.0 - slow_alpha)
            macd_line = ema12 - ema26
            dea_values.append(macd_line)
            dea = sum(dea_values[:9])/9.0 if len(dea_values) == 9 else \
                  (dea * signal_alpha + macd_line * (1.0 - signal_alpha) if len(dea_values) > 9 else macd_line)
            bars[i]["macd_histogram"] = round(macd_line - dea, 4)

    return bars
```

---

## Task 6: 运行管线集成

### 6.1 `run_analysis.py:build_report()`

在 `run_analysis.py` 第 108 行 `levels = run_all(...)` 之后追加：

```python
# 缠论分析
from chan_core import chanlun_analysis
macd_h_curr = to_float(bars[-1].get("macd_histogram")) if bars else None
macd_h_prev = to_float(bars[-2].get("macd_histogram")) if len(bars) >= 2 else None
chan = chanlun_analysis(bars=bars, current=current,
                        macd_hist_current=macd_h_curr, macd_hist_prev=macd_h_prev)
levels["chan_trend_label"] = chan.get("trend_label", "数据不足")
levels["chan_buy_point_text"] = chan.get("buy_point_text", "无")
levels["chan_strokes_count"] = chan.get("strokes_count", 0)
levels["chan_zone_last_price"] = chan.get("last_valid_zone_last_price")
levels["chan_zone_first_price"] = chan.get("last_valid_zone_first_price")
levels["chan_divergence"] = chan.get("divergence", {})
# 威科夫分析
from wyckoff_core import wyckoff_analysis
wyck = wyckoff_analysis(bars)
levels["wyckoff_spring_signal"] = wyck.get("spring_signal", False)
levels["wyckoff_summary"] = wyck.get("wyckoff_summary", "无明显信号")
```

### 6.2 `run_analysis.py` imports 追加

```python
from chan_core import chanlun_analysis  # 追到 import candidate_core 之后
from wyckoff_core import wyckoff_analysis
```

---

## Task 7: `theory_verdicts()` 打分改造

**Files:** Modify `01-功能包-packages/05-盘后复盘-review-trader/scripts/review_core.py`

### 7.1 调用威科夫分析（在 theory_verdicts 开头，`build_levels` 之后）

```python
from wyckoff_core import wyckoff_analysis
wyck = wyckoff_analysis(daily)
levels["wyckoff_spring_signal"] = wyck.get("spring_signal", False)
levels["wyckoff_summary"] = wyck.get("wyckoff_summary", "无明显信号")
levels["wyckoff_bearish_div"] = wyck.get("bearish_volume_divergence", False)
levels["wyckoff_bullish_div"] = wyck.get("bullish_volume_divergence", False)
levels["wyckoff_upthrust_signal"] = wyck.get("upthrust_signal", False)
```

### 7.2 缠论打分替换（原第 438 行 `structure_score = ...`）

| 条件 | 加分值 |
|------|-------|
| `chan_trend == "拉升段"` | +15 |
| `chan_trend == "回调段"` | -10 |
| `"一类买" in chan_bps` | +25 |
| `"二类买" in chan_bps` | +15 |
| `"三类买" in chan_bps` | +10 |
| `bottom_divergence` | +15 |
| `top_divergence` | -10 |
| `strokes_count >= 3` | +5 |
| `strokes_count < 2` | -5 |
| double_low（保留，降权） | +10 |
| low_close_reclaim（保留，降权） | +10 |
| lower_high（保留，降权） | -10 |
| above_pressure（保留，降权） | +10 |
| `macd_struc_b`（保留） | 按原逻辑 |

```python
# 新打分逻辑
structure_score = 50  # 基准分

# 缠论结构加分
if levels.get("chan_trend_label") == "拉升段":
    structure_score += 15
elif levels.get("chan_trend_label") == "回调段":
    structure_score -= 10
elif levels.get("chan_trend_label") == "中枢震荡":
    structure_score += 0

# 买卖点加分
chan_bps = str(levels.get("chan_buy_point_text", ""))
if "一类买" in chan_bps: structure_score += 25
elif "二类买" in chan_bps: structure_score += 15
elif "三类买" in chan_bps: structure_score += 10

# 背驰加分
chan_div = levels.get("chan_divergence", {})
if chan_div.get("bottom_divergence"): structure_score += 15
elif chan_div.get("top_divergence"): structure_score -= 10

# 笔数量
if levels.get("chan_strokes_count",0) >= 3: structure_score += 5
elif levels.get("chan_strokes_count",0) < 2: structure_score -= 5

# 原有判断（降权保留）
structure_score += (10 if double_low else 0) + (10 if low_close_reclaim else 0)
structure_score += 5 if current > (prev_close or current) else 0
structure_score -= 10 if lower_high else 0
structure_score += 10 if above_pressure else 0
structure_score += macd_struc_b
structure_score = max(0, min(100, round(structure_score)))
```

### 7.3 缠论文本替换（原 `chanlun = "短线修复段..."`）

```python
macd_str = "MACD金叉确认转强。" if macd_gcx else levels.get("chan_trend_label", "") + "。"
chanlun_text = macd_str
if chan_div.get("bottom_divergence"): chanlun_text += " 有底背驰，止跌信号增强。"
elif chan_div.get("top_divergence"): chanlun_text += " 有顶背驰，需警惕回调。"
elif chan_bps and chan_bps != "无买卖点": chanlun_text += " " + chan_bps
else: chanlun_text += " 结构未出现明确买卖点。"
```

### 7.4 威科夫打分替换（原第 439 行 `volume_score = ...`）

| 条件 | 加分值 |
|------|-------|
| Spring 信号 | +25 |
| Upthrust 信号 | +15 |
| 量价背离（看空） | -10 |
| 量价背离（看多） | +5 |
| volume_repair（保留降权） | +15 |
| afternoon_shrink（保留降权） | -5 |

```python
volume_score = 50
if wyck.get("spring_signal"): volume_score += 25
if wyck.get("upthrust_signal"): volume_score += 15
if wyck.get("bearish_volume_divergence"): volume_score -= 10
if wyck.get("bullish_volume_divergence"): volume_score += 5
volume_score += (15 if volume_repair else 0) - (5 if afternoon_shrink else 0)
volume_score = max(0, min(100, round(volume_score)))
```

### 7.5 威科夫文本替换（原 `wyckoff = "有 Spring 类..."`）

```python
if wyck.get("spring_signal"):
    wyckoff_text = f"Spring 吸筹信号：{wyck.get('spring_reason', '')}"
elif wyck.get("upthrust_signal"):
    wyckoff_text = f"Upthrust 派发信号：{wyck.get('upthrust_reason', '')}"
elif wyck.get("bearish_volume_divergence"):
    wyckoff_text = "量价背离（顶背离）：高价创新高但量能萎缩。"
elif wyck.get("bullish_volume_divergence"):
    wyckoff_text = "量价背离（底背离）：低价创新低但量能萎缩。"
else:
    wyckoff_text = wyck.get("wyckoff_summary", "供需平衡，无明显信号。")
```

---

## Task 8: `final_pool.py:score_report()`

**Files:** Modify `01-功能包-packages/03-选股池-trader-pool/scripts/final_pool.py`

```python
def score_report(report: dict[str, Any]) -> dict[str, int]:
    ...
    chan_score = 24  # 基础分（保留原逻辑）
    # --- 原逻辑保留 ---
    if stage == "走强": chan_score += 10
    elif stage == "修复": chan_score += 7
    elif stage == "震荡": chan_score += 3
    elif stage == "转弱": chan_score -= 10
    if scene in {"等转强", "突破确认", "突破观察", "冲高减仓"}: chan_score += 7
    elif scene in {"低吸观察", "防守观察"}: chan_score += 4
    elif scene == "暂不碰": chan_score -= 10
    ...

    # --- 新增：缠论结构加分 ---
    chan_trend = str(report.get("chan_trend_label", ""))
    chan_bps = str(report.get("chan_buy_point_text", ""))
    if "一类买" in chan_bps: chan_score += 10
    elif "二类买" in chan_bps: chan_score += 6
    elif "三类买" in chan_bps: chan_score += 5

    # 结构模糊扣分
    if report.get("chan_strokes_count",0) < 2 and chan_trend == "数据不足":
        chan_score -= 5

    chan_score = max(0, min(45, chan_score))
    ...
    return {"chanlun_score": chan_score, "wyckoff_score": wyckoff_score, ...}
```

---

## Task 9: models.py TypedDict

**Files:** Modify `02-共享模块-shared/01-行情数据-market-data/models.py`

在 `TheoryScore` 之后追加：

```python
class ChanlunSignal(TypedDict, total=False):
    """缠论分析结果"""
    trend_label: str
    buy_point_text: str
    buy_points: list[dict]
    last_valid_zone_last_price: float | None
    last_valid_zone_first_price: float | None
    strokes_count: int
    divergence: dict
    zones_count: int


class WyckoffSignal(TypedDict, total=False):
    """威科夫信号"""
    spring_signal: bool
    spring_price: float | None
    spring_reason: str
    upthrust_signal: bool
    upthrust_price: float | None
    upthrust_reason: str
    bearish_volume_divergence: bool
    bullish_volume_divergence: bool
    wyckoff_summary: str
```

---

## 测试矩阵

### 缠论测试（`tests/test_chan_core.py`）

| 测试 | 验证点 |
|------|--------|
| `test_inclusion_up` | 同向上包合并 → 1 根 K 线 |
| `test_top_fraction` | 3 根 K 线 → 1 个顶分型 |
| `test_bottom_fraction` | 3 根 K 线 → 1 个底分型 |
| `test_stroke_up` | 底→顶分型序列 → 1 笔 upward |
| `test_stroke_insufficient` | 少于 min_bars_per_stroke → 无笔 |
| `test_zone_valid` | 3 笔重叠 → zh_top > zh_bottom, valid=True |
| `test_zone_invalid` | 3 笔无重叠 → valid=False |
| `test_buy_point_1` | 下跌+底背驰 → 一类买 |
| `test_buy_point_2` | 3 笔+回踩不破 → 二类买 |
| `test_buy_point_3` | 突破中枢+回踩 → 三类买 |
| `test_divergence_top` | 价新高+MACD降 → top_divergence=True |
| `test_divergence_bottom` | 价新低+MACD升 → bottom_divergence=True |
| `test_chan_api_empty` | 空列表 → 不抛异常 |
| `test_chan_insufficient` | < 20 根 → trend_label="数据不足" |

### 威科夫测试（`tests/test_wyckoff_core.py`）

| 测试 | 验证点 |
|------|--------|
| `test_spring_detected` | 跌破支撑 + 收回 → spring=True |
| `test_spring_not_detected` | 假跌破未收回 → spring=False |
| `test_upthrust_detected` | 突破阻力 + 回踩 → upthrust=True |
| `test_vol_div_bear` | 价新高+量缩量 → bearish=True |
| `test_vol_div_bull` | 价新低+量缩量 → bullish=True |
| `test_wyckoff_empty` | < 15 根 → 不抛异常 |

### 集成测试

| 测试 | 验证点 |
|------|--------|
| `test_chan_in_report` | `build_report()` 返回含 `chan_trend_label` |
| `test_wyck_in_report` | `build_report()` 返回含 `wyckoff_spring_signal` |
| `test_chan_in_pool_score` | `score_report()` 读取缠论字段 |

---

## 验收清单

- [ ] `python3 -c "from chan_core import chanlun_analysis; print('OK')"` 可导入
- [ ] `python3 -c "from wyckoff_core import wyckoff_analysis; print('OK')"` 可导入
- [ ] 单元测试 ≥ 80% 通过
- [ ] 对南网科技 688248 运行 `final_report.py` → 输出含缠论/威科夫字段（非"数据不足"）
- [ ] 对同一票运行 `final_pool.py analyze` → 缠分/威分有实质变化
- [ ] `self_check.py` 仍然通过

---

## 执行要点

1. **所有函数使用 `to_float` 而非 `float()`**，防止 None 崩溃
2. **所有函数首行检查 `len(bars)` 最小值**，数据不足时返回空结果而非抛异常
3. **零新增依赖**，仅使用项目已有的 `light_data` 工具
4. **不修改已有结构**的 return 字典，只是新增字段
5. **所有阈值可配置**（通过 `config.py`），不在代码中硬编码
6. **MACD 数据依赖**：`review_core.py:calc_macd()` 已会在 `bars` 中写入 `macd_histogram` 字段，但 `run_analysis.py` 和 `final_pool.py` 的数据源可能已经过 `light_data` 处理不含 MACD → `chan_core.py` 需要自行调用 `_calc_macd`
