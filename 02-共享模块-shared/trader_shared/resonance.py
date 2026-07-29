# -*- coding: utf-8 -*-
"""岗位共振（局面图）— 阶段 1：只产 report['resonance']，不改出手。

契约：docs/designs/resonance-and-orchestration.md
场景 v0：pullback_probe（回踩试探）四岗 A 背景 / B 结构 / C 筹码 / D 动能。
只读 report 与 analysis_cards，禁止重跑检测实现。
"""
from __future__ import annotations

from typing import Any

SCHEMA = "resonance_v1"
SCENE_PULLBACK = "pullback_probe"

# 阶段明确否决试探背景
_BG_HARD_NO = frozenset({"派发", "衰退", "派发期", "衰退期"})
# 仍允许讨论回踩试探的阶段（宽松，可后续收紧）
_BG_SOFT_OK = frozenset({
    "蓄势", "蓄势偏强", "蓄势偏弱", "主升",
    "积累", "上涨", "观察",
})


def _s(x: Any) -> str:
    return str(x or "").strip()


def _card(cards: dict[str, Any], key: str) -> dict[str, Any]:
    c = cards.get(key)
    return c if isinstance(c, dict) else {}


def _post(ok: bool, note: str) -> dict[str, Any]:
    return {"ok": bool(ok), "note": _s(note) or ("通过" if ok else "未通过")}


def _eval_background(report: dict[str, Any], cards: dict[str, Any]) -> dict[str, Any]:
    stage = _s(report.get("major_stage"))
    w = _card(cards, "wyckoff_midline") or _card(cards, "wyckoff")
    bias = _s(w.get("bias") or w.get("direction_label")).lower()
    summary = _s(w.get("summary_line"))
    dir_w = w.get("direction")
    try:
        dir_i = int(dir_w) if dir_w is not None else 0
    except (TypeError, ValueError):
        dir_i = 0

    if any(k in stage for k in _BG_HARD_NO):
        return _post(False, f"阶段 {stage or '未知'} 不宜试探")

    # 威科夫明确空向且摘要像派发
    if dir_i < 0 and any(k in summary for k in ("派发", "砸盘", "Markdown", "markdown")):
        return _post(False, "威科夫中线偏空/派发叙事")

    if stage and any(k in stage for k in _BG_SOFT_OK):
        return _post(True, f"阶段 {stage}")
    if stage:
        # 未知阶段：不轻易绿灯
        return _post(False, f"阶段 {stage} 背景未确认可试")
    if dir_i > 0 or bias in ("bullish", "多", "偏多"):
        return _post(True, "威科夫/偏多背景（阶段缺省）")
    if summary:
        return _post(False, "阶段缺失，背景不足")
    return _post(False, "背景数据不足")


def _price_in_zones(current: float, report: dict[str, Any]) -> bool:
    if current <= 0:
        return False
    for key in ("key_prices", "mid_key_prices"):
        kp = report.get(key)
        if not isinstance(kp, dict):
            continue
        for zone_key in ("buy_zone", "pullback_zone", "buy_low", "buy_high", "retrace_zone"):
            z = kp.get(zone_key)
            if isinstance(z, (list, tuple)) and len(z) >= 2:
                try:
                    lo, hi = float(z[0]), float(z[1])
                    if lo > hi:
                        lo, hi = hi, lo
                    if lo <= current <= hi * 1.01:
                        return True
                except (TypeError, ValueError):
                    pass
        # 区间字段 buy_zone_low/high
        try:
            lo = kp.get("buy_zone_low") or kp.get("pullback_low")
            hi = kp.get("buy_zone_high") or kp.get("pullback_high")
            if lo is not None and hi is not None:
                lo_f, hi_f = float(lo), float(hi)
                if lo_f > hi_f:
                    lo_f, hi_f = hi_f, lo_f
                if lo_f <= current <= hi_f * 1.01:
                    return True
        except (TypeError, ValueError):
            pass
    return False


def _eval_structure(report: dict[str, Any], cards: dict[str, Any]) -> dict[str, Any]:
    ch = _card(cards, "chan")
    type_short = _s(ch.get("type_short") or ch.get("type_raw"))
    buy_like = any(
        k in type_short
        for k in ("一买", "二买", "三买", "类二", "买点", "buy")
    )
    try:
        current = float(report.get("current") or 0)
    except (TypeError, ValueError):
        current = 0.0
    in_zone = _price_in_zones(current, report)

    # 纪律/结论里的回踩提示（弱信号）
    disc = report.get("discipline") if isinstance(report.get("discipline"), dict) else {}
    cl = disc.get("entry_checklist") if isinstance(disc.get("entry_checklist"), dict) else {}
    flags = cl.get("flags") if isinstance(cl.get("flags"), dict) else {}
    items = cl.get("items") if isinstance(cl.get("items"), dict) else {}
    pullback_flag = bool(
        flags.get("pullback_ready")
        or flags.get("retrace_ok")
        or items.get("pullback")
        or items.get("retrace")
    )

    if buy_like and in_zone:
        return _post(True, f"买点 {type_short} 且价在回踩/买点区")
    if buy_like:
        return _post(True, f"买点信号 {type_short}")
    if in_zone:
        return _post(True, "现价在回踩/买点区")
    if pullback_flag:
        return _post(True, "清单标记回踩相关就绪")
    if type_short:
        return _post(False, f"结构 {type_short}，未到可试位置")
    return _post(False, "无买点且未回买点区")


