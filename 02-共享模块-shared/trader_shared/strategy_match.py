"""策略闸口匹配（P2）：纯函数，无网络。

契约：docs/designs/strategy-gates.md · strategy-pack.md
输入：report-like dict 或已展平的 context。
输出：每闸 primary / mode / 填数后的执行视图。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_PACKS_DIR = Path(__file__).resolve().parent / "config" / "strategy_packs"

GATES = ("select", "entry", "manage", "scale", "take", "stop")


def stop_buffer(price: float) -> float:
    """威科夫 trail 缓冲（与 strategy-pack 草案一致）。"""
    p = float(price or 0)
    if p <= 0:
        return 0.05
    if p > 100:
        return 0.25
    if p < 10:
        return 0.03
    return round(max(0.05, p * 0.002), 2)


def load_strategy_packs(packs_dir: Path | None = None) -> list[dict[str, Any]]:
    """加载 YAML 策略包；失败则返回内置最小集。"""
    d = packs_dir or _PACKS_DIR
    packs: list[dict[str, Any]] = []
    if d.is_dir():
        try:
            import yaml
        except ImportError:
            yaml = None  # type: ignore
        if yaml is not None:
            for path in sorted(d.glob("*.yaml")):
                try:
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data.get("id"):
                        packs.append(data)
                except Exception as exc:
                    _logger.debug("skip pack %s: %s", path, exc)
    if not packs:
        packs = _builtin_packs()
    return packs


def _builtin_packs() -> list[dict[str, Any]]:
    return [
        {"id": "select.observe_G", "name": "空仓观察", "gate": "select", "priority": 10, "match": "always", "veto_entry": False},
        {"id": "select.defense_E", "name": "防守否决", "gate": "select", "priority": 100, "match": "defense", "veto_entry": True},
        {"id": "entry.chan_buy1_probe", "name": "结构试探·一买", "gate": "entry", "priority": 80, "match": "chan_buy1"},
        {"id": "entry.chan_buy2_add", "name": "结构·二买", "gate": "entry", "priority": 50, "match": "chan_buy1_or_2"},
        {"id": "manage.wyckoff_trail", "name": "威科夫移动止损", "gate": "manage", "priority": 90, "match": "always", "stop_policy": "全清"},
        {"id": "stop.invalidate_full", "name": "证伪全清", "gate": "stop", "priority": 100, "match": "always", "stop_policy": "全清"},
    ]


def build_match_context(report: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    """从 report-like dict 抽取匹配上下文；overrides 优先。"""
    r = report if isinstance(report, dict) else {}
    disc = r.get("discipline") if isinstance(r.get("discipline"), dict) else {}
    cl = disc.get("entry_checklist") if isinstance(disc.get("entry_checklist"), dict) else {}
    fusion = r.get("fusion") if isinstance(r.get("fusion"), dict) else {}
    sig = fusion.get("signals_detail") if isinstance(fusion.get("signals_detail"), dict) else {}

    # 意见卡（若已挂在 report）
    cards = r.get("analysis_cards") if isinstance(r.get("analysis_cards"), dict) else {}
    chan_c = cards.get("chan") if isinstance(cards.get("chan"), dict) else {}
    wyk_c = cards.get("wyckoff") if isinstance(cards.get("wyckoff"), dict) else {}
    chip_c = cards.get("chip") if isinstance(cards.get("chip"), dict) else {}

    action = str(
        disc.get("action")
        or r.get("action_text")
        or (r.get("conclusion") or {}).get("execution")
        or ""
    )
    regime = r.get("regime") or (r.get("market_env") or {}).get("level") or r.get("market_env") or ""
    if isinstance(regime, dict):
        regime = regime.get("level") or ""

    allow = disc.get("allow_new_entry")
    if allow is None:
        allow = r.get("allow_new_entry")
    if allow is None:
        # 从动作文案推断
        allow = not any(k in action for k in ("不新开", "不买", "观望", "空仓", "不追"))

    all_green = bool(cl.get("all_green")) if cl else bool(r.get("checklist_all_green"))

    chan_short = str(
        chan_c.get("type_short")
        or r.get("chan_type_short")
        or ""
    )
    chan_raw = str(chan_c.get("type_raw") or r.get("chan_type_raw") or "")
    # fusion chan reason 兜底
    if not chan_short and not chan_raw:
        cr = sig.get("chan") if isinstance(sig.get("chan"), dict) else {}
        reason = str(cr.get("reason") or "")
        for raw, short in (("一类买", "一买"), ("二类买", "二买"), ("三类买", "三买")):
            if raw in reason:
                chan_raw, chan_short = raw, short
                break

    wyk_event = str(
        wyk_c.get("event_code")
        or r.get("wyckoff_event")
        or ""
    )
    if wyk_event in ("—", "-", "无"):
        wyk_event = ""

    support_tag = str(chip_c.get("support_tag") or r.get("chip_support_tag") or "")
    trapped = str(chip_c.get("trapped_tag") or r.get("chip_trapped_tag") or "")
    chip_weak = bool(r.get("chip_support_weak")) or ("支撑弱" in support_tag)

    current = float(r.get("current") or 0)
    stop = r.get("stop")
    support = r.get("support")
    try:
        stop_f = float(stop) if stop is not None else None
    except (TypeError, ValueError):
        stop_f = None
    try:
        support_f = float(support) if support is not None else None
    except (TypeError, ValueError):
        support_f = None

    cost = r.get("cost")
    try:
        cost_f = float(cost) if cost is not None and float(cost) > 0 else None
    except (TypeError, ValueError):
        cost_f = None

    has_pos = bool(r.get("has_position"))
    if cost_f and not has_pos and r.get("has_position") is None:
        has_pos = True

    ctx = {
        "current": current,
        "stop": stop_f,
        "support": support_f,
        "has_position": has_pos,
        "cost": cost_f,
        "regime": str(regime or ""),
        "action_text": action,
        "allow_new_entry": bool(allow),
        "checklist_all_green": all_green,
        "chan_type_short": chan_short,
        "chan_type_raw": chan_raw,
        "wyckoff_event": wyk_event,
        "chip_support_weak": chip_weak,
        "chip_trapped_tag": trapped,
        "block_new": any(k in action for k in ("不新开", "不买", "空仓")) or not bool(allow),
    }
    ctx.update(overrides)
    return ctx


def _match_pack(pack: dict[str, Any], ctx: dict[str, Any]) -> bool:
    m = pack.get("match", "always")
    if m == "always" or m is None:
        return True
    if m == "defense":
        return _match_defense(ctx)
    if m == "chan_buy1":
        return ctx.get("chan_type_short") == "一买" or ctx.get("chan_type_raw") == "一类买"
    if m == "chan_buy1_or_2":
        return ctx.get("chan_type_short") in ("一买", "二买") or ctx.get("chan_type_raw") in (
            "一类买",
            "二类买",
        )
    if isinstance(m, dict):
        return _eval_match_dict(m, ctx)
    return False


def _match_defense(ctx: dict[str, Any]) -> bool:
    ev = str(ctx.get("wyckoff_event") or "")
    if ev in ("SOW", "UT", "UTAD", "LPSY"):
        return True
    if str(ctx.get("regime") or "") in ("很差",):
        return True
    if ctx.get("chip_support_weak") and "套牢面大" in str(ctx.get("chip_trapped_tag") or ""):
        return True
    if ctx.get("chip_support_weak") and ctx.get("wyckoff_event") == "SOW":
        return True
    # SOW alone already covered; chip weak alone for S-02 with SOW
    if ctx.get("chip_support_weak") and ev == "SOW":
        return True
    # S-02: SOW + 支撑弱 — SOW enough
    return False


def _eval_match_dict(m: dict[str, Any], ctx: dict[str, Any]) -> bool:
    if "any" in m:
        return any(_eval_clause(c, ctx) for c in (m.get("any") or []) if isinstance(c, dict))
    if "all" in m:
        return all(_eval_clause(c, ctx) for c in (m.get("all") or []) if isinstance(c, dict))
    return _eval_clause(m, ctx)


def _eval_clause(c: dict[str, Any], ctx: dict[str, Any]) -> bool:
    field = c.get("field")
    if not field:
        return False
    val = ctx.get(str(field))
    if "in" in c:
        return val in (c.get("in") or [])
    if "eq" in c:
        ok = val == c.get("eq")
        if ok and c.get("and_trapped"):
            return c["and_trapped"] in str(ctx.get("chip_trapped_tag") or "")
        return ok
    return False


def _pick_primary(packs: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not packs:
        return None, []
    ordered = sorted(packs, key=lambda p: int(p.get("priority") or 0), reverse=True)
    primary = ordered[0]
    candidates = ordered[1:2]  # 最多 1 候选
    return primary, candidates


def _floor_price(ctx: dict[str, Any]) -> float | None:
    for k in ("support", "stop"):
        v = ctx.get(k)
        if v is not None and float(v) > 0:
            return float(v)
    return None


def _manage_stage(ctx: dict[str, Any]) -> str:
    if not ctx.get("has_position"):
        return "S1"
    cost = ctx.get("cost")
    if cost is None or float(cost) <= 0:
        return "S1"
    cur = float(ctx.get("current") or 0)
    if cur <= 0:
        return "S1"
    pnl = (cur - float(cost)) / float(cost)
    if pnl >= 0.015:
        return "S2"
    return "S1"


def match_strategies(
    report: dict[str, Any] | None = None,
    *,
    packs: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """主入口：返回各闸口匹配结果。"""
    ctx = context if context is not None else build_match_context(report)
    pack_list = packs if packs is not None else load_strategy_packs()

    by_gate: dict[str, list[dict[str, Any]]] = {g: [] for g in GATES}
    for p in pack_list:
        gate = str(p.get("gate") or "")
        if gate not in by_gate:
            continue
        if _match_pack(p, ctx):
            by_gate[gate].append(p)

    # select
    sel_p, sel_c = _pick_primary(by_gate["select"])
    veto_entry = bool(sel_p and sel_p.get("veto_entry"))
    # 若 defense 与 observe 都在，primary 已是 priority 更高的 defense

    select_out = {
        "primary": _pack_summary(sel_p),
        "candidates": [_pack_summary(x) for x in sel_c],
        "mode": "active",
        "veto_entry": veto_entry,
    }

    # entry
    entry_mode = "off"
    ent_p, ent_c = None, []
    if ctx.get("has_position"):
        entry_mode = "off"
        ent_p, ent_c = None, []
    else:
        ent_p, ent_c = _pick_primary(by_gate["entry"])
        if ent_p is None:
            entry_mode = "off"
        elif veto_entry or ctx.get("block_new") or not ctx.get("allow_new_entry"):
            entry_mode = "plan"
        elif not ctx.get("checklist_all_green"):
            entry_mode = "plan"  # S-03 不全绿不可执行
        else:
            entry_mode = "active"

    entry_out = {
        "primary": _pack_summary(ent_p) if entry_mode != "off" or ent_p else _pack_summary(ent_p),
        "candidates": [_pack_summary(x) for x in ent_c],
        "mode": entry_mode,
        "executable": entry_mode == "active",
    }
    if entry_mode == "off":
        entry_out["primary"] = None
        entry_out["candidates"] = []

    # manage
    man_p, man_c = _pick_primary(by_gate["manage"])
    floor = _floor_price(ctx)
    buf = stop_buffer(float(ctx.get("current") or floor or 0))
    stop_price = None
    if floor is not None:
        stop_price = round(floor - buf, 2)
    elif ctx.get("stop") is not None:
        stop_price = float(ctx["stop"])
    stage = _manage_stage(ctx)
    manage_mode = "active" if ctx.get("has_position") else "plan"
    manage_out = {
        "primary": _pack_summary(man_p),
        "candidates": [_pack_summary(x) for x in man_c],
        "mode": manage_mode,
        "stage_id": stage,
        "floor_price": floor,
        "stop_price": stop_price,
        "stop_policy": (man_p or {}).get("stop_policy") or "全清",
        "buffer": buf,
    }

    # scale
    if not ctx.get("has_position"):
        scale_mode, scale_reason = "deny", "无持仓"
    elif veto_entry or ctx.get("block_new"):
        scale_mode, scale_reason = "deny", "选股否决或不新开"
    elif not ctx.get("checklist_all_green"):
        scale_mode, scale_reason = "deny", "清单未全绿"
    else:
        scale_mode, scale_reason = "allow", "持仓且清单全绿（上限见纪律 cap）"
    scale_out = {"mode": scale_mode, "reason": scale_reason, "primary": None}

    # take（P2 轻量）
    take_mode = "off"
    take_hint = ""
    if ctx.get("has_position") and ctx.get("cost") and float(ctx.get("current") or 0) > 0:
        pnl = (float(ctx["current"]) - float(ctx["cost"])) / float(ctx["cost"])
        if pnl >= 0.05:
            take_mode = "plan"
            take_hint = "浮盈可观，可考虑分批锁定（完整 take 包见 P4）"
    take_out = {"mode": take_mode, "hint": take_hint, "primary": None}

    # stop
    stop_p, _ = _pick_primary(by_gate["stop"])
    sp = stop_price if stop_price is not None else ctx.get("stop")
    triggered = False
    if sp is not None and float(ctx.get("current") or 0) > 0:
        triggered = float(ctx["current"]) <= float(sp)
    stop_out = {
        "primary": _pack_summary(stop_p),
        "mode": "hard",
        "stop_price": sp,
        "stop_policy": "全清",
        "triggered": triggered,
    }

    # M1: stop triggered → scale deny
    if triggered:
        scale_out = {"mode": "deny", "reason": "止损已触发，禁止加仓", "primary": None}

    return {
        "schema_version": "strategy_match_v1",
        "context": {
            "has_position": ctx.get("has_position"),
            "allow_new_entry": ctx.get("allow_new_entry"),
            "checklist_all_green": ctx.get("checklist_all_green"),
            "regime": ctx.get("regime"),
        },
        "gates": {
            "select": select_out,
            "entry": entry_out,
            "manage": manage_out,
            "scale": scale_out,
            "take": take_out,
            "stop": stop_out,
        },
    }


def _pack_summary(p: dict[str, Any] | None) -> dict[str, Any] | None:
    if not p:
        return None
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "gate": p.get("gate"),
        "priority": p.get("priority"),
        "summary": p.get("summary") or p.get("motto") or "",
        "lineage": p.get("lineage"),
    }


def format_gates_brief(result: dict[str, Any]) -> str:
    """纯文本摘要（报告 📐 用，P3 可再美化）。"""
    g = result.get("gates") or {}
    lines = ["📐 策略"]
    sel = g.get("select") or {}
    if sel.get("primary"):
        lines.append(f"  选股：{sel['primary'].get('name')}（{sel['primary'].get('id')}）")
    ent = g.get("entry") or {}
    if ent.get("mode") == "off":
        lines.append("  买：关闭（已持仓或无开仓匹配）")
    elif ent.get("primary"):
        tag = "执行" if ent.get("mode") == "active" else "预案"
        lines.append(f"  买：{ent['primary'].get('name')} · {tag}")
    else:
        lines.append("  买：无匹配开仓包")
    man = g.get("manage") or {}
    if man.get("primary"):
        sp = man.get("stop_price")
        st = man.get("stage_id")
        pol = man.get("stop_policy")
        mode = "执行" if man.get("mode") == "active" else "预案"
        sp_s = f"{sp:.2f}" if isinstance(sp, (int, float)) else "—"
        lines.append(f"  持：{man['primary'].get('name')} · {st} · 止损 {sp_s}（{pol}）· {mode}")
    sc = g.get("scale") or {}
    lines.append(f"  加：{sc.get('mode')}（{sc.get('reason') or ''}）")
    tk = g.get("take") or {}
    if tk.get("mode") != "off":
        lines.append(f"  止盈：{tk.get('hint') or tk.get('mode')}")
    st = g.get("stop") or {}
    sp = st.get("stop_price")
    sp_s = f"{sp:.2f}" if isinstance(sp, (int, float)) else "—"
    trig = "已触发" if st.get("triggered") else "监视中"
    lines.append(f"  止损：{sp_s} · {st.get('stop_policy')} · {trig}")
    return "\n".join(lines)
