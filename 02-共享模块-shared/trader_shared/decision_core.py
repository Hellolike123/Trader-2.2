from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from trader_shared.light_data import to_float
from trader_shared.safe_cast import safe_float, safe_dict
from trader_shared.modifier_rule_engine import apply_score_modifiers
from trader_shared._logging import get_logger
from trader_shared.interfaces import DataFetcher
from trader_shared.fetchers import get_fetcher

_logger = get_logger(__name__)

# ── [2.3] Volume Profile 日内量价分布（可选，无则降级）────────────────────────────
try:
    from trader_shared.volume_profile import assess_vp_breakout as _vp_assess
    _VP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _VP_AVAILABLE = False
    def _vp_assess(price, vp, is_buy_context=True):
        return {"vp_signal": "no_data", "vp_confidence": 0.5, "vp_note": "无量价分布模块"}
_engine_loaded: bool = False


def _get_engine() -> Any:
    global _engine, _engine_loaded
    if _engine_loaded:
        return _engine
    _engine_loaded = True

    # Search multiple candidate paths so this works both from the source tree
    # and when installed into a skill bundle (the shared module gets copied
    # into <skill>/scripts/ via pack_all.py).
    _base = Path(__file__).resolve().parent
    candidates = [
        # Source tree: candidate/ ← ../trader_shared/status_rules.yml
        _base.parent.parent / "trader_shared" / "status_rules.yml",
        # Installed: <skill>/scripts/ directly (pack_all copies shared files there)
        _base.parent / "trader_shared" / "status_rules.yml",
    ]
    for rules_path in candidates:
        if rules_path.exists():
            try:
                from trader_shared.rule_engine import RuleEngine
                _engine = RuleEngine.from_yaml(str(rules_path))
                return _engine
            except (ImportError, OSError, ValueError) as exc:
                _logger.warning("Rule engine loaded from %s but evaluation failed: %s", rules_path, exc)

    _engine = None
    return None

from trader_shared.config import (
    STATUS_SCORE,
    CHANGE_THRESHOLD_STRONG,
    CHANGE_THRESHOLD_LARGE,
    CHANGE_THRESHOLD_LARGE_DROP,
    CHANGE_THRESHOLD_DROP,
    POSITION_RATIO_STRONG,
    POSITION_RATIO_CONFIRM,
    POSITION_RATIO_HIGH,
)

try:
    from trader_shared.config import TREND_MA_SHORT, TREND_MA_LONG, TREND_FILTER_ENABLED
except Exception:
    TREND_MA_SHORT = 30
    TREND_MA_LONG = 250  # 年线过滤
    TREND_FILTER_ENABLED = True

try:
    from trader_shared.config import FUSION_OVERRIDE_ENABLED, FUSION_CONFIDENCE_THRESHOLD
except Exception:
    FUSION_OVERRIDE_ENABLED = False
    FUSION_CONFIDENCE_THRESHOLD = 0.6


def _close(vals: list[dict[str, Any]]) -> list[float]:
    result = []
    for v in vals:
        try:
            c = float(v.get("close"))
            result.append(c)
        except (TypeError, ValueError):
            pass
    return result


def _trend_filter(bars: list[dict[str, Any]]) -> bool:
    """250日线趋势过滤：短期均线是否在长期均线上方。"""
    closes = _close(bars)
    if len(closes) < TREND_MA_LONG:
        return True  # 数据不足，不过滤
    try:
        ma_short = sum(closes[-TREND_MA_SHORT:]) / TREND_MA_SHORT
        ma_long = sum(closes[-TREND_MA_LONG:]) / TREND_MA_LONG
    except Exception:
        return True
    if ma_long <= 0:
        return True
    return ma_short > ma_long


