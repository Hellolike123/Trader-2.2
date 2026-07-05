"""四阶段定位模型（Stage Positioning Model）— 主力行为驱动版

三层判定架构：
  第一层：主力行为主判定（60%） — main_force 五阶段（吸筹/试盘/拉升/派发/砸盘）
  第二层：量价确认（30%） — 验证主力信号真伪，降级虚假信号，Wyckoff 增强
  第三层：结构兜底（10%） — 量价启发式，主力数据不可用时使用

短期动能（走强/修复/震荡/转弱）→ 基于 MA5/MA10 + change_pct

四层防护（从宽松到严格）：
  1. 多日确认（连续 3 日信号一致才确认阶段转换）
  2. 置信度评分（<35% 保持上次阶段，从 50% 降低）
  3. 缠论+动量交叉验证（冲突时降级）
  4. 阶段锁定期（转换后锁定 3 天，从 5 天降低）

用法:
    from stage_positioning import assess_stage
    result = assess_stage(current, ma_values, change_pct, bars)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from trader_shared._logging import get_logger
from trader_shared.config import (
    ACCUMULATION_DAYS_LIMIT, MARKUP_DAYS_LIMIT,
    RALLY_REDUCE_FULL_SCORE, RALLY_REDUCE_MIN_SCORE,
    RALLY_REDUCE_POSITION_PCT, RALLY_REDUCE_LITE_POSITION_PCT,
    CORRELATION_THRESHOLD, CORRELATION_LOOKBACK_DAYS,
)

_logger = get_logger(__name__)


# ── 持仓相关性熔断（P2-1）────────────────────────────────────

def calc_portfolio_correlation(
    positions: list[dict[str, Any]],
    bars_map: dict[str, list[dict[str, Any]]],
    threshold: float = CORRELATION_THRESHOLD,
    lookback: int = CORRELATION_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """计算持仓个股两两相关性，识别集中风险暴露。

    当任意两只持仓的相关系数 R > threshold 时，将它们合并为同一风险组。
    触发熔断后，该风险组的总仓位上限 = 单票上限（降为最保守值）。

    Args:
        positions: 持仓列表，每个 dict 至少含 "code" 和 "position_pct" 键。
                   code 为股票代码，position_pct 为仓位百分比。
        bars_map:  {code: bars} 字典，bars 为 K 线列表（含 "close" 键）。
        threshold: 相关系数阈值，默认 0.7。
        lookback:  收价回溯天数，默认 20。

    Returns:
        {
            "correlation_matrix": dict,       # {("A","B"): r, ...} 两两相关系数
            "risk_groups": list[list[str]],   # 合并后的风险组（相关 > 阈值的股票归为一组）
            "triggered": bool,                # 是否触发熔断
            "adjusted_total_limit": int|None, # 触发时降为单票上限，否则 None
        }
    """
    if not positions or len(positions) < 2:
        return {
            "correlation_matrix": {},
            "risk_groups": [[p.get("code", "")] for p in positions] if positions else [],
            "triggered": False,
            "adjusted_total_limit": None,
        }

    # 提取各持仓的 20 日收盘价序列
    codes: list[str] = []
    close_arrays: list[list[float]] = []
    for pos in positions:
        code = pos.get("code", "")
        bars = bars_map.get(code, [])
        if not bars or len(bars) < 2:
            # 数据不足，跳过该票（不参与相关性计算）
            _logger.debug("correlation: %s bars不足，跳过", code)
            continue
        recent = bars[-lookback:]
        closes = [float(b.get("close") or 0) for b in recent]
        if len(closes) < 2:
            continue
        codes.append(code)
        close_arrays.append(closes)

    if len(codes) < 2:
        return {
            "correlation_matrix": {},
            "risk_groups": [[c] for c in codes] if codes else [],
            "triggered": False,
            "adjusted_total_limit": None,
        }

    # 对齐长度（取最短序列长度）
    min_len = min(len(arr) for arr in close_arrays)
    aligned = [arr[-min_len:] for arr in close_arrays]

    # 计算两两相关系数矩阵
    n = len(codes)
    matrix = np.array(aligned, dtype=np.float64)  # shape: (n, min_len)
    corr = np.corrcoef(matrix)  # shape: (n, n)

    # 提取相关系数 > 阈值的配对
    correlation_pairs: dict[tuple[str, str], float] = {}
    high_corr_pairs: list[tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            r = float(corr[i, j])
            correlation_pairs[(codes[i], codes[j])] = round(r, 4)
            if r > threshold:
                high_corr_pairs.append((i, j))

    # 合并高相关股票为风险组（Union-Find）
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i, j in high_corr_pairs:
        union(i, j)

    # 按根节点分组
    groups_map: dict[int, list[str]] = {}
    for idx in range(n):
        root = find(idx)
        groups_map.setdefault(root, []).append(codes[idx])
    risk_groups = list(groups_map.values())

    # 是否触发熔断（存在至少一个组含 2 只以上股票）
    triggered = any(len(g) > 1 for g in risk_groups)

    # 触发时：将触发组的总仓位上限降为单票上限
    # 这里返回单票上限提示，调用方负责实际仓位调整
    adjusted_total_limit: int | None = None
    if triggered:
        # 默认单票上限 30%（震荡市），调用方可根据 market_env 覆盖
        adjusted_total_limit = 30
        for group in risk_groups:
            if len(group) > 1:
                _logger.info(
                    "correlation: 风险暴露熔断触发，组 %s 相关系数 > %.2f，"
                    "总仓位上限降为 %d%%",
                    group, threshold, adjusted_total_limit,
                )

    return {
        "correlation_matrix": correlation_pairs,
        "risk_groups": risk_groups,
        "triggered": triggered,
        "adjusted_total_limit": adjusted_total_limit,
    }


# ── 阶段状态持久化（多日确认 + 锁定期）──────────────────────
_STATE_FILE = Path.home() / ".trader" / "stage_state.json"


def _load_stage_state(symbol: str = "") -> dict[str, Any]:
    """加载阶段状态（用于多日确认和锁定期）。

    P0 Fix: 按 symbol 隔离，避免多票分析时状态互相覆盖。
    存储格式: {"<symbol>": {...state...}, ...}
    """
    try:
        if _STATE_FILE.exists():
            raw = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                # 兼容旧格式（无 symbol 维度）：旧 dict 没有 symbol key 时视为全局
                if symbol and symbol in raw:
                    return raw[symbol]
                # 旧格式迁移：如果顶层没有 symbol key 且不含嵌套 dict，视为全局状态
                if symbol and not any(isinstance(v, dict) and k != symbol for k, v in raw.items()):
                    return raw
                return raw.get(symbol, {}) if symbol else raw
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("Stage state load failed: %s", exc)
    return {}


def _save_stage_state(state: dict[str, Any], symbol: str = "") -> None:
    """保存阶段状态。

    P0 Fix: 按 symbol 隔离存储。
    """
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if symbol:
            # 读取现有完整状态，更新当前 symbol 的部分
            all_states: dict[str, Any] = {}
            if _STATE_FILE.exists():
                try:
                    all_states = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                    if not isinstance(all_states, dict):
                        all_states = {}
                except (json.JSONDecodeError, OSError):
                    all_states = {}
            all_states[symbol] = state
            _STATE_FILE.write_text(json.dumps(all_states, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        _logger.debug("Stage state save failed: %s", exc)


# ── 量价关系判定（兜底备用层，权重 10%）──────────────────────

def _assess_volume_price(
    bars: list[dict[str, Any]],
    wyckoff_result: dict[str, Any] | None = None,
) -> tuple[str, float, str]:
    """威科夫量价关系判定四阶段。

    优先使用 wyckoff_core 的真实信号（spring/upthrust/背离），
    无威科夫信号时 fallback 到量比+涨跌幅启发式判断。

    Returns:
        (stage, score, reason)
        score: 0-100，该维度对阶段判定的置信度
    """
    if not bars or len(bars) < 20:
        return "蓄势", 30, "数据不足，默认蓄势"

    # ── 威科夫信号优先判定 ──
    if wyckoff_result:
        # 兼容两种格式：嵌套（wyckoff_strategy 包装后 {"wyckoff": {...}}）
        # 和扁平（wyckoff_analysis 直接返回 {...}）
        if isinstance(wyckoff_result, dict) and "wyckoff" in wyckoff_result:
            wyk = wyckoff_result["wyckoff"]
        else:
            wyk = wyckoff_result if isinstance(wyckoff_result, dict) else {}
        if isinstance(wyk, dict):
            spring = wyk.get("spring_signal")
            upthrust = wyk.get("upthrust_signal")
            bullish_div = wyk.get("bullish_volume_divergence")
            bearish_div = wyk.get("bearish_volume_divergence")
            spring_reason = wyk.get("spring_reason", "")

            # Spring = 吸筹确认 → 蓄势偏强/主升前兆
            if spring:
                return "蓄势偏强", 75, f"威科夫弹簧确认（{spring_reason}），吸筹末期"

            # 上冲回落 = 派发信号
            if upthrust:
                return "派发", 70, "威科夫上冲回落，派发信号"

            # 看多量价背离 = 吸筹
            if bullish_div and not bearish_div:
                return "蓄势偏强", 60, "威科夫看多量价背离，吸筹中"

            # 看空量价背离 = 派发
            if bearish_div and not bullish_div:
                return "派发", 60, "威科夫看空量价背离，派发中"

    recent5 = bars[-5:]
    recent20 = bars[-20:]

    # 计算量能比率
    vol_5 = [float(b.get("volume") or 0) for b in recent5]
    vol_20 = [float(b.get("volume") or 0) for b in recent20]
    avg_vol_5 = sum(vol_5) / max(len(vol_5), 1)
    avg_vol_20 = sum(vol_20) / max(len(vol_20), 1)
    vol_ratio = avg_vol_5 / max(avg_vol_20, 1)

    # P1 Fix: 计算 5 日涨幅时，剔除历史单日涨跌幅 > 7% 的跳空缺口日，
    # 避免单日缺口主导阶段判定（如涨停后横盘 4 天被误判为"主升"）
    # 注意：最后一天（今天）不排除，真突破不应被误杀
    close_5_start = float(recent5[0].get("close") or 0)
    close_5_end = float(recent5[-1].get("close") or 0)

    # 计算每日涨跌幅，找出跳空日（排除最后一天/今天）
    gap_indices: set[int] = set()
    for i, b in enumerate(recent5):
        if i == 0 or i == len(recent5) - 1:
            continue
        prev_c = float(recent5[i - 1].get("close") or 0)
        cur_c = float(b.get("close") or 0)
        if prev_c > 0 and abs(cur_c - prev_c) / prev_c > 0.07:
            gap_indices.add(i)

    if close_5_start > 0:
        if gap_indices:
            # P1 Fix: 剔除跳空日，基准价为第一个跳空日前一日的收盘价。
            # 原代码 base_idx 循环从 0 开始、index 0 永不为 gap，永远返回 0 —— 跳空检测完全旁路。
            base_idx = max(0, min(gap_indices) - 1)
            base_price = float(recent5[base_idx].get("close") or close_5_start)
            if base_price > 0:
                price_change_5 = (close_5_end - base_price) / base_price
            else:
                price_change_5 = 0.0
        else:
            price_change_5 = (close_5_end - close_5_start) / close_5_start
    else:
        price_change_5 = 0.0

    # 计算振幅
    highs = [float(b.get("high") or 0) for b in recent5]
    lows = [float(b.get("low") or 0) for b in recent5]
    if close_5_start > 0:
        amplitude = (max(highs) - min(lows)) / close_5_start
    else:
        amplitude = 0.0

    # 威科夫四阶段判定
    is_low_volume = vol_ratio < 0.8    # 缩量
    is_high_volume = vol_ratio > 1.2   # 放量
    is_rising = price_change_5 > 0.03  # 涨幅 > 3%
    is_falling = price_change_5 < -0.03  # 跌幅 > 3%
    is_flat = abs(price_change_5) < 0.01  # 振幅 < 1%
    is_strong_rising = price_change_5 > 0.08  # 涨幅 > 8%，强势突破

    if is_low_volume and is_flat and amplitude < 0.05:
        return "蓄势", 70, f"缩量横盘（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"
    if is_high_volume and is_rising:
        return "主升", 80, f"放量上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
    if is_strong_rising and is_high_volume:
        return "主升", 75, f"放量强势上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
    elif is_strong_rising:
        return "蓄势偏强", 55, f"缩量强势上涨，量价不配合（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
    if is_high_volume and is_flat:
        return "派发", 65, f"放量不涨（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"
    if is_high_volume and is_falling:
        return "衰退", 75, f"放量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"

    # 弱信号：缩量下跌（可能是衰退末期的缩量筑底）
    if is_low_volume and is_falling:
        return "蓄势", 50, f"缩量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%），可能筑底"

    # 弱信号：放量但方向不明确
    if is_high_volume:
        return "派发", 45, f"放量方向不明（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"

    # ── 正常量能区域分化（vol_ratio 0.8~1.2，覆盖约 65% 的交易日） ──
    if vol_ratio >= 0.8 and vol_ratio < 1.2:
        if price_change_5 > 0.03:
            return "蓄势偏强", 65, f"正常量能上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if price_change_5 > 0.01:
            return "蓄势偏强", 58, f"温和上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if price_change_5 < -0.03:
            return "蓄势偏弱", 55, f"正常量能下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"
        if price_change_5 < -0.01:
            return "蓄势偏弱", 48, f"正常量能回调（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"
        # 正常量能 + 横盘 → 真正的蓄势
        return "蓄势", 40, f"正常量能横盘（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"

    # ── 缩量区域分化 ──
    if vol_ratio < 0.8:
        if price_change_5 > 0.01:
            return "蓄势偏强", 58, f"缩量上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if price_change_5 < -0.01:
            return "蓄势偏弱", 42, f"缩量下跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"
        # 缩量横盘已在上面处理（is_low_volume and is_flat），这里兜底
        return "蓄势", 40, f"缩量横盘（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"

    # ── 放量区域 ──
    # 已在上面处理（is_high_volume + rising/flat/falling）
    # 这里是放量但幅度不够大的兜底
    if price_change_5 > 0:
        return "蓄势偏强", 50, f"放量微涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
    if price_change_5 < 0:
        return "蓄势偏弱", 48, f"放量微跌（量比{vol_ratio:.1f}，跌{price_change_5*100:+.1f}%）"

    # 默认
    return "蓄势", 40, f"量价无明确信号（量比{vol_ratio:.1f}，涨跌{price_change_5*100:+.1f}%）"


# ── 主力行为 → 大阶段映射（权重 60%）──────────────────────────

def _detect_main_force_stage(main_force_result: dict | None) -> tuple[str | None, float, str]:
    """主力行为 → 大阶段映射。

    Args:
        main_force_result: detect_main_force_stage() 的返回值，含 stage/confidence/signals

    Returns:
        (stage, confidence, reason)
        stage=None 表示无数据，不参与融合
        confidence: 0-100
    """
    if not main_force_result or not isinstance(main_force_result, dict):
        return None, 0.0, ""

    mf_stage = main_force_result.get("stage", "unknown")
    mf_confidence = float(main_force_result.get("confidence", 0))
    mf_signals = main_force_result.get("signals", [])

    if mf_stage == "unknown" or mf_confidence <= 0:
        return None, 0.0, ""

    signal_text = "；".join(mf_signals[-2:]) if mf_signals else ""

    mapping = {
        "accumulation": ("蓄势", 60),
        "testing": ("蓄势偏强", 55),
        "markup": ("主升", 70),
        "distribution": ("派发", 65),
        "markdown": ("衰退", 60),
    }

    result = mapping.get(mf_stage)
    if result is None:
        return None, 0.0, ""

    stage, base_conf = result
    # 置信度打折：main_force 的 confidence 是 0-1，一致性高时全额，低时打折
    conf_multiplier = min(mf_confidence, 1.0) if mf_confidence > 0 else 0.5
    confidence = min(100, int(base_conf * min(conf_multiplier, 1.0)))

    reason = f"主力{mf_stage}(置信度{mf_confidence:.2f})"
    if signal_text:
        reason += f" [{signal_text}]"

    return stage, confidence, reason


# ── 量价确认（权重 30%）─────────────────────────────────────

def _volume_price_confirm(
    mf_stage: str,
    bars: list[dict[str, Any]] | None,
    wyckoff_result: dict[str, Any] | None = None,
) -> tuple[str, float, str]:
    """量价确认主力信号的真假。

    不独立判阶段，只对主力信号做确认/降级/升级。

    Args:
        mf_stage: main_force 输出的阶段 (accumulation/testing/markup/distribution/markdown)
        bars: K线数据
        wyckoff_result: 威科夫分析结果

    Returns:
        (action, confidence, reason)
        action: "confirm" / "downgrade" / "upgrade"
        confidence: 0-1 确认置信度
    """
    if not bars or len(bars) < 5:
        return "confirm", 0.0, "数据不足，默认确认"

    recent5 = bars[-5:]

    # ── 量价计算 ──
    vol_5 = [float(b.get("volume") or 0) for b in recent5]
    vol_20_avg = 0.0
    if len(bars) >= 20:
        vol_20 = [float(b.get("volume") or 0) for b in bars[-20:]]
        vol_20_avg = sum(vol_20) / max(len(vol_20), 1)
    elif len(bars) >= 10:
        vol_10 = [float(b.get("volume") or 0) for b in bars[-10:]]
        vol_20_avg = sum(vol_10) / max(len(vol_10), 1)
    avg_vol_5 = sum(vol_5) / max(len(vol_5), 1)
    vol_ratio = avg_vol_5 / max(vol_20_avg, 1) if vol_20_avg > 0 else 1.0

    close_5_start = float(recent5[0].get("close") or 0)
    close_5_end = float(recent5[-1].get("close") or 0)
    price_change_5 = (close_5_end - close_5_start) / close_5_start if close_5_start > 0 else 0.0

    # ── 提取威科夫信号 ──
    spring = False
    upthrust = False
    if wyckoff_result:
        wyk = wyckoff_result.get("wyckoff", {}) if isinstance(wyckoff_result, dict) else {}
        if isinstance(wyk, dict):
            spring = wyk.get("spring_signal", False)
            upthrust = wyk.get("upthrust_signal", False)

    # ── 量价判断 ──
    rising = price_change_5 > 0.03
    falling = price_change_5 < -0.03
    flat = abs(price_change_5) < 0.01
    high_vol = vol_ratio > 1.2
    low_vol = vol_ratio < 0.8

    if mf_stage == "markup":
        # 拉升 → 需放量上涨确认
        if high_vol and rising:
            return "confirm", 0.30, f"放量上涨（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if falling:
            return "downgrade", 0.20, f"价跌，不配合拉升信号"
        if low_vol:
            return "downgrade", 0.20, f"缩量拉升，量价不配合（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        return "confirm", 0.15, f"量价中性（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"

    elif mf_stage == "accumulation":
        # 吸筹 → 缩量筑底最佳
        if low_vol and flat:
            return "confirm", 0.30, f"缩量筑底（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if high_vol and falling:
            return "downgrade", 0.25, f"放量下跌，吸筹期走坏"
        if spring:
            return "upgrade", 0.25, "Wyckoff Spring确认吸筹"
        if falling:
            return "downgrade", 0.15, "价跌，可能吸筹失败"
        return "confirm", 0.15, f"量价中性（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"

    elif mf_stage == "distribution":
        # 派发 → 放量滞涨或价跌
        if high_vol and (flat or falling):
            return "confirm", 0.30, f"放量滞涨/下跌（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"
        if upthrust:
            return "confirm", 0.30, "Wyckoff Upthrust确认派发"
        if low_vol and rising:
            return "downgrade", 0.20, "缩量上涨，非典型派发"
        return "confirm", 0.15, f"量价中性（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"

    elif mf_stage == "testing":
        # 试盘 → 价冲高+小幅回落是正常试盘
        return "confirm", 0.15, "试盘期量价中性"

    elif mf_stage == "markdown":
        # 砸盘 → 放量下跌确认
        if high_vol and falling:
            return "confirm", 0.30, f"放量下跌确认砸盘"
        return "confirm", 0.15, f"量价中性（量比{vol_ratio:.1f}，涨{price_change_5*100:+.1f}%）"

    return "confirm", 0.0, "未知主力阶段"


# ── 升降级辅助函数 ────────────────────────────────────────────

def _downgrade_stage(stage: str) -> str:
    """将阶段降一级。用于量价不配合主力信号时的保守处理。

    Note: "蓄势偏弱"下再无更低阶段可降，main_force "衰退"已是最差阶段。
    """
    mapping = {
        "主升": "蓄势偏强",
        "蓄势偏强": "蓄势",
        "蓄势": "蓄势偏弱",
        "派发": "蓄势偏弱",
    }
    return mapping.get(stage, stage)


def _upgrade_stage(stage: str) -> str:
    """将阶段升一级。用于 Wyckoff 等信号增强确认时。"""
    mapping = {
        "蓄势": "蓄势偏强",
        "蓄势偏强": "主升",
        "蓄势偏弱": "蓄势偏强",  # 蓄势偏弱跳一级到蓄势偏强
    }
    return mapping.get(stage, stage)


# ── 综合阶段判定 ──────────────────────────────────────────

def _detect_major_stage(
    current: float,
    ma_values: dict[str, float | None],
    bars: list[dict[str, Any]] | None = None,
    fusion_hint: dict[str, Any] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    chan_result: dict[str, Any] | None = None,
    main_force_result: dict[str, Any] | None = None,
) -> tuple[str, float, str, str]:
    """主力行为三层架构判定大阶段。

    第一层：主力行为主判定（60%） — main_force 五阶段映射
    第二层：量价确认（30%） — 验证主力信号真伪
    第三层：结构兜底（10%） — 主力数据不可用时使用量价启发式

    All new params default None for backward compatibility.

    Args:
        current: 当前价格
        ma_values: 均线值字典（保留用于兜底兼容）
        bars: K线数据
        fusion_hint: 融合层信号（微调用）
        wyckoff_result: 威科夫分析结果
        chan_result: 缠论分析结果（兜底保留，当前未使用）
        main_force_result: 主力行为分析结果

    Returns:
        (stage, confidence, reason, vp_stage)
    """
    # 始终计算量价评估供 vp_stage 兼容 + 兜底
    vp_stage, vp_score, vp_reason = _assess_volume_price(bars, wyckoff_result=wyckoff_result)

    # ── 第一步：主力行为主判定 ──
    mf_stage, mf_conf, mf_reason = _detect_main_force_stage(main_force_result)

    if mf_stage is not None:
        # ── 第二步：量价确认（用原始英文 stage 匹配）──
        raw_mf_stage = main_force_result.get("stage", "unknown") if isinstance(main_force_result, dict) else "unknown"
        confirm_action, confirm_conf, confirm_reason = _volume_price_confirm(
            raw_mf_stage, bars, wyckoff_result
        )

        if confirm_action == "confirm":
            final_stage = mf_stage
            confidence = min(100, int(mf_conf + 30 * confirm_conf))
            reason = f"主力:{mf_reason} | 量价确认:{confirm_reason}"
        elif confirm_action == "downgrade":
            final_stage = _downgrade_stage(mf_stage)
            confidence = int(mf_conf * 0.6)
            reason = f"主力:{mf_reason} | 量价不符，降级:{confirm_reason}"
        elif confirm_action == "upgrade":
            final_stage = _upgrade_stage(mf_stage)
            confidence = min(100, mf_conf + 15)
            reason = f"主力:{mf_reason} | Wyckoff增强:{confirm_reason}"
        else:
            final_stage = mf_stage
            confidence = mf_conf
            reason = mf_reason

        # fusion_hint 微调 (不影响阶段，只做边际调整)
        if fusion_hint:
            ws = fusion_hint.get("weighted_score")
            conf = fusion_hint.get("confidence", 0)
            if ws is not None and conf is not None and conf >= 0.3:
                try:
                    ws_f = float(ws)
                    if ws_f > 0.25 and final_stage in ("蓄势", "蓄势偏弱"):
                        # 强买入信号 → 偏积极方向微调
                        if final_stage == "蓄势偏弱":
                            final_stage = "蓄势"
                        elif final_stage == "蓄势":
                            final_stage = "蓄势偏强"
                        confidence = min(100, confidence + 10)
                    elif ws_f < -0.2 and final_stage in ("主升", "蓄势偏强", "蓄势"):
                        # 强卖出信号 → 偏保守方向微调
                        base_for_downgrade = final_stage
                        if base_for_downgrade in ("蓄势偏强", "蓄势"):
                            final_stage = _downgrade_stage(base_for_downgrade)
                        elif base_for_downgrade == "主升":
                            final_stage = "蓄势偏强"
                        confidence = max(0, confidence - 10)
                except (TypeError, ValueError):
                    pass
    else:
        # ── 第三步：结构兜底 — 量价启发式 ──
        final_stage = vp_stage
        confidence = vp_score
        reason = f"量价兜底:{vp_reason}"

    return final_stage, confidence, reason, vp_stage


# ── 短期动能判定 ──────────────────────────────────────────────

def _detect_short_term_momentum(
    current: float,
    expma10: float | None,
    expma20: float | None,
    change_pct: float,
    position_ratio: float,
) -> tuple[str, str]:
    """判定短期动能：走强/修复/震荡/转弱"""
    if expma10 is None or expma20 is None:
        return "震荡", "EXPMA数据不足"

    dist_to_expma20 = (current - expma20) / max(expma20, 1)

    # 走强 (Strong)：现价站上 EXPMA(10) 且 EXPMA(10) > EXPMA(20)
    if current >= expma10 and expma10 > expma20:
        return "走强", "站上EXPMA(10)且多头排列"

    # 均线粘合优先判断为震荡（需在修复之前，避免粘合期误报修复）
    if abs(expma10 - expma20) / max(expma20, 1) < 0.01:
        return "震荡", "EXPMA均线粘合"

    # 修复 (Recovery)：现价在 EXPMA(10) 与 EXPMA(20) 之间
    if min(expma10, expma20) <= current < max(expma10, expma20):
        return "修复", "回踩生命线(EXPMA10/20之间)"

    if current < expma20:
        if change_pct < -2.0 or expma10 < expma20:
            return "转弱", "跌破EXPMA(20)且走势破位"
        if abs(dist_to_expma20) < 0.03:
            return "震荡", "跌破EXPMA(20)但距离不远"
        return "转弱", "跌破EXPMA(20)且偏离较大"

    return "震荡", "走势未匹配极强/极弱特征"


# ── 四层防护机制 ──────────────────────────────────────────────

def _layer1_multi_day_confirm(
    raw_stage: str,
    state: dict[str, Any],
    trade_date: str = "",
    price_change_5: float = 0.0,
) -> tuple[str, bool]:
    """第一层：多日确认。默认连续 3 日信号一致才确认阶段转换。
    但当近5日涨幅>5%时，只需1天确认（避免强势突破被死板规则拖住）。

    Returns:
        (confirmed_stage, is_transition)
    """
    prev_stage = state.get("last_confirmed_stage", "蓄势")
    pending_stage = state.get("pending_stage", "")
    pending_count = state.get("pending_count", 0)
    pending_date = state.get("pending_date", "")

    # 强势突破时降低确认天数
    required_days = 1 if abs(price_change_5) > 0.05 else 3

    if raw_stage == prev_stage:
        # 信号一致，重置 pending
        return prev_stage, False

    if not trade_date:
        # 降级模式：trade_date 为空时直接返回原始阶段，不触发转换
        state["pending_stage"] = ""
        state["pending_count"] = 0
        state["pending_date"] = ""
        return raw_stage, False

    if raw_stage == pending_stage:
        # 连续相同的非当前信号 — 按交易日计数
        if trade_date == pending_date:
            # 同一天：如果已满确认天数，直接确认；否则不递增
            if pending_count >= required_days:
                return raw_stage, True
            return prev_stage, False
        # 新交易日，递增
        pending_count += 1
        if pending_count >= required_days:
            # 确认转换
            return raw_stage, True
        # 还没到确认天数，保持当前阶段
        state["pending_count"] = pending_count
        state["pending_date"] = trade_date
        return prev_stage, False
    else:
        # 新的非当前信号，重新计数
        state["pending_stage"] = raw_stage
        state["pending_count"] = 1
        state["pending_date"] = trade_date
        return prev_stage, False


def _layer2_confidence_gate(
    stage: str,
    confidence: int,
    state: dict[str, Any],
    vp_stage: str = "",
) -> tuple[str, int]:
    """第二层：置信度评分。< 35% 保持上次阶段，但量价明确判主升/衰退时不拦截。

    Returns:
        (final_stage, final_confidence)
    """
    if confidence < 35:
        # 量价维度明确判主升或衰退时，信任量价信号（不被置信度门控拦截）
        if vp_stage in ("主升", "衰退"):
            return stage, max(confidence, 40)
        prev_stage = state.get("last_confirmed_stage", "蓄势")
        return prev_stage, confidence
    return stage, confidence


def _layer3_cross_validation(
    stage: str,
    chan_result: dict[str, Any] | None,
    momentum_result: dict[str, Any] | None,
) -> tuple[str, str | None]:
    """第三层：缠论+动量交叉验证。冲突时降级。

    Returns:
        (final_stage, conflict_note)
    """
    if chan_result is None and momentum_result is None:
        return stage, None

    # 缠论冲突检查
    if chan_result and isinstance(chan_result, dict):
        chan = chan_result.get("chanlun", {})
        if isinstance(chan, dict):
            divergence = chan.get("divergence", {})
            if stage == "主升" and divergence.get("top_divergence"):
                return "派发", "缠论顶背离与主升冲突，降级为派发"
            if stage == "衰退" and divergence.get("bottom_divergence"):
                return "蓄势", "缠论底背离与衰退冲突，降级为蓄势"

    # 动量冲突检查
    if momentum_result and isinstance(momentum_result, dict):
        mom = momentum_result.get("momentum", {})
        if isinstance(mom, dict):
            direction = mom.get("direction", "neutral")
            if stage == "主升" and direction == "bearish":
                return "派发", "动量看空与主升冲突，降级为派发"
            if stage == "衰退" and direction == "bullish":
                return "蓄势", "动量看多与衰退冲突，降级为蓄势"

    return stage, None


def _layer4_stage_lock(
    stage: str,
    state: dict[str, Any],
    is_transition: bool,
) -> tuple[str, bool]:
    """第四层：阶段锁定期。转换后锁定 3 天（从 5 天降低，避免错过波段窗口）。

    Returns:
        (final_stage, is_locked)
    """
    lock_remaining = state.get("lock_remaining", 0)

    if is_transition:
        # 新转换，设置锁定期（从 5 天降低到 3 天）
        state["lock_remaining"] = 3
        return stage, True

    if lock_remaining > 0:
        # 锁定期内
        state["lock_remaining"] = lock_remaining - 1
        prev_stage = state.get("last_confirmed_stage", "蓄势")
        return prev_stage, True

    return stage, False


# ── 组合决策矩阵 ──────────────────────────────────────────────

_DECISION_MATRIX: dict[str, dict[str, tuple[str, int]]] = {
    "蓄势": {
        "走强": ("低吸试盘", 20),
        "修复": ("回调低吸", 15),
        "震荡": ("观望等待", 0),
        "转弱": ("观望等待", 0),
    },
    "蓄势偏强": {
        "走强": ("试探建仓", 30),
        "修复": ("回调低吸", 25),
        "震荡": ("小仓试探", 10),
        "转弱": ("观望等待", 0),
    },
    "蓄势偏弱": {
        "走强": ("观望等待", 0),
        "修复": ("观望等待", 0),
        "震荡": ("观望等待", 0),
        "转弱": ("观望等待", 0),
    },
    "主升": {
        "走强": ("顺势加仓", 60),
        "修复": ("回踩加仓", 40),
        "震荡": ("底仓持有", 20),
        "转弱": ("跌破防线减仓", 20),
    },
    "派发": {
        "走强": ("逢高减磅", 20),
        "修复": ("逢反弹减仓", 10),
        "震荡": ("逢反弹减仓", 10),
        "转弱": ("清仓逃命", 0),
    },
    "衰退": {
        "走强": ("空仓规避", 0),
        "修复": ("空仓规避", 0),
        "震荡": ("空仓规避", 0),
        "转弱": ("空仓规避", 0),
    },
}


# ── 大盘环境对仓位的影响 ──────────────────────────────────────

_ENV_LIMITS: dict[str, dict[str, int]] = {
    #                单票上限  总仓位上限  新建仓
    "牛市": {"single": 40, "total": 80, "init": 10},
    "震荡市": {"single": 30, "total": 60, "init": 10},
    "熊市": {"single": 20, "total": 30, "init": 10},
}


def compute_position_with_env(
    stage: str,
    momentum: str,
    market_env: str = "震荡市",
    pnl_pct: float = 0.0,
    total_position_pct: float = 0.0,
) -> dict[str, Any]:
    """根据阶段+大盘环境计算建议仓位。

    Returns:
        {
            "stage_position_pct": int,   # 阶段仓位
            "env_limit_pct": int,        # 大盘环境单票上限
            "total_limit_pct": int,      # 大盘环境总仓位上限
            "suggested_pct": int,        # 建议仓位（取较小值）
            "market_env": str,
            "hard_rule_blocked": bool,   # 硬规则阻止
            "hard_rule_reason": str,
        }
    """
    # 阶段仓位
    stage_pct = _DECISION_MATRIX.get(stage, {}).get(momentum, ("观察", 0))[1]

    # 大盘环境限制
    env = _ENV_LIMITS.get(market_env, _ENV_LIMITS["震荡市"])
    single_limit = env["single"]
    total_limit = env["total"]

    # 硬规则检查（收集所有触发的原因）
    hard_blocked = False
    hard_reasons: list[str] = []

    if pnl_pct < 0:
        hard_blocked = True
        hard_reasons.append("持仓亏损，禁止加仓")

    if stage == "衰退":
        hard_blocked = True
        hard_reasons.append("衰退期，禁止建仓")

    if total_position_pct >= total_limit:
        hard_blocked = True
        hard_reasons.append(f"总仓位 {total_position_pct}% 已达上限 {total_limit}%")

    # 合并原因为字符串
    hard_reason = "；".join(hard_reasons) if hard_reasons else ""

    # 建议仓位
    if hard_blocked:
        suggested = 0
    else:
        suggested = min(stage_pct, single_limit)

    return {
        "stage_position_pct": stage_pct,
        "env_limit_pct": single_limit,
        "total_limit_pct": total_limit,
        "suggested_pct": suggested,
        "market_env": market_env,
        "hard_rule_blocked": hard_blocked,
        "hard_rule_reason": hard_reason,
    }


# ── fusion action 持仓场景化仲裁 ────────────────────────────────────

# fusion action 分类常量
_REDUCE_ACTIONS = frozenset({"减仓", "空仓/止损", "空仓 (大盘很差, 一票否决)"})
_ADD_ACTIONS = frozenset({"增持", "半仓试 (多方主导)", "半仓试 (多方主导但有分歧)"})


def action_for_holding_state(
    fusion_action: str,
    has_position: bool,
) -> dict[str, str]:
    """根据持仓状态给 fusion action 加场景标签，消除与 suggested_pct 的互斥。

    当 fusion action 说「减仓」但 suggested_pct=0（未持仓）时，
    两个语义互斥：减仓的前提是你有仓位才能减。
    此函数通过 holding_hint 明确场景，让 AI 渲染时不再同框打架。

    Returns:
        {
            "action": str,        # 原始 action 保留
            "holding_hint": str,  # 场景化提示（显示给用户/AI）
        }
    """
    action = str(fusion_action).strip()

    if action in _REDUCE_ACTIONS:
        if has_position:
            return {"action": action, "holding_hint": "已有仓位者执行减仓/止损"}
        return {"action": action, "holding_hint": "未持仓者不参与，无仓可减"}

    if action in _ADD_ACTIONS:
        if has_position:
            return {"action": action, "holding_hint": "已有仓位者按 suggested_pct 加仓"}
        return {"action": action, "holding_hint": "未持仓者按 suggested_pct 建仓"}

    # 持股观望 / 等转强观察 / 观望(信号冲突) 等
    return {"action": action, "holding_hint": "观望等待，不操作"}


def assess_stage(
    current: float,
    ma_values: dict[str, float | None],
    change_pct: float,
    bars: list[dict[str, Any]] | None = None,
    position_ratio: float = 0.5,
    chan_result: dict[str, Any] | None = None,
    momentum_result: dict[str, Any] | None = None,
    support: float = 0.0,
    pnl_pct: float = 0.0,
    atr14: float = 0.0,
    chip_migration: dict[str, Any] | None = None,
    fib_retrace: dict[str, Any] | None = None,
    symbol: str = "",
    trade_date: str = "",
    fusion_hint: dict[str, Any] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    main_force_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """四阶段定位主函数（主力行为驱动 + 量价确认 + 四层防护）

    Returns:
        {
            "major_stage": str,       # 蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退
            "major_reason": str,
            "momentum": str,          # 走强/修复/震荡/转弱
            "momentum_reason": str,
            "action": str,            # 操作建议
            "max_position_pct": int,  # 最大仓位百分比
            "stage_label": str,       # "蓄势期 + 修复"
            "confidence": int,        # 阶段置信度 0-100
            "protection_notes": list, # 四层防护触发说明
            "stop_losses": dict,
        }
    """
    ma5 = ma_values.get("ma5")
    ma10 = ma_values.get("ma10")
    ma20 = ma_values.get("ma20")

    # 第一步：综合阶段判定（主力行为优先 + 量价确认 + 结构兜底）
    raw_stage, raw_confidence, raw_reason, vp_stage = _detect_major_stage(
        current, ma_values, bars, fusion_hint=fusion_hint, wyckoff_result=wyckoff_result,
        chan_result=chan_result, main_force_result=main_force_result,
    )

    # P1 Fix: 新股置信度打折 — 当数据不足 60 天时，置信度按比例折扣
    new_stock_warning = ""
    if bars and len(bars) < 60:
        discount = len(bars) / 60.0
        raw_confidence = int(raw_confidence * discount)
        new_stock_warning = f"新股数据不足（{len(bars)}天），置信度打折"

    # 加载阶段状态
    state = _load_stage_state(symbol=symbol)
    protection_notes: list[str] = []

    # P1 Fix: 新股数据不足警告
    if new_stock_warning:
        protection_notes.append(new_stock_warning)

    # Fix A4: 实际执行顺序：层2(置信度) → 层1(多日确认) → 层3(交叉验证) → 层4(锁定)
    # 逻辑合理：先过滤低置信信号，再做多日确认，注释编号之前写反了

    # 置信度门控（先于多日确认，过滤噪音信号）
    gated_stage, gated_confidence = _layer2_confidence_gate(raw_stage, raw_confidence, state, vp_stage=vp_stage)
    if gated_stage != raw_stage:
        protection_notes.append(f"置信度{raw_confidence}%<35%，保持{gated_stage}")

    # 多日确认（在置信度过滤之后，确认阶段转换真实性）
    # 计算5日涨幅，强势时降低确认天数
    _price_change_5 = 0.0
    if bars and len(bars) >= 5:
        try:
            _c5 = float(bars[-5].get("close") or 0)
            _cend = float(bars[-1].get("close") or 0)
            if _c5 > 0:
                _price_change_5 = (_cend - _c5) / _c5
        except (TypeError, ValueError):
            pass
    confirmed_stage, is_transition = _layer1_multi_day_confirm(
        gated_stage, state, trade_date=trade_date, price_change_5=_price_change_5
    )
    if confirmed_stage != gated_stage:
        _req = 1 if abs(_price_change_5) > 0.05 else 3
        protection_notes.append(f"多日确认中（{state.get('pending_count', 0)}/{_req}）")

    # 第三层：交叉验证
    validated_stage, conflict_note = _layer3_cross_validation(
        confirmed_stage, chan_result, momentum_result
    )
    if conflict_note:
        protection_notes.append(conflict_note)

    # 第四层：阶段锁定期
    final_stage, is_locked = _layer4_stage_lock(validated_stage, state, is_transition)
    if is_locked:
        protection_notes.append(f"阶段锁定3天")
        if final_stage != validated_stage:
            protection_notes.append(f"锁定期内保持{final_stage}")

    # 保存状态
    if is_transition:
        state["last_confirmed_stage"] = final_stage
        state["pending_stage"] = ""
        state["pending_count"] = 0
        state["pending_date"] = ""
    _save_stage_state(state, symbol=symbol)

    # 短期动能判定
    expma10 = ma_values.get("expma10")
    expma20 = ma_values.get("expma20")
    momentum, momentum_reason = _detect_short_term_momentum(
        current, expma10, expma20, change_pct, position_ratio
    )

    # 决策矩阵
    action, max_position = _DECISION_MATRIX.get(final_stage, {}).get(
        momentum, ("观察", 0)
    )

    # 黄金坑共振验证 (Golden Bid Resonance)
    if fib_retrace and "golden_bid" in fib_retrace and fib_retrace["golden_bid"] is not None:
        golden_bid = float(fib_retrace["golden_bid"])
        # Check if EXPMA(10) or EXPMA(20) is near golden_bid (e.g. within 1.5%)
        expma_vals = [v for v in (expma10, expma20) if v is not None]
        if expma_vals:
            for expma_val in expma_vals:
                if golden_bid > 0 and abs(expma_val - golden_bid) / golden_bid <= 0.015:
                    action = "🌟黄金共振加仓"
                    # 黄金共振：EXPMA支撑与Golden Bid重合，强力信号
                    # 拔高至 80% 作为最大建议仓位（实际仓位由 compute_position_with_env 根据大盘环境截断）
                    max_position = 80
                    protection_notes.append("触发黄金共振（EXPMA与Golden Bid重合）")
                    break

    stage_label = f"{final_stage}期 + {momentum}"

    # 硬规则同步: 亏损/衰退期 → action 强制改为"不碰"，position 归零
    if pnl_pct < 0 and action not in ("不碰", "清仓"):
        action = "不碰"
        max_position = 0
        stage_label = f"{final_stage}期 + {momentum}（亏损不加仓）"
    elif final_stage == "衰退" and action not in ("不碰", "清仓"):
        action = "不碰"
        max_position = 0

    # 三层止损体系
    stop_losses = compute_stop_losses(
        stage=final_stage,
        current=current,
        support=support,
        ma20=ma20,
        bars=bars,
        atr14=atr14,
        chip_migration=chip_migration,
    )

    return {
        "major_stage": final_stage,
        "major_reason": raw_reason,
        "momentum": momentum,
        "momentum_reason": momentum_reason,
        "action": action,
        "max_position_pct": max_position,
        "stage_label": stage_label,
        "confidence": gated_confidence,
        "protection_notes": protection_notes,
        "stop_losses": stop_losses,
    }


# ── 三层止损体系 ──────────────────────────────────────────────

def compute_stop_losses(
    stage: str,
    current: float,
    support: float,
    ma20: float | None,
    bars: list[dict[str, Any]] | None = None,
    atr14: float = 0.0,
    chip_migration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """三层止损体系（ATR + 筹码驱动）。

    第一层：技术止损（支撑位 - 1.5×ATR，牛市防洗盘）
    第二层：阶段止损（随阶段变化）
    第三层：时间止损（买入后 N 天不涨走人）

    筹码驱动移动止损：
      底部筹码峰没松动 → 止损跟 MA10
      底部筹码峰松动 > 40% → 止损收紧到 MA20
      底部筹码峰搬家 > 50% → 清仓

    Args:
        stage: 当前阶段
        current: 当前价
        support: 支撑位
        ma20: 20 日均线
        bars: K线数据
        atr14: 14日ATR值
        chip_migration: 筹码搬家监控结果

    Returns:
        {
            "technical": {"price": float, "reason": str},
            "stage_based": {"price": float, "reason": str},
            "time_limit": {"days": int, "reason": str},
            "chip_trailing": {"price": float, "reason": str} | None,
        }
    """
    # 第一层：技术止损（ATR-based）
    if support > 0 and atr14 > 0:
        # 支撑位 - 1.5×ATR，确保止损价为正
        tech_stop = round(max(0.01, support - 1.5 * atr14), 2)
        tech_reason = f"支撑 {support:.2f} - 1.5×ATR({atr14:.2f})"
    elif support > 0:
        # 无 ATR 数据，退回旧逻辑
        tech_stop = round(support * 0.975, 2)
        tech_reason = f"关键支撑 {support:.2f} 下方2.5%"
    else:
        tech_stop = round(current * 0.95, 2)
        tech_reason = "无明确支撑，当前价下方5%"

    # 第二层：阶段止损
    if stage == "蓄势":
        if support > 0 and atr14 > 0:
            stage_stop = round(max(0.01, support - 1.5 * atr14), 2)
            stage_reason = f"蓄势期保护本金，支撑 - 1.5×ATR"
        elif support > 0:
            stage_stop = round(support * 0.98, 2)
            stage_reason = f"蓄势区间下沿 {support:.2f}"
        else:
            stage_stop = round(current * 0.95, 2)
            stage_reason = "蓄势期保护本金"
    elif stage == "主升":
        if ma20 is not None and ma20 > 0:
            stage_stop = round(ma20 * 0.98, 2)  # MA20 附近
            stage_reason = f"主升期保护利润，MA20 {ma20:.2f}"
        else:
            stage_stop = round(current * 0.92, 2)
            stage_reason = "主升期保护利润"
    elif stage == "派发":
        if ma20 is not None and ma20 > 0:
            stage_stop = round(ma20 * 0.98, 2)  # MA20 下方锁定收益
            stage_reason = f"派发期锁定收益，MA20上方 {ma20:.2f}"
        else:
            stage_stop = round(current * 0.95, 2)
            stage_reason = "派发期锁定收益"
    else:  # 衰退
        stage_stop = 0.0  # 衰退阶段不设阶段止损，由技术止损兜底
        stage_reason = "衰退期技术止损兜底"

    # 第三层：时间止损
    if stage == "蓄势":
        time_days = 30
        time_reason = "蓄势期30天内不突破走人"
    elif stage == "主升":
        time_days = 15
        time_reason = "主升期15天内不创新高减仓"
    elif stage == "派发":
        time_days = 0
        time_reason = "派发期不建议买入"
    else:
        time_days = 0
        time_reason = "衰退期不持有"

    # 筹码驱动移动止损
    chip_trailing: dict[str, Any] | None = None
    if isinstance(chip_migration, dict) and chip_migration.get("has_history"):
        migration_pct = chip_migration.get("migration_pct", 0)
        warning_level = chip_migration.get("warning_level", "none")

        if warning_level == "critical":
            # 底部筹码峰搬家 > 50% → 清仓
            chip_trailing = {
                "price": 0.0,
                "reason": f"底部筹码搬家 {migration_pct:.0f}%，清仓信号",
                "action": "清仓",
            }
        elif warning_level == "warning":
            # 底部筹码峰松动 > 40% → 止损收紧到 MA20
            if ma20 is not None and ma20 > 0:
                chip_trailing = {
                    "price": round(ma20, 2),
                    "reason": f"筹码松动 {migration_pct:.0f}%，止损收紧到 MA20",
                    "action": "减仓",
                }
        else:
            # 底部筹码峰没松动 → 止损跟 MA10（如果有的话）
            # 这里返回 None，表示使用默认止损
            pass

    return {
        "technical": {"price": tech_stop, "reason": tech_reason},
        "stage_based": {"price": stage_stop, "reason": stage_reason},
        "time_limit": {"days": time_days, "reason": time_reason},
        "chip_trailing": chip_trailing,
    }


# ── 分批止盈计划 ──────────────────────────────────────────────

def compute_exit_plan(
    entry_price: float,
    stop_price: float,
    resistance_price: float | None,
    current_stage: str,
    bars: list[dict[str, Any]] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    atr14: float = 0.0,
) -> dict[str, Any]:
    """计算分批止盈计划（条件止盈，威科夫信号驱动）。

    三批退出：
      第一笔：BC 信号出现 → 卖 1/3（购买高潮，主力在出货）
      第二笔：1R 目标达到 → 卖 1/3（保本，锁定部分利润）
      第三笔：阶段转派发 或 筹码搬家 > 50% → 清仓（趋势变了）

    阻力位不再是"到了就卖"，而是"看信号决定"：
      - 大阳线突破 + 放量 → 继续持有
      - BC 信号 → 卖 1/3
      - UTAD 信号 → 立刻减仓

    Args:
        entry_price: 买入价
        stop_price: 止损价
        resistance_price: 最近阻力位（可选）
        current_stage: 当前阶段（蓄势/主升/派发/衰退）
        bars: K线数据（用于计算动态阻力位）
        wyckoff_result: 威科夫分析结果（包含 BC/UTAD 信号）
        atr14: 14日ATR值

    Returns:
        止盈计划字典
    """
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return {
            "risk_r": 0.0,
            "target_1r": 0.0,
            "resistance_exit": None,
            "stage_exit": current_stage,
            "exit_plan": [],
            "already_exited": [],
            "wyckoff_signals": {},
        }

    # 1R 计算
    risk_r = round(entry_price - stop_price, 2)
    target_1r = round(entry_price + risk_r, 2)

    # 阻力位退出价
    resistance_exit: float | None = None
    if resistance_price is not None and resistance_price > entry_price:
        resistance_exit = round(resistance_price, 2)
    elif bars and len(bars) >= 20:
        # 动态计算阻力位：近 20 日最高价
        highs = [float(b.get("high") or 0) for b in bars[-20:]]
        max_high = max(highs) if highs else 0
        if max_high > entry_price:
            resistance_exit = round(max_high, 2)

    # 1R 目标价不超过阻力位（阻力位卖出优先于 1R 保本）
    if resistance_exit is not None and resistance_exit > entry_price and target_1r > resistance_exit:
        target_1r = round(resistance_exit * 0.99, 2)

    # 阶段退出条件
    stage_exit = "派发"  # 主升转派发时清仓

    # 提取威科夫信号
    bc_signal = False
    bc_reason = ""
    utad_signal = False
    utad_reason = ""
    if isinstance(wyckoff_result, dict):
        wyk = wyckoff_result.get("wyckoff", wyckoff_result)
        if isinstance(wyk, dict):
            bc_signal = wyk.get("bc_signal", False)
            bc_reason = wyk.get("bc_reason", "")
            utad_signal = wyk.get("upthrust_signal", False)
            utad_reason = wyk.get("upthrust_reason", "")

    # 构建退出计划（条件止盈），确保总比例为1.0
    exit_plan: list[dict[str, Any]] = []
    has_resistance_exit = resistance_exit is not None and resistance_exit > entry_price

    # 根据是否有阻力位退出，动态分配比例
    if has_resistance_exit:
        # 四笔退出：各25%
        ratios = [0.25, 0.25, 0.25, 0.25]
    else:
        # 三笔退出：各1/3
        ratios = [0.33, 0.33, 0.34]

    # 第一笔：BC 信号（购买高潮）
    if bc_signal:
        exit_plan.append({
            "price": None,
            "ratio": ratios[0],
            "reason": "购买高潮（BC），减仓",
            "condition": "BC 信号出现",
            "triggered": True,
        })
    else:
        exit_plan.append({
            "price": None,
            "ratio": ratios[0],
            "reason": "等待 BC 信号",
            "condition": "BC 信号出现",
            "triggered": False,
        })

    # 第二笔：阻力位止盈（如果有效）
    if has_resistance_exit:
        exit_plan.append({
            "price": resistance_exit,
            "ratio": ratios[1],
            "reason": "阻力位",
            "condition": "触及阻力位",
            "triggered": False,
        })

    # 第三笔：1R 目标
    exit_plan.append({
        "price": target_1r,
        "ratio": ratios[2] if has_resistance_exit else ratios[1],
        "reason": "1R 目标，保本",
        "condition": "1R 达到",
        "triggered": False,
    })

    # 第四笔：阶段转派发
    exit_plan.append({
        "price": None,
        "ratio": ratios[3] if has_resistance_exit else ratios[2],
        "reason": "阶段转派发，清仓",
        "condition": "阶段转派发",
        "triggered": False,
    })

    # 突破跟进逻辑
    breakout_followup: dict[str, Any] | None = None
    if resistance_exit is not None and atr14 > 0:
        # 突破阻力位后的新止损和新目标
        new_stop = resistance_exit  # 旧阻力位 → 新支撑位
        # 新目标：下一个阻力位或 2R
        next_resistance = None
        if bars and len(bars) >= 40:
            all_highs = [float(b.get("high") or 0) for b in bars[-40:]]
            above_resistance = [h for h in all_highs if h > resistance_exit * 1.01]
            if above_resistance:
                next_resistance = round(min(above_resistance), 2)
        if next_resistance is None:
            next_resistance = round(entry_price + risk_r * 2, 2)

        breakout_followup = {
            "new_stop": round(new_stop, 2),
            "new_target": next_resistance,
            "add_on_pullback": True,
            "note": "突破阻力位后止损上移，回踩新支撑不破可加仓",
        }

    # UTAD 假突破信号
    utad_action: dict[str, Any] | None = None
    if utad_signal:
        utad_action = {
            "signal": "UTAD",
            "reason": utad_reason,
            "action": "立刻减仓",
            "note": "上冲回落假突破，止损下移回原支撑位",
        }

    return {
        "risk_r": risk_r,
        "target_1r": target_1r,
        "resistance_exit": resistance_exit,
        "stage_exit": stage_exit,
        "exit_plan": exit_plan,
        "already_exited": [False, False, False],
        "wyckoff_signals": {
            "bc_signal": bc_signal,
            "bc_reason": bc_reason,
            "utad_signal": utad_signal,
            "utad_reason": utad_reason,
        },
        "breakout_followup": breakout_followup,
        "utad_action": utad_action,
    }


def compute_stage_stop(
    stage: str,
    ma20: float | None,
    range_low: float | None = None,
    atr_pct: float = 0.02,
    expma20: float | None = None,
) -> dict[str, Any]:
    """根据阶段计算止损位。

    蓄势期：蓄势区间下沿（保护本金）
    主升期：MA20（保护利润）
    派发期：EXPMA(20) 上方（锁定收益）
    衰退期：不持有

    Args:
        stage: 当前阶段
        ma20: 20 日均线
        range_low: 蓄势区间下沿（可选）
        atr_pct: ATR 占比
        expma20: 20 日 EXPMA（可选，派发期优先使用）

    Returns:
        {"price": float, "reason": str}
    """
    if stage == "蓄势":
        if range_low is not None and range_low > 0:
            return {"price": round(range_low, 2), "reason": f"蓄势区间下沿 {range_low:.2f}"}
        if ma20 is not None and ma20 > 0:
            return {"price": round(ma20 * 0.95, 2), "reason": f"蓄势期保护本金，MA20下方5%"}
        return {"price": 0.0, "reason": "数据不足"}
    elif stage == "主升":
        if ma20 is not None and ma20 > 0:
            return {"price": round(ma20, 2), "reason": f"主升期保护利润，MA20 {ma20:.2f}"}
        return {"price": 0.0, "reason": "数据不足"}
    elif stage == "派发":
        # 派发期优先使用 EXPMA(20)，fallback 到 MA20
        ref_price = expma20 if (expma20 is not None and expma20 > 0) else ma20
        ref_name = "EXPMA(20)" if (expma20 is not None and expma20 > 0) else "MA20"
        if ref_price is not None and ref_price > 0:
            return {"price": round(ref_price * (1 + atr_pct * 0.5), 2), "reason": f"派发期锁定收益，{ref_name}上方"}
        return {"price": 0.0, "reason": "数据不足"}
    else:  # 衰退
        return {"price": 0.0, "reason": "衰退期不持有"}


def check_time_stop(
    entry_date: str | None,
    current_stage: str,
    days_held: int,
    made_new_high: bool,
    has_position: bool = True,
) -> dict[str, Any]:
    """检查时间止损。

    蓄势期买入：30 天不突破 → 走人
    主升期买入：15 天不创新高 → 减仓
    派发期买入：不建议

    Args:
        entry_date: 买入日期（YYYY-MM-DD）
        current_stage: 当前阶段
        days_held: 已持有天数
        made_new_high: 是否创新高
        has_position: 是否有持仓（空仓时不触发清仓）

    Returns:
        {"triggered": bool, "action": str, "days_left": int}
    """
    if not has_position:
        return {"triggered": False, "action": "空仓不触发时间止损", "days_left": 0}

    if current_stage == "蓄势":
        limit = ACCUMULATION_DAYS_LIMIT
        if days_held >= limit and not made_new_high:
            return {"triggered": True, "action": f"蓄势期{limit}天不突破，走人", "days_left": 0}
        return {"triggered": False, "action": "等待突破", "days_left": max(0, limit - days_held)}
    elif current_stage == "主升":
        limit = MARKUP_DAYS_LIMIT
        if days_held >= limit and not made_new_high:
            return {"triggered": True, "action": f"主升期{limit}天不创新高，减仓", "days_left": 0}
        return {"triggered": False, "action": "等待创新高", "days_left": max(0, limit - days_held)}
    elif current_stage == "派发":
        return {"triggered": False, "action": "派发期不建议买入", "days_left": 0}
    else:  # 衰退
        return {"triggered": True, "action": "衰退期清仓", "days_left": 0}


def compute_stop_summary(
    technical_stop: float,
    stage_stop: float,
    time_stop: dict[str, Any],
    current_price: float,
) -> dict[str, Any]:
    """汇总三层止损，取最近的作为最终止损。

    Args:
        technical_stop: 技术止损价
        stage_stop: 阶段止损价
        time_stop: 时间止损结果
        current_price: 当前价

    Returns:
        {"final_stop": float, "stops": dict, "time_stop": dict}
    """
    stops: dict[str, float] = {}
    if technical_stop > 0:
        stops["技术止损"] = technical_stop
    if stage_stop > 0:
        stops["阶段止损"] = stage_stop

    # 取最高的止损价（最近当前价的）
    final_stop = max(stops.values()) if stops else 0.0

    return {
        "final_stop": final_stop,
        "stops": stops,
        "time_stop": time_stop,
    }


# ── 五状态仓位管理状态机 ──────────────────────────────────────

# 状态定义
POSITION_STATES = {
    "空仓": 0,
    "初始建仓": 1,
    "阻力位分歧": 2,
    "回踩加仓": 3,
    "主升浪跟踪": 4,
    "退出再买": 5,
}

# 状态转移矩阵：(当前状态, 条件) → 下一状态
# 条件由 evaluate_position_state() 返回


def evaluate_position_state(
    current_price: float,
    support: float,
    resistance: float,
    stop_price: float,
    confirm_price: float,
    atr14: float,
    major_stage: str,
    momentum: str,
    bars: list[dict[str, Any]] | None = None,
    wyckoff_result: dict[str, Any] | None = None,
    holding_days: int = 0,
    has_position: bool = False,
    entry_price: float = 0.0,
    highest_close: float = 0.0,
    expma10: float | None = None,
    chip_migration: dict[str, Any] | None = None,
    high_zone_lower: float = 0.0,
    trailing_stop: float | None = None,
    last_add_date: str | None = None,
) -> dict[str, Any]:
    """五状态仓位管理状态机。

    状态流转：
      空仓 → 初始建仓（支撑位买 10%，止损支撑位-1.5×ATR）
      初始建仓 → 阻力位分歧（到达阻力位，弱→卖1/3，强→不卖）
      初始建仓 → 回踩加仓（回踩支撑位，条件满足加仓）
      阻力位分歧 → 回踩加仓（回踩后条件满足）
      回踩加仓 → 主升浪跟踪（筹码没搬家+EXPMA(10)上→拿着）
      主升浪跟踪 → 退出再买（跌破止损/阶段转衰退）
      退出再买 → 初始建仓（回到支撑位+止跌信号+阶段没变）

    Returns:
        {
            "state": str,               # 当前状态
            "state_code": int,          # 状态代码 0-5
            "action": str,              # 建议动作
            "position_pct": int,        # 建议仓位 %
            "stop_price": float,        # 止损价
            "take_profit_price": float, # 止盈价（条件止盈）
            "conditions": dict,         # 各条件检查结果
            "transition_reason": str,   # 状态转移原因
        }
    """
    # 基础检查
    if current_price <= 0:
        return _empty_position_state("空仓", "数据不足")

    # ATR 止损计算，确保止损价为正
    atr_stop = round(max(0.01, support - 1.5 * atr14), 2) if support > 0 and atr14 > 0 else round(current_price * 0.95, 2)

    # 提取威科夫信号
    bc_signal = False
    utad_signal = False
    sow_signal = False
    if isinstance(wyckoff_result, dict):
        wyk = wyckoff_result.get("wyckoff", wyckoff_result)
        if isinstance(wyk, dict):
            bc_signal = wyk.get("bc_signal", False)
            utad_signal = wyk.get("upthrust_signal", False)
            sow_signal = wyk.get("sow_signal", False)

    # 筹码搬家检查
    chip_warning = "none"
    if isinstance(chip_migration, dict):
        chip_warning = chip_migration.get("warning_level", "none")

    # 条件检查
    # 统一止损：取 hard_stop / atr_stop / trailing_stop 三者最高（只紧不松）
    effective_stop = max(
        stop_price if stop_price > 0 else 0,
        atr_stop if atr_stop > 0 else 0,
        trailing_stop if trailing_stop and trailing_stop > 0 else 0,
    )

    conditions = {
        "at_support": support > 0 and abs(current_price - support) / max(support, 1) < 0.03,
        "at_resistance": resistance > 0 and abs(current_price - resistance) / max(resistance, 1) < 0.03,
        "in_high_zone": high_zone_lower > 0 and high_zone_lower <= current_price <= resistance,
        "above_stop": stop_price <= 0 or current_price > stop_price,
        "above_atr_stop": current_price > atr_stop,
        "above_trailing_stop": trailing_stop is None or trailing_stop <= 0 or current_price > trailing_stop,
        "above_effective_stop": effective_stop <= 0 or current_price > effective_stop,
        "breakout_confirmed": confirm_price > 0 and current_price >= confirm_price,
        "pullback_to_support": support > 0 and current_price <= support * 1.02 and current_price >= support * 0.98,
        "chip_stable": chip_warning not in ("critical", "warning"),
        "expma10_up": expma10 is not None and current_price > expma10,
        "bc_signal": bc_signal,
        "utad_signal": utad_signal,
        "sow_signal": sow_signal,
        "stage_accumulation": major_stage == "蓄势",
        "stage_markup": major_stage == "主升",
        "stage_distribution": major_stage == "派发",
        "stage_decline": major_stage == "衰退",
        "momentum_strong": momentum in ("走强", "修复"),
        "momentum_weak": momentum in ("转弱",),
    }

    # 状态判定
    if not has_position:
        # 空仓状态
        if conditions["stage_decline"]:
            return _make_position_state("空仓", "衰退期不碰", 0, conditions)
        if conditions["at_support"] and conditions["momentum_strong"] and not conditions["stage_decline"]:
            return _make_position_state(
                "初始建仓", "到达支撑位+短期走强，试探买10%",
                10, conditions, stop_price=atr_stop,
            )
        return _make_position_state("空仓", "等待到达支撑位", 0, conditions)

    # 有持仓的状态流转
    # 检查统一止损（hard_stop / atr_stop / trailing_stop 取最高）
    if not conditions["above_effective_stop"]:
        return _make_position_state(
            "退出再买", "跌破止损，清仓等待",
            0, conditions, stop_price=0,
        )

    # 检查 UTAD / SOW / 筹码搬家 → 退出
    if conditions["utad_signal"] or conditions["sow_signal"] or chip_warning == "critical":
        reason = "UTAD上冲回落" if conditions["utad_signal"] else "SOW弱势信号" if conditions["sow_signal"] else "筹码搬家清仓"
        return _make_position_state(
            "退出再买", f"{reason}，清仓等待",
            0, conditions, stop_price=0,
        )

    # 衰退期 → 退出
    if conditions["stage_decline"]:
        return _make_position_state(
            "退出再买", "阶段转衰退，清仓",
            0, conditions, stop_price=0,
        )

    # 派发期 → 阻力位分歧（用多因子评分决定减仓力度）
    if conditions["stage_distribution"]:
        rally_score = _calc_rally_reduce_score(conditions, bars, current_price, resistance, atr14)
        if conditions["at_resistance"]:
            if bc_signal:
                return _make_position_state(
                    "阻力位分歧", "派发期+BC信号，减仓1/3",
                    0, conditions, stop_price=atr_stop,
                )
            if rally_score >= RALLY_REDUCE_FULL_SCORE:
                return _make_position_state(
                    "阻力位分歧", f"派发期+冲高条件充分（{rally_score}/5），减仓15%",
                    RALLY_REDUCE_POSITION_PCT, conditions, stop_price=atr_stop,
                )
            if rally_score >= RALLY_REDUCE_MIN_SCORE:
                return _make_position_state(
                    "阻力位分歧", f"派发期+冲高条件部分满足（{rally_score}/5），减仓10%",
                    RALLY_REDUCE_LITE_POSITION_PCT, conditions, stop_price=atr_stop,
                )
            return _make_position_state(
                "阻力位分歧", f"派发期到达阻力位（{rally_score}/5），观察是否突破",
                0, conditions, stop_price=atr_stop,
            )
        return _make_position_state(
            "阻力位分歧", "派发期，逢高减仓",
            0, conditions, stop_price=atr_stop,
        )

    # 主升浪跟踪
    if conditions["stage_markup"]:
        # 底仓止损：上移到阻力位（更宽的止损）
        base_stop = round(resistance * 0.98, 2) if resistance > 0 else atr_stop

        # 进入高抛区间时，用评分决定是否提前减仓
        if conditions["in_high_zone"]:
            rally_score = _calc_rally_reduce_score(conditions, bars, current_price, resistance, atr14)
            if rally_score >= RALLY_REDUCE_FULL_SCORE:
                return _make_position_state(
                    "阻力位分歧", f"主升期进入高抛区+冲高条件充分（{rally_score}/5），减仓15%",
                    RALLY_REDUCE_POSITION_PCT, conditions, stop_price=expma10 if expma10 else base_stop,
                )
            if rally_score >= RALLY_REDUCE_MIN_SCORE:
                return _make_position_state(
                    "阻力位分歧", f"主升期进入高抛区+冲高条件部分满足（{rally_score}/5），减仓10%",
                    RALLY_REDUCE_LITE_POSITION_PCT, conditions, stop_price=expma10 if expma10 else base_stop,
                )

        if conditions["chip_stable"] and conditions["expma10_up"]:
            return _make_position_state(
                "主升浪跟踪", "主升期+筹码稳定+EXPMA(10)支撑，持有",
                0, conditions, stop_price=expma10 if expma10 else base_stop,
            )
        if not conditions["chip_stable"]:
            return _make_position_state(
                "主升浪跟踪", "主升期但筹码松动，收紧止损",
                0, conditions, stop_price=atr_stop,
            )
        return _make_position_state(
            "主升浪跟踪", "主升期，持有观察",
            0, conditions, stop_price=base_stop,
        )

    # 回踩加仓（蓄势期+回踩支撑+条件满足）
    if conditions["stage_accumulation"] and conditions["pullback_to_support"]:
        # T+1 隔离锁：当天已加仓则冷却，不重复加仓
        today = datetime.now().strftime("%Y-%m-%d")
        if last_add_date is not None and last_add_date == today:
            return _make_position_state(
                "持仓观察", "T+1冷却，今日已加仓，等待明日再评估",
                0, conditions,
            )

        # 必要条件 + 加分条件评分
        add_score = _calc_pullback_add_score(
            conditions, bars, current_price, support, atr14,
        )
        
        # 加仓独立止损：设在回踩支撑位下方（比底仓止损更窄）
        # 使用 1.0×ATR 作为止损距离（可配置）
        _ADD_ON_STOP_ATR_MULTIPLE = 1.0
        add_on_stop = round(support - _ADD_ON_STOP_ATR_MULTIPLE * atr14, 2) if support > 0 and atr14 > 0 else round(current_price * 0.97, 2)
        
        if add_score >= 5:
            return _make_position_state(
                "回踩加仓", f"回踩支撑+条件满足（{add_score}/5），加仓15%",
                15, conditions, stop_price=add_on_stop, pullback_add_score=add_score,
            )
        if add_score >= 3:
            return _make_position_state(
                "回踩加仓", f"回踩支撑+部分条件满足（{add_score}/5），加仓10%",
                10, conditions, stop_price=add_on_stop, pullback_add_score=add_score,
            )
        return _make_position_state(
            "回踩加仓", f"回踩支撑但条件不足（{add_score}/5），观望",
            0, conditions, stop_price=add_on_stop, pullback_add_score=add_score,
        )

    # 阻力位分歧（到达阻力位，用多因子评分决定减仓力度）
    if conditions["at_resistance"]:
        rally_score = _calc_rally_reduce_score(conditions, bars, current_price, resistance, atr14)

        if bc_signal:
            return _make_position_state(
                "阻力位分歧", "到达阻力位+BC信号，减仓1/3",
                0, conditions, stop_price=atr_stop,
            )
        if conditions["breakout_confirmed"]:
            return _make_position_state(
                "阻力位分歧", "突破阻力位确认，继续持有",
                0, conditions, stop_price=atr_stop,
            )
        if rally_score >= RALLY_REDUCE_FULL_SCORE:
            return _make_position_state(
                "阻力位分歧", f"冲高条件充分（{rally_score}/5），减仓15%",
                RALLY_REDUCE_POSITION_PCT, conditions, stop_price=atr_stop,
            )
        if rally_score >= RALLY_REDUCE_MIN_SCORE:
            return _make_position_state(
                "阻力位分歧", f"冲高条件部分满足（{rally_score}/5），减仓10%",
                RALLY_REDUCE_LITE_POSITION_PCT, conditions, stop_price=atr_stop,
            )
        return _make_position_state(
            "阻力位分歧", f"到达阻力位（{rally_score}/5），观察量能",
            0, conditions, stop_price=atr_stop,
        )

    # 默认：持有观察
    return _make_position_state(
        "初始建仓", "持仓观察中",
        0, conditions, stop_price=atr_stop,
    )


def _calc_pullback_add_score(
    conditions: dict[str, bool],
    bars: list[dict[str, Any]] | None,
    current_price: float,
    support: float,
    atr14: float,
) -> int:
    """计算回踩加仓条件评分（满分5分）。

    必要条件（2分）：
      1. 到达支撑位附近（1分）
      2. 出现止跌信号（1分）

    加分条件（3分）：
      3. 缩量回踩（1分）
      4. RSI 超卖区反弹（1分）
      5. MACD 底背离或金叉（1分）
    """
    score = 0

    # 必要条件1：到达支撑位附近（1分）
    if support > 0 and abs(current_price - support) / max(support, 1) < 0.03:
        score += 1

    # 必要条件2：出现止跌信号（1分）— 价格企稳（近3天未创新低）
    if bars and len(bars) >= 3:
        recent_lows = [float(b.get("low") or 0) for b in bars[-3:]]
        if min(recent_lows) >= support * 0.98:
            score += 1

    # 加分条件3：缩量回踩（1分）
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        if earlier_vol > 0 and recent_vol < earlier_vol * 0.8:
            score += 1

    # 加分条件4：RSI 超卖区反弹（1分）
    if bars and len(bars) >= 14:
        closes = [float(b.get("close") or 0) for b in bars[-14:] if b.get("close")]
        if len(closes) >= 14:
            gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
            losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
            avg_gain = sum(gains) / len(gains) if gains else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            rs = avg_gain / max(avg_loss, 0.01)
            rsi = 100 - (100 / (1 + rs))
            if rsi < 40:
                score += 1

    # 加分条件5：MACD 金叉（1分）— 使用真正的 EMA
    if bars and len(bars) >= 26:
        from trader_shared.indicator_math import calc_expma
        closes = [float(b.get("close") or 0) for b in bars if b.get("close")]
        if len(closes) >= 26:
            ema12 = calc_expma(closes, 12)
            ema26 = calc_expma(closes, 26)
            if ema12 is not None and ema26 is not None and ema12 > ema26:
                score += 1

    return score


def _calc_reentry_score(
    conditions: dict[str, bool],
    bars: list[dict[str, Any]] | None,
    current_price: float,
    support: float,
    expma10: float | None,
) -> int:
    """计算退出再买条件评分（满分4分）。

    必要条件（1分）：
      1. 价格回到支撑位附近

    加分条件（3分）：
      2. 缩量止跌（1分）
      3. 价格站上 EXPMA(10)（1分）
      4. 阶段没变坏（1分）
    """
    score = 0
    
    # 必要条件：价格回到支撑位附近
    if support > 0 and abs(current_price - support) / max(support, 1) < 0.03:
        score += 1
    
    # 加分条件：缩量止跌
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        if earlier_vol > 0 and recent_vol < earlier_vol * 0.8:
            score += 1
    
    # 加分条件：价格站上 EXPMA(10)
    if expma10 and current_price > expma10:
        score += 1
    
    # 加分条件：阶段没变坏（不是衰退期）
    if not conditions.get("stage_decline", False):
        score += 1
    
    return score


def _calc_rally_reduce_score(
    conditions: dict[str, bool],
    bars: list[dict[str, Any]] | None,
    current_price: float,
    resistance: float,
    atr14: float,
) -> int:
    """计算冲高减仓条件评分（满分5分，对称 _calc_pullback_add_score）。

    必要条件（2分）：
      1. 接近阻力位（距阻力 < 3%）
      2. 创新高后回落（近5日高点 > 前期高点，且当前 < 高点×0.98）

    加分条件（3分）：
      3. 放量滞涨（近3日均量 > 7日均量×1.2 且涨幅 < 3%）
      4. RSI 超买（RSI14 > 70）
      5. MACD 死叉（EMA12 < EMA26）
    """
    from trader_shared.indicator_math import calc_expma

    score = 0

    # 必要条件1：接近阻力位（1分）
    if resistance > 0 and abs(current_price - resistance) / max(resistance, 1) < 0.03:
        score += 1

    # 必要条件2：创新高后回落（1分）
    if bars and len(bars) >= 10:
        highs = [float(b.get("high") or 0) for b in bars if float(b.get("high") or 0) > 0]
        recent_5_high = max(highs[-5:]) if len(highs) >= 5 else 0
        earlier_high = max(highs[:-5]) if len(highs) > 5 else 0
        if recent_5_high > earlier_high and earlier_high > 0:
            if current_price < recent_5_high * 0.98:
                score += 1

    # 加分条件3：放量滞涨（1分）— 量增但价不涨（允许下跌）
    if bars and len(bars) >= 10:
        recent_vol = sum(float(b.get("volume") or 0) for b in bars[-3:]) / 3
        earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
        recent_change = 0
        if len(bars) >= 4:
            prev_close = float(bars[-4].get("close") or 0)
            if prev_close > 0:
                recent_change = (current_price - prev_close) / prev_close
        if earlier_vol > 0 and recent_vol > earlier_vol * 1.2 and recent_change < 0.03:
            score += 1

    # 加分条件4：RSI 超买（1分）
    if bars and len(bars) >= 14:
        closes = [float(b.get("close") or 0) for b in bars[-14:] if b.get("close")]
        if len(closes) >= 14:
            gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
            losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
            avg_gain = sum(gains) / len(gains) if gains else 0
            avg_loss = sum(losses) / len(losses) if losses else 0
            rs = avg_gain / max(avg_loss, 0.01)
            rsi = 100 - (100 / (1 + rs))
            if rsi > 70:
                score += 1

    # 加分条件5：MACD 死叉（1分）— 使用真正的 EMA
    if bars and len(bars) >= 26:
        closes = [float(b.get("close") or 0) for b in bars if b.get("close")]
        if len(closes) >= 26:
            ema12 = calc_expma(closes, 12)
            ema26 = calc_expma(closes, 26)
            if ema12 is not None and ema26 is not None and ema12 < ema26:
                score += 1

    return score


def _assess_resistance_strength(
    bars: list[dict[str, Any]] | None,
    current_price: float,
    resistance: float,
) -> str:
    """评估阻力位强度。

    弱阻力（可以止盈）：
      - 连续2日缩量
      - 价格在阻力位附近震荡

    强阻力（等回踩加仓）：
      - 放量突破
      - 大阳线突破

    Returns:
        "weak" 或 "strong"
    """
    if not bars or len(bars) < 10 or resistance <= 0:
        return "strong"  # 默认认为强阻力
    
    recent3 = bars[-3:]
    
    # 检查是否缩量
    recent_vol = sum(float(b.get("volume") or 0) for b in recent3) / 3
    earlier_vol = sum(float(b.get("volume") or 0) for b in bars[-10:-3]) / 7
    is_low_volume = earlier_vol > 0 and recent_vol < earlier_vol * 0.8
    
    # 检查是否在阻力位附近震荡
    near_resistance = abs(current_price - resistance) / max(resistance, 1) < 0.02
    
    # 检查是否有大阳线突破（含涨停板特殊处理）
    has_big_green = False
    has_limit_up = False
    for bar in recent3:
        open_p = float(bar.get("open") or 0)
        close_p = float(bar.get("close") or 0)
        high_p = float(bar.get("high") or 0)
        if open_p > 0 and close_p > open_p * 1.03:  # 涨幅 > 3%
            has_big_green = True
        # 涨停板判断：收盘价 = 最高价，且涨幅 > 9%
        if open_p > 0 and close_p == high_p and close_p > open_p * 1.09:
            has_limit_up = True
    
    # 弱阻力：缩量 + 在阻力位附近震荡 + 没有大阳线突破 + 没有涨停板
    if is_low_volume and near_resistance and not has_big_green and not has_limit_up:
        return "weak"
    
    return "strong"
def _make_position_state(
    state: str,
    reason: str,
    position_pct: int,
    conditions: dict[str, bool],
    stop_price: float = 0.0,
    take_profit_price: float = 0.0,
    pullback_add_score: int = 0,
) -> dict[str, Any]:
    """构建状态机返回值。"""
    return {
        "state": state,
        "state_code": POSITION_STATES.get(state, 0),
        "action": reason,
        "position_pct": position_pct,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "conditions": conditions,
        "transition_reason": reason,
        "pullback_add_score": pullback_add_score,
    }


def _empty_position_state(state: str, reason: str) -> dict[str, Any]:
    """空状态返回值。"""
    return {
        "state": state,
        "state_code": POSITION_STATES.get(state, 0),
        "action": reason,
        "position_pct": 0,
        "stop_price": 0.0,
        "take_profit_price": 0.0,
        "conditions": {},
        "transition_reason": reason,
    }


# ── 条件止盈（威科夫信号驱动）──────────────────────────────────

def compute_conditional_take_profit(
    current_price: float,
    entry_price: float,
    stop_price: float,
    resistance_price: float,
    major_stage: str,
    wyckoff_result: dict[str, Any] | None = None,
    bars: list[dict[str, Any]] | None = None,
    atr14: float = 0.0,
) -> dict[str, Any]:
    """条件止盈（威科夫信号驱动，不是机械止盈）。

    三批退出：
      第一笔：BC 信号出现 → 卖 1/3（购买高潮，主力在出货）
      第二笔：1R 目标达到 → 卖 1/3（保本，锁定部分利润）
      第三笔：阶段转派发 或 筹码搬家 > 50% → 清仓（趋势变了）

    阻力位不再是"到了就卖"，而是"看信号决定"：
      - 大阳线突破 + 放量 → 继续持有
      - BC 信号 → 卖 1/3
      - UTAD 信号 → 立刻减仓
    """
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return {
            "risk_r": 0.0,
            "target_1r": 0.0,
            "exit_plan": [],
            "wyckoff_signals": {},
        }

    # 1R 计算
    risk_r = round(entry_price - stop_price, 2)
    target_1r = round(entry_price + risk_r, 2)

    # 提取威科夫信号
    bc_signal = False
    bc_reason = ""
    utad_signal = False
    utad_reason = ""
    if isinstance(wyckoff_result, dict):
        wyk = wyckoff_result.get("wyckoff", wyckoff_result)
        if isinstance(wyk, dict):
            bc_signal = wyk.get("bc_signal", False)
            bc_reason = wyk.get("bc_reason", "")
            utad_signal = wyk.get("upthrust_signal", False)
            utad_reason = wyk.get("upthrust_reason", "")

    # 构建三批退出计划
    exit_plan: list[dict[str, Any]] = []

    # 第一笔：BC 信号 → 卖 1/3
    if bc_signal:
        exit_plan.append({
            "price": None,
            "ratio": 0.33,
            "reason": "购买高潮（BC），减仓1/3",
            "condition": "BC 信号出现",
            "triggered": True,
        })
    else:
        exit_plan.append({
            "price": None,
            "ratio": 0.33,
            "reason": "等待 BC 信号",
            "condition": "BC 信号出现",
            "triggered": False,
        })

    # 第二笔：1R 目标
    exit_plan.append({
        "price": target_1r,
        "ratio": 0.33,
        "reason": "1R 目标，保本",
        "condition": "1R 达到",
        "triggered": current_price >= target_1r,
    })

    # 第三笔：阶段转派发
    exit_plan.append({
        "price": None,
        "ratio": 0.34,
        "reason": "阶段转派发，清仓",
        "condition": "阶段变化",
        "triggered": major_stage == "派发",
    })

    return {
        "risk_r": risk_r,
        "target_1r": target_1r,
        "exit_plan": exit_plan,
        "wyckoff_signals": {
            "bc_signal": bc_signal,
            "bc_reason": bc_reason,
            "utad_signal": utad_signal,
            "utad_reason": utad_reason,
        },
    }


# ── 止盈规则 ──────────────────────────────────────────────────

def compute_take_profit(
    stage: str,
    current: float,
    highest_close: float,
    atr_pct: float,
    market_env: str = "震荡市",
) -> dict[str, Any]:
    """止盈规则：不主动止盈，只在趋势反转时退出。

    移动止损（保护利润）:
      主升期不看止损，只看阶段
      阶段转派发后，移动止损生效
      移动止损 = 最高收盘价 × (1 - ATR% × 倍数)

    大盘环境决定参数:
      牛市: ATR×4.0，不主动止盈
      震荡市: ATR×3.0，阻力位减仓
      熊市: ATR×2.0，快止盈
    """
    # ATR 倍数根据大盘环境
    env_multipliers = {"牛市": 4.0, "震荡市": 3.0, "熊市": 2.0}
    mult = env_multipliers.get(market_env, 3.0)

    if stage == "主升":
        # 主升期不看止损，只看阶段
        trailing_stop = None
        action = "让利润跑，阶段转派发再减仓"
    elif stage == "派发":
        # 派发期移动止损生效
        trailing_stop = round(highest_close * (1 - atr_pct * mult), 2)
        action = f"移动止损 {trailing_stop:.2f}，跌破减仓"
    elif stage == "衰退":
        # 衰退期清仓
        trailing_stop = round(highest_close * (1 - atr_pct * 2.0), 2)
        action = "衰退期清仓"
    else:
        # 蓄势期用技术止损
        trailing_stop = None
        action = "蓄势期用技术止损"

    return {
        "trailing_stop": trailing_stop,
        "action": action,
        "atr_multiplier": mult,
        "market_env": market_env,
    }
