from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_PATH = Path.home() / ".trader" / "signal_log.jsonl"
LOG_DIR = LOG_PATH.parent

VALID_OUTCOMES = {"win", "loss", "expired", "stopped", "unknown", None}


def _ensure_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def stable_id(skill: str, target: str, date: str, signal_type: str) -> str:
    key = f"{date}::{skill}::{target}::{signal_type}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def log(
    skill: str,
    target: str,
    symbol: str,
    signal_type: str,
    price: float,
    env_level: str = "",
    env_note: str = "",
) -> str:
    today = _today()
    sig_id = stable_id(skill, target, today, signal_type)
    record = {
        "signal_id": sig_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "skill": skill,
        "target": target,
        "symbol": symbol,
        "signal_type": signal_type,
        "price": price,
        "env_level": env_level,
        "env_note": env_note,
        "outcome_pnl_pct": None,
        "outcome_days": None,
        "outcome": None,
        "filled_at": None,
    }
    _ensure_dir()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return sig_id


def log_safe(
    skill: str,
    target: str,
    symbol: str,
    signal_type: str,
    price: float,
    env_level: str = "",
    env_note: str = "",
) -> str:
    today = _today()
    sig_id = stable_id(skill, target, today, signal_type)
    if not LOG_PATH.exists():
        _create_record(sig_id, skill, target, symbol, signal_type, price, env_level, env_note)
        return sig_id
    records = _load_all()
    for r in records:
        if r.get("signal_id") == sig_id:
            return sig_id
    _create_record(sig_id, skill, target, symbol, signal_type, price, env_level, env_note)
    return sig_id


def _create_record(sig_id: str, skill: str, target: str, symbol: str, signal_type: str, price: float, env_level: str, env_note: str) -> None:
    record = {
        "signal_id": sig_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "skill": skill,
        "target": target,
        "symbol": symbol,
        "signal_type": signal_type,
        "price": price,
        "env_level": env_level,
        "env_note": env_note,
        "outcome_pnl_pct": None,
        "outcome_days": None,
        "outcome": None,
        "filled_at": None,
    }
    _ensure_dir()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def fill(signal_id: str, pnl_pct: float, days_held: int = 0, outcome: str = "unknown") -> tuple[bool, str]:
    if outcome not in VALID_OUTCOMES:
        return False, f"invalid outcome: {outcome}"
    if not LOG_PATH.exists():
        return False, "log file not found"
    lines = LOG_PATH.read_text(encoding="utf-8").strip().split("\n")
    found = False
    new_lines = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        if rec.get("signal_id") == signal_id:
            rec["outcome_pnl_pct"] = round(pnl_pct, 2)
            rec["outcome_days"] = days_held
            rec["outcome"] = outcome
            rec["filled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            found = True
        new_lines.append(json.dumps(rec, ensure_ascii=False))
    if found:
        LOG_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True, "ok"
    return False, "signal_id not found"


def fill_by_target(target: str, pnl_pct: float, days_held: int = 0, outcome: str = "unknown") -> tuple[int, list[str]]:
    if not LOG_PATH.exists():
        return 0, []
    lines = LOG_PATH.read_text(encoding="utf-8").strip().split("\n")
    updated = []
    new_lines = []
    for line in lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        if rec.get("target") == target and rec.get("outcome_pnl_pct") is None:
            rec["outcome_pnl_pct"] = round(pnl_pct, 2)
            rec["outcome_days"] = days_held
            rec["outcome"] = outcome
            rec["filled_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            updated.append(rec.get("signal_id"))
        new_lines.append(json.dumps(rec, ensure_ascii=False))
    if updated:
        LOG_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return len(updated), updated


def _load_all() -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    records = []
    for line in LOG_PATH.read_text(encoding="utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def load_recent(
    target: str = "",
    symbol: str = "",
    skill: str = "",
    signal_type: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    records = _load_all()
    filtered = []
    for r in records:
        if target and str(r.get("target") or "") != target:
            continue
        if symbol and str(r.get("symbol") or "") != symbol:
            continue
        if skill and str(r.get("skill") or "") != skill:
            continue
        if signal_type and str(r.get("signal_type") or "") != signal_type:
            continue
        filtered.append(r)
    return filtered[-limit:]


def stats(
    skill: str = "",
    signal_type: str = "",
    target: str = "",
    months: int = 1,
) -> dict[str, Any]:
    records = _load_all()
    cutoff = f"{datetime.now().year}-{datetime.now().month:02d}-01" if months <= 1 else ""
    filtered = []
    for r in records:
        if skill and r.get("skill") != skill:
            continue
        if signal_type and r.get("signal_type") != signal_type:
            continue
        if target and r.get("target") != target:
            continue
        ts = str(r.get("timestamp") or "")
        if cutoff and ts[:7] < cutoff:
            continue
        filtered.append(r)

    total = len(filtered)
    filled = [r for r in filtered if r.get("outcome_pnl_pct") is not None]
    wins = [r for r in filled if (r.get("outcome_pnl_pct") or 0) > 0]
    losses = [r for r in filled if (r.get("outcome_pnl_pct") or 0) <= 0]

    outcomes: dict[str, int] = {}
    for r in filled:
        o = r.get("outcome") or "unknown"
        outcomes[o] = outcomes.get(o, 0) + 1

    return {
        "total_signals": total,
        "filled_count": len(filled),
        "pending": total - len(filled),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(filled), 2) if filled else 0.0,
        "avg_gain_pct": round(sum(r.get("outcome_pnl_pct") or 0 for r in wins) / len(wins), 2) if wins else 0.0,
        "avg_loss_pct": round(sum(r.get("outcome_pnl_pct") or 0 for r in losses) / len(losses), 2) if losses else 0.0,
        "outcomes": outcomes,
    }


def stats_by_type(skill: str = "", target: str = "") -> dict[str, dict[str, Any]]:
    records = _load_all()
    types: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if skill and r.get("skill") != skill:
            continue
        if target and r.get("target") != target:
            continue
        st = str(r.get("signal_type") or "")
        types.setdefault(st, []).append(r)

    result = {}
    for st, recs in types.items():
        filled = [r for r in recs if r.get("outcome_pnl_pct") is not None]
        wins = [r for r in filled if (r.get("outcome_pnl_pct") or 0) > 0]
        result[st] = {
            "total": len(recs),
            "filled": len(filled),
            "pending": len(recs) - len(filled),
            "wins": len(wins),
            "losses": len(filled) - len(wins),
            "win_rate": round(len(wins) / len(filled), 2) if filled else 0.0,
            "avg_gain": round(sum(r.get("outcome_pnl_pct") or 0 for r in wins) / len(wins), 2) if wins else 0.0,
            "avg_loss": round(sum(r.get("outcome_pnl_pct") or 0 for r in filled if (r.get("outcome_pnl_pct") or 0) <= 0) / max(len(filled) - len(wins), 1), 2),
        }
    return result


if __name__ == "__main__":
    sid = log_safe("trader", "南网科技", "688248.SH", "低吸观察", 54.91, "偏弱", "中证1000 五日线下")
    print("logged:", sid)
    ok, _ = fill(sid, 3.5, 5, "win")
    print("filled:", ok)
    print("stats:", stats(skill="trader"))
    print("by type:", stats_by_type("trader"))
    print("recent:", load_recent(target="南网科技"))
