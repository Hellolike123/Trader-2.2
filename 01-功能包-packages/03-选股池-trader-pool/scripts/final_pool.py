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

ROOT = Path(__file__).resolve().parents[3]
SHARED_CANDIDATE = ROOT / "02-共享模块-shared" / "02-候选逻辑-candidate"
SHARED_SCRIPTS = ROOT / "02-共享模块-shared" / "scripts"
SHARED_ROOT = ROOT / "02-共享模块-shared"
SHARED_TS = SHARED_ROOT / "trader_shared"
for _p in (SHARED_CANDIDATE, SHARED_SCRIPTS, SHARED_ROOT, SHARED_TS):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from run_analysis import build_report
import candidate_core as core

try:
    from trader_shared import get_market_level, get_market_note, write_stock
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


POOL_LIMIT = 10
EXECUTION_LIMIT = 3
CONTRACT_VERSION = "trader_pool_v1"


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
    payload = load_json(pending_path(), empty_pending())
    payload.setdefault("contract_version", CONTRACT_VERSION_PENDING)
    payload.setdefault("items", [])
    return payload


def save_pending(payload: dict[str, Any]) -> None:
    payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_json(pending_path(), payload)


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
    payload = load_json(pool_path(), empty_pool())
    payload.setdefault("contract_version", CONTRACT_VERSION)
    payload.setdefault("items", [])
    return payload


def save_pool(payload: dict[str, Any]) -> None:
    payload["updated_at"] = today_text()
    save_json(pool_path(), payload)


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
        "stage": "震荡",
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
    chan = 24
    wyckoff = 15
    chip = 15

    if stage == "走强":
        chan += 10
    elif stage == "修复":
        chan += 7
    elif stage == "震荡":
        chan += 3
    elif stage == "转弱":
        chan -= 10

    if scene in {"等转强", "突破确认", "突破观察", "冲高减仓"}:
        chan += 7
    elif scene in {"低吸观察", "防守观察"}:
        chan += 4
    elif scene == "暂不碰":
        chan -= 10

    if current and confirm:
        distance = abs(confirm - current) / max(current, 0.01)
        if distance <= 0.02:
            chan += 4
        elif distance <= 0.05:
            chan += 2

    volume_text = str(report.get("volume_text") or "")
    if "放大" in volume_text or "放量" in volume_text:
        wyckoff += 8
    elif "缩量" in volume_text or "收缩" in volume_text:
        wyckoff += 5
    else:
        wyckoff += 3
    if momentum_passes(report):
        wyckoff += 5

    if current > stop:
        chip += 5
    if support <= current <= max(confirm, support):
        chip += 4
    if take > current:
        chip += 3

    chan = max(0, min(45, chan))
    wyckoff = max(0, min(30, wyckoff))
    chip = max(0, min(25, chip))
    return {"chanlun_score": chan, "wyckoff_score": wyckoff, "chip_score": chip, "total_score": chan + wyckoff + chip}


def admission_for(report: dict[str, Any], scores: dict[str, int]) -> dict[str, str]:
    current = to_float(report.get("current")) or 0.0
    confirm = to_float(report.get("confirm")) or current
    stop = to_float(report.get("stop")) or current
    if stop and current <= stop:
        return {"result": "拒绝", "reason": "现价跌破或贴近防守位，结构审查失败。", "status": "淘汰"}
    if not confirm or not stop:
        return {"result": "待补", "reason": "触发位或防守位不清楚，暂不参与排序。", "status": "观察"}
    if scores["total_score"] >= 70:
        status = "执行" if momentum_passes(report) else "观察"
        return {"result": "入池", "reason": "结构成立，触发位和防守位清楚。", "status": status}
    if scores["total_score"] >= 55:
        return {"result": "入池", "reason": "结构可跟踪，但动能或位置仍需确认。", "status": "观察"}
    return {"result": "待补", "reason": "结构尚未充分确认，暂不进入执行排序。", "status": "观察"}


