# -*- coding: utf-8 -*-
"""薄决策视图（阶段 3）：共振 ∧ 策略 ∧ 纪律 → 是否推荐新开。

契约：docs/designs/resonance-and-orchestration.md
铁律：可推荐新开 ⇔ 共振齐 ∧ 主入场策略亮 ∧ 纪律允许
只收紧、不放松 discipline.allow_new_entry。
"""
from __future__ import annotations

from typing import Any

SCHEMA = "decision_view_v1"

# 入场闸 primary 存在即视为「策略亮」（mode 可为 plan/active；off 时 primary 已被清空）
_ENTRY_GATES = ("entry",)


def _disc(report: dict[str, Any]) -> dict[str, Any]:
    d = report.get("discipline")
    return d if isinstance(d, dict) else {}


def _res(report: dict[str, Any]) -> dict[str, Any]:
    r = report.get("resonance")
    return r if isinstance(r, dict) else {}


def _sm(report: dict[str, Any]) -> dict[str, Any]:
    s = report.get("strategy_match")
    return s if isinstance(s, dict) else {}


def _entry_primary(strategy_match: dict[str, Any]) -> dict[str, Any] | None:
    gates = strategy_match.get("gates") if isinstance(strategy_match.get("gates"), dict) else {}
    ent = gates.get("entry") if isinstance(gates.get("entry"), dict) else {}
    primary = ent.get("primary")
    return primary if isinstance(primary, dict) and primary.get("id") else None


def build_decision_view(report: dict[str, Any] | None) -> dict[str, Any]:
    """纯函数：从 report 聚合决策视图。"""
    if not isinstance(report, dict):
        return {
            "schema_version": SCHEMA,
            "allow_new_recommend": False,
            "discipline_allow": False,
            "resonance_ok": False,
            "strategy_entry_lit": False,
            "resonance_grade": "",
            "primary_entry_id": None,
            "primary_entry_name": None,
            "block_reasons": ["无报告"],
            "summary_line": "决策：数据不足，不推荐新开",
            "applied_tighten": False,
        }

    disc = _disc(report)
    res = _res(report)
    sm = _sm(report)

    discipline_allow = bool(disc.get("allow_new_entry", False))
    grade = str(res.get("grade") or "")
    resonance_ok = grade == "aligned"
    primary = _entry_primary(sm)
    strategy_entry_lit = primary is not None
    primary_id = str(primary.get("id")) if primary else None
    primary_name = str(primary.get("name") or primary_id or "") if primary else None

    block_reasons: list[str] = []
    if not discipline_allow:
        block_reasons.append("纪律不允许新开")
    if not resonance_ok:
        if grade == "conflict":
            block_reasons.append("共振冲突")
        elif grade == "momentum_veto":
            block_reasons.append("动能拆台")
        elif grade == "empty" or not grade:
            block_reasons.append("共振不足")
        elif grade.startswith("missing_"):
            try:
                from trader_shared.resonance import resonance_grade_label

                # 「缺结构」→「共振缺结构」；禁止 missing_structure 英文上屏
                label = resonance_grade_label(grade)
            except Exception:
                label = "缺岗"
            block_reasons.append(f"共振{label}" if not str(label).startswith("共振") else label)
        else:
            try:
                from trader_shared.resonance import resonance_grade_label

                block_reasons.append(f"共振未齐（{resonance_grade_label(grade)}）")
            except Exception:
                block_reasons.append("共振未齐")
    if not strategy_entry_lit:
        block_reasons.append("无入场策略")

    allow = discipline_allow and resonance_ok and strategy_entry_lit

    if allow:
        summary = f"决策：可试探新开"
        if primary_name:
            summary += f"（{primary_name}）"
    else:
        summary = "决策：不推荐新开"
        if block_reasons:
            summary += f"（{'｜'.join(block_reasons)}）"

    return {
        "schema_version": SCHEMA,
        "allow_new_recommend": bool(allow),
        "discipline_allow": discipline_allow,
        "resonance_ok": resonance_ok,
        "strategy_entry_lit": strategy_entry_lit,
        "resonance_grade": grade,
        "primary_entry_id": primary_id,
        "primary_entry_name": primary_name,
        "block_reasons": block_reasons,
        "summary_line": summary,
        "applied_tighten": False,
    }


