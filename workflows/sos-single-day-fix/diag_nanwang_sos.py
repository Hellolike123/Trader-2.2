#!/usr/bin/env python3
"""诊断南网日线 SOS 为何不亮。仓库根执行：

  python3 workflows/sos-single-day-fix/diag_nanwang_sos.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import trader_shared  # noqa: F401
except ImportError:
    _d = Path(__file__).resolve().parent
    for _ in range(8):
        if (_d / "trader_shared").is_dir():
            if str(_d) not in sys.path:
                sys.path.insert(0, str(_d))
            break
        if (_d / "02-共享模块-shared" / "trader_shared").is_dir():
            shared = str(_d / "02-共享模块-shared")
            if shared not in sys.path:
                sys.path.insert(0, shared)
            break
        _d = _d.parent
    else:
        raise

from trader_shared.light_data import load_market_snapshot, to_float
from trader_shared.wyckoff_core import wyckoff_analysis
from trader_shared.wyckoff_events import (
    _detect_sos,
    _detect_sos_at_tip,
    _detect_trading_range,
    _sos_baseline_avg_vol,
    _sos_thrust_baseline_vol,
    _sos_thrust_creek,
    _try_sos_thrust,
)


def main() -> None:
    snap = load_market_snapshot(
        "南网科技",
        days=300,
        include_5m=False,
        include_weekly=True,
        include_monthly=False,
        include_ticks=False,
    )
    db = list(snap.daily_bars or [])
    print("daily_bars", len(db))
    print("last5:")
    for b in db[-5:]:
        print(
            " ",
            b.get("date") or b.get("datetime"),
            b.get("open"),
            b.get("high"),
            b.get("low"),
            b.get("close"),
            b.get("volume"),
        )

    tr = _detect_trading_range(db)
    print("TR", tr)

    wa = wyckoff_analysis(db, symbol="688248")
    print(
        "sc",
        wa.get("sc_signal"),
        wa.get("sc_price"),
        "idx",
        wa.get("sc_bar_idx"),
        "ar",
        wa.get("ar_signal"),
        wa.get("ar_high"),
    )
    print(
        "sos",
        wa.get("sos_signal"),
        wa.get("sos_kind"),
        wa.get("sos_price"),
        wa.get("sos_reason"),
    )
    print("phase_a", wa.get("phase_a_status"), wa.get("phase_a_range"))

    sc_i = wa.get("sc_bar_idx")
    tr_ctx: dict = dict(tr) if isinstance(tr, dict) else {}
    pa = wa.get("phase_a_range") or {}
    tr_ctx["phase_a_range"] = pa
    if pa.get("ar_high") is not None:
        tr_ctx["ar_high"] = pa.get("ar_high")
    print("creek", _sos_thrust_creek(tr_ctx))

    floor = int(sc_i) if sc_i is not None else -1
    hits = []
    for i in range(max(floor + 1, 15), len(db)):
        r = _detect_sos_at_tip(db[: i + 1], tr_ctx)
        if r.get("sos_signal"):
            b = db[i]
            hits.append(
                (
                    i,
                    b.get("date") or b.get("datetime"),
                    r.get("sos_kind"),
                    r.get("sos_price"),
                    r.get("sos_reason"),
                )
            )
    print("post_sc_sos_hits", len(hits))
    for h in hits[-15:]:
        print(" ", h)

    print("--- gain>=4% bars after SC: thrust gate ---")
    for i in range(max(floor + 1, len(db) - 80), len(db)):
        b = db[i]
        o = to_float(b.get("open"))
        c = to_float(b.get("close"))
        v = to_float(b.get("volume"))
        if not o or not c or not v or c <= o:
            continue
        gain = (c - o) / o
        if gain < 0.04:
            continue
        sub = db[: i + 1]
        creek = _sos_thrust_creek(tr_ctx) or 0.0
        fb = _sos_baseline_avg_vol(sub, tr_ctx, robust=True)
        base = _sos_thrust_baseline_vol(sub, tr_ctx, creek, fb)
        thr = _try_sos_thrust(sub, tr_ctx, fb if fb > 0 else 1.0)
        print(
            i,
            b.get("date") or b.get("datetime"),
            f"g={gain*100:.1f}%",
            f"c={c}",
            f"v={v:.0f}",
            f"base={base:.0f}",
            f"ratio={(v/base) if base else 0:.2f}",
            f"creek={creek}",
            thr.get("sos_signal"),
            thr.get("sos_reason"),
        )

    # 主路径一次
    sc_i = wa.get("sc_bar_idx")
    try:
        sc_i = int(sc_i) if sc_i is not None else None
    except (TypeError, ValueError):
        sc_i = None
    main = _detect_sos(db, tr_ctx=tr_ctx, lookback_tips=30, min_tip_idx=sc_i)
    print("main_detect_sos", main)


if __name__ == "__main__":
    main()
