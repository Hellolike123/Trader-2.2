"""中短线标题挂灯：🧭 中线｜🔴 防守 / ⚡ 短线｜🔴 不新开。"""
from trader_shared.report_renderer.short_midline import format_track_header_light


def test_mid_header_failed_is_red_defense():
    r = {
        "wyckoff_midline": {"phase_a_status": "failed", "phase_label": "失效"},
    }
    assert format_track_header_light(track="mid", report=r) == "🧭 中线｜🔴 防守"


def test_mid_header_distribution_is_red_defense():
    r = {
        "wyckoff_midline": {
            "phase": "distribution_d",
            "phase_label": "派发期 D",
            "bc_signal": True,
        }
    }
    assert format_track_header_light(track="mid", report=r) == "🧭 中线｜🔴 防守"


def test_mid_header_accumulation_is_green_track():
    r = {
        "wyckoff_midline": {
            "phase": "accumulation_b",
            "phase_label": "积累期 B",
            "sc_signal": True,
            "ar_signal": True,
        }
    }
    assert format_track_header_light(track="mid", report=r) == "🧭 中线｜🟢 可跟踪"


def test_mid_header_none_is_yellow_watch():
    r = {"wyckoff_midline": {"phase": "none", "phase_label": ""}}
    assert format_track_header_light(track="mid", report=r) == "🧭 中线｜🟡 观望"


def test_short_header_distribution_is_red_no_entry():
    r = {
        "wyckoff_daily": {
            "timeframe": "daily",
            "bc_signal": True,
            "lpsy_signal": True,
            "phase_a_status": "established",
        }
    }
    assert format_track_header_light(track="short", report=r) == "⚡ 短线｜🔴 不新开"


def test_short_header_accumulation_open_is_green_qual():
    r = {
        "wyckoff_daily": {
            "timeframe": "daily",
            "sc_signal": True,
            "sos_signal": True,
            "phase_a_status": "established",
        },
        "decision_view": {"allow_new_recommend": True},
    }
    assert format_track_header_light(track="short", report=r) == "⚡ 短线｜🟢 去看trader"


def test_short_header_accumulation_but_closed_is_red():
    r = {
        "wyckoff_daily": {
            "timeframe": "daily",
            "sc_signal": True,
            "sos_signal": True,
            "phase_a_status": "established",
        },
        "decision_view": {"allow_new_recommend": False},
    }
    assert format_track_header_light(track="short", report=r) == "⚡ 短线｜🔴 不新开"


def test_short_header_unformed_is_yellow():
    r = {
        "wyckoff_daily": {
            "timeframe": "daily",
            "phase": "none",
            "phase_a_status": "none",
        }
    }
    assert format_track_header_light(track="short", report=r) == "⚡ 短线｜🟡 仅观察"
