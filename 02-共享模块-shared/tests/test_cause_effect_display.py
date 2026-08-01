"""量度目标面板文案契约（L3 诚实标签）。"""

from trader_shared.wyckoff_view import format_cause_effect_display


def test_format_cause_effect_display_short_copy() -> None:
    line = format_cause_effect_display({
        "cause_effect_up_target": 50.91,
        "cause_effect_down_target": 32.39,
        "measure_allowed": True,
    })
    assert line == "量度目标：上 50.91｜下 32.39（P&F，非出手）"


def test_format_cause_effect_display_empty_without_targets() -> None:
    assert format_cause_effect_display({}) == ""
    assert format_cause_effect_display(None) == ""
    assert format_cause_effect_display({
        "cause_effect_up_target": 10.0,
        "cause_effect_down_target": None,
        "measure_allowed": True,
    }) == ""


def test_format_cause_effect_display_height_1to1_not_pnf() -> None:
    """M-R7：1:1 fallback 标签不得冒充 P&F。"""
    line = format_cause_effect_display({
        "cause_effect_up_target": 92.0,
        "cause_effect_down_target": 72.0,
        "pnf_method": "height_1to1_fallback",
        "measure_allowed": True,
    })
    assert line == "量度目标：上 92.00｜下 72.00（高度1:1，非出手）"
    assert "P&F" not in line


def test_format_cause_effect_display_measure_not_allowed_defensive() -> None:
    """measure_allowed=False 时即使残留目标也返回空串。"""
    assert format_cause_effect_display({
        "cause_effect_up_target": 50.0,
        "cause_effect_down_target": 40.0,
        "measure_allowed": False,
        "pnf_method": "horizontal",
    }) == ""


def test_format_cause_effect_display_missing_measure_allowed_safe() -> None:
    """缺省 measure_allowed 且非 L3 → 不得贴假量度。"""
    assert format_cause_effect_display({
        "cause_effect_up_target": 50.0,
        "cause_effect_down_target": 40.0,
        "pnf_method": "horizontal",
    }) == ""
    assert format_cause_effect_display({
        "cause_effect_up_target": 50.0,
        "cause_effect_down_target": 40.0,
        "tr_maturity": "L2",
    }) == ""


def test_format_cause_effect_display_nested_view_shape() -> None:
    line = format_cause_effect_display({
        "cause_effect": {
            "up_target": 11.5,
            "down_target": 9.5,
            "pnf_method": "vertical",
            "measure_allowed": True,
        },
    })
    assert line == "量度目标：上 11.50｜下 9.50（P&F，非出手）"


def test_format_cause_effect_display_nested_measure_blocked() -> None:
    assert format_cause_effect_display({
        "cause_effect": {
            "up_target": 11.5,
            "down_target": 9.5,
            "measure_allowed": False,
        },
    }) == ""
