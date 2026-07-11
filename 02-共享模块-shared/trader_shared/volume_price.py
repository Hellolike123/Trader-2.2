#!/usr/bin/env python3
"""量价背离检测模块 (Volume-Price Divergence Detection)

检测放量滞涨、天量天价等量价背离信号。

用法:
    from volume_price import detect_volume_divergence, VolumeWarning

    warning = detect_volume_divergence(bars)
    print(warning.warning_type)  # "stagnation" | "climactic" | "none"
    print(warning.signal)        # -1=看空, 0=无信号
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# 开盘/尾盘噪音时段（HHMM 格式，左闭右闭）
_OPEN_NOISE_START = 930   # 09:30
_OPEN_NOISE_END = 945     # 09:45
_CLOSE_NOISE_START = 1445 # 14:45
_CLOSE_NOISE_END = 1500   # 15:00


@dataclass
class VolumeWarning:
    """量价快照 / 背离警告（始终应有量比与近3日涨跌）。"""
    warning_type: str = "none"      # "stagnation" | "climactic" | "none" | "follow" | "shrink"
    signal: int = 0                 # -1=看空, 0=中性, +1=偏多
    confidence: float = 0.0         # 0-1
    volume_ratio: float = 0.0       # 近5日均量 / 前5日均量
    price_change: float = 0.0       # 近3日涨跌幅%
    reason: str = ""                # 人类可读描述
    vol_label: str = ""             # 放量|缩量|平量


def _safe_float(val: Any) -> float:
    """安全转换为 float，避免重复的 str().replace() 调用。"""
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _parse_hhmm(bar: Dict[str, Any]) -> int | None:
    """从 bar 的 time 字段提取 HHMM 整数（如 930、1445）。

    支持格式: "YYYY-MM-DD HH:MM", "HH:MM:SS", "HH:MM"。
    解析失败返回 None。
    """
    raw = bar.get("time") or bar.get("date") or ""
    raw = str(raw).strip()
    if not raw:
        return None
    # "YYYY-MM-DD HH:MM" 或 "YYYY-MM-DD HH:MM:SS"
    if " " in raw:
        raw = raw.split(" ", 1)[1]
    # 现在 raw 应该是 "HH:MM" 或 "HH:MM:SS"
    parts = raw.split(":")
    if len(parts) < 2:
        return None
    try:
        hh = int(parts[0])
        mm = int(parts[1])
        return hh * 100 + mm
    except (ValueError, TypeError):
        return None


def _is_noise_window(hhmm: int) -> bool:
    """判断 HHMM 是否在开盘或尾盘噪音窗口内。"""
    return (_OPEN_NOISE_START <= hhmm <= _OPEN_NOISE_END
            or _CLOSE_NOISE_START <= hhmm <= _CLOSE_NOISE_END)


def calc_weighted_volume(bars_5m: List[Dict[str, Any]]) -> float:
    """基于 5 分钟 K线计算排除开盘/尾盘噪音后的加权均量。

    1. 排除 9:30-9:45（开盘15分钟）和 14:45-15:00（尾盘15分钟）的 bar。
    2. 对剩余 bar 按 amount/volume 计算成交额加权均量（VWAP 模型）。
       若 amount 不可用，则退化为简单均量。
    3. 数据不足（<3 根有效 bar）时返回 0.0。

    Args:
        bars_5m: 5分钟 K线数据列表，每根需含 volume 和 time 字段。

    Returns:
        加权均量（float），可用于替代日线成交量做放量判断。
    """
    if not bars_5m:
        return 0.0

    filtered: list[tuple[float, float]] = []  # (volume, amount) pairs
    for bar in bars_5m:
        hhmm = _parse_hhmm(bar)
        if hhmm is not None and _is_noise_window(hhmm):
            continue
        vol = _safe_float(bar.get("volume", 0))
        if vol <= 0:
            continue
        amt = _safe_float(bar.get("amount", 0))
        filtered.append((vol, amt))

    if len(filtered) < 3:
        return 0.0

    total_vol = sum(v for v, _ in filtered)
    total_amt = sum(a for _, a in filtered)

    # 有成交额时用 VWAP 模型：加权均量 = total_amount / total_volume
    # 含义：平均每手（或每单位成交量）的成交额，反映真实交易活跃度
    if total_amt > 0 and total_vol > 0:
        return total_amt / total_vol

    # 退化：简单均量
    return total_vol / len(filtered)


def _calc_volume_ratio(bars: List[Dict[str, Any]], window: int = 5) -> float:
    """计算量比（近N日均量 / 前N日均量）。

    注意：bars 从老到新遍历，前 window 根实为「前N日」，后 window 根为「近N日」。
    变量命名以时间顺序为准（older=前段、newer=近段），return 为 newer/older。
    """
    if len(bars) < 2 * window:
        return 1.0

    older_sum = 0.0
    older_count = 0
    newer_sum = 0.0
    newer_count = 0

    for b in bars[-2 * window:]:
        v = _safe_float(b.get("volume", 0))
        if v <= 0:
            continue
        if older_count < window:
            older_sum += v
            older_count += 1
        else:
            newer_sum += v
            newer_count += 1

    if older_count == 0 or newer_count == 0:
        return 1.0

    avg_older = older_sum / older_count
    avg_newer = newer_sum / newer_count

    return avg_newer / avg_older if avg_older > 0 else 1.0


def _calc_price_change(bars: List[Dict[str, Any]], days: int = 3) -> float:
    """计算近N日涨跌幅。"""
    if len(bars) < days + 1:
        return 0.0

    current = _safe_float(bars[-1].get("close", 0))
    prev = _safe_float(bars[-1 - days].get("close", 0))

    return (current - prev) / prev if prev > 0 else 0.0


def _has_upper_shadow(bar: Dict[str, Any], threshold: float = 0.3) -> bool:
    """检查是否有长上影线（上影线占实体比例 > threshold）。"""
    high = _safe_float(bar.get("high", 0))
    low = _safe_float(bar.get("low", 0))
    close = _safe_float(bar.get("close", 0))
    open_ = _safe_float(bar.get("open", 0))

    if high == low or high == 0:
        return False

    body_top = max(open_, close)
    upper_shadow = high - body_top
    body = abs(close - open_)

    if body < 1e-10:
        return upper_shadow / (high - low) > threshold

    return upper_shadow / body > threshold


def _vol_label(vol_ratio: float) -> str:
    if vol_ratio >= 1.5:
        return "放量"
    if vol_ratio <= 0.7:
        return "缩量"
    return "平量"


def detect_volume_divergence(
    bars: List[Dict[str, Any]],
    vol_ratio_threshold: float = 1.5,
    price_change_threshold: float = 0.01,
    climactic_threshold: float = 3.0,
) -> VolumeWarning:
    """量价快照 + 背离/配合检测（始终返回量比与近3日涨跌）。

    强信号:
    1. 放量滞涨: 量比 > 1.5 但价格涨幅 < 1%（或上影）
    2. 天量天价: 量比 > 3.0 且股价创新高
    弱配合（无背离时仍给出可读结论）:
    3. 放量跟涨 / 放量下跌 / 缩量上涨乏力 / 缩量下跌 / 平量
    """
    if len(bars) < 10:
        return VolumeWarning(reason="数据不足，需要至少10根K线", vol_label="")

    vol_ratio = _calc_volume_ratio(bars)
    price_change = _calc_price_change(bars, days=3)
    vr = round(vol_ratio, 2)
    pc_pct = round(price_change * 100, 2)
    label = _vol_label(vol_ratio)

    # 检查近3天是否有上影线
    recent_upper_shadow = any(
        _has_upper_shadow(bars[i]) for i in range(-3, 0)
    )

    # 检查是否创新高（近20日）
    recent_highs = [_safe_float(b.get("high", 0)) for b in bars[-20:]]
    recent_highs = [h for h in recent_highs if h > 0]
    if len(recent_highs) < 2:
        return VolumeWarning(
            volume_ratio=vr,
            price_change=pc_pct,
            vol_label=label,
            reason=f"{label}（量比{vr:.1f}），高低点数据不足",
        )
    current_high = recent_highs[-1]
    max_recent_high = max(recent_highs[:-1])
    is_new_high = current_high > max_recent_high

    # 天量天价检测
    if vol_ratio >= climactic_threshold and is_new_high and price_change > 0:
        return VolumeWarning(
            warning_type="climactic",
            signal=-1,
            confidence=0.7,
            volume_ratio=vr,
            price_change=pc_pct,
            vol_label=label,
            reason=f"天量天价（量比{vr:.1f}，近3日{pc_pct:+.1f}%创新高），注意见顶",
        )

    # 放量滞涨 / 放量弱涨
    if vol_ratio >= vol_ratio_threshold:
        if abs(price_change) < price_change_threshold or recent_upper_shadow:
            if price_change >= 0:
                return VolumeWarning(
                    warning_type="stagnation",
                    signal=-1,
                    confidence=0.5,
                    volume_ratio=vr,
                    price_change=pc_pct,
                    vol_label=label,
                    reason=f"放量滞涨（量比{vr:.1f}，近3日{pc_pct:+.1f}%），上涨乏力",
                )
            return VolumeWarning(
                warning_type="stagnation",
                signal=-1,
                confidence=0.4,
                volume_ratio=vr,
                price_change=pc_pct,
                vol_label=label,
                reason=f"放量下跌（量比{vr:.1f}，近3日{pc_pct:+.1f}%），注意风险",
            )
        # 放量且有明显涨跌：配合
        if price_change >= price_change_threshold:
            return VolumeWarning(
                warning_type="follow",
                signal=1,
                confidence=0.35,
                volume_ratio=vr,
                price_change=pc_pct,
                vol_label=label,
                reason=f"放量跟涨（量比{vr:.1f}，近3日{pc_pct:+.1f}%）",
            )
        if price_change <= -price_change_threshold:
            return VolumeWarning(
                warning_type="follow",
                signal=-1,
                confidence=0.4,
                volume_ratio=vr,
                price_change=pc_pct,
                vol_label=label,
                reason=f"放量下跌（量比{vr:.1f}，近3日{pc_pct:+.1f}%）",
            )

    # 缩量配合
    if vol_ratio <= 0.7:
        if price_change >= price_change_threshold:
            return VolumeWarning(
                warning_type="shrink",
                signal=-1,
                confidence=0.3,
                volume_ratio=vr,
                price_change=pc_pct,
                vol_label=label,
                reason=f"缩量上涨（量比{vr:.1f}，近3日{pc_pct:+.1f}%），上攻偏弱",
            )
        if price_change <= -price_change_threshold:
            return VolumeWarning(
                warning_type="shrink",
                signal=0,
                confidence=0.25,
                volume_ratio=vr,
                price_change=pc_pct,
                vol_label=label,
                reason=f"缩量下跌（量比{vr:.1f}，近3日{pc_pct:+.1f}%），抛压减轻中",
            )
        return VolumeWarning(
            warning_type="none",
            signal=0,
            confidence=0.2,
            volume_ratio=vr,
            price_change=pc_pct,
            vol_label=label,
            reason=f"缩量整理（量比{vr:.1f}，近3日{pc_pct:+.1f}%）",
        )

    # 平量默认：仍带数字，便于报告展示
    return VolumeWarning(
        warning_type="none",
        signal=0,
        confidence=0.2,
        volume_ratio=vr,
        price_change=pc_pct,
        vol_label=label,
        reason=f"平量（量比{vr:.1f}，近3日{pc_pct:+.1f}%）",
    )


def volume_snapshot_dict(warning: VolumeWarning) -> dict:
    """始终可序列化的价量快照（供 VPF / fusion，含无警告情况）。"""
    return {
        "warning_type": warning.warning_type or "none",
        "signal": int(warning.signal or 0),
        "direction": int(warning.signal or 0),
        "confidence": float(warning.confidence or 0.0),
        "volume_ratio": float(warning.volume_ratio or 0.0),
        "price_change": float(warning.price_change or 0.0),
        "vol_label": warning.vol_label or _vol_label(float(warning.volume_ratio or 1.0)),
        "reason": warning.reason or "量价数据不足",
        "raw_key": "volume_price",
    }


def volume_warning_to_signal(warning: VolumeWarning) -> dict:
    """将 VolumeWarning 转换为融合层信号格式。"""
    return volume_snapshot_dict(warning)
