from __future__ import annotations

from typing import Any

try:
    from trader_shared.pipeline import write_market

    _HAS_PIPELINE = True
except (ImportError, AttributeError):
    # #26 修复：pipeline 模块不存在或 write_market 接口变更都应静默降级
    _HAS_PIPELINE = False

from trader_shared._logging import get_logger
from trader_shared.config import INDEX_CODE
from trader_shared.data_provider import get_provider

_logger = get_logger(__name__)


def _is_market_open_now() -> bool:
    """判断当前是否是交易时段（用于 data_freshness 标记）。"""
    try:
        from trader_shared.trading_context import data_freshness
        return data_freshness() == "live"
    except ImportError:
        from trader_shared.light_data import is_trading_time
        return is_trading_time()


def _tencent_index_code(raw_code: str) -> str:
    """Convert INDEX_CODE format (000852.SH) to Tencent format (sh000852)."""
    parts = raw_code.split(".")
    market = parts[1].lower() if len(parts) > 1 else "sh"
    code = parts[0]
    return f"{market}{code}"


def _fetch_index_data() -> dict[str, Any]:
    """Fetch current index data via Tencent real-time quote API.

    Tencent index response format (after =quote):
    market~name~code~~~current_high_low_volume~~pre_change~change_pct~current_price~pre_close~today_high~today_low~~...
    Key indices: [9]=current, [10]=empty, [12]=pre_change, [13]=change_pct, [14]=current_price, [15]=pre_close
    """
    import urllib.request

    tencent_code = _tencent_index_code(INDEX_CODE)
    url = f"http://qt.gtimg.cn/q={tencent_code}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com"},
        )
        # 腾讯 API 直连（跳过系统代理，解决代理挂掉导致行情停滞的问题）
        import urllib.request as _ur
        _handler = _ur.ProxyHandler({})
        _opener = _ur.build_opener(_handler)
        with _opener.open(req, timeout=10) as resp:
            raw = resp.read().decode("gbk")
    except Exception:
        return {}

    raw = raw.strip()
    if '"' not in raw:
        return {}
    value = raw.split('"', 1)[1].strip().rstrip(";")
    parts = value.split("~")
    if len(parts) < 20:
        return {}

    # [1]=name [3]=current_open [32]=change_pct [33]=high [34]=low [35]=price/vol/amount
    try:
        change_pct = float(parts[32])
    except (ValueError, IndexError):
        return {}

    # [35] = "price/vol/amount" — the current price as of market close
    price_part = parts[35] if len(parts) > 35 and parts[35] else ""
    # Fallback: if no price_part, use [3] which is the last known open (approx close)
    current = 0
    if price_part:
        try:
            current = float(price_part.split("/")[0])
        except (ValueError, IndexError):
            current = 0
    if current == 0:
        current = float(parts[3]) if len(parts) > 3 and parts[3] else 0
    # Compute pre_close from change_pct: current = pre_close * (1 + pct/100)
    if change_pct and current:
        pre_close = round(current / (1 + change_pct / 100), 2)
    else:
        pre_close = 0

    if change_pct == 0 and current == 0:
        return {}

    # For MA calculations we still need daily K-line bars, fetch 90 days for stable HMM
    try:
        provider = get_provider()
        sec = provider.resolve_security(INDEX_CODE)
        bars = provider.fetch_qfq_daily(sec, days=90) or []
    except Exception:
        bars = []

    return {
        "current": current,
        "pre_close": pre_close,
        "change_pct": round(change_pct, 2),
        "bars": bars,
    }


def _ma(bars: list[dict[str, Any]], period: int) -> float | None:
    closes = []
    for b in bars:
        c = b.get("close")
        if c is not None:
            closes.append(float(c))
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


# ── 进程内缓存（批量刷新时避免每票重复 HTTP + HMM 计算）──
_assess_cache: dict[str, Any] | None = None
_assess_cache_time: float = 0
_ASSess_CACHE_TTL = 60  # 1 分钟内复用进程内结果


