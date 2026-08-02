"""威科夫吸筹链：同道内排序 + 链文案（威：SC→AR→Spring确认→LPS，还差SOS）。

禁止「事件 n/5」、S级/星级。派发侧不进此链（由分道先别碰处理）。
SSOT：池排序与 wyckoff Skill 共用本模块。

周线 RS（相对强弱）：原典选股过滤器，不改 phase；同道内排序 + 弱 RS 谨慎。
"""
from __future__ import annotations

from typing import Any

# 吸筹链固定顺序（ST 槽位认 st_* / spring_test_* / secondary_test_sc_*；展示名见 _CHAIN_DISPLAY）
ACCUM_CHAIN = ("SC", "AR", "ST", "LPS", "SOS")

# 同道内 RS 排序档：弱侧更重（原典：弱相对强弱更常用来降级）
# strong=3 > neutral/missing=1 > weak=0
_RS_RANK = {
    "strong": 3,
    "neutral": 1,
    "missing": 1,
    "weak": 0,
}

_SIGNAL_KEYS = {
    "SC": "sc_signal",
    "AR": "ar_signal",
    "ST": "st_signal",  # 兼容；提取时亦认 spring_test_signal
    "LPS": "lps_signal",
    "SOS": "sos_signal",
}

_CHAIN_DISPLAY = {
    "SC": "SC",
    "AR": "AR",
    "ST": "Spring确认",
    "LPS": "LPS",
    "SOS": "SOS",
}


def _wyckoff_dict(report_or_item: dict[str, Any] | None) -> dict[str, Any]:
    """合并 nested wyckoff + 扁平旗；扁平覆盖同名键（池缓存优先）。"""
    if not isinstance(report_or_item, dict):
        return {}
    merged: dict[str, Any] = {}
    wyk = report_or_item.get("wyckoff")
    if isinstance(wyk, dict) and wyk:
        merged.update(wyk)
    for label, key in _SIGNAL_KEYS.items():
        if report_or_item.get(key) is not None:
            merged[key] = report_or_item.get(key)
        cached = report_or_item.get(f"wyckoff_{label.lower()}_signal")
        if cached is not None:
            merged[key] = cached
    # 广义 ST（测 SC）与 Spring 确认：扁平字段也要并入，供 extract_accum_events 认灯
    for flat_key in (
        "secondary_test_sc_signal",
        "spring_test_signal",
        "wyckoff_secondary_test_sc_signal",
        "wyckoff_spring_test_signal",
    ):
        if report_or_item.get(flat_key) is not None:
            canon = flat_key.replace("wyckoff_", "")
            merged[canon] = report_or_item.get(flat_key)
    if report_or_item.get("wyckoff_bc_signal") is not None:
        merged["bc_signal"] = report_or_item.get("wyckoff_bc_signal")
    # Phase A 失败态可来自顶层或 nested wyckoff；顶层覆盖缓存，供链文案收口。
    for key in ("phase_a_status", "phase_a_range"):
        if report_or_item.get(key) is not None:
            merged[key] = report_or_item.get(key)
    if report_or_item.get("wyckoff_phase_a_status") is not None:
        merged["phase_a_status"] = report_or_item.get("wyckoff_phase_a_status")
    # 仅有链标签、无任何 signal 旗时，用链回填
    has_any_flag = any(merged.get(k) for k in _SIGNAL_KEYS.values())
    chain = report_or_item.get("wyckoff_chain")
    if isinstance(chain, (list, tuple)) and chain and not has_any_flag:
        for label in chain:
            key = _SIGNAL_KEYS.get(str(label))
            if key:
                merged[key] = True
    return merged


def extract_accum_events(report_or_item: dict[str, Any] | None) -> list[str]:
    """按 SC→AR→ST→LPS→SOS 顺序提取已亮事件（缺则跳过）。"""
    wyk = _wyckoff_dict(report_or_item)
    out: list[str] = []
    for label in ACCUM_CHAIN:
        key = _SIGNAL_KEYS[label]
        lit = bool(wyk.get(key))
        if label == "ST":
            # 广义 ST（回测 SC）与 Spring 确认均可点亮链上 ST；与 L0–L3 真 ST 对齐
            lit = (
                lit
                or bool(wyk.get("spring_test_signal"))
                or bool(wyk.get("secondary_test_sc_signal"))
            )
        if lit:
            out.append(label)
    return out


