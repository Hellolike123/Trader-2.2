"""Pool commands — add.py"""
from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from pool_cmds.common import *  # noqa: F403

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

