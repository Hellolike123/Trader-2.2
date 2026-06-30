#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

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
    WYCKOFF_BASE,
    WYCKOFF_VOL_AMPLIFY_BONUS,
    WYCKOFF_VOL_SHRINK_BONUS,
    WYCKOFF_VOL_NORMAL_BONUS,
    WYCKOFF_MOMENTUM_PASS_BONUS,
    WYCKOFF_SPRING_BONUS,
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
    root = Path.home() / ".trader"
    root.mkdir(parents=True, exist_ok=True)
    return root


def pool_path() -> Path:
    return state_dir() / "pool.json"


def last_plan_path() -> Path:
    return state_dir() / "last_plan.json"


def archive_path() -> Path:
    return state_dir() / "pool_archive.json"


def pending_path() -> Path:
    return state_dir() / "pending.json"


CONTRACT_VERSION_PENDING = "trader_pending_v1"


def empty_pending() -> dict[str, Any]:
    return {"contract_version": CONTRACT_VERSION_PENDING, "updated_at": today_text(), "items": []}

def load_pending() -> dict[str, Any]:
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
        "scene": "防守观察",
        "low_zone": f"{support:.2f}-{base:.2f}元",
        "volume_text": "离线样本，量能按待确认处理。",
        "upward_momentum": "价格还没贴近确认区，结论：动能仍是弱修复，暂不按启动处理。",
        "ma": {"ma5": f"{base:.2f}", "ma10": f"{base * 0.995:.2f}", "ma20": f"{base * 0.99:.2f}", "ma30": f"{base * 0.985:.2f}"},
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


def to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def momentum_passes(report: dict[str, Any]) -> bool:
    current = to_float(report.get("current")) or 0.0
    confirm = to_float(report.get("confirm")) or current
    ma = report.get("ma") or {}
    ma5 = to_float(ma.get("ma5"))
    ma10 = to_float(ma.get("ma10"))
    ma20 = to_float(ma.get("ma20"))
    near_confirm = current >= confirm * 0.985
    ma_support = ma5 is not None and ma10 is not None and ma20 is not None and ma5 >= ma10 and current >= ma20
    stage_ok = report.get("stage") in {"走强", "修复"}
    scene_ok = report.get("scene") in {"等转强", "突破确认", "突破观察", "冲高减仓"}
    return bool((near_confirm and ma_support) or (stage_ok and scene_ok and ma_support))


