"""classic vs cards fusion 对账（纯逻辑，无网络）。

供 scripts/compare_fusion_paths.py 与单测复用。
契约：默认生产仍 classic；本模块只做漂移度量，不改默认路径。
"""
from __future__ import annotations

from typing import Any


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _seat(sig: dict[str, Any] | None) -> dict[str, Any]:
    s = sig if isinstance(sig, dict) else {}
    return {
        "direction": int(s.get("direction") or 0),
        "confidence": round(_f(s.get("confidence")), 4),
        "reason": str(s.get("reason") or "")[:80],
        "from_card": bool(s.get("from_card")),
    }


def snapshot_from_fusion(fusion: dict[str, Any] | None) -> dict[str, Any]:
    """从 merge_decisions / report['fusion'] 抽可对账快照。"""
    f = fusion if isinstance(fusion, dict) else {}
    detail = f.get("signals_detail") if isinstance(f.get("signals_detail"), dict) else {}
    return {
        "path": str(f.get("fusion_input_path") or ""),
        "weighted_score": round(_f(f.get("weighted_score")), 4),
        "confidence": round(_f(f.get("confidence")), 4),
        "disagreement": round(_f(f.get("disagreement")), 4),
        "action": str(f.get("action") or ""),
        "regime": str(f.get("regime") or ""),
        "chan": _seat(detail.get("chan") if isinstance(detail.get("chan"), dict) else None),
        "momentum": _seat(detail.get("momentum") if isinstance(detail.get("momentum"), dict) else None),
        "vpf": _seat(detail.get("vpf") if isinstance(detail.get("vpf"), dict) else None),
    }


def snapshot_from_report(report: dict[str, Any] | None) -> dict[str, Any]:
    r = report if isinstance(report, dict) else {}
    snap = snapshot_from_fusion(r.get("fusion") if isinstance(r.get("fusion"), dict) else {})
    snap["name"] = str(r.get("name") or "")
    snap["symbol"] = str(r.get("symbol") or "")
    snap["current"] = r.get("current")
    snap["data_status"] = str(r.get("data_status") or "")
    return snap


def diff_snapshots(
    classic: dict[str, Any],
    cards: dict[str, Any],
    *,
    score_eps: float = 0.05,
    conf_eps: float = 0.08,
) -> dict[str, Any]:
    """比较两份快照，返回 flags + 摘要。"""
    flags: list[str] = []
    score_delta = round(
        _f(cards.get("weighted_score")) - _f(classic.get("weighted_score")), 4
    )
    if abs(score_delta) > score_eps:
        flags.append(f"scoreΔ={score_delta:+.3f}")

    a_c = str(classic.get("action") or "")
    a_k = str(cards.get("action") or "")
    if a_c != a_k:
        flags.append("action≠")

    seat_dirs: dict[str, dict[str, int]] = {}
    for seat in ("chan", "momentum", "vpf"):
        sc = classic.get(seat) if isinstance(classic.get(seat), dict) else {}
        sk = cards.get(seat) if isinstance(cards.get(seat), dict) else {}
        dc, dk = int(sc.get("direction") or 0), int(sk.get("direction") or 0)
        seat_dirs[seat] = {"classic": dc, "cards": dk}
        if dc != dk:
            flags.append(f"{seat}_dir {dc}→{dk}")
        cc, ck = _f(sc.get("confidence")), _f(sk.get("confidence"))
        if abs(cc - ck) > conf_eps:
            flags.append(f"{seat}_confΔ={ck - cc:+.2f}")

    # 动量席静音特征：classic 有方向/置信，cards 近 0
    mc = classic.get("momentum") if isinstance(classic.get("momentum"), dict) else {}
    mk = cards.get("momentum") if isinstance(cards.get("momentum"), dict) else {}
    if (
        abs(_f(mc.get("direction"))) != 0
        and abs(_f(mk.get("direction"))) == 0
        and _f(mk.get("confidence")) < 0.05
        and _f(mc.get("confidence")) >= 0.2
    ):
        flags.append("mom_silenced")

    if not flags:
        level = "stable"
    elif any(x.startswith("mom_silenced") or x.startswith("action") or "scoreΔ" in x for x in flags):
        # 分数/动作/动量静音 → 不稳；仅 conf 微差可 mild
        hard = [
            x
            for x in flags
            if x.startswith("mom_silenced")
            or x.startswith("action")
            or x.startswith("scoreΔ")
            or "_dir " in x
        ]
        level = "unstable" if hard else "mild"
    else:
        level = "mild"

    return {
        "level": level,
        "flags": flags,
        "score_delta": score_delta,
        "action_classic": a_c,
        "action_cards": a_k,
        "seat_dirs": seat_dirs,
    }


def summarize_batch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """rows: [{target, name, level, flags, score_delta, ...}]"""
    n = len(rows)
    by = {"stable": 0, "mild": 0, "unstable": 0, "error": 0}
    for r in rows:
        lv = str(r.get("level") or "error")
        by[lv] = by.get(lv, 0) + 1
    recommend = "keep_classic"
    if n > 0 and by.get("unstable", 0) == 0 and by.get("error", 0) == 0:
        if by.get("mild", 0) <= max(1, n // 5):
            recommend = "consider_cards_default"
        else:
            recommend = "keep_classic_mild_drift"
    elif n > 0 and by.get("unstable", 0) / n >= 0.3:
        recommend = "keep_classic_fix_cards"
    return {
        "n": n,
        "counts": by,
        "recommend": recommend,
        "recommend_zh": {
            "keep_classic": "偏差偏大：可临时 FUSION_FROM_CARDS=classic 对照，优先修 cards",
            "keep_classic_mild_drift": "有轻微漂移：生产仍默认 cards，建议逐票看",
            "consider_cards_default": "对齐良好（生产已默认 cards）",
            "keep_classic_fix_cards": "不稳定：优先修 cards；必要时 classic 回退",
        }.get(recommend, recommend),
    }


def format_text_report(rows: list[dict[str, Any]], summary: dict[str, Any] | None = None) -> str:
    lines: list[str] = []
    lines.append("Fusion 路径对账 classic vs cards")
    lines.append("")
    for r in rows:
        if r.get("level") == "error":
            lines.append(f"✗ {r.get('target')}  {r.get('error', 'error')}")
            continue
        name = r.get("name") or ""
        tgt = r.get("target") or ""
        lv = r.get("level") or ""
        mark = {"stable": "✓", "mild": "~", "unstable": "!"}.get(lv, "?")
        sc = r.get("score_classic")
        sk = r.get("score_cards")
        flags = " ".join(r.get("flags") or []) or "—"
        lines.append(
            f"{mark} {name}({tgt})  {lv}  "
            f"score {sc}→{sk} (Δ{r.get('score_delta', 0):+.3f})  "
            f"act「{r.get('action_classic','')}」/「{r.get('action_cards','')}」"
        )
        lines.append(f"    {flags}")
        mom_c = r.get("mom_classic")
        mom_k = r.get("mom_cards")
        if mom_c is not None or mom_k is not None:
            lines.append(f"    mom dir/conf  classic={mom_c}  cards={mom_k}")
    lines.append("")
    sm = summary or summarize_batch(rows)
    c = sm.get("counts") or {}
    lines.append(
        f"合计 n={sm.get('n')}  stable={c.get('stable',0)}  "
        f"mild={c.get('mild',0)}  unstable={c.get('unstable',0)}  error={c.get('error',0)}"
    )
    lines.append(f"建议：{sm.get('recommend_zh') or sm.get('recommend')}")
    return "\n".join(lines)
