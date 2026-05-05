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
from review_render import model_summary, render_json, render_single
from review_store import save_review


def _compute_display(review: dict) -> dict:
    theory = review["theory"]
    cost = review.get("cost")
    close = review["quote"]["close"]
    is_midday = review.get("session") == "midday"

    summary_text = model_summary(theory)

    state = theory["state"]
    if is_midday:
        conclusion = "午间弱修复，午后还要看是否重新放量。" if state == "弱修复观察" else "午间继续修复，但还没突破关键压力。" if state != "转强确认" else "午间尝试转强，午后还要看站稳。"
    else:
        conclusion = "弱修复观察，还不能按反转处理。" if state == "弱修复观察" else "短线止跌修复，但还不是反转。" if state != "转强确认" else "正在尝试转强，仍要看回踩确认。"

    if is_midday:
        one_liner = "午间有修复，还没过成本区。" if cost and close < cost else "午间方向不明，看午后确认。"
    elif cost and close < cost:
        one_liner = "现在不适合割肉，也不适合提前加仓。"
    else:
        one_liner = "现在不适合追高，先等关键位确认。"

    return {"model_summary_text": summary_text, "conclusion_text": conclusion, "one_liner_text": one_liner}


def run_single(target: str, cost: float | None = None, trade_date: str | None = None, output: str = "markdown", session: str = "close") -> str:
    review = build_review(target, cost=cost, trade_date=trade_date, session=session)
    enrich_with_signal_backtrack(review)
    review.update(_compute_display(review))
    save_review(review)
    if output == "json":
        return render_json(review)
    return render_single(review)
