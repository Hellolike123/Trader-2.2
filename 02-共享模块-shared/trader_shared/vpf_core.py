"""价量资金专家 (Volume-Price-Fund, VPF)。

短线融合第三席：替代日线威科夫投票。
  - 价量：volume_price 背离/天量（日K，通常可得）+ 近5日量价趋势
  - 资金：fund_flow 特征（多源；缺失则降级，禁止 K 线假资金进方向）

返回与 fusion 统一的 signal 字典：
  {direction, confidence, reason, raw_key="vpf", ...}
"""

from __future__ import annotations

from typing import Any

from trader_shared.signal_schema import SignalTier, vpf_tier_from_reason


def _clip_conf(x: float) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


def _as_int_dir(v: Any) -> int:
    try:
        d = int(v)
    except (TypeError, ValueError):
        return 0
    if d > 0:
        return 1
    if d < 0:
        return -1
    return 0


def _calc_vp_trend(bars: list[dict] | None) -> dict[str, Any]:
    """计算近5日量价趋势分，作为单日价量信号的补充。

    Returns:
        {trend_direction, trend_conf, consistency, vol_slope}
        bars 不足5根时返回全零中性。
    """
    _empty = {
        "trend_direction": 0,
        "trend_conf": 0.0,
        "consistency": 0.0,
        "vol_slope": 0.0,
    }
    if not bars or len(bars) < 5:
        return _empty

    try:
        # 取近6根K线（第1根用于算第2根的变化量）
        window = bars[-6:] if len(bars) >= 6 else bars
        closes = []
        volumes = []
        for b in window:
            c = b.get("close") if isinstance(b, dict) else getattr(b, "close", None)
            v = b.get("volume") if isinstance(b, dict) else getattr(b, "volume", None)
            if c is None or v is None:
                return _empty
            closes.append(float(str(c).replace(",", "")))
            volumes.append(float(str(v).replace(",", "")))

        if len(closes) < 5 or any(c <= 0 for c in closes) or any(v <= 0 for v in volumes):
            return _empty

        # 每日量价变化（近5根K线，用前一根作为基准）
        n = len(closes) - 1  # 有效天数
        vol_ratios = []  # 量能趋势：每日量 / 前一日量
        price_dirs = []  # 价格方向
        vol_dirs = []    # 量能方向
        for i in range(1, len(closes)):
            p_dir = 1 if closes[i] > closes[i - 1] else (-1 if closes[i] < closes[i - 1] else 0)
            vr = volumes[i] / volumes[i - 1] if volumes[i - 1] > 0 else 1.0
            v_dir = 1 if vr > 1.1 else (-1 if vr < 0.9 else 0)
            price_dirs.append(p_dir)
            vol_dirs.append(v_dir)
            vol_ratios.append(vr)

        # 量价一致性：价格方向与量能方向相同的天数占比
        match_count = sum(1 for p, v in zip(price_dirs, vol_dirs) if p != 0 and v != 0 and p == v)
        total_trend_days = sum(1 for p, v in zip(price_dirs, vol_dirs) if p != 0 and v != 0)
        consistency = match_count / total_trend_days if total_trend_days > 0 else 0.0

        # 量能趋势斜率：(近3日均量比 - 前2日均量比) / 前2日均量比
        if len(vol_ratios) >= 5:
            avg_last3 = sum(vol_ratios[-3:]) / 3
            avg_first2 = sum(vol_ratios[:2]) / 2
            vol_slope = (avg_last3 - avg_first2) / avg_first2 if avg_first2 > 0 else 0.0
        else:
            avg_all = sum(vol_ratios) / len(vol_ratios)
            vol_slope = (vol_ratios[-1] - avg_all) / avg_all if avg_all > 0 else 0.0

        # 综合价格方向：近5日收盘价整体方向
        overall_dir = 1 if closes[-1] > closes[0] else (-1 if closes[-1] < closes[0] else 0)

        # 趋势方向与置信度
        trend_direction = 0
        trend_conf = 0.0
        if consistency >= 0.8 and vol_slope > 0.1:
            # 量价同向放量：趋势方向跟价格方向
            trend_direction = overall_dir
            # 一致性越高 + 量能趋势越陡 → 置信度越高
            trend_conf = min(0.5, 0.3 + consistency * 0.1 + min(vol_slope, 0.5) * 0.2)
        elif consistency >= 0.6 and vol_slope > 0.05:
            # 弱同向：给低置信
            trend_direction = overall_dir
            trend_conf = min(0.3, 0.2 + consistency * 0.05)

        return {
            "trend_direction": trend_direction,
            "trend_conf": round(trend_conf, 3),
            "consistency": round(consistency, 3),
            "vol_slope": round(vol_slope, 3),
        }
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return _empty


