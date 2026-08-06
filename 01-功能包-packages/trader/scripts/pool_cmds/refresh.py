"""Pool commands — refresh.py"""
from __future__ import annotations

import argparse
from typing import Any

from pool_cmds.common import *  # noqa: F403

def cmd_refresh(args: argparse.Namespace) -> int:
    """批量重跑 build_report 刷新全池 record，写回 pool.json。

    - 默认刷新全部 active 项；--target <名称> 只刷单只。
    - 保留 added_at，更新 updated_at，重新走 admission 判定（确保 status 与当前评分/阶段一致）。
    - 衰退期 → 自动标淘汰。
    - 并行刷新（max_workers=5，与 build_report 内部并行一致）。
    - 单只失败 → safe_build_report 自动降级为离线 record，不中断全池。
    - 优化：复用全局共享线程池，避免嵌套 ThreadPoolExecutor 线程爆炸。
    - 批量默认关闭区间套（TRADER_CHAN_NESTING=0），避免每票额外拉 30m 分钟线；
      若调用方已显式设置该环境变量则尊重不覆盖。单票精看仍可 export 开启。
    """
    import os
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 批量路径：未显式配置时默认关 nesting（省 I/O）；已设置则不覆盖
    if "TRADER_CHAN_NESTING" not in os.environ:
        os.environ["TRADER_CHAN_NESTING"] = "0"

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
    # ⚠ 死锁修复（2026-08-06）：不能用全局共享池跑 build_report。
    # build_report → light_data.load_market_snapshot 内部用同一个共享池
    # submit quote/daily/5m/weekly 并 as_completed 等结果；外层把 5 worker
    # 占满后子任务永远排不上 → 全池卡死（实测 300s 零输出）。
    # 这里用独立池跑 build_report，共享池留给内部并行，两层互不抢占。
    target_keys = [str(t.get("target") or t.get("name")) for t in targets]
    # enrich 预热（②b/B2）：批量路径开头集中并行抓取扩展字段写缓存，
    # 让后续 build_report 的 snapshot 阶段命中（TTL 不变，零语义改动；
    # TRADER_SNAPSHOT_ENRICH=0 或失败时自动跳过/降级）。
    try:
        from trader_shared.data_provider import prewarm_enrich

        prewarm_enrich(target_keys)
    except Exception:
        pass  # 预热失败不影响 refresh 主流程
    results: dict[str, dict[str, Any] | None] = {}
    refresh_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="trader-pool-refresh")
    future_to_key: dict = {
        refresh_pool.submit(safe_build_report, key): key for key in target_keys
    }
    for fut in as_completed(future_to_key):
        key = future_to_key[fut]
        try:
            results[key] = fut.result()
        except Exception:
            results[key] = None  # 失败保留原 record
    refresh_pool.shutdown(wait=True)

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
        # 分道/衰退：record_from_report 已写入 lane+status；衰退保持淘汰
        if str(new_record.get("major_stage")) == "衰退" or new_record.get("status") == "淘汰":
            new_record["status"] = "淘汰"
            declined.append(str(new_record.get("name") or key))
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
