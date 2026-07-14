"""[DEPRECATED] superseded by `scripts/golden_diff_gate.py capture` (unified seam).

Deterministic render-equivalence capture for the domain/presentation split.

Runs build_report + render_markdown under a FULLY OFFLINE, deterministic mock
seam (all network leak points patched), masks date tokens, and writes the
masked markdown to the path given as argv[1].

Run BEFORE the split  -> pre baseline
Run AFTER the split   -> post baseline
Diff the two; they must be byte-identical (modulo DATE mask) to prove the
split is behavior-preserving.

Usage:
  PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts \
    python scripts/_render_eq_capture.py <out_path>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SHARED = _REPO / "02-共享模块-shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))


def _mask_dates(text: str) -> str:
    return re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", text)


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
            "open": round(o, 2), "close": round(c, 2),
            "high": round(h, 2), "low": round(l, 2),
            "volume": 1_000_000 + i * 1000,
            "atr14": 0.5, "atr_ratio": 0.02, "atr7": 0.4, "tr": 0.3,
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
            daily_bars=daily, bars_5m=bars_5m,
            weekly_bars=weekly, monthly_bars=monthly, data_status="full",
        )


class _UnavailableClient:
    available = False


def main() -> None:
    import trader_shared.tushare_client as _tc
    import trader_shared.chip_data as _chip
    import trader_shared.market_env as _me
    import trader_shared.cache_utils as _cu
    from trader_shared import fetchers as _fetchers
    from trader_shared.data_provider import set_provider

    # --- offline deterministic seam (patch ALL network leak points) ---
    set_provider(_MockProvider())
    _fetchers.TencentFetcher = _fetchers.MockFetcher
    _me.get_env_for_skill = lambda *a, **k: {"level": "正常", "hmm_regime_en": "range"}
    _cu.fetch_fund_flow_cached = lambda *a, **k: None
    _tc.get_client = lambda *a, **k: _UnavailableClient()      # sector -> None fast
    _chip.get_cyq_perf = lambda *a, **k: None                  # chip -> None fast

    from trader_shared.report_builder import build_report, render_markdown

    report = build_report("600000")
    md = render_markdown(report)
    masked = _mask_dates(md)

    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(masked, encoding="utf-8")
    print("RENDER EQ CAPTURE ->", out)
    print("  len =", len(masked), "lines =", masked.count("\n") + 1)


if __name__ == "__main__":
    main()
