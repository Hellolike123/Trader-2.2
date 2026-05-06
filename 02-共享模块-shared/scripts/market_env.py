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


def _fetch_index_bars(days: int = 30) -> list[dict[str, Any]]:
    try:
        provider = get_provider()
        sec = provider.resolve_security(INDEX_CODE)
        raw = provider.fetch_kline(sec, scale="240", datalen=days)
        return normalize_bars(raw)
    except Exception:
        return []


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
    bars = _fetch_index_bars(30)
    if len(bars) < 5:
        return {
            "level": "未知",
            "trend_5d": "",
            "change_pct": 0.0,
            "ma5": None,
            "ma20": None,
            "data_status": "insufficient",
            "note": "中证1000数据不足",
        }

    last = bars[-1]
    current = float(last.get("close") or 0)
    prev = float(bars[-2].get("close") or current) if len(bars) >= 2 else current
    change_pct = round(((current - prev) / prev) * 100, 2) if prev else 0.0

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
        "trend_5d": trend_5d,
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
        env = {"level": "未知", "data_status": "insufficient", "note": "大盘数据暂不可用"}
    env["skill_note"] = env_note_for(env, skill)
    return env


if __name__ == "__main__":
    env = refresh()
    print("level:", env["level"])
    print("note:", env["note"])
    print("t0:", env_note_for(env, "t0"))
    print("trader:", env_note_for(env, "trader"))
    print("portfolio:", env_note_for(env, "portfolio"))
