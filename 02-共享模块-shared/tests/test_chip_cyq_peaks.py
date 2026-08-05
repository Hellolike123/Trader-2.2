# -*- coding: utf-8 -*-
from __future__ import annotations

from trader_shared.chip_data import cyq_chips_to_peaks


def test_cyq_chips_to_peaks_already_percent_bins():
    """专属网关：percent=1.46 表示 1.46%，不要再 *100。"""
    peaks = cyq_chips_to_peaks(
        [
            {"price": 10.0, "percent": 0.5},
            {"price": 12.5, "percent": 1.8},
            {"price": 15.0, "percent": 0.7},
            {"price": 0, "percent": 99},
        ],
        top_n=2,
    )
    assert len(peaks) == 2
    assert peaks[0]["price"] == 12.5
    assert peaks[0]["share_of_total"] == 1.8


def test_cyq_chips_to_peaks_ratio_0_1_scale():
    """少数源：ratio 合计≈1 时按比例转百分。"""
    peaks = cyq_chips_to_peaks(
        [
            {"cost": 20.1, "ratio": 0.22},
            {"cost": 19.0, "ratio": 0.10},
            {"cost": 21.0, "ratio": 0.08},
        ],
        top_n=1,
    )
    assert peaks and peaks[0]["price"] == 20.1
    assert peaks[0]["share_of_total"] == 22.0