def _ma250_check(current: float, bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    """250日线检查：价格在年线下方时返回提醒信息（不再一票否决）。

    Returns:
        None if pass (price above MA250), dict with 提醒信息 if below MA250.
        注意：返回 dict 只携带警告信息，不包含任何 status/决策字段。
        调用方（status_layers L263）只取 ma250_warning 和 ma250 两个字段。
    """
    closes = _close(bars)
    if len(closes) < TREND_MA_LONG:
        return None  # 数据不足，放行
    ma250 = sum(closes[-TREND_MA_LONG:]) / TREND_MA_LONG
    # Fix A1: 只返回警告信息，不返回 "暂不碰" 决策字段
    # 原来包含 base_status/theory_status="暂不碰" 与"不再一票否决"矛盾
    if current < ma250:
        return {
            "ma250_warning": True,
            "ma250": round(ma250, 2),
        }
    return None


# S-2 fix: 融合层 action → status 映射
# 当融合层置信度足够高时，直接用融合层的判断替代纯数学 status
_FUSION_STATUS_MAP: dict[str, str] = {
    "半仓试 (多方主导)": "低吸观察",
    "半仓试 (多方主导但有分歧)": "等转强",
    "增持": "低吸观察",
    "等转强观察": "等转强",       # Fix A7: Fix 3 新增的 action，需在此补充映射
    "持股观望": "等转强",
    "减仓": "冲高减仓",
    "空仓/止损": "暂不碰",
    "空仓 (大盘很差, 一票否决)": "暂不碰",
    "观望 (信号冲突)": "防守观察",
    "等转强 (多方主导但有分歧)": "等转强",
}


def _check_theory_breakout(
    current: float,
    confirm: float,
    support: float,
    position_ratio: float,
    chan_result: dict | None,
    wyk: dict | None,
    vp_result: dict | None = None,  # [2.3新增] Volume Profile 日内量价分布
) -> bool:
    if not chan_result and not wyk:
        return False

    # 价格前提：当前价格不能跌破支撑位
    if current < support:
        return False

    # 价格已经接近或突破确认位，或者在强势运行区间（position_ratio >= 0.50）
    price_strong = (current >= confirm * 0.985) or (position_ratio >= 0.50)
    if not price_strong:
        return False

    # 1. 缺论验证
    chan_ok = False
    if isinstance(chan_result, dict):
        buy_point_text = str(chan_result.get("buy_point_text") or "")
        trend_label = str(chan_result.get("trend_label") or "")
        strokes = chan_result.get("strokes", [])

        # 最强确认：触发三类买点（突破回踩确认）
        if "三类买" in buy_point_text:
            chan_ok = True
        # 或是拉升段/上攻笔中
        elif trend_label == "拉升段" or trend_label == "拉升窗口":
            chan_ok = True
        elif isinstance(strokes, list) and len(strokes) > 0:
            if strokes[-1].get("direction") == "up":
                chan_ok = True

    # 2. 威科夫验证
    wyk_ok = False
    if isinstance(wyk, dict):
        has_upthrust = wyk.get("upthrust_signal", False)
        has_spring = wyk.get("spring_signal", False)
        has_bullish_div = wyk.get("bullish_volume_divergence", False)

        # 排除假突破 (Upthrust)
        if not has_upthrust:
            # 确认有做多结构 (Spring 或看多背离)
            if has_spring or has_bullish_div:
                wyk_ok = True
            else:
                summary = str(wyk.get("wyckoff_summary", ""))
                if "看多" in summary:
                    wyk_ok = True

    theory_ok = chan_ok or wyk_ok
    if not theory_ok:
        return False

    # 3. [2.3新增] Volume Profile 日内量价分布验证
    # 价格跳空下 VA 下沿 = 量价结构不支持突破，封索确认
    if _VP_AVAILABLE and isinstance(vp_result, dict) and vp_result.get("fitted"):
        try:
            vp_info = _vp_assess(current, vp_result, is_buy_context=True)
            vp_signal = vp_info.get("vp_signal", "no_data")
            if vp_signal == "below_va":
                return False
        except Exception:
            pass  # VP 异常静默降级

    return True           # 其他状态（va_breakout/above_poc/va_support/no_data）正常通过


def status_layers(
    current: float,
    support: float,
    low_zone_upper: float,
    confirm: float,
    hard_stop: float,
    position_ratio: float,
    change_pct: Any,
    ma_values: dict[str, float | None],
    pressure_space_pct: float,
    bars: list[dict[str, Any]] | None = None,
    space_threshold: float = 0.008,
    fusion_result: dict[str, Any] | None = None,  # S-2 fix: 接收融合层结果
    chan_result: dict[str, Any] | None = None,
    vp_result: dict[str, Any] | None = None,  # [2.3] Volume Profile 日内量价分布
    fetcher: DataFetcher | None = None,  # DI: 可注入数据源
    ) -> dict[str, Any]:
    if fetcher is None:
        fetcher = get_fetcher()
    # === current=0 前置检查 ===
    if current <= 0:
        return {
            "base_status": "数据不足",
            "theory_status": "数据不足",
            "status": "数据不足",
            "fusion_override_used": False,
            "trend_ok": False,
            "change": 0.0,
            "below_ma_count": 0,
            "above_ma5_ma10": False,
            "pressure_space_pct": 0.0,
        }

    # === 250日线提醒（不屏蔽，只标记） ===
    ma250_warning = False
    ma250_value = None
    if bars and TREND_FILTER_ENABLED:
        ma250_result = _ma250_check(current, bars)
        if ma250_result is not None:
            ma250_warning = True
            ma250_value = ma250_result.get("ma250")

    # === S-2 fix: 融合层覆盖 ===
    # 当融合层开启、置信度足够高、且有明确映射时，用融合层判断替代纯数学判断
    fusion_override_used = False
    fusion_status = None
    if FUSION_OVERRIDE_ENABLED and isinstance(fusion_result, dict):
        fc = safe_float(fusion_result, "confidence")
        if fc >= FUSION_CONFIDENCE_THRESHOLD:
            fusion_action = str(fusion_result.get("action") or "").strip()
            mapped_status = _FUSION_STATUS_MAP.get(fusion_action)
            if mapped_status is not None:
                if mapped_status == "暂不碰" and current <= hard_stop:
                    fusion_status = "暂不碰"
                    fusion_override_used = True
                elif mapped_status == "暂不碰":
                    fusion_status = "防守观察"
                    fusion_override_used = True
                else:
                    fusion_status = mapped_status
                    fusion_override_used = True

    trend_ok = _trend_filter(bars) if (bars and TREND_FILTER_ENABLED) else True
    change = to_float(change_pct) or 0.0
    below_ma_count = sum(1 for value in ma_values.values() if value is not None and current < value)
    _ma5 = ma_values.get("ma5")
    _ma10 = ma_values.get("ma10")
    above_ma5_ma10 = _ma5 is not None and _ma10 is not None and current >= _ma5 and current >= _ma10

    # 从 fusion_result 中提取威科夫信号，用于理论突破验证
    signals_detail = fusion_result.get("signals_detail", {}) if isinstance(fusion_result, dict) else {}
    wyk = signals_detail.get("wyckoff", {}) if isinstance(signals_detail, dict) else None

    # 进行三维理论验证突破判定
    is_theory_breakout = _check_theory_breakout(
        current=current,
        confirm=confirm,
        support=support,
        position_ratio=position_ratio,
        chan_result=chan_result,
        wyk=wyk,
        vp_result=vp_result,
    )

    # P0: 假跌破检测 + 分阶段退出
    _fake_break = False
    _near_stop = False
    try:
        from trader_shared.config import PULLBACK_CONFIRM_DAYS, EXIT_PHASED_ENABLED
    except Exception:
        PULLBACK_CONFIRM_DAYS = 3
        EXIT_PHASED_ENABLED = True

    if current <= hard_stop and isinstance(bars, list) and len(bars) > 2:
        lookback = min(PULLBACK_CONFIRM_DAYS, len(bars) - 1)
        for i in range(-lookback, 0):
            prev_close = to_float(bars[i].get("close"))
            if prev_close is not None and prev_close >= hard_stop:
                _fake_break = True
                break

    if EXIT_PHASED_ENABLED and not _fake_break and current > hard_stop:
        # Fix A6: hard_stop 和 support 可能极近（如止损就在支撑位附近），
        # 导致 atr_est 接近0，几乎所有价格都误触发 _near_stop
        # 用当前价×1.5%（约1个ATR）作为下限，确保合理触发距离
        atr_est = max(current * 0.015 if current > 0 else 0.01, abs(hard_stop - support) / 2 if support > 0 else 0.01)
        if current - hard_stop < atr_est * 2:
            _near_stop = True

    base_status = "风险回避"
    if _fake_break:
        base_status = "防守观察"  # 假跌破，不直接清仓
    elif current <= hard_stop or current < support * 0.995:
        base_status = "风险回避"
    elif _near_stop:
        base_status = "冲高减仓"  # 靠近止损，先减仓
    elif trend_ok and change <= CHANGE_THRESHOLD_DROP and current > low_zone_upper:
        base_status = "风险回避"
    elif is_theory_breakout:
        base_status = "突破确认"
    elif current <= low_zone_upper:
        base_status = "低位修复"
    elif current >= confirm:
        base_status = "确认观察"
    elif above_ma5_ma10 or position_ratio >= POSITION_RATIO_STRONG:
        base_status = "均线修复"
    elif below_ma_count >= 3:
        base_status = "防守整理"
    elif position_ratio >= POSITION_RATIO_CONFIRM:
        base_status = "临近确认"
    elif 0 <= pressure_space_pct < space_threshold:
        base_status = "空间偏紧"
    else:
        base_status = "中性整理"

    theory_status = "防守观察"
    if _fake_break:
        theory_status = "防守观察"  # 假跌破，不升级
    elif current <= hard_stop or current < support * 0.995:
        theory_status = "暂不碰"
    elif _near_stop:
        theory_status = "冲高减仓"
    elif trend_ok and change <= CHANGE_THRESHOLD_DROP and current > low_zone_upper:
        theory_status = "暂不碰"
    elif is_theory_breakout:
        theory_status = "突破确认"
    elif current <= low_zone_upper:
        # Fix 1: 先判断是否有均线承接信号，有则保留；无则才按 trend_ok 降级
        # 原逻辑：承接存在 赋值后又被 not trend_ok 强行覆盖 → bug
        if below_ma_count >= 3 and current > support:
            # 三根均线压着但价格仍站在支撑上方，有实质性承接，大盘弱势不降级
            theory_status = "承接存在"
        elif trend_ok:
            theory_status = "修复观察"
        else:
            theory_status = "防守观察"
    elif current >= confirm:
        # Fix 8: 体系转强确认放宽，允许 position_ratio 高位（接近阻力位）作为辅助确认
        # 原逻辑只看当日涨幅，会漏掉"缩量整理后温和突破"的真实转强
        strong_breakout = change >= CHANGE_THRESHOLD_STRONG or position_ratio >= POSITION_RATIO_HIGH
        if strong_breakout and trend_ok:
            theory_status = "体系转强确认"
        elif trend_ok and above_ma5_ma10 and position_ratio >= POSITION_RATIO_STRONG:
            theory_status = "未确认转强"
        else:
            theory_status = "转强不足"
    elif above_ma5_ma10 and position_ratio >= POSITION_RATIO_STRONG:
        theory_status = "未确认转强"
    elif below_ma_count >= 3:
        theory_status = "防守观察"
    elif position_ratio >= POSITION_RATIO_CONFIRM:
        theory_status = "未确认转强"
    elif 0 <= pressure_space_pct < space_threshold:
        theory_status = "转强不足"
    else:
        theory_status = "修复观察" if trend_ok else "防守观察"

    if fusion_override_used and fusion_status is not None:
        if theory_status == "暂不碰" and current <= hard_stop:
            pass
        else:
            theory_status = fusion_status

    return {
        "base_status": base_status,
        "theory_status": theory_status,
        "status": theory_status,
        "fusion_override_used": fusion_override_used,
        "trend_ok": trend_ok,
        "change": change,
        "below_ma_count": below_ma_count,
        "above_ma5_ma10": above_ma5_ma10,
        "pressure_space_pct": pressure_space_pct,
        "ma250_warning": ma250_warning,
        "ma250": ma250_value,
    }


def status_for(
    current: float,
    support: float,
    low_zone_upper: float,
    confirm: float,
    hard_stop: float,
    position_ratio: float,
    change_pct: Any,
    ma_values: dict[str, float | None],
    pressure_space_pct: float,
    bars: list[dict[str, Any]] | None = None,
    space_threshold: float = 0.008,
    fusion_result: dict[str, Any] | None = None,  # S-2 fix: 接收融合层结果
    chan_result: dict[str, Any] | None = None,
    vp_result: dict[str, Any] | None = None,  # [2.3] Volume Profile 日内量价分布
    fetcher: DataFetcher | None = None,  # DI: 可注入数据源
) -> str:
    return str(status_layers(
        current,
        support,
        low_zone_upper,
        confirm,
        hard_stop,
        position_ratio,
        change_pct,
        ma_values,
        pressure_space_pct,
        bars=bars,
        space_threshold=space_threshold,
        fusion_result=fusion_result,
        chan_result=chan_result,
        vp_result=vp_result,
        fetcher=fetcher,
    )["theory_status"])


def action_for(status: str, low: float, high: float, sell_observe: float, confirm: float) -> str:
    if status in {"突破确认", "突破观察"}:
        return f"突破已确认/确认中，回踩不破 {confirm:.2f}元 可看多，勿盲目追涨。"
    if status in {"低吸观察", "修复观察"}:
        return f"等 {low:.2f}-{high:.2f}元 止跌，不追。"
    if status in {"等转强", "未确认转强"}:
        return f"不追，等站稳 {confirm:.2f}元 后再看。"
    if status in {"冲高减仓", "体系转强确认"}:
        return f"冲高先看 {sell_observe:.2f}元 附近量能，不机械卖。"
    if status in {"空间不足", "转强不足"}:
        return "上方空间太近或力度不足，先观察，不追。"
    if status in _DEFENSE_STATUSES or status == "防守观察":
        return "先看防守是否稳定，低吸和减仓都等确认。"
    if status == "承接存在":
        return "有承接但还没确认转强，先观察是否延续。"
    if status == "暂不碰":
        return "风险不清楚，先不参与。"
    return "数据失败，先不参与。"


_DEFENSE_STATUSES = {"防守观察", "防守观察，趋势下行谨慎"}


def _is_defense(status: str) -> bool:
    """Check if status represents a defensive posture."""
    return status in _DEFENSE_STATUSES


def score_for(item: dict[str, Any]) -> float:
    status = item.get("status") or ""
    current = safe_float(item, "current")
    low_upper = item.get("low_zone_upper")
    confirm = item.get("confirm_price")
    hard_stop = safe_float(item, "hard_stop", default=current)
    position_ratio = safe_float(item, "position_ratio")
    change = to_float(item.get("change_pct")) or 0.0
    below_ma_count = int(item.get("below_ma_count") or 0)

    rule_mod = apply_score_modifiers(item)
    if rule_mod is None:
        score = float(STATUS_SCORE.get(status, STATUS_SCORE.get("等转强", 60)))
        if status != "暂不碰" and low_upper is not None and current <= float(low_upper):
            score += 10
        if status != "暂不碰" and confirm is not None and current >= float(confirm):
            score += 8
        if current <= hard_stop:
            score -= 40
        if abs((current - hard_stop) / max(current, 1)) < 0.01:
            score -= 8
        if change <= CHANGE_THRESHOLD_LARGE_DROP and status != "低吸观察":
            score -= 8
        if change >= CHANGE_THRESHOLD_LARGE and position_ratio >= POSITION_RATIO_HIGH:
            score -= 10
        # P0 Fix: 当 current >= confirm 时，跳过 gap 扣分（已突破的票不应被扣分）
        if confirm is not None and current >= float(confirm):
            pass  # 已突破确认位，不扣 gap 分
        else:
            gap_pct = (float(confirm) - current) / max(current, 1) if confirm is not None else 0
            if gap_pct <= 0:
                score -= 4
            else:
                score += min(max(int(gap_pct * 250), 0), 5)
        if item.get("low_zone") and item.get("confirm_price"):
            score += 5
        score -= below_ma_count * 2
        return score

    score = float(STATUS_SCORE.get(status, 0)) + rule_mod
    score -= below_ma_count * 2
    return score


def atr_volatility_level(atr_ratio: float) -> tuple[str, int]:
    if atr_ratio <= 0:
        return ("数据不足", 10)
    if atr_ratio >= ATR_HIGH_THRESHOLD:
        return ("波幅偏高", 5)
    if atr_ratio >= ATR_ELEVATED_THRESHOLD:
        return ("波动偏大", 7)
    if atr_ratio >= ATR_NORMAL_THRESHOLD:
        return ("波动正常", 10)
    return ("波动较低", 20)


def atr_stop_buffer(atr_ratio: float, atr14: float) -> tuple[float, str]:
    if atr14 <= 0:
        return (0, "ATR数据不足")
    distance = round(atr14 * 2, 2)
    level, _ = atr_volatility_level(atr_ratio)
    if atr_ratio >= ATR_ELEVATED_THRESHOLD:
        return (distance, f"{level} | ATR×2={distance:.2f}元")
    return (distance, f"ATR×2={distance:.2f}元")


try:
    from trader_shared.config import PYRAMID_SCALES
except Exception:  # pragma: no cover - optional per skill
    PYRAMID_SCALES = {0: 0, 1: 0.15, 2: 0.35, 3: 0.6, 4: 0.85, 5: 1.0}

try:
    from trader_shared.config import BASE_WEIGHTS
except Exception:  # pragma: no cover - optional per skill
    BASE_WEIGHTS = {0: 15, 1: 10, 2: 7, 3: 4}

try:
    from trader_shared.config import ATRLV_INDEX
except Exception:  # pragma: no cover - optional per skill
    ATRLV_INDEX = {"数据不足": 0, "波幅偏高": 3, "波动偏大": 2, "波动正常": 1, "波动较低": 0}

try:
    from trader_shared.config import ATR_HIGH_THRESHOLD
except Exception:  # pragma: no cover - optional per skill
    ATR_HIGH_THRESHOLD = 0.03

try:
    from trader_shared.config import ATR_ELEVATED_THRESHOLD
except Exception:  # pragma: no cover - optional per skill
    ATR_ELEVATED_THRESHOLD = 0.02

try:
    from trader_shared.config import ATR_NORMAL_THRESHOLD
except Exception:  # pragma: no cover - optional per skill
    ATR_NORMAL_THRESHOLD = 0.01


def base_weight(atr_level: str) -> int:
    idx = ATRLV_INDEX.get(atr_level, 1)
    return BASE_WEIGHTS.get(idx, 10)