def structure_summary(report: dict[str, Any]) -> str:
    stage = str(report.get("stage") or "待补")
    scene = str(report.get("scene") or "待补")
    if scene in {"等转强", "突破确认", "突破观察", "冲高减仓"}:
        return f"{stage}中，接近确认位，等待放量站稳。"
    if scene in {"低吸观察", "防守观察"}:
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
    return {
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
        "atr14": atr14,
        "atr_ratio": atr_ratio,
        "atr_level": atr_level,
        "atr_cap": atr_cap,
        **scores,
    }


def active_items(pool: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in pool.get("items", []) if item.get("status") in {"执行", "观察", "淘汰"}]


def sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_rank = {"执行": 3, "观察": 2, "淘汰": 1}
    return sorted(items, key=lambda item: (status_rank.get(str(item.get("status")), 0), int(item.get("total_score") or 0), -float(item.get("atr_ratio") or 0)), reverse=True)


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


def cmd_show(args: argparse.Namespace) -> int:
    pool = load_pool()
    items = sort_items(active_items(pool))
    count = counts(items)
    print(f"选股池  {len(items)}/{POOL_LIMIT}  执行{count['执行']}  观察{count['观察']}  淘汰{count['淘汰']}")
    print("")
    for item in items:
        print(f"  {item.get('name')}  {item.get('status')}  评分{item.get('total_score')}  触发{price_yuan(item.get('trigger'))}  防守{price_yuan(item.get('defense'))}")
    return 0


def rank_status(item: dict[str, Any]) -> str:
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
}


def render_rank(items: list[dict[str, Any]]) -> str:
    from candidate_core import atr_volatility_level

    sorted_items = sort_items(items)
    market_level = get_market_level()

    lines = [f"选股池  ｜  {'大盘' + market_level + '，防守优先' if market_level else '持仓排序'}"]
    lines.append("")

    for i, item in enumerate(sorted_items):
        rs = rank_status(item)
        stars = STAR_MAP.get(rs, "⭐")
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f" {i+1}."

        name = item.get("name", "?")
        current = to_float(item.get("current")) or 0
        atr_ratio = to_float(item.get("atr_ratio")) or 0
        atr_level, atr_cap = atr_volatility_level(atr_ratio) if atr_ratio > 0 else ("数据不足", 10)
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

        if buy_low and buy_high:
            buy_text = f"买  {buy_low:.2f}-{buy_high:.2f} 止跌确认"
        elif buy_low:
            buy_text = f"买  {buy_low:.2f} 止跌确认"
        else:
            buy_text = "买  暂无"

        lines.append(f"{medal}  {stars}  {name}  {rs}  {current:.2f}  {atr_text}")
        lines.append(f"    {buy_text}  ｜  仓位 {atr_cap}%  ｜  止损 {stop_val:.2f}")
        lines.append("")

    first = sorted_items[0] if sorted_items else None
    second = sorted_items[1] if len(sorted_items) > 1 else None
    third = sorted_items[2] if len(sorted_items) > 2 else None

    lines.append("👉  ")

    if first:
        fname = first.get("name", "?")
        fs = rank_status(first)
        fcap = atr_volatility_level(to_float(first.get("atr_ratio")) or 0)[1]
        lines.append(f"    首选{fname}。{fs}信号最强，仓位压到{fcap}%所以风险可控。")

    if second:
        sname = second.get("name", "?")
        ss = rank_status(second)
        lines.append(f"    {sname}{ss}差一档，做备选。")

    if third:
        tname = third.get("name", "?")
        lines.append(f"    {tname}再等等。")

    lines.extend([
        "",
        "    利弗莫尔：\"他们不是被市场打败的，是被自己打败的——",
        "    有脑子，但坐不住。\"",
        "    不抢跑，等止跌确认再动手。",
    ])

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
    return f"{item.get('name')} 有明确触发和防守，具体盘中触发交给 t0-trader。"


def rank_sentence(actionable: list[dict[str, Any]]) -> str:
    if not actionable:
        return "今天池内没有明确优先对象，先不主动参与。"
    first = actionable[0]
    return f"今天优先盯{first.get('name')}，只按触发位和防守位执行，不把观察区当操作价。"


