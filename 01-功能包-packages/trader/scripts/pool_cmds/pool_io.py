"""选股池 I/O：路径、JSON 读写、offline/safe_build_report。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from pool_cmds._bootstrap import ensure_imports

ensure_imports()

from run_analysis import build_report
from trader_shared import candidate_core as core
from config import (
    ADMISSION_SCORE_EXECUTE,
    ADMISSION_SCORE_OBSERVE,
    CHAN_BASE,
    CHAN_STAGE_BONUS,
    CHAN_SCENE_BONUS,
    CHAN_CONFIRM_CLOSE_BONUS,
    CHAN_CONFIRM_FAR_BONUS,
    CHAN_BUYPOINT_BONUS,
    CHAN_DATA_INSUFFICIENT_PENALTY,
    CHIP_BASE,
    CHIP_ABOVE_STOP_BONUS,
    CHIP_IN_ZONE_BONUS,
    CHIP_UPSIDE_BONUS,
    FUSION_BONUS_SCALE,
    FUSION_DISAGREEMENT_CAP,
    ENABLE_RISK_REWARD_FILTER,
    RISK_REWARD_THRESHOLDS,
)

try:
    from trader_shared import get_market_level, get_market_note, write_stock
    from trader_shared.data_manager import DataManager
    from trader_shared.stage_positioning import assess_stage
    _SHARED_OK = True
except ImportError:
    import warnings
    warnings.warn(
        "[pool] shared module not available — market status and pool write are disabled.",
        stacklevel=2,
    )
    _SHARED_OK = False

    def get_market_level() -> str: return ""
    def get_market_note() -> str: return ""
    def write_stock(name: str, status: str, weight: int, source: str) -> None: pass

    def assess_stage(**kwargs: Any) -> dict[str, Any]:
        return {"major_stage": "蓄势", "momentum": "震荡", "stage_label": "蓄势期+震荡", "action": "等待", "max_position_pct": 0}

POOL_LIMIT = 20
EXECUTION_LIMIT = 3
CONTRACT_VERSION = "trader_pool_v1"

STAGE_PRIORITY = {"主升": 1, "蓄势": 2, "派发": 3, "衰退": 4}


def today_text() -> str:
    return date.today().isoformat()


def state_dir() -> Path:
    """~/.trader 或 TRADER_ROOT（trader_paths SSOT）。"""
    from trader_shared.trader_paths import path as trader_path

    root = trader_path("root")
    root.mkdir(parents=True, exist_ok=True)
    return root


def pool_path() -> Path:
    from trader_shared.trader_paths import path as trader_path

    return trader_path("pool")


def last_plan_path() -> Path:
    from trader_shared.trader_paths import path as trader_path

    return trader_path("last_plan")


def archive_path() -> Path:
    from trader_shared.trader_paths import path as trader_path

    return trader_path("pool_archive")


def pending_path() -> Path:
    from trader_shared.trader_paths import path as trader_path

    return trader_path("pending")


CONTRACT_VERSION_PENDING = "trader_pending_v1"


def empty_pending() -> dict[str, Any]:
    return {"contract_version": CONTRACT_VERSION_PENDING, "updated_at": today_text(), "items": []}

def load_pending() -> dict[str, Any]:
    """加载待确认池（load_state 内部使用 _read_lock 与 save_state 的 state_lock 互斥）"""
    payload = DataManager.load_state("pending", empty_pending())
    payload.setdefault("contract_version", CONTRACT_VERSION_PENDING)
    payload.setdefault("items", [])
    return payload

def save_pending(payload: dict[str, Any]) -> None:
    with DataManager.state_lock("pending"):
        payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        DataManager.save_state("pending", payload)


def price(value: Any) -> str:
    if value is None:
        return "无"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def price_yuan(value: Any) -> str:
    value_text = price(value)
    return "无" if value_text == "无" else f"{value_text}元"


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        backup = path.with_suffix(path.suffix + f".broken-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(path, backup)
        return default


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def empty_pool() -> dict[str, Any]:
    return {"contract_version": CONTRACT_VERSION, "updated_at": today_text(), "items": []}

def load_pool() -> dict[str, Any]:
    payload = DataManager.load_state("pool", empty_pool())
    payload.setdefault("contract_version", CONTRACT_VERSION)
    payload.setdefault("items", [])
    return payload

def save_pool(payload: dict[str, Any]) -> None:
    with DataManager.state_lock("pool"):
        payload["updated_at"] = today_text()
        DataManager.save_state("pool", payload)


def offline_report(target: str) -> dict[str, Any]:
    base = 10 + (sum(ord(char) for char in target) % 700) / 100
    support = round(base * 0.975, 2)
    confirm = round(base * 1.035, 2)
    stop = round(base * 0.945, 2)
    take = round(base * 1.09, 2)
    ma5 = round(base, 2)
    ma10 = round(base * 0.995, 2)
    ma20 = round(base * 0.99, 2)
    ma30 = round(base * 0.985, 2)
    ma250 = round(base * 1.05, 2)
    return {
        "name": target,
        "symbol": target,
        "current": round(base, 2),
        "change_pct": 0.0,
        "support": support,
        "resistance": take,
        "confirm": confirm,
        "stop": stop,
        "take": take,
        "stage": "蓄势",
        "major_stage": "蓄势",
        "momentum": "震荡",
        "short_term_momentum": "震荡",
        "stage_label": "蓄势期+震荡",
        "scene": "防守观察",
        "low_zone": f"{support:.2f}-{base:.2f}元",
        "volume_text": "离线样本，量能按待确认处理。",
        "volume_ratio": 1.0,
        "volume_warning": False,
        "upward_momentum": "价格还没贴近确认区，结论：动能仍是弱修复，暂不按启动处理。",
        "ma": {"ma5": f"{ma5:.2f}", "ma10": f"{ma10:.2f}", "ma20": f"{ma20:.2f}", "ma30": f"{ma30:.2f}", "ma250": f"{ma250:.2f}"},
        "ma_values": {"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma30": ma30, "ma250": ma250},
        "fusion": {
            "action": "观望",
            "confidence": 0,
            "weighted_score": 0.0,
            "regime": "",
            "hmm_regime": "range",
            "disagreement": 0,
            "signals_detail": {},
            "weights_used": {},
        },
        "chanlun": {"score": 0, "label": "离线"},
        "chan_buy_point_text": "无",
        "chan_trend_label": "数据不足",
        "chan_buy_point_types": [],
        "chan_sell_point_types": [],
        "chan_strokes_count": 0,
        "chan_divergence": {},
        "wyckoff_spring_signal": False,
        "wyckoff_upthrust_signal": False,
        "wyckoff": {"accumulation": False, "spring": False, "spring_signal": False},
        "fib_retrace": {"level_382": base * 0.618, "level_500": base * 0.5, "level_618": base * 0.382},
        "fib_ext_1382": round(base * 1.382, 2),
        "fib_ext_1618": round(base * 1.618, 2),
        "position_cap": {"sector_cap": 10, "score_cap": 10},
        "atr14": round(base * 0.03, 2),
        "atr_ratio": 0.03,  # 与 atr14≈3%×price 一致（旧值 1.0 会误判波幅偏高）
        "stage_status": "蓄势期+震荡",
        "data_note": "离线占位数据（offline_report），非实时分析结果。",
        "data_status": "offline",
        "data_freshness": "offline",
    }


def safe_build_report(target: str, offline: bool = False) -> dict[str, Any]:
    if offline:
        return offline_report(target)
    try:
        return build_report(target)
    except Exception as exc:
        report = offline_report(target)
        report["data_note"] = f"实时数据失败，使用离线占位：{exc}"
        return report

__all__ = [
    "ADMISSION_SCORE_EXECUTE",
    "ADMISSION_SCORE_OBSERVE",
    "CONTRACT_VERSION",
    "CONTRACT_VERSION_PENDING",
    "DataManager",
    "ENABLE_RISK_REWARD_FILTER",
    "EXECUTION_LIMIT",
    "POOL_LIMIT",
    "RISK_REWARD_THRESHOLDS",
    "STAGE_PRIORITY",
    "archive_path",
    "assess_stage",
    "empty_pending",
    "empty_pool",
    "get_market_level",
    "get_market_note",
    "last_plan_path",
    "load_json",
    "load_pending",
    "load_pool",
    "offline_report",
    "pending_path",
    "pool_path",
    "price",
    "price_yuan",
    "safe_build_report",
    "save_json",
    "save_pending",
    "save_pool",
    "state_dir",
    "today_text",
    "write_stock",
]
