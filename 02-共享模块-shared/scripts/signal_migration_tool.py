#!/usr/bin/env python3
"""Signal Migration Tool.

Provides a helper utility to convert pre-existing historical signals in ~/.trader/signals.jsonl
and ~/.trader/signal_results.jsonl so that they have stable, correct signal_id values.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add parent directory to path to allow importing signal_tracker
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from signal_tracker import migrate_signal_ids
except ImportError:
    # Handle if run from another directory
    SHARED_DIR = SCRIPTS_DIR.parent
    if str(SHARED_DIR) not in sys.path:
        sys.path.insert(0, str(SHARED_DIR))
    from scripts.signal_tracker import migrate_signal_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy signal IDs and consolidate flat logs.")
    parser.add_argument("--force", action="store_true", help="Force recalculating signal IDs even if already present.")
    parser.add_argument("--signals", type=Path, default=None, help="Custom path to signals.jsonl")
    parser.add_argument("--results", type=Path, default=None, help="Custom path to signal_results.jsonl")
    parser.add_argument("--logs", type=Path, default=None, help="Custom path to signal_log.jsonl")
    args = parser.parse_args()

    print("🚀 Starting Signal ID Migration & Log Consolidation...")
    try:
        result = migrate_signal_ids(
            store_path=args.signals,
            results_path=args.results,
            force=args.force,
            log_path=args.logs
        )
        print("✅ Signal ID migration and log consolidation complete:")
        print(f"  signal_log.jsonl     : Consolidated {result.get('logs_consolidated', 0)} legacy flat logs into signals.jsonl")
        print(f"  signals.jsonl        : Migrated/Cleaned {result['signals_migrated']} records, skipped {result['signals_skipped']}")
        print(f"  signal_results.jsonl : Migrated/Cleaned {result['results_migrated']} records, skipped {result['results_skipped']}")
        return 0
    except Exception as e:
        print(f"❌ Error during migration: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
