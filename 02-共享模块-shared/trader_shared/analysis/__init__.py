"""分析层包：意见卡与 fusion 读卡适配（不负责策略匹配）。

架构：docs/designs/analysis-strategy-boundaries.md
"""
from trader_shared.analysis.cards import (
    assert_card_numeric_finite,
    build_chan_card,
    build_chip_card,
    build_momentum_card,
    build_vpf_card,
    build_wyckoff_card,
    ensure_report_analysis_cards,
)
from trader_shared.analysis.fusion_card_signals import (
    chan_card_to_fusion_signal,
    fusion_signals_from_cards,
    momentum_card_to_fusion_signal,
    vpf_card_to_fusion_signal,
)

__all__ = [
    "assert_card_numeric_finite",
    "build_chan_card",
    "build_chip_card",
    "build_momentum_card",
    "build_vpf_card",
    "build_wyckoff_card",
    "ensure_report_analysis_cards",
    "chan_card_to_fusion_signal",
    "fusion_signals_from_cards",
    "momentum_card_to_fusion_signal",
    "vpf_card_to_fusion_signal",
]
