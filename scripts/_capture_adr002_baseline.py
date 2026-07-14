"""[DEPRECATED] superseded by `scripts/golden_diff_gate.py capture` (unified seam).

Capture ADR-002 equivalence baseline from CURRENT build_report behavior.

Run BEFORE routing build_report through PluginRegistry.analyze_all().
Produces tests/fixtures/report_baseline.json with EXACT field values
(weighted_score, confidence, action, disagreement, midline dicts) used as the
ground truth by tests/test_build_report_adr002_equivalence.py.

The baseline is the only safe net for ADR-002 trap #2 (daily-chan silent drift
when weekly_bars is dropped): golden range-assertions cannot catch it, but an
exact field-by-field diff against this baseline can.

Usage:
  PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \
    python scripts/_capture_adr002_baseline.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent  # repo root
_SHARED = _REPO / "02-共享模块-shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import numpy as np  # noqa: E402


def _default(o):
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, set):
        return list(o)
    return str(o)


def _gen_bars(n, start, step):
    bars = []
    price = start
    for i in range(n):
        price = price + step * (1 if i % 2 == 0 else -1) + (i % 7 - 3) * 0.05
        o = price - 0.1
        c = price
        h = max(o, c) + 0.15
        l = min(o, c) - 0.15
        bars.append({
            "date": f"2026-0{i // 30 + 1:02d}-{i % 28 + 1:02d}",
            "open": round(o, 2),
            "close": round(c, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "volume": 1_000_000 + i * 1000,
            "atr14": 0.5,
            "atr_ratio": 0.02,
            "atr7": 0.4,
            "tr": 0.3,
            "pre_close": round(price - step, 2),
        })
    return bars


class _MockProvider:
    name = "mock"

    def resolve_security(self, target):
        from trader_shared.data_provider import Security
        return Security(code=target, market="SH" if target.startswith("6") else "SZ", name="测试股")

    def fetch_quote(self, sec):
        return {
            "name": "测试股", "symbol": sec.qq_symbol, "current_price": 10.5,
            "pre_close": 10.3, "volume": 5_000_000, "current_change_pct": 1.94,
            "trade_date": "2026-07-10", "trade_time": "15:00", "turnover_rate": 2.1,
        }

    def fetch_qfq_daily(self, sec, days=365):
        return _gen_bars(80, 9.0, 0.05)

    def fetch_kline(self, sec, **kw):
        return []

    def load_market_snapshot(self, target, days=365, include_5m=True,
                             include_weekly=True, include_monthly=True, include_ticks=True):
        from trader_shared.data_provider import MarketSnapshot
        daily = _gen_bars(80, 9.0, 0.05)
        weekly = _gen_bars(40, 9.0, 0.12)
        monthly = _gen_bars(16, 9.0, 0.4)
        bars_5m = _gen_bars(10, 10.4, 0.02)
        return MarketSnapshot(
            security=self.resolve_security(target),
            quote=self.fetch_quote(self.resolve_security(target)),
            daily_bars=daily,
            bars_5m=bars_5m,
            weekly_bars=weekly,
            monthly_bars=monthly,
            data_status="full",
        )


def main() -> None:
    from trader_shared.data_provider import set_provider
    from trader_shared import fetchers as _fetchers

    set_provider(_MockProvider())
    _fetchers.TencentFetcher = _fetchers.MockFetcher

    import trader_shared.market_env as _me
    import trader_shared.cache_utils as _cu
    _me.get_env_for_skill = lambda *a, **k: {"level": "正常", "hmm_regime_en": "range"}
    _cu.fetch_fund_flow_cached = lambda *a, **k: None

    from trader_shared.report_builder import build_report

    report = build_report("600000")
    fusion = report.get("fusion") or {}
    baseline = {
        "fusion_weighted_score": fusion.get("weighted_score"),
        "fusion_confidence": fusion.get("confidence"),
        "fusion_action": fusion.get("action"),
        "fusion_disagreement": fusion.get("disagreement"),
        "chanlun_midline": report.get("chanlun_midline"),
        "wyckoff_midline": report.get("wyckoff_midline"),
    }

    out = _SHARED / "tests" / "fixtures" / "report_baseline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2, default=_default), encoding="utf-8")
    print("BASELINE written:", out)
    print("  weighted_score =", baseline["fusion_weighted_score"])
    print("  confidence      =", baseline["fusion_confidence"])
    print("  action          =", baseline["fusion_action"])
    print("  disagreement    =", baseline["fusion_disagreement"])


if __name__ == "__main__":
    main()