def cmd_rank(args: argparse.Namespace) -> int:
    pool = load_pool()
    print(render_rank(active_items(pool)))
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
    sorted_items = sort_items(items)
    count = counts(sorted_items)
    execution_items = [item for item in sorted_items if item.get("status") == "执行"][:EXECUTION_LIMIT]
    top_items = execution_items + [item for item in sorted_items if item.get("status") != "执行"]

    lines = [
        f"选股池盘后分析 — {today_text()}",
        f"容量 {len(sorted_items)}/{POOL_LIMIT}｜执行{count['执行']}｜观察{count['观察']}｜淘汰{count['淘汰']}｜明日只盯Top2",
        "",
    ]

    if top_items:
        lines.append("明日优先级")
        for i, item in enumerate(top_items[:3], 1):
            rank_emoji = ["🥇", "🥈", "🥉"][i - 1]
            lines.append(f"{rank_emoji} {item['name']}（{item['status']}）")
            lines.append(f"  {action_for(item)}")
            lines.append(f"  触发{price(item.get('trigger'))}元  防守{price(item.get('defense'))}元  仓位{position_for(item)}")

        lines.append("")
        lines.append("评分总览")
        for item in sorted_items:
            lines.append(
                f"  {item.get('name')}  总分{item['total_score']}  "
                f"缠{item['chanlun_score']}/45 威{item['wyckoff_score']}/30 筹{item['chip_score']}/25  "
                f"{item['status']}"
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


def trade_hint(item: dict[str, Any]) -> str:
    if item.get("status") == "执行":
        return f"放量站稳{price(item['trigger'])}元才买 → 回踩不破可加至3成"
    return f"{price(item['trigger'])}元站稳再看，防守{price(item.get('defense'))}元"


def one_sentence(items: list[dict[str, Any]]) -> str:
    top = [str(item.get("name")) for item in items[:2]]
    if not top:
        return "当前选股池没有可执行对象，明天不主动处理。"
    return f"明天只重点盯 {' 和 '.join(top)}；不触发不买，其他只盘后更新。"


def cmd_plan(args: argparse.Namespace) -> int:
    pool = load_pool()
    items = active_items(pool)
    markdown = render_plan(items)
    execution = [item for item in sort_items(items) if item.get("status") == "执行"][:EXECUTION_LIMIT]
    save_json(last_plan_path(), {"contract_version": CONTRACT_VERSION, "date": today_text(), "execution_items": execution, "markdown": markdown})
    print(markdown)
    return 0


def cmd_add_last(args: argparse.Namespace) -> int:
    last_target_path = os.path.expanduser("~/.trader/last_target.txt")
    if not os.path.exists(last_target_path):
        print("没有找到最近分析的标的，请先运行 trader 分析。")
        return 1
    target = open(last_target_path).read().strip()
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
    record["added_at"] = record["added_at"]
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
    plan = load_json(last_plan_path(), {"execution_items": []})
    execution_items = plan.get("execution_items") or []
    rows: list[tuple[dict[str, Any], str, str, str, str]] = []
    summary = {"命中": 0, "未触发": 0, "失效": 0, "误判": 0}
    for item in execution_items:
        report = safe_build_report(str(item.get("target") or item.get("name")), args.offline)
        result, performance, note = review_result(item, report)
        summary[result] = summary.get(result, 0) + 1
        rows.append((item, f"{price(item.get('trigger'))} 触发，{price(item.get('defense'))} 防守", performance, result, note))

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
        existing = load_json(archive_path(), {"items": []})
        existing["items"] = existing.get("items", []) + archive
        save_json(archive_path(), existing)
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
    targets = [t.strip() for t in (args.targets or []) if t.strip()]
    if len(targets) < 2:
        print("至少需要两只股票做比较", file=sys.stderr)
        return 1
    results = []
    for target in targets:
        try:
            r = build_report(target)
            results.append(r)
        except Exception as exc:
            print(f"{target}：数据获取失败（{exc}）", file=sys.stderr)
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
        from signal_store import load_recent_signals
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
        return f"🟢T0低吸{action if source == 't0-trader' else ''}"
    if sig_type in ("high_sell_triggered", "high_sell_watch", "high_sell"):
        return f"🔴T0高抛" if source == "t0-trader" else f"🔴高抛{action}"
    if sig_type == "risk_stop":
        return "⚠️止损"
    if sig_type == "reduce":
        return f"📉减仓({action})"
    if sig_type == "track":
        return f"👁跟踪"
    return ""


def render_compare(reports: list[dict[str, Any]]) -> str:
    from candidate_core import STATUS_SCORE, atr_volatility_level

    def sort_key(r: dict[str, Any]):
        scene = str(r.get("scene") or "")
        atr_ratio = float(r.get("atr_ratio", 0) or 0)
        return (-STATUS_SCORE.get(scene, 0), atr_ratio)

    sorted_reports = sorted(reports, key=sort_key)
    market_level = get_market_level()
    lines = [f"对比 — {' vs '.join(r.get('name','?') for r in sorted_reports)}", ""]
    if market_level:
        lines.append(f"🌍 大盘{market_level} | {get_market_note()}")
        lines.append("")

    for i, r in enumerate(sorted_reports, 1):
        name = r.get("name", "?")
        scene = str(r.get("scene") or "?")
        current = float(r.get("current", 0) or 0)
        atr14 = float(r.get("atr14", 0) or 0)
        atr_ratio = float(r.get("atr_ratio", 0) or 0)
        atr_level, atr_cap = atr_volatility_level(atr_ratio)
        atr_pct = atr_ratio * 100
        stop_val = float(r.get("stop", 0) or 0)

        if atr_ratio >= 0.03:
            atr_text = f"波幅偏高({atr_pct:.0f}%)"
        elif atr_ratio >= 0.02:
            atr_text = f"波动偏大({atr_pct:.0f}%)"
        elif atr14 > 0:
            atr_text = f"波动正常({atr_pct:.0f}%)"
        else:
            atr_text = "数据不足"

        wr_text = ""
        try:
            from trader_shared import stats_by_type
            st = stats_by_type("trader")
            signal_stats = st.get(scene, {})
            if signal_stats.get("filled", 0) >= 1:
                wr_text = f" 胜率{signal_stats['win_rate']*100:.0f}%"
        except Exception:
            pass

        signal_summary = _latest_signal_summary(r)
        signal_text = f"  {signal_summary}" if signal_summary else ""

        lines.append(f"{i}. {name}  {scene}  {current:.2f}元  {atr_text}{wr_text}{signal_text}")
        lines.append(f"   首仓≤{atr_cap}% | 止损 {stop_val:.2f}元")
        lines.append("")

    if market_level == "很差":
        lines.append("👉 大盘很差，所有标的先观察，不急着买")
    elif market_level == "偏弱":
        lines.append("👉 大盘偏弱，优先选波动小、信号靠谱的")
    else:
        lines.append("👉 同等条件下，优先选波动小的")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage Trader Pool candidate workflow.")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("analyze", "add", "add-pending"):
        item = sub.add_parser(command)
        item.add_argument("--target", required=True)
        item.add_argument("--offline", action="store_true")
    sub.add_parser("show")
    sub.add_parser("show-pending")
    sub.add_parser("rank")
    sub.add_parser("plan")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    handlers = {
        "analyze": cmd_analyze,
        "add": cmd_add,
        "show": cmd_show,
        "show-pending": cmd_show_pending,
        "add-pending": cmd_add_pending,
        "confirm-to-pool": cmd_confirm_to_pool,
        "compare": cmd_compare,
        "rank": cmd_rank,
        "plan": cmd_plan,
        "add-last": cmd_add_last,
        "review": cmd_review,
        "remove": cmd_remove,
        "archive-exited": cmd_archive_exited,
    }
    try:
        return handlers[args.command](args)
    except Exception as exc:
        print(f"trader-pool failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
