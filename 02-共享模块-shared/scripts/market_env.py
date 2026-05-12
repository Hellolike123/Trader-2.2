from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ── path setup (MUST precede all imports below) ──
_SHARED_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _SHARED_ROOT / "scripts"
_MARKET_DATA = _SHARED_ROOT / "01-行情数据-market-data"
for _p in (_SCRIPTS_DIR, _MARKET_DATA):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from pipeline import write_market

    _HAS_PIPELINE = True
except ImportError:
    _HAS_PIPELINE = False

from light_data import normalize_bars
from trader_shared.config import INDEX_CODE
from trader_shared.data_provider import get_provider


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
        with urllib.request.urlopen(req, timeout=10) as resp:
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
    if price_part:
        current = float(price_part.split("/")[0])
    else:
        current = float(parts[3]) if len(parts) > 3 and parts[3] else 0
    # Compute pre_close from change_pct: current = pre_close * (1 + pct/100)
    if change_pct and current:
        pre_close = round(current / (1 + change_pct / 100), 2)
    else:
        pre_close = 0

    if change_pct == 0 and current == 0:
        return {}

    # For MA calculations we still need K-line bars
    try:
        provider = get_provider()
        sec = provider.resolve_security(INDEX_CODE)
        raw_bars = provider.fetch_kline(sec, scale="240", datalen=30)
        bars = normalize_bars(raw_bars) if raw_bars else []
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


def assess() -> dict[str, Any]:
    idx_data = _fetch_index_data()

    if not idx_data:
        return {
            "level": "未知",
            "current": 0,
            "change_pct": 0.0,
            "ma5": None,
            "ma20": None,
            "data_status": "degraded",
            "note": "中证1000数据不足",
        }

    current = idx_data.get("current", 0)
    change_pct = idx_data.get("change_pct", 0.0)
    bars = idx_data.get("bars", [])

    ma5 = _ma(bars, 5)
    ma20 = _ma(bars, 20)
    trend_5d = "up" if (ma5 is not None and current >= ma5) else "down"

    level = ""
    if trend_5d == "down" and change_pct < -2.0:
        level = "很差"
    elif trend_5d == "down" or (change_pct < 0 and change_pct > -2.0):
        level = "偏弱"
    else:
        level = "正常"

    note = f"中证1000 {'五条线上方' if trend_5d == 'up' else '五条线下方'} + 今日{'涨' if change_pct >= 0 else '跌'}{abs(change_pct):.1f}%"

    return {
        "level": level,
        "current": current,
        "change_pct": change_pct,
        "ma5": round(ma5, 2) if ma5 else None,
        "ma20": round(ma20, 2) if ma20 else None,
        "data_status": "full",
        "note": note,
    }


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
