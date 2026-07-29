from __future__ import annotations

import os
from typing import Any

from trader_shared.light_data import pct_change, to_float
from trader_shared.safe_cast import safe_float
from trader_shared._logging import get_logger
from trader_shared.interfaces import DataFetcher
from trader_shared.fetchers import get_fetcher


def _find_swing_lows(prices: list[float], window: int = 5) -> list[tuple[int, float]]:
    """找摆动低点：price[i] 是 [i-window, i+window] 范围内的最小值。"""
    swing_lows: list[tuple[int, float]] = []
    for i in range(window, len(prices) - window):
        price = prices[i]
        if price is None:
            continue
        left = prices[i - window:i]
        right = prices[i + 1:i + window + 1]
        if any(p is None for p in left) or any(p is None for p in right):
            continue
        if price <= min(left) and price <= min(right):
            swing_lows.append((i, price))
    return swing_lows

_logger = get_logger(__name__)

# ── [2.3] HMM 大势检测器（可选导入，阵列中无则降级）──────────────────────────────
try:
    from trader_shared.hmm_regime import detect_regime as _hmm_detect_regime, regime_to_multiplier as _hmm_multiplier
    _HMM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _HMM_AVAILABLE = False
    def _hmm_detect_regime(returns): return {"state_en": "range", "confidence": 0.5}
    def _hmm_multiplier(r): return {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 1.0}

# ── [2.3] 离线自校准参数加载器（可选，无则用默认参数）───────────────────────────────
try:
    from trader_shared.self_calibration import load_calibrated_params as _load_calibrated_params
    _CALIBRATION_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CALIBRATION_AVAILABLE = False
    def _load_calibrated_params(): return {"zone_width": 1.0, "confirm_buffer": 1.0, "stop_buffer": 1.0}

# 是否启用 HMM 前瞻大势认定（默认开启）
_HMM_REGIME_ENABLED = os.environ.get("HMM_REGIME_ENABLED", "true").lower() not in ("false", "0", "no")

try:
    from trader_shared.models import BarData, CandidateLevels, MAValues, QuoteData
except ImportError:
    BarData = dict
    CandidateLevels = dict
    MAValues = dict
    QuoteData = dict

from trader_shared.config import (
    RECENT_WINDOW,
    STRUCTURE_WINDOW,
    TAKE_PROFIT_BUFFER,
    MA_PERIODS,
    MA_WEIGHTS,
    MIN_ZONE_WIDTH_PCT,
    MAX_ZONE_WIDTH_PCT,
    MIN_STOP_BUFFER_PCT,
    MAX_STOP_BUFFER_PCT,
    MIN_CONFIRM_SPACE_PCT,
    MAX_REASONABLE_MA_DISTANCE_PCT,
)

try:
    from trader_shared.time_window_detector import check_time_windows as _check_time_windows_raw
