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

# 板块对照指数：展示短名 + ts 代码（环境档与涨跌同源）
_BOARD_INDEX_BY_PREFIX: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("688",), "000688.SH", "科创"),
    (("300", "301"), "399006.SZ", "创业板"),
    (("60",), "000001.SH", "上证"),
    (("000", "001", "002", "003"), "399001.SZ", "深成"),
)


def resolve_board_index(code_or_sec: Any = None) -> tuple[str, str]:
    """个股 → (指数 ts_code, 短标签)。

    688→科创50；30x→创业板指；60→上证；00/001/002→深成；其余回退 INDEX_CODE。
    """
    raw = ""
    if code_or_sec is None:
        return INDEX_CODE, "中证1000"
    if hasattr(code_or_sec, "code"):
        raw = str(getattr(code_or_sec, "code", "") or "")
        ts = str(getattr(code_or_sec, "ts_code", "") or "")
        if not raw and ts:
            raw = ts.split(".")[0]
    else:
        raw = str(code_or_sec or "").strip().upper()
        raw = raw.replace("SH", "").replace("SZ", "").replace("BJ", "")
        raw = raw.split(".")[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 6:
        digits = digits[-6:]
    for prefixes, idx, label in _BOARD_INDEX_BY_PREFIX:
        if any(digits.startswith(p) for p in prefixes):
            return idx, label
    # 北交所等：暂回退宽基，避免无源
    return INDEX_CODE, "中证1000"


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


def _fetch_index_data(index_code: str | None = None) -> dict[str, Any]:
    """Fetch current index data via Tencent real-time quote API.

    Tencent index response format (after =quote):
    market~name~code~~~current_high_low_volume~~pre_change~change_pct~current_price~pre_close~today_high~today_low~~...
    Key indices: [9]=current, [10]=empty, [12]=pre_change, [13]=change_pct, [14]=current_price, [15]=pre_close
    """
    import urllib.request

    idx = (index_code or INDEX_CODE).strip() or INDEX_CODE
    tencent_code = _tencent_index_code(idx)
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
        sec = provider.resolve_security(idx)
        bars = provider.fetch_qfq_daily(sec, days=90) or []
    except Exception:
        bars = []

    return {
        "current": current,
        "pre_close": pre_close,
        "change_pct": round(change_pct, 2),
        "bars": bars,
        "index_code": idx,
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


# ── 进程内缓存（按指数代码分桶；批量同板块票复用）──
_assess_cache_by_index: dict[str, tuple[float, dict[str, Any]]] = {}
_ASSESS_CACHE_TTL = 60  # 1 分钟内复用进程内结果

# 兼容旧测：单槽镜像（默认 INDEX_CODE）
_assess_cache: dict[str, Any] | None = None
_assess_cache_time: float = 0


def _index_cache_target(index_code: str) -> str:
    return f"index_{(index_code or INDEX_CODE).strip().replace('.', '_')}"


def _label_for_index(index_code: str) -> str:
    for _, idx, label in _BOARD_INDEX_BY_PREFIX:
        if idx == index_code:
            return label
    if index_code == INDEX_CODE:
        return "中证1000"
    return "指数"


def assess(index_code: str | None = None) -> dict[str, Any]:
    """评估市场环境。index_code 缺省为全局 INDEX_CODE；单票报告应传所属板块指数。"""
    global _assess_cache, _assess_cache_time, _assess_cache_by_index
    import time as _time

    idx = (index_code or INDEX_CODE).strip() or INDEX_CODE
    idx_label = _label_for_index(idx)
    now = _time.time()
    cached_hit = _assess_cache_by_index.get(idx)
    if cached_hit is not None and now - cached_hit[0] < _ASSESS_CACHE_TTL:
        return dict(cached_hit[1])

    # ── 文件缓存：同一自然日直接复用（当天第一次之后不再打网）──
    # level / HMM 日频足够；换日回源。失败兜底仍用旧缓存 bars。
    _cached_env = None
    _cache_target = _index_cache_target(idx)
    try:
        from trader_shared.cache_utils import (
            get_cached as _file_cached,
            CACHE_MARKET_ENV,
            TTL_DAILY,
            cache_calendar_date,
            is_fetch_date_today,
        )
        _cached_result = _file_cached(CACHE_MARKET_ENV, _cache_target, ttl=TTL_DAILY * 3)
        _cached_env = _cached_result.data if _cached_result is not None else None
        # 兼容旧缓存键 "index"（仅默认宽基）
        if _cached_env is None and idx == INDEX_CODE:
            _cached_result = _file_cached(CACHE_MARKET_ENV, "index", ttl=TTL_DAILY * 3)
            _cached_env = _cached_result.data if _cached_result is not None else None
        if (
            _cached_env
            and isinstance(_cached_env, dict)
            and is_fetch_date_today(_cached_env)
            and _cached_env.get("level")
        ):
            env = dict(_cached_env)
            env.setdefault("index_code", idx)
            env.setdefault("index_label", idx_label)
            _assess_cache_by_index[idx] = (now, env)
            if idx == INDEX_CODE:
                _assess_cache = env
                _assess_cache_time = now
            return env
    except Exception:
        pass

    idx_data = _fetch_index_data(idx)

    if not idx_data:
        # 缓存有数据但实时抓取失败 → 使用缓存（标记 bars 陈旧，避免下游误判为新鲜）
        if _cached_env and isinstance(_cached_env, dict) and _cached_env.get("bars"):
            _cached_env = dict(_cached_env)
            _cached_env["bars_stale"] = True
            _cached_env.setdefault("index_code", idx)
            _cached_env.setdefault("index_label", idx_label)
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
            "note": f"{idx_label}数据不足",
            "index_code": idx,
            "index_label": idx_label,
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
            # 用 bars 中最新交易日而非墙钟，避免 backtest / 盘前用错"今天"
            _dates = [b.get("date") or b.get("time") or "" for b in bars if b.get("date") or b.get("time")]
            today_str = max(_dates) if _dates else __import__("datetime").datetime.now().strftime("%Y-%m-%d")
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
            # 现价：今日 bar 已在序列末则原地更新；否则追加一日（勿对已有今日 bar 再 append）
            if current > 0 and closes:
                last_d = str(closes_vol[-1].get("date") or closes_vol[-1].get("time") or "")[:10]
                try:
                    from trader_shared.trading_context import _last_trading_day
                    from trader_shared.cn_time import today_cn
                    expected_d = _last_trading_day(today_cn()).isoformat()
                except Exception:
                    expected_d = last_d
                if last_d == expected_d:
                    closes[-1] = current
                elif abs(closes[-1] - current) > 1e-5:
                    closes.append(current)
                    volumes.append(volumes[-1] if volumes else 0.0)
            elif current > 0:
                closes.append(current)
                volumes.append(0.0)
            index_returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
            # 每日量比序列：当日量 / 近5日均量（非正值兜底为 1.0，避免 inf/nan）
            vol_series = []
            for i in range(1, len(volumes)):
                window = volumes[max(0, i - 4):i + 1]
                if volumes[i] <= 0 or sum(window) <= 0:
                    vol_series.append(1.0)
                else:
                    vol_series.append(volumes[i] / (sum(window) / len(window)))
            # fit 需 ≥30；短序列先验 Viterbi 不可靠
            if len(index_returns) >= 30 and len(vol_series) == len(index_returns):
                from trader_shared.hmm_regime import detect_regime
                _as_of = str(closes_vol[-1].get("date") or closes_vol[-1].get("time") or "")[:10] or None
                hmm_res = detect_regime(index_returns, volume_ratio=vol_series, as_of=_as_of)
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

    # 日涨跌幅兜底：先判 -5%（很差），再判 -3%（偏弱）；勿用 if/elif 让 -5 卡在偏弱
    if change_pct <= -5.0:
        level = "很差"
    elif change_pct <= -3.0 and level == "正常":
        level = "偏弱"

    note = (
        f"{idx_label} MA5/MA20 {'>' if mid_term == 'up' else '<'} "
        f"趋势{'偏多' if mid_term == 'up' else '偏空'} 今日{change_pct:+.1f}%"
    )

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
        "index_code": idx,
        "index_label": idx_label,
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
            _file_set(CACHE_MARKET_ENV, _cache_target, result)
            # 默认宽基同时写旧键，兼容未升级读侧
            if idx == INDEX_CODE:
                _file_set(CACHE_MARKET_ENV, "index", result)
        except Exception:
            pass

    # ── 进程内缓存 ──
    _assess_cache_by_index[idx] = (now, result)
    if idx == INDEX_CODE:
        _assess_cache = result
        _assess_cache_time = now

    return result


def refresh(write_pipeline: bool = True, index_code: str | None = None) -> dict[str, Any]:
    env = assess(index_code=index_code)
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


def get_env_for_skill(skill: str, index_code: str | None = None) -> dict[str, Any]:
    """skill 环境注记。单票报告应传所属板块指数代码（见 resolve_board_index）。"""
    try:
        env = assess(index_code=index_code)
    except Exception:
        idx = (index_code or INDEX_CODE).strip() or INDEX_CODE
        env = {
            "level": "未知",
            "data_status": "degraded",
            "note": "大盘数据暂不可用",
            "index_code": idx,
            "index_label": _label_for_index(idx),
        }
    env["skill_note"] = env_note_for(env, skill)
    return env


if __name__ == "__main__":
    env = assess()
    print("level:", env["level"])
    print("note:", env["note"])
    print("change_pct:", env["change_pct"])
    print("current:", env["current"])
    print("ma5:", env["ma5"])
    print("index:", env.get("index_code"), env.get("index_label"))
    print("t0:", env_note_for(env, "t0"))
    print("trader:", env_note_for(env, "trader"))
    print("portfolio:", env_note_for(env, "portfolio"))