def first_missing_accum(events: list[str] | None) -> str | None:
    """链上第一个未出现的事件；全齐返回 None。"""
    have = set(events or [])
    for label in ACCUM_CHAIN:
        if label not in have:
            return label
    return None


def _chain_label(label: str) -> str:
    return _CHAIN_DISPLAY.get(label, label)


def is_phase_a_failed(report_or_item: dict[str, Any] | None) -> bool:
    """Phase A copy 层失败态：phase_a_status 或 phase_a_range.status 任一 failed 即收口。"""
    wyk = _wyckoff_dict(report_or_item)
    if str(wyk.get("phase_a_status") or "").strip().lower() == "failed":
        return True
    pa = wyk.get("phase_a_range")
    if isinstance(pa, dict) and str(pa.get("status") or "").strip().lower() == "failed":
        return True
    return False


def _bc_watch_only(wyk: dict[str, Any], events: list[str]) -> bool:
    """仅有 BC、吸筹链尚无事件时观望（有 SC 等则走链文案）。"""
    return bool(wyk.get("bc_signal")) and len(events) == 0 and not wyk.get("sos_signal")


def format_wyckoff_chain_plain(report_or_item: dict[str, Any] | list[str] | None) -> str:
    """人话链文案（始终按信号现算，不读 wyckoff_chain_plain 缓存）。

    - 有缺口：威：SC→AR→ST→LPS，还差SOS
    - 全齐：威：SC→AR→ST→LPS→SOS
    - 无事件：威：吸筹链未成型
    - 仅 BC：威：BC后观望
    """
    if isinstance(report_or_item, list):
        events = [str(x) for x in report_or_item]
        wyk: dict[str, Any] = {}
    else:
        src = report_or_item if isinstance(report_or_item, dict) else {}
        wyk = _wyckoff_dict(src)
        events = extract_accum_events(src)
        if is_phase_a_failed(src):
            if events:
                chain = "→".join(_chain_label(e) for e in events)
                return f"威：{chain}（Phase A 已失效）"
            return "威：结构已失效"
        if _bc_watch_only(wyk, events):
            return "威：BC后观望"

    if not events:
        # Spring 已亮但无确认测试 → 点名缺口（可选增强）
        if wyk.get("spring_signal") and not (
            wyk.get("st_signal") or wyk.get("spring_test_signal")
        ):
            return "威：吸筹链未成型，还差Spring确认"
        return "威：吸筹链未成型"

    miss = first_missing_accum(events)
    chain = "→".join(_chain_label(e) for e in events)
    if miss is None:
        return f"威：{chain}"
    return f"威：{chain}，还差{_chain_label(miss)}"


def wyckoff_chain_rank(report_or_item: dict[str, Any] | list[str] | None) -> int:
    """同道内排序分：命中个数 0–5；无 ST 时封顶 2（ST 未确认偏弱）。

    始终按信号现算，不读 wyckoff_chain_rank 缓存。
    仅 BC 观望 → 0。
    """
    if isinstance(report_or_item, list):
        events = [str(x) for x in report_or_item]
        wyk: dict[str, Any] = {}
    else:
        src = report_or_item if isinstance(report_or_item, dict) else {}
        wyk = _wyckoff_dict(src)
        events = extract_accum_events(src)
        if _bc_watch_only(wyk, events):
            return 0

    n = len(events)
    if n == 0:
        return 0
    if "ST" not in events:
        return min(n, 2)
    return n