except ImportError:
    def _check_time_windows_raw(bars, chan_result=None):
        return {"window_active": False, "window_type": "", "bars_since_pivot": 0, "tolerance": 0, "all_active": []}


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _check_time_window(bars: list[BarData], chan_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """安全包装 time_window_detector，异常时静默降级。"""
    try:
        return _check_time_windows_raw(bars, chan_result)
    except (TypeError, ValueError) as exc:
        _logger.debug("Time window check failed: %s", exc)
        return {"window_active": False, "window_type": "", "bars_since_pivot": 0, "tolerance": 0, "all_active": []}


def min_price(bars: list[BarData], field: str) -> float | None:
    values = [to_float(item.get(field)) for item in bars]
    valid = [value for value in values if value is not None]
    return min(valid) if valid else None


def max_price(bars: list[BarData], field: str) -> float | None:
    values = [to_float(item.get(field)) for item in bars]
    valid = [value for value in values if value is not None]
    return max(valid) if valid else None


def moving_average(bars: list[BarData], period: int) -> float | None:
    closes = [to_float(item.get("close")) for item in bars[-period:]]
    if len(closes) < period or None in closes:
        return None
    return sum(closes) / period


def moving_averages(bars: list[BarData]) -> dict[str, float | None]:
    return {f"ma{period}": moving_average(bars, period) for period in MA_PERIODS}


def average_amplitude_pct(bars: list[BarData]) -> float | None:
    values: list[float] = []
    for item in bars[-STRUCTURE_WINDOW:]:
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        close = to_float(item.get("close"))
        if high is None or low is None or close is None or close <= 0 or high < low:
            continue
        values.append((high - low) / close)
    return sum(values) / len(values) if values else None


def average_atr_pct(bars: list[BarData], period: int | None = None) -> float | None:
    """计算近 period 根K线的平均真实波幅百分比 (ATR/close)。

    ATR 使用 True Range = max(high-low, |high-prev_close|, |low-prev_close|)，
    比简单振幅 (high-low) 更能捕捉跳空缺口的影响。
    先算 ATR 绝对值，再除以最新 close，避免逐根归一化后再平均导致的偏差。
    """
    period = period or STRUCTURE_WINDOW
    tr_values: list[float] = []
    last_close: float | None = None
    # P1 Fix: 当 len(bars) > period 时，首根 K 线的 prev_close 应取 bars[-period-1].close
    # 原代码始终用 None 初始化为 prev_close，首根 K 线跳空缺口被漏算导致 ATR 低估。
    preview = bars[-(period + 1):] if len(bars) > period else bars[-period:]
    prev_close: float | None = None
    if len(bars) > period and len(preview) > period:
        first_prev = to_float(bars[-period - 1].get("close"))
        if first_prev is not None and first_prev > 0:
            prev_close = first_prev
    for item in preview:
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        close = to_float(item.get("close"))
        if high is None or low is None or close is None or close <= 0 or high < low:
            continue
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_values.append(tr)
        prev_close = close
        last_close = close
    if not tr_values or last_close is None or last_close <= 0:
        return None
    atr = sum(tr_values) / len(tr_values)
    return atr / last_close


def add_level(levels: list[dict[str, Any]], name: str, value: float | None, weight: float) -> None:
    if value is None or value <= 0:
        return
    levels.append({"name": name, "price": round(value, 2), "weight": weight})


def add_ma_levels(levels: list[dict[str, Any]], current: float, ma_values: dict[str, float | None], *, below: bool) -> None:
    for name, value in ma_values.items():
        if value is None or value <= 0:
            continue
        if abs(value - current) / max(current, 1) > MAX_REASONABLE_MA_DISTANCE_PCT:
            continue
        weight = MA_WEIGHTS.get(name, 0.5)
        if below and value <= current:
            add_level(levels, name.upper(), value, weight)
        elif not below and value >= current:
            add_level(levels, name.upper(), value, weight)


def choose_level(levels: list[dict[str, Any]], current: float, *, below: bool) -> dict[str, Any]:
    if not levels:
        raise RuntimeError("candidate price levels unavailable")
    directional = [item for item in levels if (item["price"] <= current if below else item["price"] >= current)]
    candidates = directional or sorted(levels, key=lambda item: abs(float(item["price"]) - current))[:3]

    def sort_key(item: dict[str, Any]) -> tuple[float, float]:
        distance = abs(float(item["price"]) - current) / max(current, 1)
        weight = safe_float(item, "weight")
        return (distance / max(weight, 0.1), distance)

    return sorted(candidates, key=sort_key)[0]


def _open_price(quote: dict[str, Any] | None) -> float | None:
    if quote is None:
        return None
    for key in ("open", "open_price", "today_open"):
        v = quote.get(key)
        if v is not None:
            return to_float(v)
    return None


def _gap_status(
    low_zone_lower: float,
    low_zone_upper: float,
    hard_stop: float,
    open_price: float | None,
    prev_close: float | None,
) -> dict[str, Any]:
    if open_price is None or prev_close is None or prev_close <= 0:
        return {"condition": "unknown", "text": "无开盘数据"}
    gap_up = open_price > prev_close * 1.003
    gap_down = open_price < prev_close * 0.997

    if gap_down and open_price < hard_stop:
        return {"condition": "gap_down_stop", "text": "跳空低开，跌破止损"}
    if gap_up and open_price > low_zone_upper:
        return {"condition": "gap_up", "text": "跳空高开，低吸区今日无效"}
    if gap_down and open_price < low_zone_lower:
        return {"condition": "gap_down", "text": "跳空低开，低开低于低吸区，关注止损"}
    if gap_up:
        return {"condition": "gap_up_low", "text": "跳空高开，但未超过低吸区上沿"}
    return {"condition": "normal", "text": "正常开盘"}


def zone_position(current: float, support: float, confirm: float) -> float:
    if confirm <= support:
        return 0.5  # 无有效区间，返回中间值
    return max(0.0, min(1.0, (current - support) / (confirm - support)))



def _theory_multipliers(fusion_result: dict[str, Any] | None, index_returns: list[float] | None = None) -> dict[str, float]:
    """根据融合层理论信号及大盘环境计算参数微调系数。

    [2.3升级] 三层叠加架构：
      层-0：离线历史胜率寻优的自校准参数作为基准倍率
      层-1：均线大势 Regime（正常/偏弱/很差）调节
      层-2：[2.3新增] HMM 前瞻 Regime（bull/bear/range）进一步徣化调节（叠加50%）
      层-3：理论信号（缺论/威科夫/动能）微调
    若 fusion_result 为 None 且无 HMM 数据，层-0 校准值直接返回。
    映射规则（详见 docs/buy-zone-accessibility-fix-plan.md P3）：
      缺论上攻笔/三买 → zone_width 放大 +15%
      缺论下跌笔未结束 → zone_width 缩小 -10%
      威科夫吸筹/Spring → confirm_buffer 收窄 -30%
      动量强势（bullish + score≥65）→ space_threshold 收窄 -20%
      动量弱势（bearish + score≤35）→ space_threshold 加宽 +30%
    """
    # 层-0：离线历史寻优的自校准基准值
    _cal = _load_calibrated_params() if _CALIBRATION_AVAILABLE else {}
    
    # 动态根据当前 HMM 大势或均线大势级别决定参数子集
    regime = "正常"
    if fusion_result is not None:
        regime = fusion_result.get("regime", "正常")

    hmm_state = None
    if fusion_result is not None and isinstance(fusion_result, dict):
        hmm_state = fusion_result.get("hmm_regime")

    # 标准化状态 Key
    state_key = hmm_state if hmm_state in ("bull", "bear", "range") else None
    if not state_key:
        if regime in ("偏弱", "很差"):
            state_key = "bear"
        else:
            state_key = "range"

    # 读取嵌套参数（Bull/Bear/Range/Global）并完美向下兼容老版本平面字典
    if state_key in _cal and isinstance(_cal[state_key], dict):
        cal_subset = _cal[state_key]
    elif "global" in _cal and isinstance(_cal["global"], dict):
        cal_subset = _cal["global"]
    else:
        cal_subset = _cal

    multipliers = {
        "zone_width":      cal_subset.get("zone_width", 1.0),
        "confirm_buffer":  cal_subset.get("confirm_buffer", 1.0),
        "space_threshold": 1.0,
        "stop_buffer":     cal_subset.get("stop_buffer", 1.0),
    }

    # 层-1：均线大势 Regime
    if regime in ("偏弱", "很差"):
        multipliers["stop_buffer"] = multipliers["stop_buffer"] * 0.8
        multipliers["confirm_buffer"] = multipliers["confirm_buffer"] * 1.3
        # [P1 Fix] 大盘偏弱/很差时，买入区间应收窄而非维持不变
        multipliers["zone_width"] = multipliers["zone_width"] * 0.85
    elif regime == "正常":
        multipliers["zone_width"] = multipliers["zone_width"] * 1.2
        multipliers["confirm_buffer"] = multipliers["confirm_buffer"] * 0.8

    # 层-2：[2.3新增] HMM 前瞻 Regime 进一步徣化（50% 叠加）
    # fit() 需 ≥30 根才做 Baum-Welch；短序列先验 Viterbi 不可靠，与 market_env 对齐
    if _HMM_AVAILABLE and _HMM_REGIME_ENABLED and (hmm_state or (index_returns and len(index_returns) >= 30)):
        try:
            if hmm_state:
                hmm_result = {"state_en": hmm_state, "confidence": 0.8}
            else:
                hmm_result = _hmm_detect_regime(index_returns)
            hmm_mult = _hmm_multiplier(hmm_result)
            for k in ("zone_width", "confirm_buffer", "stop_buffer"):
                base = multipliers.get(k, 1.0)
                hmm_adj = hmm_mult.get(k, 1.0)
                # 真混合：base 和 HMM 推荐值各占 50%，确保 HMM 有足够纠偏力
                multipliers[k] = round(base * 0.5 + hmm_adj * 0.5, 4)
        except (TypeError, ValueError) as exc:  # 任何 HMM 异常静默降级
            _logger.debug("HMM regime detection failed: %s", exc)

    if fusion_result is None:
        return multipliers

    # 从 fusion_result 中读取理论信号详情
    signals_detail = fusion_result.get("signals_detail", {})
    if not isinstance(signals_detail, dict):
        return multipliers

    # --- 缠论信号 ---
    chan = signals_detail.get("chan", {})
    if isinstance(chan, dict):
        reason = str(chan.get("reason", ""))
        direction = max(-1, min(1, int(chan.get("direction", 0) or 0)))  # 范围截断
        confidence = safe_float(chan, "confidence")
        # 上攻笔/三买/底背驰 → 低吸区更宽
        if direction == 1 and confidence >= 0.4:
            if any(kw in reason for kw in ("三类买", "二类买", "一类买", "拉升段", "底背驰")):
                multipliers["zone_width"] = multipliers["zone_width"] * 1.15
        # 下跌笔/回调段 → 低吸区收窄
        elif direction == -1 and confidence >= 0.4:
            if any(kw in reason for kw in ("回调段", "顶背驰")):
                multipliers["zone_width"] = multipliers["zone_width"] * 0.90

    # --- 威科夫信号 ---
    wyk = signals_detail.get("wyckoff", {})
    if isinstance(wyk, dict):
        reason = str(wyk.get("reason", ""))
        direction = wyk.get("direction", 0)
        confidence = safe_float(wyk, "confidence")
        # Spring / 看多背离 → 突破更可信，确认缓冲收窄
        if direction == 1 and confidence >= 0.5:
            if "弹簧" in reason or "看多" in reason:
                multipliers["confirm_buffer"] = multipliers["confirm_buffer"] * 0.70  # 0.005 * 0.70 = 0.0035
        # 上冲回落/看空 → 不收窄
        elif direction == -1 and confidence >= 0.5:
            multipliers["confirm_buffer"] = multipliers["confirm_buffer"] * 1.0

    # --- 动量信号 ---
    mom = signals_detail.get("momentum", {})
    if isinstance(mom, dict):
        direction = mom.get("direction", 0)
        confidence = safe_float(mom, "confidence")
        # 动量强势 → space阈值收窄（更激进，空间小也给进）
        if direction == 1 and confidence >= 0.5:
            multipliers["space_threshold"] = multipliers["space_threshold"] * 0.80
        # 动量弱势 → space阈值加宽（更保守）
        elif direction == -1 and confidence >= 0.5:
            multipliers["space_threshold"] = multipliers["space_threshold"] * 1.30

    return multipliers


def _calc_trendline_support(bars: list[BarData]) -> float | None:
    """从摆动低点计算上升趋势线在当前日的投影支撑价。

    算法：
    1. 在最近 60 根 K 线中找摆动低点（窗口 5：最低价且左右各 2 根更高）
    2. 取最近至少 2 个上升的摆动低点
    3. 计算趋势线斜率，投影到今日
    4. 验证至少被触碰过 3 次（最低价 <= 趋势线价 * 1.02）
    """
    try:
        window = 5
        lookback = min(60, len(bars))
        recent = bars[-lookback:]

        # 找摆动低点（使用公共函数）
        recent_lows = [to_float(b.get("low")) for b in recent]
        swing_lows = _find_swing_lows(recent_lows, window)

        if len(swing_lows) < 2:
            return None

        # 取最近 2 个，必须上升
        p1_idx, p1 = swing_lows[-2]
        p2_idx, p2 = swing_lows[-1]
        if p2 <= p1:
            return None

        # 趋势线投影到今日
        slope = (p2 - p1) / max(p2_idx - p1_idx, 1)
        current_idx = len(recent) - 1
        trend_price = p2 + slope * (current_idx - p2_idx)
        if trend_price <= 0:
            return None

        # 验证至少被触碰 3 次（用各 index 处的趋势线投影价判断）
        touch_count = 0
        for j in range(p1_idx, current_idx + 1):
            bar_low = to_float(recent[j].get("low"))
            if bar_low is not None:
                trend_at_j = p2 + slope * (j - p2_idx)
                if bar_low <= trend_at_j * 1.02:
                    touch_count += 1

        return round(trend_price, 2) if touch_count >= 3 else None
    except (TypeError, ValueError, IndexError):
        return None


def _calc_rsi_divergence(closes: list[float], bars: list[BarData]) -> float | None:
    """检测 RSI 底背离：价格创更低低点但 RSI 未创新低 -> 支撑信号。"""
    try:
        from trader_shared.momentum_core import calc_rsi
        rsi = calc_rsi(closes, 14)
        if len(rsi) < 30:
            return None

        # 最近 30 根 K 线的摆动低点
        lookback = 30
        recent_bars = bars[-lookback:]
        recent_rsi = rsi[-lookback:]
        recent_lows = [to_float(b.get("low")) for b in recent_bars]
        if any(l is None for l in recent_lows):
            return None

        window = 5
        swing_lows = _find_swing_lows(recent_lows, window)

        if len(swing_lows) < 2:
            return None

        p1_idx, p1_price = swing_lows[-2]
        p2_idx, p2_price = swing_lows[-1]

        # 必须价格创新低
        if p2_price >= p1_price:
            return None

        rsi1 = recent_rsi[p1_idx]
        rsi2 = recent_rsi[p2_idx]
        if rsi1 is not None and rsi2 is not None and rsi2 > rsi1:
            return round(p2_price, 2)

        return None
    except (TypeError, ValueError, IndexError):
        return None


def _calc_macd_divergence(closes: list[float], bars: list[BarData]) -> float | None:
    """检测 MACD 底背离：价格创更低低点但 MACD (EMA12-EMA26) 未创新低 -> 支撑信号。"""
    try:
        if len(closes) < 26:
            return None

        from trader_shared.indicator_math import calc_macd_series
        macd_result = calc_macd_series(closes)
        macd_series = macd_result["histogram"]

        # 最近 30 根 K 线的摆动低点
        lookback = 30
        recent_bars = bars[-lookback:]
        recent_macd = macd_series[-lookback:]
        recent_lows = [to_float(b.get("low")) for b in recent_bars]
        if any(l is None for l in recent_lows):
            return None

        window = 5
        swing_lows = _find_swing_lows(recent_lows, window)

        if len(swing_lows) < 2:
            return None

        p1_idx, p1_price = swing_lows[-2]
        p2_idx, p2_price = swing_lows[-1]

        if p2_price >= p1_price:
            return None

        m1 = recent_macd[p1_idx]
        m2 = recent_macd[p2_idx]
        if m1 is not None and m2 is not None and m2 > m1:
            return round(p2_price, 2)

        return None
    except (TypeError, ValueError, IndexError):
        return None


def build_structure_context(current: float, bars: list[BarData], change_pct: Any = None, quote: QuoteData | None = None, fusion_result: dict[str, Any] | None = None, chan_result: dict[str, Any] | None = None, fetcher: DataFetcher | None = None, pnl_pct: float | None = None, vp_result: dict[str, Any] | None = None, major_stage: str | None = None) -> dict[str, Any]:
    if fetcher is None:
        fetcher = get_fetcher()
    recent5 = bars[-RECENT_WINDOW:] if len(bars) >= RECENT_WINDOW else bars
    recent20 = bars[-STRUCTURE_WINDOW:] if len(bars) >= STRUCTURE_WINDOW else bars
    if not recent5:
        raise RuntimeError("daily support/resistance unavailable")

    quote = quote or {}
    open_price = _open_price(quote)
    prev_close = to_float(quote.get("pre_close"))
    ma_values = moving_averages(bars)
    support_levels: list[dict[str, Any]] = []
    resistance_levels: list[dict[str, Any]] = []

    add_level(support_levels, "5日低点", min_price(recent5, "low"), 1.0)
    add_level(resistance_levels, "5日高点", max_price(recent5, "high"), 1.0)
    add_level(support_levels, "今日低点", to_float(quote.get("low")), 0.95)
    add_level(support_levels, "20日低点", min_price(recent20, "low"), 0.85)
    add_level(resistance_levels, "20日高点", max_price(recent20, "high"), 0.85)
    add_ma_levels(support_levels, current, ma_values, below=True)
    add_ma_levels(resistance_levels, current, ma_values, below=False)

    from trader_shared.momentum_core import calc_expma
    _closes = [to_float(b.get("close")) for b in bars if b.get("close") is not None]
    if _closes:
        expma10_list = calc_expma(_closes, 10)
        expma20_list = calc_expma(_closes, 20)
        expma10 = expma10_list[-1] if expma10_list else None
        expma20 = expma20_list[-1] if expma20_list else None
        
        if expma10 is not None:
            ma_values["expma10"] = expma10
            if current > expma10:
                add_level(support_levels, "EXPMA10", expma10, 0.9)
            else:
                add_level(resistance_levels, "EXPMA10", expma10, 0.9)
        
        if expma20 is not None:
            ma_values["expma20"] = expma20
            if current > expma20:
                add_level(support_levels, "EXPMA20", expma20, 0.9)
            else:
                add_level(resistance_levels, "EXPMA20", expma20, 0.9)

    # ═══════ 布林下轨支撑 ═══════
    if len(_closes) >= 20:
        from trader_shared.momentum_core import calc_bollinger
        bb = calc_bollinger(_closes, 20, 2.0)
        bb_lower = bb.get("lower")
        bb_middle = bb.get("middle")
        if bb_lower is not None and bb_middle is not None:
            if current > bb_lower:
                add_level(support_levels, "布林下轨", bb_lower, 0.80)
            else:
                add_level(resistance_levels, "布林下轨", bb_lower, 0.80)

    # ═══════ 趋势线支撑 ═══════
    if len(bars) >= 30:
        _trendline_price = _calc_trendline_support(bars)
        if _trendline_price is not None and _trendline_price < current:
            add_level(support_levels, "趋势线", _trendline_price, 0.85)

    # ═══════ RSI 底背离支撑 ═══════
    # P2 Fix: bars 与 _closes 可能不同长度（closed bars 有 None close），需要对齐后传入
    _bars = [b for b in bars if b.get("close") is not None]
    if len(_closes) >= 30:
        _rsi_div_price = _calc_rsi_divergence(_closes, _bars)
        if _rsi_div_price is not None and _rsi_div_price < current:
            add_level(support_levels, "RSI底背离", _rsi_div_price, 0.75)

    # ═══════ MACD 底背离支撑 ═══════
    if len(_closes) >= 30:
        _macd_div_price = _calc_macd_divergence(_closes, _bars)
        if _macd_div_price is not None and _macd_div_price < current:
            add_level(support_levels, "MACD底背离", _macd_div_price, 0.75)

    support = choose_level(support_levels, current, below=True) if support_levels else {"name": "现价兜底", "price": round(current, 2), "weight": 0.1}
    resistance = choose_level(resistance_levels, current, below=False) if resistance_levels else {"name": "现价兜底", "price": round(current, 2), "weight": 0.1}
    support_price = float(support["price"])

    # confirm_price: 需要放量站稳的启动确认价（阻力位 + 缓冲）
    # P3: 缓冲受威科夫吸筹信号影响，Spring/看多背离时收窄
    theory = _theory_multipliers(fusion_result)
    # P3 安全模式：THEORY_ADJUST_LOG_ONLY=true 时只记录不生效
    try:
        from trader_shared.config import THEORY_ADJUST_LOG_ONLY
    except (ImportError, AttributeError):
        THEORY_ADJUST_LOG_ONLY = False
    if THEORY_ADJUST_LOG_ONLY and any(v != 1.0 for v in theory.values()):
        print(f"THEORY-ADJUST-LOG: multipliers={theory} (suppressed by THEORY_ADJUST_LOG_ONLY)")
        theory = {"zone_width": 1.0, "confirm_buffer": 1.0, "space_threshold": 1.0, "stop_buffer": 1.0}
    # Clamp confirm_buffer to prevent extreme values from accumulated multiplications
    theory["confirm_buffer"] = max(0.5, min(2.0, theory["confirm_buffer"]))
    effective_confirm_space = MIN_CONFIRM_SPACE_PCT * theory["confirm_buffer"]
    confirm_price = round(float(resistance["price"]) * (1 + effective_confirm_space), 2)
    # resistance: 实际阻力位，用于减仓参考
    resistance_price = float(resistance["price"])

    # 使用 ATR 替代振幅，ATR 能捕捉跳空缺口，对"买入位到不了"的跳空场景更敏感
    # P3: zone_width 受缠论信号影响，上攻笔/三买时放大，下跌笔时收窄
    atr_pct = average_atr_pct(recent20) or 0.02
    zone_width_pct = clamp(atr_pct * 0.25 * theory["zone_width"], MIN_ZONE_WIDTH_PCT, MAX_ZONE_WIDTH_PCT)
    stop_buffer_pct = clamp(atr_pct * 0.40 * theory.get("stop_buffer", 1.0), MIN_STOP_BUFFER_PCT, MAX_STOP_BUFFER_PCT)
    low_zone_lower = round(support_price, 2)
    low_zone_upper = round(support_price * (1 + zone_width_pct), 2)
    # ATR 动态 clamp：支撑离现价超过 1.5×ATR 时，切换到最近的真实支撑
    atr_abs = atr_pct * current if current > 0 else 0
    atr_floor = current - 1.5 * atr_abs if atr_abs > 0 else current * 0.85
    if support_price < atr_floor:
        # 支撑太远：从已有候选里找最近的 ≥ atr_floor 的真实支撑
        _nearby = [
            lv for lv in support_levels
            if float(lv.get("price", 0)) >= atr_floor and float(lv.get("price", 0)) <= current
        ]
        if _nearby:
            _best = sorted(_nearby, key=lambda x: float(x["price"]))[-1]
            support_price = float(_best["price"])
            low_zone_lower = round(support_price, 2)
            low_zone_upper = round(support_price * (1 + zone_width_pct), 2)
        else:
            # 兜底：以 ATR 等距为买点区下沿
            support_price = round(atr_floor, 2)
            low_zone_lower = support_price
            low_zone_upper = round(support_price * (1 + zone_width_pct), 2)

    # ═══════ 止损：MA20 + 前低融合 ═══════
    ma20_val = ma_values.get('ma20')
    recent_lows = [float(b.get('low') or 0) for b in bars[-20:] if b.get('low')]
    prev_low = min(recent_lows) if recent_lows else 0
    candidates = [v for v in [ma20_val, prev_low] if v and v > 0]
    if candidates:
        support_ref = max(candidates)  # 取更接近现价的（较大的）
        stop = round(support_ref * (1 - stop_buffer_pct), 2)
    else:
        stop = round(current * 0.95, 2)

    # ═══════ 止盈：按阶段动态 ═══════
    if major_stage in ('蓄势', '蓄势偏强'):
        take = round(resistance_price, 2) if resistance_price else round(current * 1.05, 2)
    elif major_stage == '主升':
        # 主升期有趋势加持，多看 5%
        take = round(resistance_price * 1.05, 2) if resistance_price else round(current * 1.10, 2)
    elif major_stage == '派发':
        # 派发期还有一段震荡出货，折价卖而非现价卖
        take = round(resistance_price * 0.98, 2) if resistance_price else round(current, 2)
    elif major_stage == '蓄势偏弱':
        take = round(resistance_price * 0.98, 2) if resistance_price else round(current, 2)
    elif major_stage == '衰退':
        take = None  # 衰退期不设止盈，只靠止损退出
    else:
        take = round(resistance_price, 2) if resistance_price else round(current * 1.05, 2)
    # 安全网: 止盈不能低于现价（衰退期除外）
    if take is not None:
        take = max(take, current)
    position = zone_position(current, support_price, confirm_price)
    pressure_space_pct = (confirm_price - current) / current if current > 0 else 0
    below_ma = count_below_ma(current, ma_values)

    # ═══════ Fibonacci Retracement & Golden Levels (Direction 2) ═══════
    swing_high = None
    swing_low = None
    retrace_382 = None
    retrace_500 = None
    retrace_618 = None
    golden_bid = None

    if isinstance(chan_result, dict):
        # 兼容 chanlun_strategy 包装层 {"chanlun": {...}} 与扁平分析 dict
        try:
            from trader_shared.chan_core import unwrap_chan
            _chan = unwrap_chan(chan_result)
        except ImportError:  # pragma: no cover
            _chan = chan_result.get("chanlun") if isinstance(chan_result.get("chanlun"), dict) else chan_result
        strokes = _chan.get("strokes", []) if isinstance(_chan, dict) else []
        if isinstance(strokes, list) and len(strokes) >= 1:
            last_stroke = strokes[-1]
            direction = last_stroke.get("direction")
            if direction == "up":
                try:
                    swing_low = float(last_stroke.get("start_price") or 0.0)
                    swing_high = float(last_stroke.get("end_price") or 0.0)
                except (ValueError, TypeError):
                    pass
            elif direction == "down" and len(strokes) >= 2:
                prev_stroke = strokes[-2]
                try:
                    swing_low = float(prev_stroke.get("start_price") or 0.0)
                    swing_high = float(prev_stroke.get("end_price") or 0.0)
                except (ValueError, TypeError):
                    pass

            # 安全检查：确保 swing_high > swing_low
            if swing_high is not None and swing_low is not None and swing_high < swing_low:
                swing_high, swing_low = swing_low, swing_high

            if swing_low is not None and swing_high is not None and swing_high > swing_low and swing_low > 0:
                diff = swing_high - swing_low
                retrace_382 = swing_high - diff * 0.382
                retrace_500 = swing_high - diff * 0.500
                retrace_618 = swing_high - diff * 0.618

                # Select strongest retracement level that falls inside low-buy zone
                # Priority: 61.8% > 50.0% > 38.2%
                for level in (retrace_618, retrace_500, retrace_382):
                    if low_zone_lower <= level <= low_zone_upper:
                        golden_bid = round(level, 2)
                        break

    fib_retrace = {
        "swing_high": round(swing_high, 2) if swing_high is not None else None,
        "swing_low": round(swing_low, 2) if swing_low is not None else None,
        "retrace_382": round(retrace_382, 2) if retrace_382 is not None else None,
        "retrace_500": round(retrace_500, 2) if retrace_500 is not None else None,
        "retrace_618": round(retrace_618, 2) if retrace_618 is not None else None,
        "golden_bid": golden_bid
    }

    # ═══════ 高抛区间 & Fibonacci 扩展目标位（对称低吸区间）═══════
    high_zone_upper = round(resistance_price, 2)
    high_zone_lower = max(
        round(resistance_price * (1 - zone_width_pct), 2),
        round(current * 1.005, 2),  # 不低于现价的 0.5% 上方
    )
    # 约束：高抛区间下限不超过现价上方 8%（避免融合说"现在减"但买卖点说"等涨 9%"的矛盾）
    high_zone_lower = min(high_zone_lower, round(current * 1.08, 2))

    # Fibonacci 扩展目标位（从缠论笔计算 138.2% / 161.8%）
    fib_ext_1382 = None
    fib_ext_1618 = None
    if swing_low is not None and swing_high is not None and swing_high > swing_low and swing_low > 0:
        diff = swing_high - swing_low
        fib_ext_1382 = round(swing_low + diff * 1.382, 2)
        fib_ext_1618 = round(swing_low + diff * 1.618, 2)

    # ── P0: ATR 移动止损 ──
    from trader_shared.config import ENABLE_TRAILING_STOP, TRAILING_STOP_ATR_MULTIPLE
        
    if pnl_pct is not None:
        if pnl_pct >= 0.40:
            TRAILING_STOP_ATR_MULTIPLE = 1.2
        elif pnl_pct >= 0.30:
            TRAILING_STOP_ATR_MULTIPLE = 1.5
        elif pnl_pct >= 0.20:
            TRAILING_STOP_ATR_MULTIPLE = 2.0

    trailing_stop = None
    highest_close = None
    if ENABLE_TRAILING_STOP and atr_pct and atr_pct > 0:
        # 近 STRUCTURE_WINDOW 窗内最高收（勿用全历史高点，否则回撤票止损远高于现价误触发）
        recent_bars = bars[-STRUCTURE_WINDOW:] if bars else []
        closes = [v for b in recent_bars if (v := to_float(b.get("close"))) is not None]
        if closes:
            highest_close = max(closes)
            trailing_stop = round(highest_close * (1 - atr_pct * TRAILING_STOP_ATR_MULTIPLE), 2)
            # 移动止损不应低于原始 hard_stop（不扩大亏损）
            if trailing_stop is not None:
                trailing_stop = max(trailing_stop, stop)

    # keep compatibility for callers that expect status from structure payload
    from trader_shared.decision_core import status_layers  # local import to avoid tighter module coupling

    # 基于ATR的动态"空间不足"阈值：高波幅票给更多容忍，低波幅票收紧
    # P3: 受动量信号影响，强势时收窄（更激进），弱势时加宽（更保守）
    dynamic_space_threshold = max(0.002, atr_pct * 0.35 * theory["space_threshold"])
    layer_result = status_layers(
        current=current,
        support=support_price,
        low_zone_upper=low_zone_upper,
        confirm=confirm_price,
        hard_stop=stop,
        position_ratio=position,
        change_pct=change_pct,
        ma_values=ma_values,
        pressure_space_pct=pressure_space_pct,
        bars=bars,
        space_threshold=dynamic_space_threshold,
        fusion_result=fusion_result,  # S-2 fix: 传入融合层结果
        chan_result=chan_result,
        vp_result=vp_result,  # VP 日内量价分布
    )
    status = str(layer_result["theory_status"])
    fusion_override_used = layer_result.get("fusion_override_used", False)

    return {
        "main_support": round(support_price, 2),
        "main_resistance": round(resistance_price, 2),
        "support": round(support_price, 2),
        "support_source": support["name"],
        "resistance": round(resistance_price, 2),
        "resistance_source": resistance["name"],
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "resistance_list": sorted(resistance_levels, key=lambda x: abs(x['price'] - current))[:3],
        "ma_values": ma_values,
        "below_ma_count": below_ma,
        "atr_pct": round(atr_pct, 4),
        "zone_width_pct": round(zone_width_pct, 4),
        "stop_buffer_pct": round(stop_buffer_pct, 4),
        "low_zone_lower": low_zone_lower,
        "low_zone_upper": low_zone_upper,
        "low_zone": f"{low_zone_lower:.2f}-{low_zone_upper:.2f}元",
        "open_price": open_price,
        "gap": _gap_status(low_zone_lower, low_zone_upper, stop, open_price, prev_close),
        "confirm_price": round(confirm_price, 2),
        # 当前价接近阻力时，确认位改为"突破确认位"并标注条件（方案B）
        "confirm_label": "突破确认位" if current >= resistance_price * 0.97 else "确认位",
        "confirm_note": "需放量站稳阻力上方" if current >= resistance_price * 0.97 else "",
        "sell_observe_price": round(resistance_price, 2),
        "hard_stop": stop,
        "take": take,
        # fix: guard against inf from pct_change when current=0
        "upside_pct": round(pct_change(current, confirm_price), 2) if current > 0 else 0.0,
        "downside_pct": round(abs(pct_change(current, stop)), 2) if current > 0 else 0.0,
        "position_ratio": round(position, 3),
        "pressure_space_pct": round(pressure_space_pct, 4),
        "status": status,
        "fusion_override_used": fusion_override_used,
        "ma250_warning": layer_result.get("ma250_warning", False),
        "theory_multipliers": theory,  # P3: 记录理论信号对参数的微调系数，便于调试
        "time_window": _check_time_window(bars, chan_result),  # P4: 江恩时间窗口
        "fib_retrace": fib_retrace,  # [2.3新增] 斐波那契黄金回调及挂单参考
        "high_zone_upper": high_zone_upper,  # 高抛区间上沿
        "high_zone_lower": high_zone_lower,  # 高抛区间下沿
        "high_zone": f"{high_zone_lower:.2f}-{high_zone_upper:.2f}元",
        "fib_ext_1382": fib_ext_1382,  # Fibonacci 138.2% 扩展目标位
        "fib_ext_1618": fib_ext_1618,  # Fibonacci 161.8% 扩展目标位
        "trailing_stop": trailing_stop,  # P0: ATR 移动止损价
        "highest_close": highest_close,  # P0: 分析区间最高收盘价
        # 单一可信源：所有视图（单票/T0/Review/Pool）共用此价位字典
        "price_levels": {
            "stop": stop,
            "defense": round(support_price, 2),
            "confirm": round(confirm_price, 2),
            "buy_low": low_zone_lower,
            "buy_high": low_zone_upper,
            "high_low": high_zone_lower,
            "high_high": high_zone_upper,
            "take": take,
            "trailing_stop": trailing_stop,
        },
    }


def find_key_levels(bars: list[BarData]) -> dict[str, float]:
    """在 300 根数据里找三个周期的关键支撑/压力位。

    短线（10日）：最近 10 日的高低点
    中线（60日）：最近 60 日内至少 2 次触及未破的重要价位
    长线（120日）：最近 120 日内至少 2 次触及未破的重要价位

    返回 dict：
        short_support, mid_support, long_support,
        short_resist, mid_resist, long_resist
    """
    if not bars:
        return {
            "short_support": 0.0, "mid_support": 0.0, "long_support": 0.0,
            "short_resist": 0.0, "mid_resist": 0.0, "long_resist": 0.0,
        }

    n = len(bars)
    # 提取有效的 (high, low) 对
    highs: list[float] = []
    lows: list[float] = []
    for bar in bars:
        h = to_float(bar.get("high"))
        l = to_float(bar.get("low"))
        if h is not None and l is not None and h > 0 and l > 0:
            highs.append(h)
            lows.append(l)
        else:
            # 用 close 做 fallback
            c = to_float(bar.get("close"))
            if c is not None and c > 0:
                highs.append(c)
                lows.append(c)

    if not highs:
        return {
            "short_support": 0.0, "mid_support": 0.0, "long_support": 0.0,
            "short_resist": 0.0, "mid_resist": 0.0, "long_resist": 0.0,
        }

    # ── 短线：最近 10 日高低点 ──
    short_n = min(10, len(highs))
    short_support = round(min(lows[-short_n:]), 2)
    short_resist = round(max(highs[-short_n:]), 2)

    # ── ATR 自适应参数：波动大的股放宽容差，波动小的收紧 ──
    _atr_pct = average_atr_pct(bars) or 0.02
    _adapt_tol = max(0.015, 0.8 * _atr_pct)       # 容差：至少 1.5%，或 0.8×ATR%
    _adapt_unbroken = max(0.03, 1.2 * _atr_pct)    # 破位阈值：至少 3%，或 1.2×ATR%

    # ── 辅助：在指定窗口内找局部极值 + 至少 2 次触及 ──
    def _find_level_with_touches(
        window_highs: list[float],
        window_lows: list[float],
        *,
        find_support: bool,
    ) -> float | None:
        """在 window 内找局部极值，并验证至少 2 次触及未破。

        find_support=True  → 找支撑（局部低点，至少 2 次低点触及但未跌破）
        find_support=False → 找压力（局部高点，至少 2 次高点触及但未突破）
        容差和破位阈值根据 ATR 自适应。
        """
        if len(window_highs) < 5:
            return None

        swing_window = 3  # 局部极值窗口：左右各 3 根
        tolerance_pct = _adapt_tol
        unbroken_pct = _adapt_unbroken

        source = window_lows if find_support else window_highs
        extrema: list[tuple[int, float]] = []

        for i in range(swing_window, len(source) - swing_window):
            val = source[i]
            left_vals = source[i - swing_window:i]
            right_vals = source[i + 1:i + swing_window + 1]

            if find_support:
                if val <= min(left_vals) and val <= min(right_vals):
                    extrema.append((i, val))
            else:
                if val >= max(left_vals) and val >= max(right_vals):
                    extrema.append((i, val))

        if not extrema:
            return None

        # 预排序 source 用于二分查找，将 O(E×N) 优化为 O(E×logN)
        import bisect
        sorted_vals = sorted(v for v in source if v is not None)

        best_price = None
        best_count = 0

        for idx, price in extrema:
            band_lo = price * (1 - tolerance_pct)
            band_hi = price * (1 + tolerance_pct)
            # 二分查找 band 范围内的点数
            lo_pos = bisect.bisect_left(sorted_vals, band_lo)
            hi_pos = bisect.bisect_right(sorted_vals, band_hi)
            touch_count = hi_pos - lo_pos
            # 验证「未破」：必须用正确的序列判定突破/跌破
            #   压力(find_support=False)：window 内最高价超过价位 ×(1+unbroken%) 即视为已被有效突破 → 无效
            #   支撑(find_support=True)：window 内最低价低于价位 ×(1-unbroken%) 即视为已被有效跌破 → 无效
            if touch_count >= 2:
                # 排序主键：优先「触碰次数最多」，平局再按「距最新价最近」
                cand_key = (-touch_count, abs(price - source[-1]))
                if find_support:
                    if min(window_lows) >= price * (1 - unbroken_pct):
                        if best_price is None or cand_key < (-best_count, abs(best_price - source[-1])):
                            best_price = price
                            best_count = touch_count
                else:
                    if max(window_highs) <= price * (1 + unbroken_pct):
                        if best_price is None or cand_key < (-best_count, abs(best_price - source[-1])):
                            best_price = price
                            best_count = touch_count

        return round(best_price, 2) if best_price is not None else None

    # ── 中线：60 日 ──
    mid_n = min(60, len(highs))
    mid_support = _find_level_with_touches(highs[-mid_n:], lows[-mid_n:], find_support=True)
    mid_resist = _find_level_with_touches(highs[-mid_n:], lows[-mid_n:], find_support=False)
    # fallback 到周期最低/最高
    if mid_support is None:
        mid_support = round(min(lows[-mid_n:]), 2)
    if mid_resist is None:
        mid_resist = round(max(highs[-mid_n:]), 2)

    # ── 长线：120 日 ──
    long_n = min(120, len(highs))
    long_support = _find_level_with_touches(highs[-long_n:], lows[-long_n:], find_support=True)
    long_resist = _find_level_with_touches(highs[-long_n:], lows[-long_n:], find_support=False)
    if long_support is None:
        long_support = round(min(lows[-long_n:]), 2)
    if long_resist is None:
        long_resist = round(max(highs[-long_n:]), 2)

    return {
        "short_support": short_support,
        "mid_support": mid_support,
        "long_support": long_support,
        "short_resist": short_resist,
        "mid_resist": mid_resist,
        "long_resist": long_resist,
    }


def count_below_ma(current: float, ma_values: dict[str, float | None]) -> int:
    return sum(1 for value in ma_values.values() if value is not None and current < value)
