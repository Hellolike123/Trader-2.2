"""Chanlun (缠论) indicator plugin.

Wraps chan_core.py chanlun_strategy() behind the IndicatorPlugin interface.

Timeframe policy (for T0 intraday use):
- If a minute-level bar set (e.g. 5m) is supplied via ``minute_bars`` and is
  long enough, the plugin prefers it over the daily ``bars`` — giving T0
  intraday decisions minute-resolution chan buy/sell points.
- Otherwise it falls back to the daily bars (original behavior), so the plugin
  stays backward-compatible with every existing caller (fusion / registry).
"""
from __future__ import annotations

from typing import Any

from trader_shared.config import CHANLUN_MIN_BARS
from trader_shared.interfaces import IndicatorPlugin

# 与引擎门槛共用，避免双份常量漂移导致「门槛过了但引擎仍返回空」
_MINUTE_MIN_BARS = CHANLUN_MIN_BARS


def _normalize_minute_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """分钟 K 归一化：确保每根 bar 的 ``date`` 是唯一、带时分秒的时间戳。

    ⚠️ 关键坑（否则整功能静默失效）：上游 ``light_data._fetch_mins_fallback`` /
    ``_fetch_mins_mootdx`` 把分钟 K 的 ``date`` 截断成「日」（如 "2026-07-16"），
    而完整时间戳放在 ``time`` 字段（"2026-07-16 09:35:00"）。
    ``ChanlunEngine._bar_id`` 以 ``bar['date']`` 作唯一身份，且 ``update_bar`` 只比对
    最后一根——若同一天所有 5m 棒的 ``date`` 都是同日，后一根会「覆盖」前一根，
    引擎塌缩成 1 根 → ``len(_raw) < CHANLUN_MIN_BARS`` → 缠论结果恒为 ``{}``。
    因此这里必须用带时分秒的 ``time``（或 ``datetime`` / ``day``）回填 ``date``，
    使每根 5m 棒在引擎里有唯一身份；缺失时间信息时才退化为空。
    """
    norm: list[dict[str, Any]] = []
    for b in bars:
        if not isinstance(b, dict):
            continue
        nb = dict(b)
        full_ts = nb.get("time") or nb.get("datetime") or nb.get("day") or ""
        if full_ts and (":" in str(full_ts) or " " in str(full_ts)):
            nb["date"] = str(full_ts)  # 带时分秒的完整时间戳 → 唯一身份
        elif not nb.get("date"):
            nb["date"] = str(full_ts) if full_ts else ""  # 兜底：完全没有时间信息才退化
        norm.append(nb)
    return norm


class ChanlunPlugin(IndicatorPlugin):
    """Chanlun analysis plugin — detects buy points, divergences, and trend labels.

    Timeframe: prefer ``minute_bars`` (e.g. 5m) when available and sufficient;
    otherwise fall back to the daily ``bars`` passed by the fusion layer.
    """

    def name(self) -> str:
        return "chanlun"

    def analyze(
        self,
        current: float,
        bars: list[dict[str, Any]],
        change_pct: float | None,
        quote: dict[str, Any],
        weekly_bars: list[dict[str, Any]] | None = None,
        minute_bars: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from trader_shared.chan_core import chanlun_strategy

        # 5m（分钟）优先，日线兜底
        if minute_bars and len(minute_bars) >= _MINUTE_MIN_BARS:
            eff = _normalize_minute_bars(minute_bars)
            # 5m 路径只算分钟级买卖点，不叠加周线 overlay（避免 timeframe 错配）
            out = chanlun_strategy(current, eff, change_pct, quote)
            # 修正 strategy 默认的 timeframe=daily 标签，避免分钟结果被误标
            if isinstance(out, dict) and isinstance(out.get("chanlun"), dict):
                out = {
                    **out,
                    "chanlun": {
                        **out["chanlun"],
                        "timeframe": "5m",
                        "data_bars_daily": None,
                        "data_bars_lower": len(eff),
                        "data_note": "5分钟数据充足",
                    },
                }
            return out
        # 日线路径：保留 weekly_bars 透传（ADR-002，中线回退依赖它，不可丢）
        return chanlun_strategy(current, bars, change_pct, quote, weekly_bars=weekly_bars)

    def weight(self) -> float:
        return 0.45  # Default weight in fusion (matches existing chan weight)