def assess() -> dict[str, Any]:
    global _assess_cache, _assess_cache_time
    # 进程内缓存：同一进程内 60 秒内复用
    import time as _time
    now = _time.time()
    if _assess_cache is not None and now - _assess_cache_time < _ASSess_CACHE_TTL:
        return _assess_cache

    # ── 文件缓存：同一自然日直接复用（当天第一次之后不再打网）──
    # 大盘 level / HMM 日频足够；换日回源。失败兜底仍用旧缓存 bars。
    _cached_env = None
    try:
        from trader_shared.cache_utils import (
            get_cached as _file_cached,
            CACHE_MARKET_ENV,
            TTL_DAILY,
            cache_calendar_date,
            is_fetch_date_today,
        )
        _cached_result = _file_cached(CACHE_MARKET_ENV, "index", ttl=TTL_DAILY * 3)
        _cached_env = _cached_result.data if _cached_result is not None else None
        if (
            _cached_env
            and isinstance(_cached_env, dict)
            and is_fetch_date_today(_cached_env)
            and _cached_env.get("level")
        ):
            env = dict(_cached_env)
            _assess_cache = env
            _assess_cache_time = now
            return env
    except Exception:
        pass

    idx_data = _fetch_index_data()

    if not idx_data:
        # 缓存有数据但实时抓取失败 → 使用缓存（标记 bars 陈旧，避免下游误判为新鲜）
        if _cached_env and isinstance(_cached_env, dict) and _cached_env.get("bars"):
            _cached_env = dict(_cached_env)
            _cached_env["bars_stale"] = True
            return _cached_env
        return {
            "level": "未知",
            "current": 0,
            "change_pct": 0.0,
            "ma5": None,
            "ma20": None,
            "data_status": "degraded",
            "hmm_regime_en": "range",
            "hmm_regime_label": "宽幅震荡",
            "hmm_confidence": 0.5,
            "note": "中证1000数据不足",
        }

    current = idx_data.get("current", 0)
    change_pct = idx_data.get("change_pct", 0.0)
    bars = idx_data.get("bars", [])
    bars_from_cache = False  # 本次 bars 是否纯靠旧缓存顶替（实时日K取数缺失）

    # ── 合并缓存的历史 bars 与当日实时数据 ──
    if _cached_env and isinstance(_cached_env, dict):
        cached_bars = _cached_env.get("bars", [])
        if cached_bars and bars:
            # 用缓存的历史 bars 替代（更完整），追加今天的实时 bar
            today_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
            # 去重：保留缓存中非今日的数据 + 实时数据
            merged = [b for b in cached_bars if b.get("date") != today_str]
            merged.extend(bars)  # bars 里有今天的实时数据
            # 按日期排序并去重（保留每个日期最后一条）
            seen_dates: dict[str, int] = {}
            for i, b in enumerate(merged):
                d = b.get("date") or b.get("time") or ""
                if d:
                    seen_dates[d] = i
            if len(seen_dates) < len(merged):
                # 有重复日期，去重
                merged = [merged[i] for i in sorted(seen_dates.values())]
            bars = merged
        elif cached_bars and not bars:
            bars = cached_bars
            bars_from_cache = True  # 实时日K取数失败，bars 纯靠旧缓存顶替

    # Volume trend: recent 5d vol / preceding 5d vol (>1 = expanding, <1 = shrinking)
    closes_vol: list[dict[str, Any]] = [b for b in bars if b.get("close") is not None and b.get("volume") is not None]
    vol_trend: float | None = None
    if len(closes_vol) >= 10:
        vol_recent = sum(float(b["volume"]) for b in closes_vol[-5:]) / 5
        vol_prev = sum(float(b["volume"]) for b in closes_vol[-10:-5]) / 5
        if vol_prev > 0:
            vol_trend = vol_recent / vol_prev

    # [2.3] HMM 大势前瞻判定
    # DEFER-2 Fix: 传每日量比序列（当日量/近5日均量），真正启用 2D 观察维度；
    # 原实现传 vol_trend 标量被广播为常数，2D 退化为 1.5D。
    hmm_regime_en = "range"
    hmm_regime_label = "宽幅震荡"
    hmm_confidence = 0.5
    try:
        # 使用同时含 close 与 volume 的 bars，保证 returns 与量比序列等长对齐
        if len(closes_vol) >= 6:
            closes = [float(b["close"]) for b in closes_vol]
            volumes = [float(b["volume"]) for b in closes_vol]
            if current > 0 and (not closes or abs(closes[-1] - current) > 1e-5):
                closes.append(current)
                volumes.append(volumes[-1] if volumes else 0.0)
            index_returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
            # 每日量比序列：当日量 / 近5日均量（非正值兜底为 1.0，避免 inf/nan）
            vol_series = []
            for i in range(1, len(volumes)):
                window = volumes[max(0, i - 4):i + 1]
                if volumes[i] <= 0 or sum(window) <= 0:
                    vol_series.append(1.0)
                else:
                    vol_series.append(volumes[i] / (sum(window) / len(window)))
            if len(index_returns) >= 5 and len(vol_series) == len(index_returns):
                from trader_shared.hmm_regime import detect_regime
                hmm_res = detect_regime(index_returns, volume_ratio=vol_series)
                hmm_regime_en = hmm_res.get("state_en", "range")
                hmm_regime_label = hmm_res.get("state_label", "宽幅震荡")
                hmm_confidence = hmm_res.get("confidence", 0.5)
    except Exception as exc:
        _logger.debug("HMM regime detection failed: %s", exc)

    ma5 = _ma(bars, 5)
    ma20 = _ma(bars, 20)

    # Improved trend: use MA5/MA20 relationship + slope, not just current vs MA5
    mid_term = "up" if (ma5 is not None and ma20 is not None and ma5 > ma20) else "down"

    # Level classification: separate mid-term trend from short-term intraday movement
    mid_weak = mid_term == "down"
    intraday_weak = change_pct < -2.0
    intraday_moderate = 0 > change_pct >= -2.0
    shrinking = vol_trend is not None and vol_trend < 0.8

    level = "正常"
    if mid_weak and intraday_weak:
        level = "很差"
    elif mid_weak and (shrinking or intraday_moderate):
        level = "偏弱"

    # HMM 大势前瞻性修正
    if hmm_confidence >= 0.75:
        if hmm_regime_en == "bear" and level == "正常":
            level = "偏弱"
        elif hmm_regime_en == "bull" and level == "偏弱":
            level = "正常"

    # 日涨跌幅兜底：单日急跌 >=3% 强制降级
    if change_pct <= -3.0 and level == "正常":
        level = "偏弱"
    elif change_pct <= -5.0 and level in ("正常", "偏弱"):
        level = "很差"

    note = f"中证1000 MA5/MA20 {'>' if mid_term=='up' else '<'} 趋势{'偏多' if mid_term=='up' else '偏空'} 今日{change_pct:+.1f}%"

    result = {
        "level": level,
        "current": current,
        "change_pct": change_pct,
        "ma5": round(ma5, 2) if ma5 is not None else None,
        "ma20": round(ma20, 2) if ma20 is not None else None,
        "data_status": "full",
        "data_freshness": "live" if _is_market_open_now() else "stale",
        "hmm_regime_en": hmm_regime_en,
        "hmm_regime_label": hmm_regime_label,
        "hmm_confidence": hmm_confidence,
        "vol_trend": round(vol_trend, 2) if vol_trend is not None else None,
        "note": note + f" (HMM前瞻: {hmm_regime_label})",
        "bars": bars,  # 保留 bars 供缓存和下游使用
        "bars_stale": bars_from_cache,  # True 表示 bars 来自旧缓存顶替（实时日K取数失败）
    }
    try:
        from trader_shared.cache_utils import cache_calendar_date as _ccd
        result["fetch_date"] = _ccd()
    except Exception:
        result["fetch_date"] = ""

    # ── 写入文件缓存 ──
    # 仅当 bars 来自实时新鲜数据才写回：陈旧缓存顶替时不写回，避免旧值被反复刷 TTL 锁死
    # （旧逻辑：bars 用旧缓存顶上后仍无条件写回，导致一次取数失败被固化为长期陈旧）。
    if not bars_from_cache:
        try:
            from trader_shared.cache_utils import set_cached as _file_set, CACHE_MARKET_ENV
            _file_set(CACHE_MARKET_ENV, "index", result)
        except Exception:
            pass

    # ── 进程内缓存 ──
    _assess_cache = result
    _assess_cache_time = now

    return result


