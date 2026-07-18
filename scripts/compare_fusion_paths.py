#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真票 classic vs cards fusion 对账 CLI。

对同一标的各跑一遍 build_report（FUSION_FROM_CARDS=classic / cards），
比较 weighted_score、action、三席 direction/confidence。

用法（仓库根目录）::

  export PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts

  # 选股池（~/.trader/pool.json）前 N 只
  python scripts/compare_fusion_paths.py --pool --limit 8

  # 指定代码
  python scripts/compare_fusion_paths.py --targets 002050 688248 600000

  # 落盘 JSON
  python scripts/compare_fusion_paths.py --pool --limit 5 --json /tmp/fusion_compare.json

说明：
  - 生产默认已是 cards；本脚本对 classic vs cards 做观测，不改默认。
  - 需要行情网络；失败单票记 error 继续。
  - 判定：stable / mild / unstable；偏差大时建议修 cards 或临时 classic 回退。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SHARED = REPO / "02-共享模块-shared"
SCRIPTS = REPO / "01-功能包-packages" / "trader" / "scripts"
for p in (str(SHARED), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

# 区间套依赖分钟线网络，对账时默认关，保证两路径同一套日线输入
os.environ.setdefault("TRADER_CHAN_NESTING", "0")


def _load_pool_targets(limit: int | None) -> list[str]:
    path = Path.home() / ".trader" / "pool.json"
    if not path.exists():
        raise SystemExit(f"选股池不存在: {path}（可用 --targets）")
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else []
    out: list[str] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        t = str(it.get("target") or it.get("symbol") or "").strip()
        if not t:
            continue
        # 6 位代码优先
        code = t.split(".")[0]
        if code not in out:
            out.append(code)
        if limit is not None and len(out) >= limit:
            break
    if not out:
        raise SystemExit("选股池为空")
    return out


def _build_one(target: str, mode: str) -> dict[str, Any]:
    os.environ["FUSION_FROM_CARDS"] = mode
    from trader_shared.report_builder import build_report

    return build_report(target)


def run_target(
    target: str,
    *,
    score_eps: float,
    conf_eps: float,
) -> dict[str, Any]:
    from trader_shared.fusion_path_compare import (
        diff_snapshots,
        snapshot_from_report,
    )

    try:
        rep_c = _build_one(target, "classic")
        rep_k = _build_one(target, "cards")
    except Exception as exc:
        return {
            "target": target,
            "level": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }

    sc = snapshot_from_report(rep_c)
    sk = snapshot_from_report(rep_k)
    d = diff_snapshots(sc, sk, score_eps=score_eps, conf_eps=conf_eps)
    mom_c = sc.get("momentum") or {}
    mom_k = sk.get("momentum") or {}
    return {
        "target": target,
        "name": sc.get("name") or sk.get("name") or "",
        "symbol": sc.get("symbol") or sk.get("symbol") or "",
        "data_status_classic": sc.get("data_status"),
        "data_status_cards": sk.get("data_status"),
        "level": d["level"],
        "flags": d["flags"],
        "score_delta": d["score_delta"],
        "score_classic": sc.get("weighted_score"),
        "score_cards": sk.get("weighted_score"),
        "action_classic": d["action_classic"],
        "action_cards": d["action_cards"],
        "conf_classic": sc.get("confidence"),
        "conf_cards": sk.get("confidence"),
        "seat_dirs": d["seat_dirs"],
        "mom_classic": f"{mom_c.get('direction')}/{mom_c.get('confidence')}",
        "mom_cards": f"{mom_k.get('direction')}/{mom_k.get('confidence')}",
        "classic": sc,
        "cards": sk,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="classic vs cards fusion 真票对账")
    ap.add_argument("--pool", action="store_true", help="从 ~/.trader/pool.json 取票")
    ap.add_argument("--targets", nargs="*", default=[], help="股票代码/名称，空格分隔")
    ap.add_argument("--limit", type=int, default=8, help="--pool 时最多几只（默认 8）")
    ap.add_argument("--score-eps", type=float, default=0.05, help="|score| 超过则记漂移")
    ap.add_argument("--conf-eps", type=float, default=0.08, help="席位 conf 差超过则记")
    ap.add_argument("--json", dest="json_path", default="", help="写入完整 JSON 路径")
    args = ap.parse_args(argv)

    targets: list[str] = []
    if args.targets:
        targets.extend(str(t).strip() for t in args.targets if str(t).strip())
    if args.pool or not targets:
        if args.pool or not targets:
            try:
                pool_t = _load_pool_targets(args.limit if args.pool or not targets else None)
            except SystemExit:
                if not targets:
                    raise
                pool_t = []
            for t in pool_t:
                if t not in targets:
                    targets.append(t)
            if args.pool and args.limit:
                targets = targets[: args.limit]

    if not targets:
        ap.error("请指定 --pool 或 --targets")

    from trader_shared.fusion_path_compare import format_text_report, summarize_batch

    print(f"对账 {len(targets)} 只：{', '.join(targets)}", flush=True)
    print("每只跑 classic + cards 各一次 build_report（需网络）…", flush=True)

    rows: list[dict[str, Any]] = []
    for i, t in enumerate(targets, 1):
        print(f"  [{i}/{len(targets)}] {t} …", flush=True)
        row = run_target(t, score_eps=args.score_eps, conf_eps=args.conf_eps)
        rows.append(row)
        lv = row.get("level")
        if lv == "error":
            print(f"      error: {row.get('error')}", flush=True)
        else:
            print(
                f"      {lv}  score {row.get('score_classic')}→{row.get('score_cards')}  "
                f"flags={row.get('flags') or '—'}",
                flush=True,
            )

    summary = summarize_batch(rows)
    text = format_text_report(rows, summary)
    print()
    print(text)

    if args.json_path:
        out = {
            "targets": targets,
            "score_eps": args.score_eps,
            "conf_eps": args.conf_eps,
            "rows": rows,
            "summary": summary,
        }
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON → {path}")

    # 有 unstable/error 时 exit 2，便于脚本串联；stable/mild 为 0
    if summary.get("counts", {}).get("error") or summary.get("counts", {}).get("unstable"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
