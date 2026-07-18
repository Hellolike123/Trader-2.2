"""兼容 re-export：请优先 `from trader_shared.strategy import ...`。

物理路径：trader_shared/strategy/match.py
"""
from trader_shared.strategy.match import *  # noqa: F403
from trader_shared.strategy.match import (  # noqa: F401
    GATES,
    build_match_context,
    format_gates_brief,
    load_strategy_packs,
    match_strategies,
    stop_buffer,
)
