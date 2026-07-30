"""威科夫吸筹链：同道内排序 + 链文案（威：SC→AR→ST→LPS，还差SOS）。

禁止「事件 n/5」、S级/星级。派发侧不进此链（由分道先别碰处理）。
SSOT：池排序与 wyckoff Skill 共用本模块。
"""
from __future__ import annotations

from typing import Any

# 吸筹链固定顺序
ACCUM_CHAIN = ("SC", "AR", "ST", "LPS", "SOS")

_SIGNAL_KEYS = {
    "SC": "sc_signal",
    "AR": "ar_signal",
    "ST": "st_signal",
    "LPS": "lps_signal",
    "SOS": "sos_signal",
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
    if report_or_item.get("wyckoff_bc_signal") is not None:
        merged["bc_signal"] = report_or_item.get("wyckoff_bc_signal")
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
        if wyk.get(key):
            out.append(label)
    return out


def first_missing_accum(events: list[str] | None) -> str | None:
    """链上第一个未出现的事件；全齐返回 None。"""
    have = set(events or [])
    for label in ACCUM_CHAIN:
        if label not in have:
            return label
    return None


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
        if _bc_watch_only(wyk, events):
            return "威：BC后观望"

    if not events:
        return "威：吸筹链未成型"

    miss = first_missing_accum(events)
    chain = "→".join(events)
    if miss is None:
        return f"威：{chain}"
    return f"威：{chain}，还差{miss}"


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


def attach_wyckoff_chain_fields(record: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
    """写入 pool record 缓存字段；report 信号覆盖 record 旧缓存。"""
    # report 在后，覆盖同名；去掉派生缓存以免自引用脏读
    src = {**record, **(report or {})}
    for k in ("wyckoff_chain", "wyckoff_chain_plain", "wyckoff_chain_rank"):
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
    # 轻量保留嵌套，便于后续 refresh 前读
    if isinstance(report, dict) and isinstance(report.get("wyckoff"), dict):
        record["wyckoff"] = report["wyckoff"]
    return record


__all__ = [
    "ACCUM_CHAIN",
    "attach_wyckoff_chain_fields",
    "extract_accum_events",
    "first_missing_accum",
    "format_wyckoff_chain_plain",
    "wyckoff_chain_rank",
]
