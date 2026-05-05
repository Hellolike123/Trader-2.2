from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SHARED_MARKET = _ROOT / "02-共享模块-shared" / "01-行情数据-market-data"
_SHARED_CANDIDATE = _ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
for _p in (_SHARED_MARKET, _SHARED_CANDIDATE):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from review_model import build_review, enrich_with_signal_backtrack
from review_render import render_json, render_single
from review_store import save_review


def run_single(target: str, cost: float | None = None, trade_date: str | None = None, output: str = "markdown", session: str = "close") -> str:
    review = build_review(target, cost=cost, trade_date=trade_date, session=session)
    enrich_with_signal_backtrack(review)
    save_review(review)
    if output == "json":
        return render_json(review)
    return render_single(review)