def apply_decision_view(
    report: dict[str, Any],
    *,
    tighten_discipline: bool = True,
) -> dict[str, Any]:
    """写入 report['decision_view']；可选只收紧 discipline / conclusion 新开相关字段。

    返回 decision_view dict。
    """
    view = build_decision_view(report)
    applied = False

    if tighten_discipline and not view.get("allow_new_recommend"):
        disc = _disc(report)
        if disc and disc.get("allow_new_entry"):
            disc["allow_new_entry"] = False
            # 短/中线新开一并收紧（若存在）
            if "allow_new_entry_short" in disc:
                disc["allow_new_entry_short"] = False
            reasons = list(view.get("block_reasons") or [])
            # 合并 entry_checklist 缺项
            cl = disc.get("entry_checklist") if isinstance(disc.get("entry_checklist"), dict) else None
            if cl is not None:
                cl["all_green"] = False
                miss = list(cl.get("missing_labels") or [])
                for label in reasons:
                    if label and label not in miss:
                        miss.append(label)
                cl["missing_labels"] = miss
                from trader_shared.chan_discipline import format_entry_line_c1

                cl["entry_line"] = format_entry_line_c1(all_green=False, missing=miss)
                disc["entry_line"] = cl["entry_line"]
            else:
                from trader_shared.chan_discipline import format_entry_line_c1

                disc["entry_line"] = format_entry_line_c1(
                    all_green=False, missing=reasons or ["决策收紧"]
                )
            note = disc.get("entry_block_reason") or ""
            extra = "；".join(reasons)
            if extra and extra not in str(note):
                disc["entry_block_reason"] = f"{note}；{extra}".strip("；") if note else extra
            report["discipline"] = disc
            applied = True

            # 同步 conclusion 出手文案：若原先偏「可买」则压成不买（只收紧）
            conc = report.get("conclusion") if isinstance(report.get("conclusion"), dict) else None
            if conc is not None:
                exe = str(conc.get("execution") or "")
                soft_buy = any(k in exe for k in ("试探", "可买", "轻仓买", "半仓", "低吸"))
                hard_off = any(k in exe for k in ("不买", "不追", "不新开", "观望", "空仓"))
                if soft_buy and not hard_off:
                    conc["execution"] = "现价不买 · 不追"
                    reason = str(conc.get("reason") or "")
                    tag = "共振/策略/纪律未齐"
                    if tag not in reason:
                        conc["reason"] = f"{reason}；{tag}".strip("；") if reason else tag
                    report["conclusion"] = conc
                    applied = True

    view["applied_tighten"] = applied
    report["decision_view"] = view
    # 统一出口别名：新代码可读 report["decision"]
    report["decision"] = view
    return view


def format_decision_narrative_lines(report: dict[str, Any] | None) -> list[str]:
    """展示层用：共振 /（可试探时）决策 / 新开；（仪表默认隐藏）。

    只读字段，不改 report。返回已带两空格缩进的行（可直接 append）。
    「不推荐新开」与下方「新开/动作」重复，默认不输出决策行。
    融合分仪表默认隐藏；设 TRADER_SHOW_FUSION_GAUGE=1 才展示。
    """
    import os

    if not isinstance(report, dict):
        return []
    lines: list[str] = []

    res = report.get("resonance") if isinstance(report.get("resonance"), dict) else {}
    res_line = str(res.get("summary_line") or "").strip()
    if res_line:
        if not res_line.startswith("共振"):
            res_line = f"共振：{res_line}"
        lines.append(f"  {res_line}")

    dv = report.get("decision_view") if isinstance(report.get("decision_view"), dict) else {}
    # 仅可试探时展示决策行；否决场景交给「新开」+「动作」
    if dv.get("allow_new_recommend") is True:
        dv_line = str(dv.get("summary_line") or "").strip()
        if dv_line:
            if not dv_line.startswith("决策"):
                dv_line = f"决策：{dv_line}"
            lines.append(f"  {dv_line}")

    disc = report.get("discipline") if isinstance(report.get("discipline"), dict) else {}
    entry_line = str(disc.get("entry_line") or "").strip()
    if not entry_line:
        cl = disc.get("entry_checklist") if isinstance(disc.get("entry_checklist"), dict) else {}
        entry_line = str(cl.get("entry_line") or "").strip()
    if entry_line:
        # SSOT：规范化为 format_entry_line_c1 形态，禁止渲染层另写「新开」文案
        if not entry_line.startswith("新开"):
            from trader_shared.chan_discipline import format_entry_line_c1

            entry_line = format_entry_line_c1(all_green=False, missing=[entry_line])
        lines.append(f"  {entry_line}")

    # fusion 仪表：默认不上屏（避免与决策叙事抢位）
    _show_gauge = os.environ.get("TRADER_SHOW_FUSION_GAUGE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if _show_gauge:
        fusion = report.get("fusion") if isinstance(report.get("fusion"), dict) else {}
        score = fusion.get("weighted_score")
        if score is None:
            score = report.get("weighted_score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        if score_f is not None:
            action = str(fusion.get("action") or "").strip()
            action_short = action.split("（")[0].split("(")[0].strip() if action else ""
            if len(action_short) > 12:
                action_short = action_short[:10] + "…"
            bit = f"仪表：融合分 {score_f:+.2f}"
            if action_short:
                bit += f" · {action_short}"
            bit += "（仅参考）"
            lines.append(f"  {bit}")

    return lines


def apply_decision_to_execution(
    execution: str,
    report: dict[str, Any] | None,
) -> str:
    """展示前：若 decision_view 不推荐新开，把偏买 execution 压成不买。"""
    exe = str(execution or "")
    if not isinstance(report, dict):
        return exe
    dv = report.get("decision_view") if isinstance(report.get("decision_view"), dict) else {}
    if dv.get("allow_new_recommend") is True:
        return exe
    # 无 decision_view 时不强制改（兼容旧 fixture）
    if not dv:
        return exe
    soft_buy = any(k in exe for k in ("试探", "可买", "轻仓买", "半仓", "增持", "买点挂", "可按买"))
    hard_off = any(k in exe for k in ("不买", "不追", "不新开", "观望", "空仓"))
    if soft_buy and not hard_off:
        return "现价不买 · 不追"
    return exe