def _eval_chip(report: dict[str, Any], cards: dict[str, Any]) -> dict[str, Any]:
    chip = _card(cards, "chip")
    mig = report.get("chip_migration") if isinstance(report.get("chip_migration"), dict) else {}
    # 清仓/严重搬家
    for key in ("action", "signal", "warning", "level", "summary"):
        v = _s(mig.get(key) or chip.get(key))
        if any(k in v for k in ("清仓", "严重", "搬走>50", "搬空", "出货峰")):
            return _post(False, v or "筹码搬家警告")
    if mig.get("clear_signal") is True or mig.get("exit_signal") is True:
        return _post(False, "筹码搬家清仓信号")
    if mig.get("warning") is True and float(mig.get("drop_pct") or 0) >= 40:
        return _post(False, f"底峰下降约 {mig.get('drop_pct')}%")

    peaks = report.get("chip_peaks") or chip.get("peaks") or []
    if isinstance(peaks, list) and len(peaks) > 0:
        return _post(True, "筹码峰可用")
    if chip.get("raw_available") is False and not peaks:
        return _post(False, "筹码数据不足")
    # 有卡但无峰：偏中性，回踩试探偏严 → 不绿
    summary = _s(chip.get("summary_line"))
    if summary and not any(k in summary for k in ("不足", "缺失", "无")):
        return _post(True, summary[:40] or "筹码摘要可用")
    return _post(False, "筹码峰不足或不明")


def _eval_momentum(report: dict[str, Any], cards: dict[str, Any]) -> dict[str, Any]:
    """ok=True 表示「不拆台」（非强空）。"""
    m = _card(cards, "momentum")
    raw = report.get("momentum") if isinstance(report.get("momentum"), dict) else {}
    direction = m.get("direction")
    if direction is None:
        direction = raw.get("direction")
    # 字符串
    if isinstance(direction, str):
        dlow = direction.strip().lower()
        if dlow in ("bearish", "空", "偏空", "转弱"):
            dir_i = -1
        elif dlow in ("bullish", "多", "偏多", "走强"):
            dir_i = 1
        else:
            dir_i = 0
    else:
        try:
            dir_i = int(direction) if direction is not None else 0
        except (TypeError, ValueError):
            dir_i = 0

    conf = m.get("confidence")
    try:
        conf_f = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf_f = None

    # 强空：direction=-1 且置信偏高，或 score 很低
    score = m.get("score")
    if score is None:
        score = raw.get("score")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None

    strong_bear = dir_i < 0 and (
        (conf_f is not None and conf_f >= 0.55)
        or (score_f is not None and score_f <= -0.35)
        or conf_f is None  # 明确 bearish 字符串且无 conf → 仍视为拆台
    )
    if dir_i < 0 and conf_f is not None and conf_f < 0.55 and (score_f is None or score_f > -0.35):
        strong_bear = False  # 弱空：不拆台

    if dir_i < 0 and strong_bear:
        return _post(False, "动能偏空，拆台")
    if dir_i < 0:
        return _post(True, "动能略空但不强，不拆台")
    if dir_i > 0:
        return _post(True, "动能偏多（仅确认，非开仓理由）")
    return _post(True, "动能中性，不拆台")


def _grade_posts(
    background: dict[str, Any],
    structure: dict[str, Any],
    chip: dict[str, Any],
    momentum: dict[str, Any],
) -> tuple[str, list[str], bool]:
    a, b, c, d = background["ok"], structure["ok"], chip["ok"], momentum["ok"]
    missing: list[str] = []
    if not a:
        missing.append("background")
    if not b:
        missing.append("structure")
    if not c:
        missing.append("chip")
    if not d:
        missing.append("momentum")

    conflict = bool(b and not a)
    if conflict and b and not a:
        return "conflict", missing, True
    if a and b and c and d:
        return "aligned", [], False
    if a and b and c and not d:
        return "momentum_veto", ["momentum"], False
    if not b and (a or c):
        return "missing_structure", missing, False
    if b and not c and a:
        return "missing_chip", missing, False
    if not a and (b or c):
        return "missing_background", missing, conflict
    return "empty", missing, conflict


_GRADE_ZH = {
    "aligned": "共振齐",
    "momentum_veto": "动能拆台",
    "missing_structure": "缺结构",
    "missing_chip": "缺筹码",
    "missing_background": "缺背景",
    "conflict": "冲突（结构vs背景）",
    "empty": "空窗/不足",
}

