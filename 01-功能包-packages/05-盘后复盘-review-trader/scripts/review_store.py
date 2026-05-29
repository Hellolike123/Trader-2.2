from __future__ import annotations

import json
from pathlib import Path
import os
from typing import Any
from trader_shared.data_manager import DataManager


def review_summary(review: dict[str, Any]) -> dict[str, Any]:
    q = review["quote"]
    theory = review["theory"]
    levels = review["levels"]
    chip_dist = review.get("chip_distribution", {})
    return {
        "contract": "review_trader_summary_v1",
        "name": review["name"],
        "symbol": review["symbol"],
        "date": review["date"],
        "session": review.get("session", "close"),
        "close": q.get("close") or q.get("current_price"),
        "change_pct": q.get("change_pct") or q.get("current_change_pct"),
        "state": review["summary"]["state"],
        "score": review["summary"]["score"],
        "structure_score": theory["scores"]["structure"],
        "volume_score": theory["scores"]["volume"],
        "chip_score": theory["scores"]["chip"],
        "momentum_score": theory["scores"]["momentum"],
        "key_pressure": levels["key_pressure"],
        "key_support": levels["key_support"],
        "first_support": levels["first_support"],
        "has_cost": review.get("cost") is not None,
        "pnl_pct": review.get("pnl_pct"),
        "action": review["summary"]["action"],
        "supports": theory["supports"][:3],
        "blocks": theory["blocks"][:3],
        "chip_peaks": chip_dist.get("peaks", []),
    }


CACHE_PATH: Path | None = None
CACHE_DIR: Path | None = None

def load_state() -> dict[str, Any]:
    return DataManager.load_state("review_state", {"reviews": []}, path=CACHE_PATH)


def save_review(review: dict[str, Any]) -> None:
    state = load_state()
    summary = review_summary(review)
    reviews = [
        item
        for item in state["reviews"]
        if not (
            item.get("symbol") == summary["symbol"]
            and item.get("date") == summary["date"]
            and item.get("session", "close") == summary["session"]
        )
    ]
    reviews.append(summary)
    state["reviews"] = reviews[-30:]
    DataManager.save_state("review_state", state, path=CACHE_PATH)

def recent_reviews(limit: int = 5) -> list[dict[str, Any]]:
    state = load_state()
    reviews = state["reviews"]
    if not reviews:
        return []
    latest_date = reviews[-1].get("date")
    latest_session = reviews[-1].get("session", "close")
    same_day = [item for item in reviews if item.get("date") == latest_date and item.get("session", "close") == latest_session]
    return same_day[-limit:]
