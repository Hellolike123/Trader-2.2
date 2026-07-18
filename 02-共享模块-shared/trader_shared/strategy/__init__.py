"""策略层包：六闸口匹配与策略包 YAML（不重算缠/威/筹）。

架构：docs/designs/analysis-strategy-boundaries.md
"""
from trader_shared.strategy.match import (
    GATES,
    build_match_context,
    format_gates_brief,
    load_strategy_packs,
    match_strategies,
    stop_buffer,
)

__all__ = [
    "GATES",
    "build_match_context",
    "format_gates_brief",
    "load_strategy_packs",
    "match_strategies",
    "stop_buffer",
]