# 选股池离散排序档（越高越优先）；禁止当厚加权分王
_GRADE_POOL_RANK = {
    "aligned": 40,
    "missing_chip": 25,
    "missing_structure": 20,
    "missing_background": 18,
    "empty": 10,
    "momentum_veto": 5,
    "conflict": 0,
}

# 执行档硬降级：冲突 / 动能拆台不得占「执行」优先
_GRADE_DEMOTE_EXECUTION = frozenset({"conflict", "momentum_veto"})


def resonance_grade_label(grade: str | None) -> str:
    g = str(grade or "empty").strip() or "empty"
    if g.startswith("missing_") and g not in _GRADE_ZH:
        return f"缺{g[8:]}" if len(g) > 8 else "缺岗"
    return _GRADE_ZH.get(g, g or "空窗/不足")


def resonance_pool_rank(grade: str | None) -> int:
    """池排序用离散档；未知 / missing_* 回退到 empty 档附近。"""
    g = str(grade or "empty").strip() or "empty"
    if g in _GRADE_POOL_RANK:
        return _GRADE_POOL_RANK[g]
    if g.startswith("missing_"):
        return _GRADE_POOL_RANK["missing_structure"]
    return _GRADE_POOL_RANK["empty"]


def demote_execution_for_resonance(grade: str | None) -> bool:
    """True → 不得以「执行」优先（降为观察）。"""
    return str(grade or "").strip() in _GRADE_DEMOTE_EXECUTION


def extract_resonance_grade(report_or_item: dict[str, Any] | None) -> str:
    """从 report 或 pool item 取 grade；缺省 empty。"""
    if not isinstance(report_or_item, dict):
        return "empty"
    direct = report_or_item.get("resonance_grade")
    if direct:
        return str(direct).strip() or "empty"
    res = report_or_item.get("resonance")
    if isinstance(res, dict) and res.get("grade"):
        return str(res.get("grade")).strip() or "empty"
    return "empty"


def apply_resonance_admission(
    status: str,
    reason: str,
    grade: str | None,
) -> tuple[str, str]:
    """入池状态只收紧：执行 + 冲突/拆台 → 观察。"""
    st = str(status or "")
    why = str(reason or "")
    if st == "执行" and demote_execution_for_resonance(grade):
        label = resonance_grade_label(grade)
        note = f"共振{label}，降为观察"
        if note not in why:
            why = f"{why}；{note}" if why else note
        return "观察", why
    return st, why


def build_resonance(
    report: dict[str, Any] | None,
    *,
    scene: str = SCENE_PULLBACK,
) -> dict[str, Any]:
    """从 report 构建共振局面图。失败时返回 empty 占位，不抛。"""
    if not isinstance(report, dict):
        return {
            "schema_version": SCHEMA,
            "scene": scene,
            "grade": "empty",
            "posts": {
                "background": _post(False, "无报告"),
                "structure": _post(False, "无报告"),
                "chip": _post(False, "无报告"),
                "momentum": _post(False, "无报告"),
            },
            "missing": ["background", "structure", "chip", "momentum"],
            "conflict": False,
            "summary_line": "共振：数据不足",
        }

    cards = report.get("analysis_cards") if isinstance(report.get("analysis_cards"), dict) else {}

    if scene != SCENE_PULLBACK:
        # 仅实现回踩试探；其它 scene 占位
        return {
            "schema_version": SCHEMA,
            "scene": scene,
            "grade": "empty",
            "posts": {
                "background": _post(False, f"场景 {scene} 未实现"),
                "structure": _post(False, f"场景 {scene} 未实现"),
                "chip": _post(False, f"场景 {scene} 未实现"),
                "momentum": _post(False, f"场景 {scene} 未实现"),
            },
            "missing": ["background", "structure", "chip", "momentum"],
            "conflict": False,
            "summary_line": f"共振：场景 {scene} 未实现",
        }

    background = _eval_background(report, cards)
    structure = _eval_structure(report, cards)
    chip = _eval_chip(report, cards)
    momentum = _eval_momentum(report, cards)
    grade, missing, conflict = _grade_posts(background, structure, chip, momentum)
    zh = _GRADE_ZH.get(grade, grade)
    summary = f"共振：{zh}"
    if missing:
        summary += f"（缺：{'｜'.join(missing)}）"

    return {
        "schema_version": SCHEMA,
        "scene": SCENE_PULLBACK,
        "grade": grade,
        "posts": {
            "background": background,
            "structure": structure,
            "chip": chip,
            "momentum": momentum,
        },
        "missing": missing,
        "conflict": conflict,
        "summary_line": summary,
    }


def attach_resonance(report: dict[str, Any], *, scene: str = SCENE_PULLBACK) -> dict[str, Any]:
    """写入 report['resonance'] 并返回共振 dict。"""
    res = build_resonance(report, scene=scene)
    if isinstance(report, dict):
        report["resonance"] = res
    return res