def refresh(write_pipeline: bool = True) -> dict[str, Any]:
    env = assess()
    if write_pipeline and _HAS_PIPELINE:
        write_market(env.get("level", "未知"), env.get("note", ""))
    return env


def env_note_for(env: dict[str, Any], skill: str) -> str:
    level = env.get("level", "未知")
    mapping = {
        "t0": {
            "正常": "正常操作",
            "偏弱": "不做买入T0，可做卖出T0",
            "很差": "不做T0，只观察",
            "未知": "大盘数据暂不可用，谨慎操作",
        },
        "trader": {
            "正常": "正常建仓",
            "偏弱": "等大盘企稳再建仓",
            "很差": "建仓后设紧止损",
            "未知": "大盘数据暂不可用，保守对待",
        },
        "portfolio": {
            "正常": "正常配置",
            "偏弱": "不加仓、不轮入",
            "很差": "不轮入新票、压总仓",
            "未知": "大盘数据暂不可用，不轮入新票",
        },
    }
    skill_mapping = mapping.get(skill, {})
    return skill_mapping.get(level, "")


def get_env_for_skill(skill: str) -> dict[str, Any]:
    try:
        env = assess()
    except Exception:
        env = {"level": "未知", "data_status": "degraded", "note": "大盘数据暂不可用"}
    env["skill_note"] = env_note_for(env, skill)
    return env


if __name__ == "__main__":
    env = assess()
    print("level:", env["level"])
    print("note:", env["note"])
    print("change_pct:", env["change_pct"])
    print("current:", env["current"])
    print("ma5:", env["ma5"])
    print("t0:", env_note_for(env, "t0"))
    print("trader:", env_note_for(env, "trader"))
    print("portfolio:", env_note_for(env, "portfolio"))