def build_vpf_signal(
    volume_warning: dict[str, Any] | None = None,
    fund_features: dict[str, Any] | None = None,
    *,
    fund_source: str | None = None,
    bars: list[dict] | None = None,
    avg_daily_turnover_wan: float | None = None,
) -> dict[str, Any]:
    """合成价量资金专家票。

    Args:
        volume_warning: detect_volume_divergence 结果或 volume_warning_to_signal 风格 dict
        fund_features: calc_fund_flow_features 结果
        fund_source: 可选标注 sina|akshare|tdx|tushare|missing
        bars: 日K线数据（用于近5日量价趋势分计算）
        avg_daily_turnover_wan: 近20日均成交额（万元），用于资金强度比归一化

    规则（简）:
      - 资金连出强空优先；价量天量/滞涨偏空
      - 资金连入 + 价量无警告 → 偏多弱确认
      - 资金缺失 → 仅价量，置信打折；reason 标明
      - 禁止把 K 线假资金当 full quality
      - 累计资金用强度比（相对均成交额）而非绝对值
      - 价量子票叠加近5日量价趋势分
    """
    vw = volume_warning if isinstance(volume_warning, dict) else {}
    ff = fund_features if isinstance(fund_features, dict) else {}

    # ── 价量子票（始终尽量带量比/涨跌文案）──
    vp_dir = 0
    vp_conf = 0.0
    vp_reason = ""
    wtype = str(vw.get("warning_type") or "none")
    try:
        vol_ratio = float(vw.get("volume_ratio") or 0)
    except (TypeError, ValueError):
        vol_ratio = 0.0
    try:
        price_chg = float(vw.get("price_change") or 0)
    except (TypeError, ValueError):
        price_chg = 0.0
    vol_label = str(vw.get("vol_label") or "")
    if not vol_label and vol_ratio > 0:
        vol_label = "放量" if vol_ratio >= 1.5 else ("缩量" if vol_ratio <= 0.7 else "平量")

    sig = vw.get("signal")
    if sig is None:
        sig = vw.get("direction")
    vp_dir = _as_int_dir(sig)
    vp_conf = _clip_conf(vw.get("confidence") or 0.0)
    vp_reason = str(vw.get("reason") or "").strip()

    if wtype == "climactic" and vp_dir == 0:
        vp_dir, vp_conf = -1, max(vp_conf, 0.7)
        vp_reason = vp_reason or "天量天价"
    elif wtype == "stagnation" and vp_dir == 0:
        vp_dir, vp_conf = -1, max(vp_conf, 0.5)
        vp_reason = vp_reason or "放量滞涨"
    elif not vp_reason:
        if vol_ratio > 0:
            vp_reason = f"{vol_label or '量价'}（量比{vol_ratio:.1f}，近3日{price_chg:+.1f}%）"
        else:
            vp_reason = "量价数据不足"
    # 有量比但 reason 太干：补数字
    if vol_ratio > 0 and "量比" not in vp_reason and "数据不足" not in vp_reason:
        vp_reason = f"{vp_reason}（量比{vol_ratio:.1f}，近3日{price_chg:+.1f}%）"

    # ── 价量趋势分（近5日量价一致性补充）──
    _vp_trend = _calc_vp_trend(bars)
    _trend_dir = _vp_trend.get("trend_direction", 0)
    _trend_conf = _vp_trend.get("trend_conf", 0.0)
    _consistency = _vp_trend.get("consistency", 0.0)
    if wtype == "none" and _trend_dir != 0 and _consistency >= 0.8:
        # 单日无警告但5日量价同向放量 → 用趋势分替代
        vp_dir = _trend_dir
        vp_conf = max(vp_conf, _trend_conf)
        _slope = _vp_trend.get("vol_slope", 0)
        vp_reason = f"近5日量价同向（一致性{_consistency:.0%}，量能趋势{_slope:+.1%}）"
    elif wtype != "none" and _trend_conf > 0:
        # 单日有警告 + 趋势分存在 → conf 加成（+0.1封顶）
        vp_conf = min(1.0, vp_conf + min(_trend_conf, 0.1))

    # ── 资金子票 ──
    fund_dir = 0
    fund_conf = 0.0
    fund_reason = ""
    fund_quality = "missing"

    daily_5d = ff.get("daily_flow_5d") if isinstance(ff.get("daily_flow_5d"), list) else []
    con_out = int(ff.get("consecutive_outflow_days") or 0)
    con_in = int(ff.get("consecutive_inflow_days") or 0)
    cum5 = ff.get("cum_flow_5d_wan")
    try:
        cum5_f = float(cum5) if cum5 is not None else 0.0
    except (TypeError, ValueError):
        cum5_f = 0.0

    has_fund_series = bool(daily_5d) or con_out > 0 or con_in > 0 or abs(cum5_f) > 1e-6
    # flow_price_relation == 无数据 且 全 0 → 仍算 missing
    if has_fund_series and str(ff.get("flow_price_relation") or "") == "无数据" and not daily_5d:
        has_fund_series = False

    if has_fund_series:
        fund_quality = "full"

        # 资金时效性检查：latest_fund_date 超过 5 日（含周末）则降级
        _fund_date = str(ff.get("latest_fund_date") or "")
        if _fund_date:
            try:
                from datetime import datetime
                from trader_shared.cn_time import today_cn
                _fd = datetime.strptime(_fund_date, "%Y-%m-%d").date()
                if (today_cn() - _fd).days > 5:
                    fund_quality = "stale"
            except (ValueError, ImportError):
                pass

        src = fund_source or ff.get("source") or "fund_flow"
        if con_out >= 3:
            fund_dir = -1
            fund_conf = 0.75
            fund_reason = f"连{con_out}日净出"
            if abs(cum5_f) >= 100:
                fund_reason += f"（5日合计{cum5_f:.0f}万）"
        elif con_out >= 2:
            fund_dir = -1
            fund_conf = 0.55
            fund_reason = f"连{con_out}日净出"
            if abs(cum5_f) >= 100:
                fund_reason += f"（5日合计{cum5_f:.0f}万）"
        elif con_in >= 3:
            fund_dir = 1
            fund_conf = 0.75
            fund_reason = f"连{con_in}日净进"
            if abs(cum5_f) >= 100:
                fund_reason += f"（5日合计{cum5_f:.0f}万）"
        elif con_in >= 2:
            fund_dir = 1
            fund_conf = 0.55
            fund_reason = f"连{con_in}日净进"
            if abs(cum5_f) >= 100:
                fund_reason += f"（5日合计{cum5_f:.0f}万）"
        elif cum5_f <= -500:
            # 资金强度比归一化：相对均成交额判断信号强度
            fund_dir = -1
            if avg_daily_turnover_wan and avg_daily_turnover_wan > 0:
                _strength = abs(cum5_f) / avg_daily_turnover_wan  # 5日累计占均成交额比
                if _strength >= 0.01:
                    fund_conf = 0.55  # 强信号：5日累计 >= 均成交额1%
                elif _strength >= 0.003:
                    fund_conf = 0.40   # 中信号
                else:
                    fund_conf = 0.25  # 弱信号：相对市值太小
                fund_reason = f"5日净出{cum5_f:.0f}万（占比{_strength:.2%}）"
            else:
                fund_conf = 0.4
                fund_reason = f"5日净出{cum5_f:.0f}万"
        elif cum5_f >= 500:
            fund_dir = 1
            if avg_daily_turnover_wan and avg_daily_turnover_wan > 0:
                _strength = abs(cum5_f) / avg_daily_turnover_wan
                if _strength >= 0.01:
                    fund_conf = 0.55  # 强信号：对称处理
                elif _strength >= 0.003:
                    fund_conf = 0.40
                else:
                    fund_conf = 0.15
                fund_reason = f"5日净进{cum5_f:.0f}万（占比{_strength:.2%}）"
            else:
                fund_conf = 0.35
                fund_reason = f"5日净进{cum5_f:.0f}万"
        else:
            fund_dir = 0
            fund_conf = 0.25
            fund_reason = "资金中性"
        if src and src != "missing":
            pass  # reason 不强制塞源，report 可读 quality
    else:
        fund_quality = "missing"
        fund_dir = 0
        fund_conf = 0.0
        fund_reason = "资金数据不足"

    # 资金时效性降级：数据超过 5 天视为"stale"，与 "missing" 同等处理
    if fund_quality == "stale":
        fund_dir = 0
        fund_conf = 0.0
        fund_reason = "资金数据过期"
        fund_quality = "missing"

    # ── 合成（多空对称）──
    # 资金强信号（conf>=0.55）优先，多空同权
    if fund_quality == "full" and fund_conf >= 0.55:
        direction = fund_dir
        confidence = max(fund_conf, vp_conf * 0.5)
        parts = [fund_reason]
        if vp_dir == fund_dir and vp_reason:
            parts.append(vp_reason)
        elif vp_dir != 0 and vp_dir != fund_dir:
            parts.append(f"价量{vp_reason or '分歧'}")
        reason = "；".join(parts)
    elif fund_quality == "full" and fund_dir != 0:
        # 资金中等信号 + 价量同向 → 合成；分歧 → 价量优先
        if fund_dir == vp_dir:
            direction = fund_dir
            confidence = _clip_conf((fund_conf + vp_conf) * 0.5)
            parts = [fund_reason]
            if vp_reason:
                parts.append(vp_reason)
            reason = "；".join(parts)
        elif vp_dir != 0:
            # 分歧取高置信度方
            if vp_conf >= fund_conf:
                direction = vp_dir
                confidence = _clip_conf(vp_conf)
                reason = vp_reason or "价量信号"
            else:
                direction = fund_dir
                confidence = _clip_conf(fund_conf)
                reason = fund_reason
        else:
            direction = fund_dir
            confidence = _clip_conf(fund_conf * 0.8)
            reason = f"{fund_reason}·量价中性"
    elif fund_quality == "missing":
        # 仅价量，打折；reason 仍用价量快照（含量比），并标明资金未取到
        base = vp_reason or ("价量中性" if vp_dir == 0 else "价量信号")
        if "资金" not in base:
            base = f"{base}（资金未取到）"
        if vp_dir != 0:
            direction = vp_dir
            confidence = _clip_conf(max(vp_conf * 0.7, 0.15))
            reason = base
        else:
            direction = 0
            confidence = max(_clip_conf(vp_conf), 0.2) if vol_ratio > 0 else 0.2
            reason = base
    else:
        # 资金中性，听价量
        if vp_dir != 0:
            direction = vp_dir
            confidence = _clip_conf(max(vp_conf, 0.35))
            reason = vp_reason or ("价量偏空" if vp_dir < 0 else "价量偏多")
        else:
            direction = 0
            confidence = 0.25
            reason = "价量资金中性"

    return {
        "direction": int(direction),
        "confidence": round(_clip_conf(confidence), 3),
        "reason": reason or "价量资金中性",
        "raw_key": "vpf",
        "signal_tier": vpf_tier_from_reason(reason),
        "fund_quality": fund_quality,
        "vp_direction": int(vp_dir),
        "fund_direction": int(fund_dir),
        "warning_type": wtype,
        "volume_ratio": vol_ratio if vol_ratio > 0 else None,
        "price_change": price_chg if vw else None,
        "vol_label": vol_label or None,
        "vp_reason": vp_reason,
    }


def vpf_to_fusion_signal(vpf: dict[str, Any] | None) -> dict[str, Any]:
    """规范化已有 VPF 结果；空则中性。"""
    if not isinstance(vpf, dict) or not vpf:
        return {
            "direction": 0,
            "confidence": 0.2,
            "reason": "价量资金无数据",
            "raw_key": "vpf",
            "signal_tier": SignalTier.NEUTRAL,
            "fund_quality": "missing",
        }
    if vpf.get("raw_key") == "vpf" and "direction" in vpf:
        out = dict(vpf)
        out["direction"] = _as_int_dir(out.get("direction"))
        out["confidence"] = round(_clip_conf(out.get("confidence") or 0.0), 3)
        out["reason"] = str(out.get("reason") or "价量资金中性")
        out["raw_key"] = "vpf"
        # P0-1: 兜底重算 signal_tier (无论上游是否预填, 保证与 reason 一致)
        out["signal_tier"] = vpf_tier_from_reason(out["reason"])
        return out
    return build_vpf_signal(vpf, None)
