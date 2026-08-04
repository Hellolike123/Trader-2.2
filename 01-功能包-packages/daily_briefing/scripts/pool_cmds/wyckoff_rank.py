"""兼容入口：吸筹链 SSOT 在 trader_shared.wyckoff_chain。"""
from __future__ import annotations

from trader_shared.wyckoff_chain import (  # noqa: F401
    ACCUM_CHAIN,
    attach_wyckoff_chain_fields,
    extract_accum_events,
    extract_rs_label,
    first_missing_accum,
    format_rs_plain,
    format_wyckoff_chain_plain,
    wyckoff_chain_rank,
    wyckoff_rs_rank,
)

__all__ = [
    "ACCUM_CHAIN",
    "attach_wyckoff_chain_fields",
    "extract_accum_events",
    "extract_rs_label",
    "first_missing_accum",
    "format_rs_plain",
    "format_wyckoff_chain_plain",
    "wyckoff_chain_rank",
    "wyckoff_rs_rank",
]