def score_report(report: dict[str, Any]) -> dict[str, int]:
    current = to_float(report.get("current")) or 0.0
    confirm = to_float(report.get("confirm")) or current
    stop = to_float(report.get("stop")) or current
    support = to_float(report.get("support")) or current
    take = to_float(report.get("take")) or confirm
    stage = str(report.get("stage") or "")
    scene = str(report.get("scene") or "")
    chan = CHAN_BASE
    wyckoff = WYCKOFF_BASE
    chip = CHIP_BASE

    # ── 缠论分：阶段 + 场景 + 确认位距离 ──
    chan += CHAN_STAGE_BONUS.get(stage, 0)
    chan += CHAN_SCENE_BONUS.get(scene, 0)

    if current and confirm:
        distance = abs(confirm - current) / max(current, 0.01)
        if distance <= 0.02:
            chan += CHAN_CONFIRM_CLOSE_BONUS
        elif distance <= 0.05:
            chan += CHAN_CONFIRM_FAR_BONUS

    # ── 威科夫分：量价 + 动量 ──
    volume_text = str(report.get("volume_text") or "")
    if "放大" in volume_text or "放量" in volume_text:
        wyckoff += WYCKOFF_VOL_AMPLIFY_BONUS
    elif "缩量" in volume_text or "收缩" in volume_text:
        wyckoff += WYCKOFF_VOL_SHRINK_BONUS
    else:
        wyckoff += WYCKOFF_VOL_NORMAL_BONUS
    if momentum_passes(report):
        wyckoff += WYCKOFF_MOMENTUM_PASS_BONUS

    # ── 筹码分：价格位置 ──
    if current > stop:
        chip += CHIP_ABOVE_STOP_BONUS
    if support <= current <= max(confirm, support):
        chip += CHIP_IN_ZONE_BONUS
    if take > current:
        chip += CHIP_UPSIDE_BONUS

    # ── 缠论分：买点 + 数据充分性 ──
    chan_bps = str(report.get("chan_buy_point_text", ""))
    for bp_key, bp_bonus in CHAN_BUYPOINT_BONUS.items():
        if bp_key in chan_bps:
            chan += bp_bonus
            break
    chan_trend = str(report.get("chan_trend_label", ""))
    if report.get("chan_strokes_count", 0) < 2 and chan_trend == "数据不足":
        chan -= CHAN_DATA_INSUFFICIENT_PENALTY
    chan = max(0, min(45, chan))

    # ── 威科夫分：spring ──
    if report.get("wyckoff_spring_signal", False):
        wyckoff += WYCKOFF_SPRING_BONUS
    wyckoff = max(0, min(30, wyckoff))
    chip = max(0, min(25, chip))

    # ── 融合层 bonus: weighted_score(-1.35~1.35) → -20~+20 分 ──
    fusion = report.get("fusion", {}) or {}
    fw = to_float(fusion.get("weighted_score")) if isinstance(fusion, dict) else None
    fd = to_float(fusion.get("disagreement")) if isinstance(fusion, dict) else None
    fw = fw or 0.0
    fd = fd or 0.0
    fusion_bonus = max(-20, min(20, round(fw * FUSION_BONUS_SCALE)))
    if fd > 1:
        fusion_bonus = max(-FUSION_DISAGREEMENT_CAP, min(FUSION_DISAGREEMENT_CAP, fusion_bonus))

    from trader_shared.momentum_core import assess_momentum
    daily_bars = report.get("bars") or report.get("daily_bars") or []
    momentum_result = assess_momentum(daily_bars) if len(daily_bars) >= 30 else {"direction": "insufficient", "score": 0}
    momentum_dir = momentum_result.get("direction", "insufficient")
    momentum_score_val = min(20, max(0, momentum_result.get("score", 0) // 5))
    mom_tag = {"bullish": "🟢看多", "bearish": "🔴看空", "neutral": "🟡中性"}.get(momentum_dir, "⚪数据不足")
    total = max(0, min(100, chan + wyckoff + chip + fusion_bonus))
    return {"chanlun_score": chan, "wyckoff_score": wyckoff, "chip_score": chip, "fusion_score": fusion_bonus, "total_score": total, "momentum_score": momentum_score_val, "momentum_tag": mom_tag}


def _evaluate_admission(major_stage: str, total_score: int, current: float, confirm: float, stop: float) -> dict[str, str]:
    """三关筛选统一实现：阶段筛选 → 评分门槛 → 风控检查。

    Returns:
        {"result": "入池"|"待补"|"拒绝", "reason": str, "status": "执行"|"观察"|"淘汰"}
    """
    # 第一关：阶段筛选 — 衰退期直接拒绝
    if major_stage == "衰退":
        return {"result": "拒绝", "reason": "衰退期，直接拒绝入池。", "status": "淘汰"}

    # 第二关：评分门槛（查表）
    exec_threshold = ADMISSION_SCORE_EXECUTE.get(major_stage, 999)
    obs_threshold = ADMISSION_SCORE_OBSERVE.get(major_stage, 999)

    if total_score >= exec_threshold:
        status = "执行"
    elif total_score >= obs_threshold:
        status = "观察"
    else:
        threshold = min(exec_threshold, obs_threshold)
        return {"result": "待补", "reason": f"{major_stage}期但评分不足{threshold}，暂不入池。", "status": "观察"}

    # 第三关：风控检查 — 现价跌破止损
    if stop > 0 and current <= stop:
        return {"result": "拒绝", "reason": "现价跌破防守位，结构审查失败。", "status": "淘汰"}
    if confirm <= 0 or stop <= 0:
        return {"result": "待补", "reason": "触发位或防守位不清楚，暂不参与排序。", "status": "观察"}

    return {"result": "入池", "reason": "结构成立，触发位和防守位清楚。", "status": status}


def admission_for(report: dict[str, Any], scores: dict[str, int]) -> dict[str, str]:
    """三关筛选入口（从 report/scores 提取参数后委托 _evaluate_admission）。"""
    current = to_float(report.get("current")) or 0.0
    confirm = to_float(report.get("confirm")) or current
    stop = to_float(report.get("stop")) or current
    major_stage = str(report.get("major_stage") or "蓄势")
    total_score = scores["total_score"]
    return _evaluate_admission(major_stage, total_score, current, confirm, stop)


def structure_summary(report: dict[str, Any]) -> str:
    stage = str(report.get("stage") or "待补")
    scene = str(report.get("scene") or "待补")
    if scene in {"等转强", "突破确认", "突破观察", "冲高减仓"}:
        return f"{stage}中，接近确认位，等待放量站稳。"
    if scene in {"低吸观察", "防守观察", "防守观察，趋势下行谨慎"}:
        return f"{stage}观察，防守位未破，等待止跌确认。"
    if scene == "暂不碰":
        return "结构偏弱，防守逻辑不清。"
    return f"{stage}结构，{scene}。"


def momentum_text(report: dict[str, Any]) -> str:
    ma = report.get("ma") or {}
    if momentum_passes(report):
        return f"通过｜MA5 {ma.get('ma5', '--')} / MA10 {ma.get('ma10', '--')} 向上，价格接近确认位。"
    return f"未通过｜量价或均线未形成执行确认，MA5 {ma.get('ma5', '--')} / MA10 {ma.get('ma10', '--')}。"


def record_from_report(target: str, report: dict[str, Any], offline: bool = False) -> dict[str, Any]:
    scores = score_report(report)
    admission = admission_for(report, scores)
    now = today_text()
    atr14 = to_float(report.get("atr14")) or 0.0
    atr_ratio = to_float(report.get("atr_ratio")) or 0.0
    atr_level, atr_cap = core.atr_volatility_level(atr_ratio) if atr14 > 0 and atr_ratio > 0 else ("", 0)
    major_stage = str(report.get("major_stage") or "蓄势")
    momentum = str(report.get("short_term_momentum") or "震荡")
    stage_status = str(report.get("stage_label") or f"{major_stage}期+{momentum}")
    record = {
        "target": target,
        "name": report.get("name") or target,
        "symbol": report.get("symbol") or target,
        "added_at": now,
        "updated_at": now,
        "status": admission["status"],
        "admission_result": admission["result"],
        "admission_reason": admission["reason"],
        "structure_summary": structure_summary(report),
        "trigger": round(float(report.get("confirm") or 0), 2),
        "defense": round(float(report.get("stop") or 0), 2),
        "confirm": round(float(report.get("confirm") or 0), 2),
        "support": round(float(report.get("support") or 0), 2),
        "current": round(float(report.get("current") or 0), 2),
        "momentum_state": "通过" if momentum_passes(report) else "未通过",
        "momentum_text": momentum_text(report),
        "offline": offline or bool(report.get("data_note")),
        "data_freshness": report.get("data_freshness", "live"),
        "atr14": atr14,
        "atr_ratio": atr_ratio,
        "atr_level": atr_level,
        "atr_cap": atr_cap,  # ATR 波动率决定的单票最大仓位（硬上限）
        "fusion_action": (report.get("fusion") or {}).get("action"),
        "fusion_confidence": (report.get("fusion") or {}).get("confidence"),
        "fusion_score": (report.get("fusion") or {}).get("weighted_score"),
        "major_stage": major_stage,
        "momentum": momentum,
        "stage_status": stage_status,
        **scores,
    }
    # 计算盈亏比存入记录
    # 使用 trigger（确认位/实际执行入场价）而非 support（支撑位）作为入场价，
    # 因为当 trigger > support 时（突破策略），用 support 会虚增盈亏比。
    trigger_val = record.get("trigger", 0.0)
    stop_val = record.get("defense", 0.0)
    take_val = round(float(report.get("take") or 0), 2)
    risk_reward = None  # None 表示无法计算，0.0 表示计算为 0
    if stop_val > 0 and trigger_val > stop_val and take_val > trigger_val:
        risk_reward = round((take_val - trigger_val) / (trigger_val - stop_val), 1)
    record["take"] = take_val
    record["risk_reward"] = risk_reward
    return record


def active_items(pool: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in pool.get("items", []) if item.get("status") in {"执行", "观察", "淘汰"}]


def _fusion_confidence_rank(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        text = str(value).strip().lower()
        return {"low": 1, "medium": 2, "high": 3}.get(text, 0)


STAGE_STRENGTH = {"主升": 1.0, "拉升": 0.9, "蓄势偏强": 0.8, "蓄势": 0.5, "蓄势偏弱": 0.3, "派发": 0.2, "衰退": 0.0}


def sort_items_unified(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """统一排序：plan 和 rank 共用同一个排序逻辑。
    
    主键：status（执行 > 观察 > 淘汰）
    次键：融合置信度 × 40% + 总分归一化 × 30% + 阶段强度 × 30%
    附加：盈亏比提权（评分 × (1 + min(盈亏比-1,2) × 0.1)）
    """
    status_rank = {"执行": 3, "观察": 2, "淘汰": 1}
    def _composite(item: dict[str, Any]) -> float:
        conf = float(item.get("fusion_confidence") or 0)
        score = int(item.get("total_score") or 0)
        stage = str(item.get("major_stage") or "蓄势")
        stage_str = STAGE_STRENGTH.get(stage, 0.5)
        composite = conf * 0.4 + (score / 100.0) * 0.3 + stage_str * 0.3
        # R4: 盈亏比排序加分
        rr = to_float(item.get("risk_reward")) or 0
        if rr > 1.0 and ENABLE_RISK_REWARD_FILTER:
            rr_bonus = min(rr - 1.0, 2.0) * 0.1
            composite *= (1.0 + rr_bonus)
        return composite
    
    return sorted(
        items,
        key=lambda item: (
            status_rank.get(str(item.get("status")), 0),
            _composite(item),
        ),
        reverse=True,
    )


def sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_rank = {"执行": 3, "观察": 2, "淘汰": 1}
    return sorted(
        items,
        key=lambda item: (
            status_rank.get(str(item.get("status")), 0),
            int(item.get("total_score") or 0),
            -float(item.get("atr_ratio") or 0),
            _fusion_confidence_rank(item.get("fusion_confidence")),
        ),
        reverse=True,
    )


def sort_items_by_stage(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_rank = {"执行": 3, "观察": 2, "淘汰": 1}
    return sorted(
        items,
        key=lambda item: (
            STAGE_PRIORITY.get(str(item.get("major_stage") or "蓄势"), 5),
            status_rank.get(str(item.get("status")), 0),
            int(item.get("total_score") or 0),
        ),
    )


def counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "执行": len([item for item in items if item.get("status") == "执行"]),
        "观察": len([item for item in items if item.get("status") == "观察"]),
        "淘汰": len([item for item in items if item.get("status") == "淘汰"]),
    }


def cmd_analyze(args: argparse.Namespace) -> int:
    report = safe_build_report(args.target, args.offline)
    record = record_from_report(args.target, report, args.offline)
    print("入池建议")
    print("")
    print(f"结果：{record['admission_result']}")
    print(f"理由：{record['admission_reason']}")
    print(f"建议状态：{record['status']}")
    print(f"触发：{price_yuan(record['trigger'])}")
    print(f"防守：{price_yuan(record['defense'])}")
    print("下一步：如确认，请说“加入选股池”")
    if record.get("atr14") and record.get("atr14") > 0:
        atr14 = record["atr14"]
        atr_ratio = record["atr_ratio"]
        atr_level = record["atr_level"]
        atr_cap = record["atr_cap"]
        print("")
        print("📊 ATR入池检查")
        print(f"ATR {atr14:.2f}元（{atr_ratio*100:.2f}%） {atr_level}")
        print(f"建议首仓：≤{atr_cap}%")
        if atr_ratio >= 0.03:
            print("该标的波动过大，建议暂缓入池")
        elif atr_ratio >= 0.02:
            print("高波动标的，入池后仓位需严格卡上限")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    pool = load_pool()
    report = safe_build_report(args.target, args.offline)
    record = record_from_report(args.target, report, args.offline)

    # admission 门控：拒绝/待补的票不允许入池
    admission_result = record.get("admission_result", "入池")
    if admission_result in ("拒绝", "待补"):
        reason = record.get("admission_reason", "未通过筛选")
        print(f"入池被拒：{reason}")
        print(f"当前状态：{record['status']}  评分：{record['total_score']}  阶段：{record.get('major_stage', '?')}")
        return 3

    items = list(pool.get("items", []))
    existing_index = next((index for index, item in enumerate(items) if args.target in {str(item.get("target")), str(item.get("name")), str(item.get("symbol"))}), None)
    if existing_index is None and len(items) >= POOL_LIMIT:
        print(f"候选池容量已满：{len(items)}/{POOL_LIMIT}")
        print("新票入池前，请先移除、淘汰或替换一只旧票。")
        return 3
    if existing_index is None:
        items.append(record)
    else:
        record["added_at"] = items[existing_index].get("added_at") or record["added_at"]
        items[existing_index] = record
    pool["items"] = items
    save_pool(pool)
    try:
        write_stock(record["name"], record["status"], record["total_score"], "pool")
    except Exception:
        pass
    print("已加入选股池")
    print(f"当前容量：{len(items)}/{POOL_LIMIT}")
    print(f"状态：{record['status']}")
    print(f"触发：{price(record['trigger'])}")
    print(f"防守：{price(record['defense'])}")
    print("下一步：盘后可说“生成明日作战表”。")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    pool = load_pool()
    items = sort_items(active_items(pool))
    items = _refresh_pool_prices(items, pool)
    count = counts(items)
    print(f"选股池 {len(items)}/{POOL_LIMIT}")
    # P0 Fix: 检查疑似停牌
    stale_warnings = _check_stale_items(items)
    if stale_warnings:
        for w in stale_warnings:
            print(w)
    print("")
    for item in items:
        stage_str = str(item.get("stage_status") or item.get("major_stage", "蓄势") + "+" + item.get("momentum", "震荡"))
        name = item.get("name", "?")
        status = item.get("status", "?")
        trigger = price(item.get("trigger"))
        defense = price(item.get("defense"))
        print(f"{name}  {stage_str}  {status}  触发{trigger}  防守{defense}")
    return 0


def rank_status(item: dict[str, Any]) -> str:
    if item.get("_stop_broken"):
        return "已破止损"
    if item.get("status") == "执行":
        return "等转强" if item.get("momentum_state") != "通过" else "低吸观察"
    if item.get("status") == "观察":
        return "防守观察"
    return "暂不碰"


def atr_inline(item: dict[str, Any]) -> str:
    atr14 = to_float(item.get("atr14")) or 0.0
    atr_ratio = to_float(item.get("atr_ratio")) or 0.0
    if atr14 <= 0 or atr_ratio <= 0:
        return ""
    level = str(item.get("atr_level") or "")
    pct_str = f"{atr_ratio*100:.1f}%" if atr_ratio else "数据不足"
    return f"ATR {atr14:.2f}元（{pct_str}） {level}" if level else f"ATR {atr14:.2f}元（{pct_str}）"


def low_watch_text(item: dict[str, Any]) -> str:
    support = to_float(item.get("support"))
    current = to_float(item.get("current"))
    if support is None or current is None:
        return "无"
    low = min(support, current)
    high = max(support, current)
    return f"{low:.2f}-{high:.2f}元"


def t0_tendency(item: dict[str, Any]) -> str:
    if item.get("status") == "淘汰":
        return "不做"
    if item.get("status") == "执行":
        return "等待低吸触发"
    if item.get("momentum_state") == "通过":
        return "等待高抛触发"
    return "不做"


STAR_MAP = {
    "低吸观察": "⭐⭐⭐⭐⭐",
    "等转强": "⭐⭐⭐⭐",
    "防守观察": "⭐⭐⭐",
    "冲高减仓": "⭐⭐",
    "暂不碰": "⭐",
    "已破止损": "🔴",
}


def _price_freshness_warning(item: dict[str, Any]) -> str | None:
    """检测价格是否过期（超过 1 小时），返回警告文本或 None。"""
    fetched_at = item.get("price_fetched_at")
    if not fetched_at:
        return None
    try:
        fetched_dt = datetime.fromisoformat(str(fetched_at))
        age_minutes = (datetime.now() - fetched_dt).total_seconds() / 60
        if age_minutes > 60:
            return f"⚠️ 价格过期（{age_minutes:.0f}分钟前）"
    except (ValueError, TypeError):
        pass
    return None


def _trigger_distance_warning(item: dict[str, Any]) -> str | None:
    """检测触发价与现价的偏离程度，返回警告文本或 None。"""
    current = to_float(item.get("current"))
    trigger = to_float(item.get("trigger"))
    if not current or not trigger or current <= 0 or trigger <= 0:
        return None
    pct = (trigger - current) / current * 100
    if abs(pct) > 15:
        return f"⚠️ 触发价偏离 {pct:+.0f}%，可能已过期"
    if abs(pct) > 5:
        return f"触发价偏离 {pct:+.0f}%，建议运行 pool refresh"
    return None


def _is_trigger_stale(item: dict[str, Any]) -> bool:
    """触发价偏离现价超过 5%，视为过期。"""
    current = to_float(item.get("current"))
    trigger = to_float(item.get("trigger"))
    if not current or not trigger or current <= 0 or trigger <= 0:
        return False
    return abs((trigger - current) / current) > 0.05


def _days_lapsed(item: dict[str, Any], today: date) -> int:
    """Calculate days since item was added to pool."""
    try:
        added_str = str(item.get("added_at", today_text()))
        return (today - date.fromisoformat(added_str)).days
    except Exception:
        return 0


def _verify_observe_track(sig_type: str, item: dict[str, Any], current: float, days: int, summary: dict) -> str:
    """Verify observe/low_buy_watch/track signals: expect price to rise from support."""
    support = to_float(item.get("support") or item.get("current") or 0)
    confirmed_up = current > support * 1.01 if support > 0 else False
    if days <= 2:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 第1天" if days == 1 else "⏳ 第2天"
    if confirmed_up:
        summary["已验证"] = summary.get("已验证", 0) + 1
        return "✅ 确认上涨中"
    summary["守支撑"] = summary.get("守支撑", 0) + 1
    return "⏳ 支撑位守住了"


def _verify_high_sell(sig_type: str, item: dict[str, Any], current: float, days: int, summary: dict) -> str:
    """Verify high_sell_watch/high_sell_triggered signals: expect price to fall from resistance."""
    expect_down = current < to_float(item.get("resistance") or current * 1.05 or current)
    if days <= 2:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 第1天" if days == 1 else "⏳ 第2天"
    if expect_down:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 继续等"
    summary["信号错了"] = summary.get("信号错了", 0) + 1
    return "⚠️ 信号存疑"


def _verify_reduce(sig_type: str, item: dict[str, Any], current: float, days: int, summary: dict) -> str:
    """Verify reduce signals: expect price near resistance for confirmation."""
    resistance = to_float(item.get("resistance") or 0)
    hit_resistance = current >= resistance * 0.98 if resistance > 0 else False
    close_under_resistance = current < resistance * 0.99 if resistance > 0 else False
    if hit_resistance:
        summary["已验证"] = summary.get("已验证", 0) + 1
        return "⚠️ 已触压"
    if close_under_resistance:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 远离压力，暂不操作"
    summary["未验证"] = summary.get("未验证", 0) + 1
    return "⏳ 等确认"


def _verify_defensive(sig_type: str, item: dict[str, Any], current: float, defense: float, summary: dict) -> str:
    """Verify defensive signals: expect price to hold above defense."""
    if current < defense:
        summary["信号错了"] = summary.get("信号错了", 0) + 1
        return "❌ 破防守"
    summary["已验证"] = summary.get("已验证", 0) + 1
    return "⏳ 守住了"


def _verify_review_result(sig_type: str, matched: dict, item: dict[str, Any], current: float, summary: dict) -> str:
    """Verify review_result signals: check if direction matches."""
    expected_up = str(matched.get("direction", "")) in ("bullish", "bullish_lean")
    support = to_float(item.get("support") or current * 0.995 or 0)
    if current > support:
        if expected_up:
            summary["已验证"] = summary.get("已验证", 0) + 1
            return "✅ 对方向"
        summary["信号错了"] = summary.get("信号错了", 0) + 1
        return "⚠️ 方向反了"
    summary["未验证"] = summary.get("未验证", 0) + 1
    return "⏳ 没到位"


# Signal type → handler mapping
_SIGNAL_HANDLERS: dict[str, Any] = {
    "observe": _verify_observe_track,
    "low_buy_watch": _verify_observe_track,
    "track": _verify_observe_track,
    "high_sell_watch": _verify_high_sell,
    "high_sell_triggered": _verify_high_sell,
    "reduce": _verify_reduce,
    "defensive": _verify_defensive,
    "review_result": _verify_review_result,
}


def _verify_by_signal_type(
    sig_type: str, matched: dict, item: dict[str, Any],
    current: float, defense: float, today: date, summary: dict,
) -> tuple[str, dict]:
    """Dispatch to per-type signal verifier. Returns (verify_status, updated_summary)."""
    handler = _SIGNAL_HANDLERS.get(sig_type)
    if handler is None:
        summary["未验证"] = summary.get("未验证", 0) + 1
        return "⏳ 等结果", summary

    days = _days_lapsed(item, today)
    if sig_type in ("observe", "low_buy_watch", "track"):
        return handler(sig_type, item, current, days, summary), summary
    if sig_type in ("high_sell_watch", "high_sell_triggered"):
        return handler(sig_type, item, current, days, summary), summary
    if sig_type == "reduce":
        return handler(sig_type, item, current, days, summary), summary
    if sig_type == "defensive":
        return handler(sig_type, item, current, defense, summary), summary
    if sig_type == "review_result":
        return handler(sig_type, matched, item, current, summary), summary
    summary["未验证"] = summary.get("未验证", 0) + 1
    return "⏳ 等结果", summary


def _pool_signal_verifications(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    from trader_shared.signal_store import load_recent_signals

    today = date.today()
    summary = {"已验证": 0, "信号错了": 0, "未验证": 0, "暂无信号": 0}
    results: list[dict[str, Any]] = []

    for item in items:
        current = to_float(item.get("current")) or 0
        trigger = to_float(item.get("trigger")) or 0
        defense = to_float(item.get("defense")) or 0
        name = item.get("name", "?")
        symbol = item.get("symbol") or name
        status = str(item.get("status") or "")

        sig_text = "无"
        verify_status = "暂无信号"

        if trigger <= 0 or defense <= 0:
            sig_text = "无触发/防守位"
            verify_status = "暂无信号"
        else:
            try:
                signals = load_recent_signals(name, limit=10)
                if not signals:
                    signals = load_recent_signals(symbol, limit=10)
            except Exception:
                signals = []

            # FIX-T-BIAS-177: match signal to pool item's trigger/defense, not just latest
            matched = None
            if signals:
                for s in signals:
                    s_trigger = to_float(s.get("trigger", {}).get("price") or 0)
                    s_invalidation = to_float(s.get("invalidation", {}).get("price") or 0)
                    s_sig_type = str(s.get("signal_type", ""))
                    # Match by price proximity: signal trigger ~= pool trigger, signal invalidation ~= pool defense
                    trigger_ok = s_trigger > 0 and abs(s_trigger - trigger) / max(trigger, 0.01) < 0.05
                    invalidation_ok = s_invalidation > 0 and abs(s_invalidation - defense) / max(defense, 0.01) < 0.05
                    if trigger_ok and invalidation_ok:
                        matched = s
                        break
                    # Fallback: signal_type must match pool item's implied type
                    pool_type = _pool_item_signal_type(item)
                    if pool_type and s_sig_type == pool_type:
                        matched = s
                        break
                if matched is None:
                    # FIX: filter signals by stock name/symbol to avoid cross-stock contamination
                    for s in signals:
                        s_name = str(s.get("name", ""))
                        s_symbol = str(s.get("symbol", ""))
                        if s_name == name or s_symbol == symbol:
                            matched = s
                            break

            if matched:
                sig_type = str(matched.get("signal_type", ""))
                confidence = str(matched.get("confidence", ""))
                conf_map = {"low": "低", "medium": "中等", "high": "高"}
                conf_txt = conf_map.get(confidence, confidence)

                # 通用检查：破防守 / 已触发
                if current < defense:
                    verify_status = "❌ 破防守"
                    summary["信号错了"] = summary.get("信号错了", 0) + 1
                elif current >= trigger:
                    if current > trigger * 1.01:
                        verify_status = "✅ 已触发"
                        summary["已验证"] = summary.get("已验证", 0) + 1
                    else:
                        verify_status = "⏳ 触碰但未确认"
                        summary["未验证"] = summary.get("未验证", 0) + 1
                else:
                    # 按信号类型分支验证
                    verify_status, summary = _verify_by_signal_type(
                        sig_type, matched, item, current, defense, today, summary
                    )

                if matched:
                    sig_text = f"{_signal_type_label(sig_type)} {conf_txt}"
                else:
                    sig_text = "无记录"
                    verify_status = "暂无信号"
                    summary["暂无信号"] = summary.get("暂无信号", 0) + 1

        results.append({
            "name": name,
            "current": current,
            "sig_text": sig_text,
            "verify_status": verify_status,
        })

    return results, summary


def _apply_signal_adjustments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """根据信号回测结果调整排序：失败信号降级，已触发标记。"""
    from trader_shared.signal_store import load_recent_signals

    adjusted = []
    for item in items:
        item = dict(item)  # shallow copy
        name = item.get("name", "?")
        symbol = item.get("symbol") or name
        current = to_float(item.get("current")) or 0
        defense = to_float(item.get("defense")) or 0

        try:
            signals = load_recent_signals(name, limit=5)
            if not signals:
                signals = load_recent_signals(symbol, limit=5)
        except Exception:
            signals = []

        if signals:
            latest = signals[-1]
            # 检查信号结果字段
            result = str(latest.get("result") or latest.get("verify_status") or "")
            sig_status = str(latest.get("status") or "")

            # 信号失败（破防守 / 方向反了）→ 降级为观察
            if "❌" in result or "破防守" in result or "方向反" in result:
                if item.get("status") != "淘汰":
                    item["status"] = "观察"
                    item["_signal_downgrade"] = True

            # 信号已触发 → 标记
            if "✅" in result or "已触发" in result:
                item["_signal_triggered"] = True

            # 现价跌破防守位 → 降级
            if defense > 0 and current > 0 and current < defense:
                if item.get("status") != "淘汰":
                    item["status"] = "观察"
                    item["_defense_broken"] = True

        adjusted.append(item)
    return adjusted


def action_summary_for_scene(scene: str) -> str:
    """One-line action advice for pool items."""
    if scene in {"低吸观察", "防守观察", "防守观察，趋势下行谨慎"}:
        return "守纪律不追，等止跌确认"
    if scene in {"等转强"}:
        return "等放量确认"
    if scene in {"冲高减仓"}:
        return "冲高减仓，不追"
    if scene in {"突破确认", "突破观察"}:
        return "持有观察"
    if scene in {"空间不足"}:
        return "不追，等回落"
    if scene in {"暂不碰"}:
        return "不参与"
    if not scene:
        return "信息不足，暂不操作"
    return "等待，不主动追"


def _build_report_or_offline(name: str) -> dict[str, Any]:
    """Try live report, fallback to offline mock report."""
    try:
        from run_analysis import build_report
        return build_report(name)
    except Exception:
        base = 10 + (sum(ord(char) for char in name) % 700) / 100
        return {
            "name": name, "symbol": name, "current": round(base, 2),
            "change_pct": 0.0, "confirm": round(base * 1.035, 2),
            "stop": round(base * 0.945, 2), "support": round(base * 0.975, 2),
            "trigger": round(base * 1.035, 2), "stage": "震荡",
            "scene": "震荡", "bars": [], "daily_bars": [],
        }


def cmd_watch(args: argparse.Namespace) -> int:
    """Monitor top pool items with live prices and proximity alerts."""
    pool = load_pool()
    items = sort_items(active_items(pool))
    if not items:
        print("选股池为空，无需盯盘")
        return 0

    # FIX-T-BIAS-148: always include execution items beyond rank 3
    # so that high-risk stocks are never silently ignored.
    exec_items = [item for item in items if item.get("status") == "执行"]
    rank_items = [item for item in items if item.get("status") != "执行"]
    top3 = rank_items[:3]
    for item in exec_items:
        if item not in top3:
            top3.append(item)
    now = datetime.now().strftime("%H:%M")

    all_alerts: list[str] = []

    for i, item in enumerate(top3, 1):
        name = item.get("name", "?")
        current = to_float(item.get("current")) or 0
        trigger = to_float(item.get("trigger")) or 0
        defense = to_float(item.get("defense")) or 0
        support_raw = to_float(item.get("support")) or 0
        scene = str(item.get("scene") or "")
        status = str(item.get("status") or "?")

        # Try to get live quote
        change_pct = 0.0
        try:
            from trader_shared.light_data import fetch_quote, HttpClient, resolve_security
            sec = resolve_security(name)
            q = fetch_quote(sec, HttpClient())
            if q and to_float(q.get("current_price")):
                current = to_float(q.get("current_price"))
                change_pct = to_float(q.get("current_change_pct")) or 0.0
        except Exception:
            pass

        if current <= 0:
            continue

        # Dynamic threshold: each stock gets a warning zone fitted to its volatility.
        # 1. Use ATR-based distance (ATR × 2) for adaptive sensitivity:
        #    high-volatility stocks → wider zone (fewer false alarms)
        #    low-volatility stocks → tighter zone (catches early moves)
        # 2. Capped at 3% of price so extremely volatile stocks still stay actionable
        atr14 = to_float(item.get("atr14")) or 0.0
        thresh_pct = min(atr14 * 2, 0.03) if atr14 > 0 else 0.02

        stock_alerts: list[str] = []
        atr_note = f"（ATR {atr14:.2f}）" if atr14 > 0 else ""

        # 1. Defense breach (highest priority)
        if defense > 0 and current < defense:
            stock_alerts.append("🛑 破防守位！跌破防守位" + atr_note)
        # 2. Near defense (within adaptive threshold)
        elif defense > 0 and current > defense:
            dist_def = abs(current - defense) / current * 100
            if dist_def < thresh_pct * 100:
                stock_alerts.append(f"⚠️ 靠近防守，距防守仅 {dist_def:.1f}%" + atr_note)
        # 3. Near trigger
        elif trigger > 0:
            dist_trig = abs(trigger - current) / current * 100
            if dist_trig < thresh_pct * 100:
                if current >= trigger:
                    stock_alerts.append("🟢 已到触发位附近" + atr_note)
                else:
                    stock_alerts.append(f"⚡ 距触发仅 {dist_trig:.1f}%" + atr_note)
        # 4. Near support — only alert if price genuinely breached (within 1% margin)
        if support_raw > 0 and current <= support_raw * 1.01:
            dist_sup = abs(current - support_raw) / current * 100
            if dist_sup < thresh_pct * 100:
                stock_alerts.append(f"📊 距支撑仅 {dist_sup:.1f}%" + atr_note)

        # Build output for this stock
        rank_emoji = ["🥇", "🥈", "🥉"][i - 1]
        if stock_alerts:
            alert_line = " | ".join(stock_alerts)
            all_alerts.append(f"{rank_emoji} {name}  {current:.2f}（{change_pct:+.1f}%）  {alert_line}")
        else:
            action = action_summary_for_scene(scene)
            all_alerts.append(f"{rank_emoji} {name}  {current:.2f}（{change_pct:+.1f}%）  👉 {action}" + atr_note)

    # Print output
    print(f"📡 选股池盯盘 — {now} | Top3")
    print()
    for line in all_alerts:
        print(f"  {line}")

    return 0


def _pool_item_signal_type(item: dict[str, Any]) -> str | None:
    """Derive expected signal_type from pool item's trigger/defense/stop configuration."""
    trigger = to_float(item.get("trigger"))
    defense = to_float(item.get("defense"))
    support = to_float(item.get("support"))
    current = to_float(item.get("current"))
    resistance = to_float(item.get("resistance"))
    if current is None or defense is None or trigger is None:
        return None
    # If current is below defense: defensive/risk_stop scenario
    if current < defense:
        return "risk_stop"
    # If current is above trigger: track scenario
    if current >= trigger:
        return "track"
    # If current is near resistance: reduce scenario
    if resistance and current >= resistance * 0.95:
        return "reduce"
    # If current is near support: low_buy scenario
    if support and current <= support * 1.03:
        return "low_buy_watch"
    # Default: waiting for confirmation
    return "wait_for_confirmation"


def _signal_type_label(sig_type: str) -> str:
    labels = {
        "observe": "观察",
        "wait_for_confirmation": "等待确认",
        "track": "跟踪",
        "low_buy_watch": "低吸观察",
        "low_buy_triggered": "低吸触发",
        "high_sell_watch": "高抛观察",
        "high_sell_triggered": "高抛触发",
        "reduce": "减仓",
        "defensive": "防守",
        "risk_stop": "止损",
        "trigger_expired": "信号过期",
        "blocked": "受压",
        "review_result": "复盘",
    }
    return labels.get(sig_type, sig_type)


def edge_reason(item: dict[str, Any], all_items: list[dict[str, Any]]) -> str:
    """返回排名的核心优势/劣势一句话。从 pool item 字段推导。"""
    confidences = [it.get("fusion_confidence", 0) or 0 for it in all_items]
    item_conf = float(item.get("fusion_confidence") or 0)
    top_conf = max(confidences) if confidences else 1

    # 优势：从得分最高的维度提取
    scores = {}
    for key, max_s in [("chanlun_score", 45), ("wyckoff_score", 30), ("chip_score", 25), ("momentum_score", 20)]:
        v = float(item.get(key) or 0)
        scores[key] = v
    best_dim = max(scores, key=scores.get)
    dim_labels = {"chanlun_score": "结构", "wyckoff_score": "量价", "chip_score": "筹码", "momentum_score": "动能"}
    ratio = scores[best_dim] / max(max(scores.values()), 0.01)
    if ratio >= 0.85:
        advantage = dim_labels.get(best_dim, best_dim) + "突出"
    else:
        advantage = ""

    # 置信度分位
    if top_conf > 0:
        conf_pct = item_conf / top_conf
    else:
        conf_pct = 1.0

    if conf_pct >= 0.9 and advantage:
        return f"置信最高｜{advantage}"
    elif conf_pct >= 0.7:
        return f"置信较高｜{advantage}" if advantage else "置信较高"
    elif conf_pct < 0.4:
        return "置信偏低"
    elif conf_pct < 0.6:
        return "置信中等"
    elif advantage:
        return advantage
    return ""


def render_rank(items: list[dict[str, Any]]) -> str:
    from trader_shared.candidate_core import atr_volatility_level

    items = _apply_signal_adjustments(items)
    sorted_items = sort_items_unified(items)
    market_level = get_market_level()

    lines = [f"选股池  ｜  {'大盘' + market_level + '，防守优先' if market_level else '持仓排序'}"]
    lines.append("")

    for i, item in enumerate(sorted_items):
        rs = rank_status(item)
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f" {i+1}."
        reason = edge_reason(item, sorted_items)
        reason_line = f"    {reason}" if reason else ""

        name = item.get("name", "?")
        current = to_float(item.get("current")) or 0
        atr_ratio = to_float(item.get("atr_ratio")) or 0
        atr_level, base_cap = atr_volatility_level(atr_ratio) if atr_ratio > 0 else ("数据不足", 10)
        # 按阶段 × ATR × 置信度差异化仓位
        major_stage = str(item.get("major_stage") or "蓄势")
        stage_mult = STAGE_STRENGTH.get(major_stage, 0.5)
        conf = float(item.get("fusion_confidence") or 0.5)
        final_cap = round(base_cap * stage_mult * conf)
        final_cap = max(2, min(final_cap, 25))  # 夹在 2%-25%
        # 仓位理由
        cap_reason_parts = []
        if major_stage in ("主升", "拉升"):
            cap_reason_parts.append("主升期")
        elif major_stage in ("蓄势偏强",):
            cap_reason_parts.append("蓄势偏强")
        elif major_stage in ("蓄势偏弱", "派发"):
            cap_reason_parts.append(major_stage)
        if atr_ratio >= 0.03:
            cap_reason_parts.append("波幅偏高")
        if conf < 0.4:
            cap_reason_parts.append(f"置信{conf:.1f}")
        cap_reason = " × ".join(cap_reason_parts) if cap_reason_parts else ""
        atr_pct = (atr_ratio or 0) * 100

        if atr_ratio >= 0.03:
            atr_text = f"波幅偏高({atr_pct:.0f}%)" if atr_pct >= 1 else "波幅偏高"
        elif atr_ratio >= 0.02:
            atr_text = f"波动偏大({atr_pct:.0f}%)"
        elif atr_ratio > 0:
            atr_text = f"波动正常({atr_pct:.0f}%)" if atr_pct >= 1 else "波动正常"
        else:
            atr_text = "数据不足"

        buy_low = to_float(item.get("buy_low")) or to_float(item.get("support")) or 0
        buy_high = to_float(item.get("buy_high")) or (buy_low * 1.01 if buy_low else 0)
        stop_val = to_float(item.get("stop")) or to_float(item.get("defense")) or 0
        confirm = to_float(item.get("confirm")) or to_float(item.get("trigger")) or 0

        # 止损 > 现价时标记已破止损
        current_price_val = to_float(item.get("current")) or to_float(item.get("price")) or 0
        if stop_val > 0 and current_price_val > 0 and stop_val > current_price_val:
            item = dict(item)  # shallow copy to avoid mutating original
            item["_stop_broken"] = True

        if buy_low and buy_high:
            buy_text = f"买(观察区)  {buy_low:.2f}-{buy_high:.2f} 止跌确认"
        elif buy_low:
            buy_text = f"买(观察区)  {buy_low:.2f} 止跌确认"
        else:
            buy_text = "买  暂无"

        # 买入区过期检查
        if buy_low > 0 and current_price_val > 0 and buy_low > current_price_val * 1.05:
            buy_text = f"买入区已过期（{buy_low:.2f}）"

        lines.append(f"{medal}  {name}  {rs}  {current:.2f}  {atr_text}")
        if reason_line:
            lines.append(f"    {reason_line}")
        cap_display = f"仓位 {final_cap}%"
        if cap_reason:
            cap_display += f"（{cap_reason}）"
        # R4: 盈亏比显示
        rr_val = to_float(item.get("risk_reward")) or 0
        if rr_val > 0 and ENABLE_RISK_REWARD_FILTER:
            market_env_level_s = get_market_level()
            rr_th = RISK_REWARD_THRESHOLDS.get(market_env_level_s, 1.5)
            rr_ok = rr_val >= rr_th
            rr_sym = "✓" if rr_ok else "✗"
            cap_display += f" 盈亏比 {rr_val}R {rr_sym}"
        lines.append(f"    {buy_text}  ｜  {cap_display}  ｜  止损 {stop_val:.2f}")
        # 价格过期 & 触发价偏离警告
        fw = _price_freshness_warning(item)
        if fw:
            lines.append(f"    {fw}")
        tw = _trigger_distance_warning(item)
        if tw:
            lines.append(f"    {tw}")
        lines.append("")

    first = sorted_items[0] if sorted_items else None
    second = sorted_items[1] if len(sorted_items) > 1 else None
    third = sorted_items[2] if len(sorted_items) > 2 else None

    lines.append("👉  ")

    if first:
        fname = first.get("name", "?")
        fs = rank_status(first)
        lines.append(f"    首选{fname}。{fs}信号最强，优先关注。")

    if second:
        sname = second.get("name", "?")
        ss = rank_status(second)
        lines.append(f"    {sname}{ss}差一档，做备选。")

    if third:
        tname = third.get("name", "?")
        lines.append(f"    {tname}再等等。")

    lines.extend([
        "",
        "    不抢跑，等止跌确认再动手。",
    ])

    # 信号回测段
    verifications, summary = _pool_signal_verifications(sorted_items)
    if verifications:
        lines.append("")
        lines.append("📊 信号回测")
        lines.append("")
        lines.append(f"  {'名称':<8}{'信号':<12}  验证结果")
        lines.append(f"  {'-'*6:<8}{'-'*10:<12}  {'-'*10}")
        for v in verifications:
            lines.append(f"  {v['name']:<8}{v['sig_text']:<12}  {v['verify_status']}")

        total_verified = summary.get("已验证", 0)
        total_wrong = summary.get("信号错了", 0)
        total_unverified = summary.get("未验证", 0)
        total_none = summary.get("暂无信号", 0)
        total_with_signal = total_verified + total_wrong
        if total_with_signal > 0:
            accuracy_val = total_verified / total_with_signal
            accuracy = f"{accuracy_val * 100:.0f}%"
            lines.append("")
            lines.append(f"  合计：本月已验证 {total_with_signal} 次，对了 {total_verified} 次，准确率 {accuracy}。未验证 {total_unverified} 次，暂无信号 {total_none} 条。")
            # 低胜率警告
            if total_with_signal >= 5 and accuracy_val < 0.3:
                lines.append("  ⚠️ 策略近期胜率偏低（<30%），建议暂停实盘，仅保持观察")
        else:
            lines.append("")
            lines.append(f"  合计：本月无已验证信号记录（未验证 {total_unverified} 次，暂无信号 {total_none} 条）。")

    return "\n".join(lines)


def rank_action(item: dict[str, Any]) -> str:
    if item.get("status") == "执行":
        return f"等 {price_yuan(item.get('trigger'))} 放量站稳，不提前追。"
    if item.get("status") == "观察":
        return f"只观察 {price_yuan(item.get('trigger'))} 是否站稳，不主动买。"
    return "淘汰或风险不清，先不参与。"


def empty_reason(item: dict[str, Any] | None) -> str:
    if not item:
        return "池内没有适合空仓优先跟踪的候选。"
    return f"{item.get('name')} 排名靠前，但仍要等触发位确认。"


def holding_reason(item: dict[str, Any] | None) -> str:
    if not item:
        return "池内没有适合做T的候选，先不动底仓。"
    return f"{item.get('name')} 有明确触发和防守，具体盘中触发交给 t0。"


def rank_sentence(actionable: list[dict[str, Any]]) -> str:
    if not actionable:
        return "今天池内没有明确优先对象，先不主动参与。"
    first = actionable[0]
    return f"今天优先盯{first.get('name')}，只按触发位和防守位执行，不把观察区当操作价。"


def quick_add(target: str, offline: bool = False) -> dict[str, Any]:
    """One-step add: run analysis, check 三关, add to pool if passes."""
    report = safe_build_report(target, offline)
    record = record_from_report(target, report, offline)
    major_stage = str(record.get("major_stage") or "蓄势")
    total_score = int(record.get("total_score") or 0)
    current = to_float(record.get("current")) or 0.0
    confirm = to_float(record.get("confirm")) or 0.0
    stop = to_float(record.get("defense")) or 0.0

    # 统一三关筛选
    admission = _evaluate_admission(major_stage, total_score, current, confirm, stop)
    if admission["result"] != "入池":
        return {"ok": False, "reason": f"{admission['reason']}（{major_stage}，评分{total_score}）", "record": record}

    record["status"] = admission["status"]
    pool = load_pool()
    items = list(pool.get("items", []))
    existing_index = next((i for i, item in enumerate(items) if target in {str(item.get("target")), str(item.get("name")), str(item.get("symbol"))}), None)
    if existing_index is None and len(items) >= POOL_LIMIT:
        return {"ok": False, "reason": f"池容量已满 {len(items)}/{POOL_LIMIT}", "record": record}
    if existing_index is None:
        items.append(record)
    else:
        record["added_at"] = items[existing_index].get("added_at") or record["added_at"]
        items[existing_index] = record
    pool["items"] = items
    save_pool(pool)
    try:
        write_stock(record["name"], record["status"], record["total_score"], "pool")
    except Exception:
        pass
    return {"ok": True, "reason": f"已加入选股池（{major_stage}+{record.get('momentum', '震荡')}，评分{total_score}）", "record": record}


def cmd_rank(args: argparse.Namespace) -> int:
    pool = load_pool()
    items = active_items(pool)
    items = _refresh_pool_prices(items, pool)
    print(render_rank(items))
    return 0


def _match_item(items: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    """按 target/name/symbol 任一字段匹配池内项（与 cmd_add 的匹配口径一致）。"""
    for item in items:
        if target in {str(item.get("target")), str(item.get("name")), str(item.get("symbol"))}:
            return item
    return None


def cmd_refresh(args: argparse.Namespace) -> int:
    """批量重跑 build_report 刷新全池 record，写回 pool.json。

    - 默认刷新全部 active 项；--target <名称> 只刷单只。
    - 保留 added_at，更新 updated_at，重新走 admission 判定（确保 status 与当前评分/阶段一致）。
    - 衰退期 → 自动标淘汰。
    - 并行刷新（max_workers=5，与 build_report 内部并行一致）。
    - 单只失败 → safe_build_report 自动降级为离线 record，不中断全池。
    - 优化：复用全局共享线程池，避免嵌套 ThreadPoolExecutor 线程爆炸。
    """
    from concurrent.futures import as_completed
    from trader_shared.cache_utils import get_shared_build_pool

    pool = load_pool()
    all_items = list(pool.get("items", []))

    # 选定刷新目标
    if args.target:
        item = _match_item(all_items, args.target)
        if item is None:
            names = [str(i.get("name") or i.get("target")) for i in all_items]
            print(f"未在选股池中找到 {args.target}")
            print(f"池内现有标的：{', '.join(names) or '空'}")
            return 2
        targets = [item]
    else:
        targets = active_items(pool)
        if not targets:
            print("选股池为空，无需刷新")
            return 0

    # 并行刷新：用 target 作为 key（record_from_report 也用它）
    # 复用全局共享线程池，避免嵌套 pool → build_report → load_market_snapshot 的线程爆炸
    target_keys = [str(t.get("target") or t.get("name")) for t in targets]
    results: dict[str, dict[str, Any] | None] = {}
    shared = get_shared_build_pool()
    future_to_key: dict = {
        shared.submit(safe_build_report, key): key for key in target_keys
    }
    for fut in as_completed(future_to_key):
        key = future_to_key[fut]
        try:
            results[key] = fut.result()
        except Exception:
            results[key] = None  # 失败保留原 record

    # 逐只更新 record（遍历原始全量以保持顺序）
    refreshed = 0
    failed: list[str] = []
    declined: list[str] = []
    for idx, item in enumerate(all_items):
        key = str(item.get("target") or item.get("name"))
        if key not in results:
            continue
        report = results[key]
        if report is None:
            failed.append(str(item.get("name") or key))
            continue  # 失败，跳过不覆盖原 record
        new_record = record_from_report(key, report)
        # 保留原入池时间，更新本次刷新时间
        new_record["added_at"] = item.get("added_at") or new_record["added_at"]
        new_record["updated_at"] = today_text()
        # 检查 admission_result：拒绝则直接淘汰
        if str(new_record.get("admission_result")) == "拒绝":
            new_record["status"] = "淘汰"
            declined.append(str(new_record.get("name") or key))
        # 衰退自动淘汰
        elif str(new_record.get("major_stage")) == "衰退":
            new_record["status"] = "淘汰"
            declined.append(str(new_record.get("name") or key))
        else:
            # 用新 record 的 admission 结果，而非保留旧 status
            pass  # new_record["status"] 已由 record_from_report → admission_for 正确设置
        all_items[idx] = new_record
        refreshed += 1

    pool["items"] = all_items
    save_pool(pool)

    # 摘要（遵守微信端格式红线：无 #/**/|）
    print(f"选股池刷新 — {today_text()}")
    print(f"刷新 {refreshed}/{len(targets)} 只")
    if declined:
        print(f"衰退淘汰：{', '.join(declined)}")
    if failed:
        print(f"刷新失败（保留旧数据）：{', '.join(failed)}")
    print("下一步：说「生成明日作战表」查看最新池子")
    return 0


def priority_block(items: list[dict[str, Any]]) -> list[str]:
    labels = ["第一优先", "第二优先", "第三优先"]
    lines = ["明日优先级", ""]
    for label, item in zip(labels, items[:3]):
        lines.extend(
            [
                f"{label}：{item.get('name')}",
                f"状态：{item.get('status')}",
                f"结构：{item.get('structure_summary')}",
                f"动能：{item.get('momentum_state')}",
                f"动作：{action_for(item)}",
                f"失效：收盘跌破 {price(item.get('defense'))} 转淘汰",
                f"仓位：{position_for(item)}",
                "",
            ]
        )
    return lines


def action_for(item: dict[str, Any]) -> str:
    if item.get("status") == "执行":
        return f"放量站上 {price(item.get('trigger'))} 才考虑"
    if item.get("status") == "观察":
        return f"只看 {price(item.get('trigger'))} 是否站稳，不买"
    return "不参与，保留复盘记录"


def position_for(item: dict[str, Any]) -> str:
    if item.get("status") == "执行":
        return "1成试错，确认后最多3成"
    return "0"


def render_plan(items: list[dict[str, Any]]) -> str:
    items = _apply_signal_adjustments(items)
    sorted_items = sort_items_unified(items)
    # 分离触发价过期的票（距现价 > 5%）
    active_plan_items = [it for it in sorted_items if not _is_trigger_stale(it)]
    stale_plan_items = [it for it in sorted_items if _is_trigger_stale(it)]
    count = counts(sorted_items)
    execution_items = [item for item in active_plan_items if item.get("status") == "执行"][:EXECUTION_LIMIT]
    top_items = execution_items + [item for item in active_plan_items if item.get("status") != "执行"]

    lines = [
        f"选股池盘后分析 — {today_text()}",
        f"容量 {len(sorted_items)}/{POOL_LIMIT}｜执行{count['执行']}｜观察{count['观察']}｜淘汰{count['淘汰']}｜明日只盯Top2",
        "",
    ]

    if top_items:
        lines.append("明日优先级")
        for i, item in enumerate(top_items[:3], 1):
            rank_emoji = ["🥇", "🥈", "🥉"][i - 1]
            stage_str = str(item.get("stage_status") or item.get("major_stage", "蓄势") + "+" + item.get("momentum", "震荡"))
            lines.append(f"{rank_emoji} {item['name']}（{stage_str} {item['status']}）")
            lines.append(f"  {action_for(item)}")
            # R4: 计划页显示盈亏比
            rr_val = to_float(item.get("risk_reward")) or 0
            if rr_val > 0 and ENABLE_RISK_REWARD_FILTER:
                market_env_level_s = get_market_level()
                rr_th = RISK_REWARD_THRESHOLDS.get(market_env_level_s, 1.5)
                rr_ok = rr_val >= rr_th
                rr_sym = "✓" if rr_ok else "✗"
                plan_rr_text = f"  盈亏比 {rr_val}R {rr_sym}"
            else:
                plan_rr_text = ""
            lines.append(f"  触发{price(item.get('trigger'))}元  防守{price(item.get('defense'))}元  仓位{position_for(item)}{plan_rr_text}")
            fw = _price_freshness_warning(item)
            if fw:
                lines.append(f"  {fw}")

        # 远期观察（触发价过期 > 5%）
        if stale_plan_items:
            lines.append("")
            lines.append("远期观察（触发价偏离现价 > 5%，等刷新后再看）")
            for item in stale_plan_items:
                tw = _trigger_distance_warning(item)
                note = f" — {tw}" if tw else ""
                lines.append(f"  {item.get('name')}  触发{price(item.get('trigger'))}元  现价{price(item.get('current'))}元{note}")

        lines.append("")
        lines.append("评分总览")
        for item in sorted_items:
            _rr = to_float(item.get("risk_reward")) or 0
            _rr_suffix = ""
            if _rr > 0 and ENABLE_RISK_REWARD_FILTER:
                _rr_s = get_market_level()
                _rr_th = RISK_REWARD_THRESHOLDS.get(_rr_s, 1.5)
                _rr_sym = "✓" if _rr >= _rr_th else "✗"
                _rr_suffix = f" 盈亏比 {_rr}R {_rr_sym}"
            lines.append(
                f"  {item.get('name')}  {score_summary(item)}  {item['status']}{_rr_suffix}"
            )

        lines.append("")
        lines.append("交易指导")
        for item in top_items[:3]:
            lines.append(f"  {item['name']}: {trade_hint(item)}")

        lines.append("")
        lines.append("待补与拒绝")
        rejected = [item for item in sorted_items if item.get("admission_result") in {"待补", "拒绝"} or item.get("status") == "淘汰"]
        if rejected:
            for item in rejected:
                lines.append(f"  {item.get('name')}：{item['admission_reason']}")
        else:
            lines.append("  无")

        lines.append("")
        lines.append("仓位纪律 执行首次1成 确认加至3成 单票风险1R 总仓位≤5成")
        lines.append(one_sentence(top_items))
    else:
        lines.append("当前选股池没有可执行对象，今天不主动处理。")

    return "\n".join(lines)


def score_summary(item: dict[str, Any]) -> str:
    """返回压缩后的评分摘要，如：45/45 35/30 40/25 85/20 总88"""
    parts = []
    for key, max_s in [("chanlun_score", 45), ("wyckoff_score", 30), ("chip_score", 25), ("momentum_score", 20)]:
        v = float(item.get(key) or 0)
        parts.append(f"{v:.0f}/{max_s}")
    total = float(item.get("total_score") or 0)
    return "  ".join(parts) + f"  总{total:.0f}"


def trade_hint(item: dict[str, Any]) -> str:
    if item.get("_signal_triggered"):
        return f"信号已触发，按计划执行（防守{price(item.get('defense'))}元）"
    if item.get("_signal_downgrade"):
        return f"近期信号失败，暂不介入，等新信号"
    if item.get("status") == "执行":
        return f"放量站稳{price(item['trigger'])}元才买 → 回踩不破可加至3成"
    return f"{price(item['trigger'])}元站稳再看，防守{price(item.get('defense'))}元"


def one_sentence(items: list[dict[str, Any]]) -> str:
    top = [str(item.get("name")) for item in items[:2]]
    if not top:
        return "当前选股池没有可执行对象，明天不主动处理。"
    return f"明天只重点盯 {' 和 '.join(top)}；不触发不买，其他只盘后更新。"


def _refresh_pool_prices(items: list[dict[str, Any]], pool: dict[str, Any]) -> list[dict[str, Any]]:
    """批量拉取实时行情，刷新 pool item 的 current / change_pct，写回 pool.json。

    在 list / rank / plan 等只读视图中调用，确保显示的现价不超过 1 分钟。
    """
    try:
        from trader_shared.light_data import fetch_quote, HttpClient, resolve_security
    except ImportError:
        return items

    client = HttpClient()
    now_iso = datetime.now().isoformat()
    refreshed = 0

    for item in items:
        name = item.get("name", "")
        if not name:
            continue
        try:
            sec = resolve_security(name)
            q = fetch_quote(sec, client)
        except Exception:
            continue
        if not q:
            continue
        current_val = to_float(q.get("current_price"))
        if current_val is None or current_val <= 0:
            continue
        item["current"] = round(current_val, 2)
        item["change_pct"] = round(to_float(q.get("current_change_pct") or 0), 2)
        item["price_fetched_at"] = now_iso
        refreshed += 1

    if refreshed > 0:
        save_pool(pool)
    return items


def _check_stale_items(items: list[dict[str, Any]]) -> list[str]:
    """P0 Fix: 检查交易时间内数据过期的票，标记为疑似停牌。

    Returns:
        list of warning strings for stale items
    """
    try:
        from trader_shared.light_data import is_trading_time
        if not is_trading_time():
            return []
    except ImportError:
        return []

    warnings = []
    for item in items:
        freshness = str(item.get("data_freshness", "live"))
        if freshness == "stale":
            name = item.get("name") or item.get("target", "?")
            warnings.append(f"⚠️ {name} 数据过期（data_freshness=stale），疑似停牌")
    return warnings


def cmd_plan(args: argparse.Namespace) -> int:
    pool = load_pool()
    items = active_items(pool)
    items = _refresh_pool_prices(items, pool)
    # 衰退淘汰已在 refresh 中处理，plan 只读不写
    # P0 Fix: 检查疑似停牌
    stale_warnings = _check_stale_items(items)
    if stale_warnings:
        for w in stale_warnings:
            print(w)
    markdown = render_plan(items)
    execution = [item for item in sort_items(items) if item.get("status") == "执行"][:EXECUTION_LIMIT]
    with DataManager.state_lock("last_plan"):
        DataManager.save_state("last_plan", {"contract_version": CONTRACT_VERSION, "date": today_text(), "execution_items": execution, "markdown": markdown})
    print(markdown)
    return 0


def cmd_add_last(args: argparse.Namespace) -> int:
    last_target_path = os.path.expanduser("~/.trader/last_target.txt")
    if not os.path.exists(last_target_path):
        print("没有找到最近分析的标的，请先运行 trader 分析。")
        return 1
    target = Path(last_target_path).read_text(encoding="utf-8").strip()
    if not target:
        print("最近分析的标的为空，请先运行 trader 分析。")
        return 1
    pool = load_pool()
    items = list(pool.get("items", []))
    existing = next((i for i, item in enumerate(items) if target in {str(item.get("target")), str(item.get("name")), str(item.get("symbol"))}), None)
    if existing is not None:
        print(f"{target} 已在选股池中（{items[existing].get('status')}）")
        return 0
    if len(items) >= POOL_LIMIT:
        print(f"候选池容量已满：{len(items)}/{POOL_LIMIT}")
        print("新票入池前，请先移除或替换一只旧票。")
        return 2
    report = safe_build_report(target, False)
    record = record_from_report(target, report, False)

    # admission 门控：拒绝/待补的票不允许入池
    admission_result = record.get("admission_result", "入池")
    if admission_result in ("拒绝", "待补"):
        reason = record.get("admission_reason", "未通过筛选")
        print(f"入池被拒：{reason}")
        print(f"当前状态：{record['status']}  评分：{record['total_score']}  阶段：{record.get('major_stage', '?')}")
        return 3

    items.append(record)
    pool["items"] = items
    save_pool(pool)
    try:
        write_stock(record["name"], record["status"], record["total_score"], "pool")
    except Exception:
        pass
    print(f"已加入选股池：{target}")
    print(f"容量：{len(items)}/{POOL_LIMIT}")
    print(f"状态：{record['status']}  触发：{price(record['trigger'])}  防守：{price(record['defense'])}")
    return 0


def review_result(item: dict[str, Any], report: dict[str, Any]) -> tuple[str, str, str]:
    high_or_current = to_float(report.get("current")) or 0.0
    trigger = to_float(item.get("trigger")) or 0.0
    defense = to_float(item.get("defense")) or 0.0
    if high_or_current <= defense:
        return "失效", f"现价{price(high_or_current)}，跌破防守{price(defense)}", "防守失效，转淘汰观察。"
    if high_or_current >= trigger:
        return "命中", f"现价{price(high_or_current)}，达到触发{price(trigger)}", "触发有效，继续按防守位管理。"
    return "未触发", f"现价{price(high_or_current)}，未到触发{price(trigger)}", "不买是正确的，继续观察。"


def cmd_review(args: argparse.Namespace) -> int:
    plan = DataManager.load_state("last_plan", {"execution_items": []})
    execution_items = plan.get("execution_items") or []
    rows: list[tuple[dict[str, Any], str, str, str, str]] = []
    summary = {"命中": 0, "未触发": 0, "失效": 0, "误判": 0}
    declined_items: list[str] = []  # 需要降级的标的
    for item in execution_items:
        report = safe_build_report(str(item.get("target") or item.get("name")), args.offline)
        result, performance, note = review_result(item, report)
        summary[result] = summary.get(result, 0) + 1
        rows.append((item, f"{price(item.get('trigger'))} 触发，{price(item.get('defense'))} 防守", performance, result, note))
        if result == "失效":
            declined_items.append(str(item.get("target") or item.get("name")))

    lines = [
        f"选股池次日复盘 — {today_text()}",
        f"昨日执行票：{len(execution_items)}只｜命中{summary['命中']}｜未触发{summary['未触发']}｜失效{summary['失效']}｜误判{summary['误判']}",
        "",
        "复盘命中表",
        "",
    ]
    for item, yesterday, performance, result, note in rows:
        lines.append(f"  {item.get('name')}  计划{yesterday}  表现{performance}  结果{result}  复盘{note}")
    lines.extend(["", "复盘短评", ""])
    if rows:
        lines.append("执行票按昨日触发和防守位复盘；未触发不算判断错误，失效则转入风险处理。")
    else:
        lines.append("上一份作战表没有执行票，今日不做交易复盘。")
    lines.extend(["", "明日调整", ""])
    if rows:
        for item, _yesterday, _performance, result, _note in rows:
            lines.append(f"{item.get('name')}：{'保留执行，继续按防守位管理。' if result == '命中' else '降为观察，等待重新触发。'}")
    else:
        lines.append("无")
    print("\n".join(lines))

    # 写回：失效票降级为观察，写入 pool.json
    if declined_items:
        pool = load_pool()
        changed = 0
        for idx, item in enumerate(pool.get("items", [])):
            item_name = str(item.get("target") or item.get("name"))
            if item_name in declined_items and item.get("status") == "执行":
                pool["items"][idx]["status"] = "观察"
                pool["items"][idx]["updated_at"] = today_text()
                changed += 1
        if changed:
            save_pool(pool)
            print(f"\n已写回：{changed}只票从执行降为观察（{', '.join(declined_items)}）")

    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    pool = load_pool()
    before = list(pool.get("items", []))
    after = [item for item in before if args.target not in {str(item.get("target")), str(item.get("name")), str(item.get("symbol"))}]
    pool["items"] = after
    save_pool(pool)
    if len(after) == len(before):
        print(f"未找到：{args.target}")
        return 4
    print(f"已移除：{args.target}")
    return 0


def cmd_archive_exited(args: argparse.Namespace) -> int:
    pool = load_pool()
    cutoff = date.today() - timedelta(days=7)
    keep: list[dict[str, Any]] = []
    archive: list[dict[str, Any]] = []
    for item in pool.get("items", []):
        updated = date.fromisoformat(str(item.get("updated_at") or today_text()))
        if item.get("status") == "淘汰" and updated <= cutoff:
            archive.append(item)
        else:
            keep.append(item)
    pool["items"] = keep
    save_pool(pool)
    if archive:
        existing = DataManager.load_state("pool_archive", {"items": []})
        existing["items"] = existing.get("items", []) + archive
        with DataManager.state_lock("pool_archive"):
            DataManager.save_state("pool_archive", existing)
    print(f"已归档淘汰记录：{len(archive)}")
    return 0


def cmd_add_pending(args: argparse.Namespace) -> int:
    report = safe_build_report(args.target, args.offline)
    record = record_from_report(args.target, report, args.offline)
    pending = load_pending()
    items = list(pending.get("items", []))
    existing_index = next((index for index, item in enumerate(items) if args.target in {str(item.get("target")), str(item.get("name")), str(item.get("symbol"))}), None)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if existing_index is not None:
        items[existing_index] = {
            **record,
            "added_at": now,
            "source": "trader",
        }
    else:
        items.append({
            **record,
            "added_at": now,
            "source": "trader",
        })
    pending["items"] = items
    save_pending(pending)
    stage = str(report.get("stage") or "?")
    scene = str(report.get("scene") or "?")
    momentum = record.get("momentum_state", "?")
    print(f"已加入待确认池：{record['name']}")
    print(f"现价：{price(record['current'])}元  结构{stage}  场景{scene}")
    print(f"触发：{price(record['trigger'])}元")
    print(f"防守：{price(record['defense'])}元")
    print(f"建议动作：{record['status']}  动能{momentum}")
    print(f"入池建议：{record['admission_result']}{record['admission_reason']}")
    print(f"评分：{record['total_score']}分（缠{record['chanlun_score']} 威{record['wyckoff_score']} 筹{record['chip_score']}）")
    print(f"数量：{len(items)}")
    print("盘后可说\"看看待确认池\"或\"确认入池 <股票名>\"")
    return 0


def cmd_show_pending(args: argparse.Namespace) -> int:
    pending = load_pending()
    items = sorted(pending.get("items", []), key=lambda i: int(i.get("total_score") or 0), reverse=True)
    if not items:
        print("待确认池为空")
        print("盘中对 Hermes 说\"看看 XX\"，回复 1 后可加入待确认池。")
        return 0
    print(f"待确认池  {len(items)}  盘后确认后正式入池")
    print("")
    for i, item in enumerate(items, 1):
        name = item.get("name", "?")
        status = item.get("status", "?")
        score = item.get("total_score", "?")
        trigger = price_yuan(item.get("trigger"))
        defense = price_yuan(item.get("defense"))
        current = price_yuan(item.get("current"))
        admission = item.get("admission_result", "?")
        added = item.get("added_at", "")
        print(f"{i}. {name}  {current}  触发{trigger}  防守{defense}")
        print(f"   状态{status}  评分{score}  入池{admission}  加入于{added}")
    print("")
    print("对 Hermes 说\"确认入池 <股票名>\" 可将其正式加入选股池。")
    return 0


def cmd_confirm_to_pool(args: argparse.Namespace) -> int:
    pending = load_pending()
    items = list(pending.get("items", []))
    target = args.target
    found_index = next((index for index, item in enumerate(items) if target in {str(item.get("target")), str(item.get("name")), str(item.get("symbol"))}), None)
    if found_index is None:
        print(f"待确认池中未找到：{target}")
        return 4
    pending_item = items.pop(found_index)
    pool = load_pool()
    pool_items = list(pool.get("items", []))
    if len(pool_items) >= POOL_LIMIT:
        sorted_pool = sort_items(pool_items)
        ejected = sorted_pool[-1]
        ejected_status = ejected.get("status", "?")
        ejected_score = ejected.get("total_score", "?")
        print(f"池容量已满：{len(pool_items)}/{POOL_LIMIT}")
        print(f"已自动移除最后一名：{ejected['name']}（{ejected_status} 评分{ejected_score}）")
        ejected_name = ejected.get("name") or ejected.get("target") or ejected.get("symbol")
        pool_items = [p for p in pool_items if not (ejected_name and ejected_name in {str(p.get("target")), str(p.get("name")), str(p.get("symbol"))})]
    record = {
        **pending_item,
        "added_at": today_text(),
        "confirmed_in_pool_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    existing_index = next((index for index, item in enumerate(pool_items) if target in {str(item.get("target")), str(item.get("name")), str(item.get("symbol"))}), None)
    if existing_index is None:
        pool_items.append(record)
    else:
        pool_items[existing_index] = record
    pool["items"] = pool_items
    save_pool(pool)
    pending["items"] = items
    save_pending(pending)
    print(f"已确认入池：{pending_item['name']}")
    print(f"触发：{price(pending_item.get('trigger'))}元")
    print(f"防守：{price(pending_item.get('defense'))}元")
    print(f"动作：{pending_item.get('status')}  评分：{pending_item['total_score']}分")
    print("选股池")
    for item in sort_items(pool_items):
        print(f"  {item.get('name')}  {item.get('status')}  评分{item.get('total_score')}  触发{price_yuan(item.get('trigger'))}  防守{price_yuan(item.get('defense'))}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    from run_analysis import build_report
    from concurrent.futures import ThreadPoolExecutor

    targets = [t.strip() for t in (args.targets or []) if t.strip()]
    if len(targets) < 2:
        print("至少需要两只股票做比较", file=sys.stderr)
        return 1
    # 并行分析：多只票的 build_report 互相独立，并行执行总耗时≈最慢一只。
    # build_report 内部已对单票的缠论/威科夫/动量做并行，这里再做一层票间并行。
    results: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(targets), 5)) as ex:
        future_to_target = {ex.submit(build_report, t): t for t in targets}
        for fut, t in future_to_target.items():
            try:
                results.append(fut.result())
            except Exception as exc:
                errors[t] = str(exc)
    for t, msg in errors.items():
        print(f"{t}：数据获取失败（{msg}）", file=sys.stderr)
    if len(results) < 2:
        print("至少需要两只股票数据成功才能比较", file=sys.stderr)
        return 1
    print(render_compare(results))
    return 0


def _latest_signal_summary(report: dict[str, Any], store_path: Path | None = None) -> str:
    symbol = str(report.get("symbol") or "")
    if not symbol:
        return ""
    try:
        from trader_shared.signal_store import load_recent_signals
        signals = load_recent_signals(symbol, limit=3, path=store_path)
    except Exception:
        return ""
    recent = [s for s in signals if isinstance(s, dict)]
    if not recent:
        return ""
    latest = recent[-1]
    sig_type = str(latest.get("signal_type") or "")
    action = str(latest.get("action") or "")
    source = str(latest.get("source_skill") or "")
    if sig_type in ("low_buy_triggered", "low_buy_watch", "low_buy"):
        return f"🟢T0低吸{action if source == 't0' else ''}"
    if sig_type in ("high_sell_triggered", "high_sell_watch", "high_sell"):
        return f"🔴T0高抛" if source == "t0" else f"🔴高抛{action}"
    if sig_type == "risk_stop":
        return "⚠️止损"
    if sig_type == "reduce":
        return f"📉减仓({action})"
    if sig_type == "track":
        return f"👁跟踪"
    return ""


def render_compare(reports: list[dict[str, Any]]) -> str:
    from trader_shared.candidate_core import atr_volatility_level

    # ── 评分辅助函数 ──
    def _scores(r: dict[str, Any]) -> dict[str, int]:
        try:
            return score_report(r)
        except Exception:
            return {"total_score": 0, "chanlun_score": 0, "wyckoff_score": 0,
                    "chip_score": 0, "fusion_score": 0, "momentum_score": 0, "momentum_tag": ""}

    def _sort_key(r: dict[str, Any]):
        try:
            sc = score_report(r)
            return (-sc.get("total_score", 0),)
        except Exception:
            return (0,)

    sorted_reports = sorted(reports, key=_sort_key)

    # ── 大盘 ──
    market_level = get_market_level()
    lines = [f"对比 — {' vs '.join(r.get('name','?') for r in sorted_reports)}", ""]
    if market_level:
        lines.append(f"🌍 大盘{market_level} | {get_market_note()}")
        lines.append("")

    # ── 逐票详情 ──
    for i, r in enumerate(sorted_reports, 1):
        name = r.get("name", "?")
        code = str(r.get("symbol", "")).replace(".SH", "").replace(".SZ", "")
        scene = str(r.get("scene") or "?")
        current = to_float(r.get("current")) or 0.0
        stop_val = to_float(r.get("stop")) or 0.0
        support_val = to_float(r.get("support")) or 0.0
        resistance_val = to_float(r.get("resistance")) or 0.0
        confirm_val = to_float(r.get("confirm")) or 0.0
        take_val = to_float(r.get("take")) or 0.0

        atr14 = to_float(r.get("atr14")) or 0.0
        atr_ratio = to_float(r.get("atr_ratio")) or 0.0
        atr_level, atr_cap = atr_volatility_level(atr_ratio)
        atr_pct = atr_ratio * 100

        if atr_ratio >= 0.03:
            atr_text = f"波幅偏高({atr_pct:.0f}%)"
        elif atr_ratio >= 0.02:
            atr_text = f"波动偏大({atr_pct:.0f}%)"
        elif atr14 > 0:
            atr_text = f"波动正常({atr_pct:.0f}%)"
        else:
            atr_text = "数据不足"

        # 阶段 + 动能
        major_stage = str(r.get("major_stage") or "")
        momentum = str(r.get("short_term_momentum") or "")

        # 评分
        scores = _scores(r)
        total = scores.get("total_score", 0)
        chan = scores.get("chanlun_score", 0)
        wyck = scores.get("wyckoff_score", 0)
        chip = scores.get("chip_score", 0)
        fus = scores.get("fusion_score", 0)
        mom = scores.get("momentum_score", 0)
        chan_max = 45
        wyck_max = 30
        chip_max = 25
        fus_max = 20
        mom_max = 20

        # 融合详情
        fusion = r.get("fusion") or {}
        fusion_action = fusion.get("action", "")
        fusion_conf = fusion.get("confidence", 0)
        fusion_ws = fusion.get("weighted_score", 0)

        # 主力评分
        mf = r.get("main_force_score") or {}
        mf_total = mf.get("total_score", 0) if isinstance(mf, dict) else 0

        lines.append(f"{i}. {name}（{code}）  {scene}  {current:.2f}元  {atr_text}")
        lines.append(f"   阶段：{major_stage} ｜ 动能：{momentum} ｜ 综合评分：{total}")

        # 五层打分
        lines.append(f"   五层打分：缠{chan}/{chan_max} 威{wyck}/{wyck_max} 筹{chip}/{chip_max} 融{fus}/{fus_max} 动{mom}/{mom_max}")

        # 融合 + 主力
        if fusion_action:
            lines.append(f"   融合：{fusion_action}（得分 {fusion_ws:+.2f}，置信度 {fusion_conf:.0%}）")
        if mf_total > 0:
            lines.append(f"   主力评分：{mf_total}分（{mf.get('label', '')}）")

        # 关键价位
        lines.append(f"   关键位：止损 {stop_val:.2f} 支撑 {support_val:.2f} 现价 {current:.2f} 压力 {resistance_val:.2f} 确认 {confirm_val:.2f}")

        # EXPMA 趋势
        expma = r.get("expma_status") or {}
        expma_label = expma.get("trend_label", "") if isinstance(expma, dict) else ""
        if expma_label:
            lines.append(f"   EXPMA：{expma_label}")

        # 筹码峰
        chip_peaks = r.get("chip_peaks") or []
        if chip_peaks:
            support_peaks = sorted(
                [p for p in chip_peaks if float(p.get("price", 0)) < current],
                key=lambda p: float(p.get("share_of_total", 0)), reverse=True
            )
            resist_peaks = sorted(
                [p for p in chip_peaks if float(p.get("price", 0)) > current],
                key=lambda p: float(p.get("share_of_total", 0)), reverse=True
            )
            if support_peaks:
                top_s = support_peaks[0]
                lines.append(f"   筹码支撑：{float(top_s.get('price',0)):.2f}元（占比{float(top_s.get('share_of_total',0))*100:.0f}%）")
            if resist_peaks:
                top_r = resist_peaks[0]
                lines.append(f"   筹码压力：{float(top_r.get('price',0)):.2f}元（占比{float(top_r.get('share_of_total',0))*100:.0f}%）")

        # 多周期共振
        resonance = r.get("resonance") or {}
        if isinstance(resonance, dict) and resonance.get("total_score", 0) > 0:
            _format_resonance_score(resonance.get("total_score", 0), lines)

        # 信号摘要
        signal_summary = _latest_signal_summary(r)
        if signal_summary:
            lines.append(f"   信号：{signal_summary}")

        lines.append("")

    # ── 量化排序结论 ──
    ranking = _render_ranking_conclusion(sorted_reports, _scores, market_level)
    lines.extend(ranking)

    return "\n".join(lines)


def _render_ranking_conclusion(sorted_reports: list[dict[str, Any]],
                                get_scores,
                                market_level: str) -> list[str]:
    """生成量化排序结论，解释为什么这样排。"""
    if len(sorted_reports) < 2:
        return []

    scores_list = [get_scores(r) for r in sorted_reports]

    # 多维度打分对比
    dim_labels = {
        "total_score": "综合",
        "chanlun_score": "缠论",
        "wyckoff_score": "威科夫",
        "chip_score": "筹码",
        "fusion_score": "融合",
        "momentum_score": "动能",
    }

    result: list[str] = ["", "📊 多维度对比"]

    # 表头
    headers = ["标的"] + [dim_labels.get(d, d) for d in dim_labels if d != "total_score"] + ["总分"]
    result.append("  " + "  ".join(f"{h:>6s}" for h in headers))

    # 数据行（与表头顺序一致：标的 缠论 威科夫 筹码 融合 动能 总分）
    max_name_len = max((len(str(r.get("name", "?"))[:8]) for r in sorted_reports), default=4)
    for i, (r, sc) in enumerate(zip(sorted_reports, scores_list)):
        name = str(r.get("name", "?"))[:8]
        vals = [f"{name:<{max_name_len}s}"]
        for d in dim_labels:
            if d == "total_score":
                continue  # total_score 放到最后
            vals.append(f"{sc.get(d, 0):>6d}")
        vals.append(f"{sc.get('total_score', 0):>6d}")
        result.append("  " + "  ".join(vals))

    result.append("")

    # 排序理由
    winner = sorted_reports[0]
    winner_scores = scores_list[0]
    winner_name = winner.get("name", "?")
    winner_total = winner_scores.get("total_score", 0)

    reasons = []
    for j in range(1, len(sorted_reports)):
        other = sorted_reports[j]
        other_scores = scores_list[j]
        other_total = other_scores.get("total_score", 0)
        delta = winner_total - other_total
        if delta <= 0:
            continue

        # 找出赢在哪几个维度
        wins = []
        for d in ("chanlun_score", "wyckoff_score", "chip_score", "fusion_score", "momentum_score"):
            wd = winner_scores.get(d, 0) - other_scores.get(d, 0)
            if wd > 0:
                dim_name = dim_labels.get(d, d)
                wins.append(f"{dim_name}+{wd}")

        reason = f"{winner_name} 领先 {delta} 分"
        if wins:
            reason += f"（优势：{', '.join(wins[:3])}）"
        reasons.append(reason)

    # ATR 补充提示
    atr_info = []
    for r in sorted_reports:
        atr_pct = to_float(r.get("atr_ratio")) or 0.0
        atr_pct *= 100
        atr_info.append((r.get("name", "?"), atr_pct))
    min_atr_name = min(atr_info, key=lambda x: x[1])[0]
    if len(atr_info) >= 2:
        reasons.append(f"波动率最低：{min_atr_name}（{min(atr_info, key=lambda x: x[1])[1]:.0f}%）")

    if reasons:
        result.append("💡 排序理由：")
        for reason in reasons:
            result.append(f"  • {reason}")

    # 大盘提示 + 明确推荐
    if market_level == "很差":
        result.append("")
        result.append("👉 大盘很差，所有标的先观察，不急着买")
    elif market_level == "偏弱":
        result.append("")
        result.append("👉 大盘偏弱，优先选波动小、信号靠谱的")
    elif len(sorted_reports) >= 2:
        result.append("")
        w_name = winner_name
        w_score = winner_total
        s_name = sorted_reports[1].get("name", "?")
        s_score = scores_list[1].get("total_score", 0)
        if w_score > s_score:
            gap = w_score - s_score
            if gap >= 10:
                result.append(f"👉 综合评分差距明显（{gap}分），优先选择 {w_name}")
            elif gap >= 5:
                result.append(f"👉 {w_name} 综合略优（领先{gap}分），建议优先关注")
            else:
                result.append(f"👉 {w_name} 与 {s_name} 分差不大（{gap}分），结合当前持仓综合判断")
        else:
            result.append(f"👉 同等条件下，优先选波动小的（{min_atr_name} 波动最低）")

    return result


def cmd_reconcile(args: argparse.Namespace) -> int:
    """视图调和：对比 pool 快照与实时行情，暴露不一致。"""
    pool = load_pool()
    items = active_items(pool)
    items = _refresh_pool_prices(items, pool)
    sorted_items = sort_items_unified(items)

    lines = ["📋 视图调和报告", ""]
    issues_found = 0

    for item in sorted_items:
        name = item.get("name", "?")
        item_lines = [f"{name}"]

        # 1. 触发价偏离检查
        current = to_float(item.get("current")) or 0
        trigger = to_float(item.get("trigger")) or 0
        if current > 0 and trigger > 0:
            trigger_pct = (trigger - current) / current * 100
            if abs(trigger_pct) > 5:
                item_lines.append(f"  触发价 {trigger:.2f} vs 现价 {current:.2f}（偏离 {trigger_pct:+.0f}%）← 建议运行 pool refresh")
                issues_found += 1

        # 2. 价格过期检查
        fw = _price_freshness_warning(item)
        if fw:
            item_lines.append(f"  {fw}")
            issues_found += 1

        # 3. 阶段快照过期检查
        major_stage = str(item.get("major_stage") or "-")
        momentum = str(item.get("momentum") or "-")
        item_lines.append(f"  阶段快照：{major_stage}+{momentum}")

        if len(item_lines) > 1:
            lines.extend(item_lines)
            lines.append("")

    if issues_found == 0:
        lines.append("✅ 所有视图一致，无异常。")
    else:
        lines.append(f"共 {issues_found} 项不一致，建议运行 pool refresh 同步数据。")

    print("\n".join(lines))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage Trader Pool candidate workflow.")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("analyze", "add", "add-pending"):
        item = sub.add_parser(command)
        item.add_argument("--target", required=True)
        item.add_argument("--offline", action="store_true")
    sub.add_parser("watch")
    sub.add_parser("list")
    sub.add_parser("show-pending")
    sub.add_parser("plan")
    refresh = sub.add_parser("refresh")
    refresh.add_argument("--target", help="只刷新指定票（名称或代码），默认全池")
    sub.add_parser("rank")
    sub.add_parser("reconcile")
    sub.add_parser("add-last")
    review = sub.add_parser("review")
    review.add_argument("--offline", action="store_true")
    remove = sub.add_parser("remove")
    remove.add_argument("--target", required=True)
    confirm = sub.add_parser("confirm-to-pool")
    confirm.add_argument("--target", required=True)
    sub.add_parser("archive-exited")
    compare = sub.add_parser("compare")
    compare.add_argument("--targets", nargs="+", required=True)
    quick = sub.add_parser("quick-add")
    quick.add_argument("--target", required=True)
    quick.add_argument("--offline", action="store_true")
    return parser.parse_args()


def _cmd_quick_add(args: argparse.Namespace) -> int:
    result = quick_add(args.target, offline=args.offline)
    if result.get("ok"):
        rec = result.get("record", {})
        print(f"入池成功: {rec.get('target')} | 评分{rec.get('total_score')} | 阶段{rec.get('major_stage')} | 状态{rec.get('status')}")
        return 0
    else:
        print(f"入池拒绝: {result.get('reason')}")
        return 1


def main() -> int:
    args = parse_args()
    handlers = {
        "analyze": cmd_analyze,
        "add": cmd_add,
        "list": cmd_list,
        "show-pending": cmd_show_pending,
        "add-pending": cmd_add_pending,
        "confirm-to-pool": cmd_confirm_to_pool,
        "compare": cmd_compare,
        "plan": cmd_plan,
        "rank": cmd_rank,
        "refresh": cmd_refresh,
        "reconcile": cmd_reconcile,
        "add-last": cmd_add_last,
        "review": cmd_review,
        "watch": cmd_watch,
        "remove": cmd_remove,
        "archive-exited": cmd_archive_exited,
        "quick-add": lambda args: _cmd_quick_add(args),
    }
    try:
        return handlers[args.command](args)
    except Exception as exc:
        print(f"trader pool failed: {exc}", file=sys.stderr)
        return 1


def _format_resonance_score(score: int, lines: list[str]) -> None:
    """格式化共振评分（微信可读版）。"""
    parts = []
    if score >= 8:
        parts.append("多时间窗共振强")
    elif score >= 6:
        parts.append("部分时间窗共振")
    elif score >= 4:
        parts.append("低分，信号未共振")
    lines.append(f"   共振评分：{score}分（{'；'.join(parts)}）")


if __name__ == "__main__":
    raise SystemExit(main())