def _rs_source_dict(report_or_item: dict[str, Any] | None) -> dict[str, Any]:
    """从扁平 / 顶层 wyckoff / wyckoff_midline 取周线 RS 字段。"""
    if not isinstance(report_or_item, dict):
        return {}
    # 扁平优先（池缓存）
    if report_or_item.get("rs_label") is not None or report_or_item.get("rs_gate"):
        return report_or_item
    wyk = report_or_item.get("wyckoff")
    if isinstance(wyk, dict) and (
        wyk.get("rs_label") is not None or wyk.get("timeframe") == "weekly"
    ):
        return wyk
    mid = report_or_item.get("wyckoff_midline")
    if isinstance(mid, dict):
        inner = mid.get("wyckoff") if isinstance(mid.get("wyckoff"), dict) else mid
        if isinstance(inner, dict):
            return inner
    return {}


def extract_rs_label(report_or_item: dict[str, Any] | None) -> str:
    """返回 strong|neutral|weak|missing；缺省/日线 disabled → neutral。"""
    src = _rs_source_dict(report_or_item)
    gate = str(src.get("rs_gate") or "")
    if gate == "disabled":
        return "neutral"
    label = str(src.get("rs_label") or "neutral").lower()
    if label in _RS_RANK:
        return label
    if gate in {"missing", "insufficient_bars"}:
        return "missing"
    return "neutral"


def wyckoff_rs_rank(report_or_item: dict[str, Any] | None) -> int:
    """同道内 RS 排序分：strong=3 > neutral=1 > weak=0（弱侧降权更重）。"""
    return _RS_RANK.get(extract_rs_label(report_or_item), 1)


def format_rs_plain(report_or_item: dict[str, Any] | None) -> str:
    """池/作战表短句；neutral/missing 空串；weak 带「慎跟」。"""
    src = _rs_source_dict(report_or_item)
    label = extract_rs_label(report_or_item)
    note = str(src.get("rs_note") or "").strip()
    if label == "weak":
        base = note if note.startswith("弱于") else (note or "弱于对照指数")
        return f"{base} · 慎跟"
    if label == "strong":
        return note if note.startswith("强于") else (note or "强于对照指数")
    return ""


def attach_wyckoff_chain_fields(record: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
    """写入 pool record 缓存字段；report 信号覆盖 record 旧缓存。"""
    # report 在后，覆盖同名；去掉派生缓存以免自引用脏读
    src = {**record, **(report or {})}
    for k in ("wyckoff_chain", "wyckoff_chain_plain", "wyckoff_chain_rank", "wyckoff_rs_rank"):
        src.pop(k, None)
    events = extract_accum_events(src)
    record["wyckoff_chain"] = events
    record["wyckoff_chain_plain"] = format_wyckoff_chain_plain(src)
    record["wyckoff_chain_rank"] = wyckoff_chain_rank(src)
    wyk = _wyckoff_dict(src)
    for label, key in _SIGNAL_KEYS.items():
        if key in wyk:
            record[f"wyckoff_{label.lower()}_signal"] = bool(wyk.get(key))
    if wyk.get("bc_signal") is not None:
        record["wyckoff_bc_signal"] = bool(wyk.get("bc_signal"))
    # 周线 RS 扁平透传（操盘排序 / 分道谨慎）
    rs_src = _rs_source_dict(src)
    rs_label = extract_rs_label(src)
    record["rs_label"] = rs_label
    record["rs_score"] = rs_src.get("rs_score")
    record["rs_note"] = rs_src.get("rs_note") or ""
    record["rs_gate"] = rs_src.get("rs_gate") or ""
    record["rs_index"] = rs_src.get("rs_index") or ""
    record["rs_index_label"] = rs_src.get("rs_index_label") or ""
    record["rs_plain"] = format_rs_plain(src)
    record["wyckoff_rs_rank"] = wyckoff_rs_rank(src)
    # 轻量保留嵌套，便于后续 refresh 前读
    if isinstance(report, dict) and isinstance(report.get("wyckoff"), dict):
        record["wyckoff"] = report["wyckoff"]
    return record


__all__ = [
    "ACCUM_CHAIN",
    "attach_wyckoff_chain_fields",
    "extract_accum_events",
    "extract_rs_label",
    "first_missing_accum",
    "format_rs_plain",
    "format_wyckoff_chain_plain",
    "is_phase_a_failed",
    "wyckoff_chain_rank",
    "wyckoff_rs_rank",
]
