from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from signal_contract import assert_valid_signal


DEFAULT_SIGNAL_STORE_PATH = Path(os.environ.get("TRADER_SIGNAL_STORE_PATH", Path.home() / ".trader" / "signals.jsonl"))


def append_signal(signal: dict[str, Any], path: Path | None = None) -> None:
    assert_valid_signal(signal)
    store_path = path or DEFAULT_SIGNAL_STORE_PATH
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with store_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(signal, ensure_ascii=False, sort_keys=True, default=str))
        handle.write("\n")


def load_recent_signals(symbol: str | None = None, limit: int = 20, path: Path | None = None) -> list[dict[str, Any]]:
    store_path = path or DEFAULT_SIGNAL_STORE_PATH
    if not store_path.exists():
        return []
    signals: list[dict[str, Any]] = []
    for line in store_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue
        if symbol and item.get("symbol") != symbol:
            continue
        signals.append(item)
    return signals[-limit:]
