#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

# 确保 trader_shared 可导入（pack 后在 scripts/ 下，hermes 运行时 sys.path 可能不包含 scripts/）
# Ensure trader_shared package can be imported by adding workspace shared module path
_SCRIPT_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
_SHARED_MODULE_PATH = _WORKSPACE_ROOT / "02-共享模块-shared"
for p in (_WORKSPACE_ROOT, _SHARED_MODULE_PATH, _SCRIPT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import argparse
import json
import traceback
from typing import Any

from trader_shared._logging import get_logger
_logger = get_logger(__name__)

SCRIPT_DIR = _SCRIPT_DIR
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    import trader_shared
except ImportError:
    _d = Path(__file__).resolve().parent
    for _ in range(8):
        if (_d / "trader_shared").is_dir():
            if str(_d) not in sys.path:
                sys.path.insert(0, str(_d))
            import trader_shared
            break
        _d = _d.parent
    else:
        raise

from trader_shared.light_data import to_float, pct_change
from trader_shared.stage_positioning import assess_stage, compute_exit_plan, compute_stage_stop, check_time_stop, evaluate_position_state, _detect_major_stage
from trader_shared.fetchers import TencentFetcher
from trader_shared.indicator_math import aggregate_5m_to_60m, calc_supertrend, calc_vwap

from trader_shared.chip_core import analyze_chips_and_migration
from config import (
    LOOKBACK_DAYS,
    STRUCTURE_WINDOW,
    ENABLE_RISK_REWARD_FILTER,
    RISK_REWARD_THRESHOLDS,
    KELLY_MAX_TOTAL_POSITIONS,
    KELLY_MIN_TRADES,
)
try:
    from trader_shared.models import DATA_STATUS_MAP
except ImportError:
    DATA_STATUS_MAP: dict[str, str] = {
        "complete": "full",
        "partial": "partial",
        "degraded": "degraded",
        "failed": "degraded",
    }

_run_analysis_shared_failed = False

try:
    from trader_shared import conflicting_signals, get_market_level, get_market_note, write_stock, log, stats_by_type
    from trader_shared import get_env_for_skill
    track_log = log
except ImportError:
    import warnings
    if not _run_analysis_shared_failed:
        _run_analysis_shared_failed = True
        warnings.warn(
            "[trader] shared module not available — market status, signal tracking, and pool operations are disabled. "
            "The report will still be generated but may lack market context and pool integration.",
            stacklevel=2,
        )

    def _empty_str(*a, **k): return ""
    def _empty_list(*a, **k): return []
    def _empty_dict(*a, **k): return {}
    def _empty_fn(*a, **k): return None
    conflicting_signals = _empty_list
    get_market_level = _empty_str
    get_market_note = _empty_str
    get_env_for_skill = _empty_dict
    write_stock = _empty_fn
    track_log = _empty_fn
    stats_by_type = _empty_dict



from trader_shared.signal_contract import assert_valid_signal
from trader_shared.signal_core import (
    clear_signals_cache,
    read_signals_for_report,
    load_historical_win_rate,
    get_pool_count,
    build_signal,
    one_sentence,
    state_text,
    _map_fusion_to_signal,
)
from datetime import date
import os

# Compatibility aliases for testing
_clear_signals_cache = clear_signals_cache
_read_signals_for_report = read_signals_for_report
_load_historical_win_rate = load_historical_win_rate
_pool_count = get_pool_count


from trader_shared.report_builder import (
    _get_kelly_data,
    _get_major_stage,
    _degraded_quote_report,
    today_text,
    _signal_type_label,
    _signal_direction_text,
    _fusion_breakdown,
    price,
    pct,
    build_report,
    numeric_values,
    ma_text,
    determine_stage,
    structure_replay,
    chunks,
    short_date,
    sync_report_with_data,
    volume_observation,
    upward_momentum_observation,
    _get_buy_label,
    _calc_volume_ratio_from_bars,
    render_markdown,
    signal_state,
    signal_max_total_pct,
    signal_risk_flags,
    structure_view,
    volume_view,
    generate_alert,
    build_watch_alert,
    action_text_for_scene,
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes-compatible Trader report renderer.")
    parser.add_argument("--mode", choices=["http-single"], required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", choices=["markdown", "json", "signal-json", "alert-text"], default="markdown")
    parser.add_argument("--cost", type=float, default=0.0, help="持仓成本价（用于显示持仓建议和盈亏分析）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args.target, cost_price=args.cost)
    except Exception as exc:
        print(f"Trader数据获取失败：{exc}", file=sys.stderr)
        return 1

    try:
        from trader_shared.candidate_core import STATUS_SCORE
        write_stock(
            report["name"],
            report["scene"],
            int(STATUS_SCORE.get(report["scene"], 0)),
            "trader",
        )
    except Exception:
        pass

    try:
        track_log(
            "trader",
            report["name"],
            str(report.get("symbol") or ""),
            report["scene"],
            float(report.get("current") or 0),
            get_market_level(),
            get_market_note(),
        )
    except Exception:
        pass

    # 预计算 Kelly 数据（同一进程内只读一次文件，供 render_markdown 使用）
    market_env_data = report.get("market_env") or {}
    _kelly = _get_kelly_data(market_env_data.get("level", "正常"))

    if args.output == "json":
        markdown = render_markdown(report, _kelly_cache_only=_kelly)
        print(json.dumps({"full_markdown": markdown, "report": report, "signal": build_signal(report)}, ensure_ascii=False, indent=2, default=str))
    elif args.output == "signal-json":
        print(json.dumps(build_signal(report), ensure_ascii=False, indent=2, default=str))
    else:
        print(render_markdown(report, _kelly_cache_only=_kelly))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

