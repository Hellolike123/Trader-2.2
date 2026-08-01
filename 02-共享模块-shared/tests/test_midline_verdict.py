"""中线定论合成：威科夫中线阶段 + 周线缠论结构副读。

锁定 synthesize_midline_verdict：stage 钉死周线威科夫短词；
矩阵仅驱动 bias/confidence/note（BUSINESS.md §2.0）。
"""
import pytest
from trader_shared.conclusion_block import (
    synthesize_midline_verdict,
    chanlun_midline_dir,
    _chan_dir_for_midline_verdict,
    wyckoff_midline_bias,
)


def _wyck(phase, **kw):
    base = {"phase": phase, "phase_label": f"phase:{phase}"}
    base.update(kw)
    return base


def _chan(
    structure_type,
    structure_confidence="mid",
    divergence=None,
    buy_points=None,
    sell_points=None,
    timeframe=None,
):
    out = {
        "structure_type": structure_type,
        "structure_confidence": structure_confidence,
        "divergence": divergence or {},
        "buy_points": buy_points or [],
        "sell_points": sell_points or [],
    }
    if timeframe is not None:
        out["timeframe"] = timeframe
    return out


# (wyck_phase, wyck_signal, chan_type, chan_conf, chan_div, expected_stage, expected_bias, expected_conf)
# stage = 周线威科夫短词；矩阵不得 remap 吸筹→主升 / 派发→衰退
CASES = [
    # 共振：双 bullish / 双 bearish — stage 仍钉威科夫阶段
    ("accumulation_d", {"sos_signal": True}, "上涨趋势", "high", {}, "吸筹", "bull", "high"),
    ("distribution_a", {"bc_signal": True}, "下跌趋势", "high", {"top_divergence": True}, "派发", "bear", "high"),
    # 威科夫领先 + 缠论中性
    ("accumulation_c", {"spring_signal": True}, "盘整趋势", "mid", {}, "吸筹", "bull", "mid"),
    ("distribution_a", {"bc_signal": True}, "盘整趋势", "mid", {}, "派发", "bear", "mid"),
    # 威科夫无方向：阶段钉无阶段；bias 仍可听缠论方向提示
    ("none", {}, "上涨趋势", "high", {}, "无阶段", "bull", "mid"),
    ("none", {}, "下跌趋势", "high", {"top_divergence": True}, "无阶段", "bear", "mid"),
    # 冲突：降置信；stage 不因冲突改写
    ("accumulation_c", {"spring_signal": True}, "下跌趋势", "high", {"top_divergence": True}, "吸筹", "bull", "low"),
    ("distribution_a", {"bc_signal": True}, "上涨趋势", "high", {}, "派发", "bear", "low"),
    # phase 映射
    ("markup", {}, "上涨趋势", "high", {}, "主升", "bull", "mid"),
    ("markdown", {}, "下跌趋势", "high", {}, "主跌", "bear", "mid"),
]


@pytest.mark.parametrize("wyck_phase,wyck_sig,chan_type,chan_conf,chan_div,exp_stage,exp_bias,exp_conf", CASES)
def test_synthesis_matrix(wyck_phase, wyck_sig, chan_type, chan_conf, chan_div, exp_stage, exp_bias, exp_conf):
    w = _wyck(wyck_phase, **wyck_sig)
    c = _chan(chan_type, chan_conf, chan_div)
    r = synthesize_midline_verdict(c, w, fallback_stage="震荡")
    assert r["stage"] == exp_stage, r
    assert r["bias"] == exp_bias, r
    assert r["confidence"] == exp_conf, r
    assert r["source"] == "wyckoff+chanlun"


def test_m1_accumulation_sos_stays_xichou_not_zhusheng():
    """M1：吸筹 + SOS + 周线缠多 → stage 仍「吸筹」，不得矩阵改「主升」。"""
    w = _wyck("accumulation_d", sos_signal=True)
    c = _chan("上涨趋势", "high", {}, timeframe="weekly")
    r = synthesize_midline_verdict(c, w, fallback_stage="主升")
    assert r["wyck_dir"] == 1
    assert r["chan_dir"] == 1
    assert r["stage"] == "吸筹"
    assert r["stage"] != "主升"
    assert r["bias"] == "bull"
    assert r["confidence"] == "high"


def test_fallback_when_both_neutral():
    r = synthesize_midline_verdict({}, {}, fallback_stage="走强")
    assert r["source"] == "fallback_position"
    assert r["bias"] == "neutral"
    assert r["confidence"] == "low"
    assert r["stage"] == "无阶段"


def test_fallback_defaults_to_无阶段():
    r = synthesize_midline_verdict({}, {}, fallback_stage="")
    assert r["stage"] == "无阶段"
    assert "双源无明确方向" in r["note"]


def test_low_chan_conf_downgrades_resonance():
    # 双 bullish 但缠论低置信 → 共振档从 high 降到 mid；stage 仍吸筹
    w = _wyck("accumulation_d", sos_signal=True)
    c = _chan("上涨趋势", "low", {}, buy_points=[{"type": "二类买", "confidence": 3}])
    r = synthesize_midline_verdict(c, w, fallback_stage="震荡")
    assert r["stage"] == "吸筹"
    assert r["confidence"] == "mid"


def test_independent_labels_preserved():
    # 两源各自独立输出必须在返回中保留（供报告分别渲染 + 调试）
    w = _wyck("accumulation_c", phase_label="积累期 C（测试：Spring）", spring_signal=True)
    c = _chan("盘整趋势", "mid", {}, buy_points=[], sell_points=[])
    r = synthesize_midline_verdict(c, w, fallback_stage="震荡")
    assert "积累期 C" in r["wyck_label"]
    assert "盘整趋势" in r["chan_label"]
    assert r["wyck_dir"] == 1 and r["chan_dir"] == 0
    assert r["stage"] == "吸筹"


# ── P2 缠论低置信跳过生命线 ─────────────────────────────────


def test_chanlun_midline_dir_low_conf_neutral():
    """structure_confidence=low 时 chanlun_midline_dir 返回 0，
    即使结构类型看涨（不靠兜底翻转方向）。"""
    chan = _chan("上涨趋势", "low", {}, buy_points=[], sell_points=[])
    assert chanlun_midline_dir(chan) == 0


def test_chanlun_midline_dir_soft_sell_beats_bottom_div():
    """类二卖（观察档）须驱动定论看空，不得被底背驰翻成上涨。"""
    chan = _chan(
        "盘整",
        "low",
        {"bottom_divergence": True},
        buy_points=[],
        sell_points=[{"type": "类二卖", "confidence": 1, "price": 49.41}],
    )
    assert chanlun_midline_dir(chan) == -1


def test_chanlun_midline_dir_low_conf_with_buy_point():
    """有买卖点时跟主解析（含 conf=1）；与短线灯标同源。"""
    chan = _chan("下跌趋势", "low", {}, buy_points=[{"type": "二类买", "confidence": 1}], sell_points=[])
    assert chanlun_midline_dir(chan) == 1


def test_verdict_note_soft_sell_and_wyck_no_phase():
    """三花类：威科夫无阶段 × 周线类二卖 → 阶段无阶段；bias 可偏空；不定「领先」。"""
    w = _wyck("none", phase_tr_gated=True, phase_tr_gate_reason="no_tr")
    c = _chan(
        "盘整",
        "low",
        {"bottom_divergence": True},
        sell_points=[{"type": "类二卖", "confidence": 1}],
        timeframe="weekly",
    )
    r = synthesize_midline_verdict(c, w, fallback_stage="震荡")
    assert r["chan_dir"] == -1
    assert r["wyck_dir"] == 0
    assert r["stage"] == "无阶段"
    assert r["bias"] == "bear"
    assert "上涨" not in r["note"]
    assert "类二卖" in r["note"]
    assert "无阶段" in r["note"]
    assert "领先" not in r["note"]
    assert "结构副读" in r["note"]


def test_low_chan_conf_skips_lifeline_in_verdict():
    """缠论低置信 + 威科夫看多 → 威科夫取胜但置信降低。"""
    w = _wyck("accumulation_c", spring_signal=True)
    c = _chan("下跌趋势", "low", {}, buy_points=[], sell_points=[])
    r = synthesize_midline_verdict(c, w, fallback_stage="震荡")
    # 威科夫 bull → 结果 bull，但缠论低置信且中性 → 降置信
    assert r["bias"] == "bull"
    assert r["confidence"] in ("low", "mid")
    assert r["chan_dir"] == 0
    assert r["stage"] == "吸筹"


# ── P0 合同：A1 / A2 / M1 / M6 ─────────────────────────────────────────


def test_a1_accumulation_plus_like2_stays_xichou_not_zhusheng():
    """南网类：周线威科夫吸筹 + 缠论类二买 → 阶段仍吸筹，不得主升初期。"""
    w = _wyck("accumulation_b")  # 无 spring/sos → wyck_dir=0
    c = _chan(
        "盘整",
        "mid",
        {},
        buy_points=[{"type": "类二买", "confidence": 1, "price": 10.0}],
        timeframe="weekly",
    )
    r = synthesize_midline_verdict(c, w, fallback_stage="蓄势")
    assert r["wyck_dir"] == 0
    assert r["chan_dir"] == 1
    assert r["stage"] == "吸筹"
    assert r["stage"] != "主升初期"
    assert "领先" not in r["note"]
    assert "结构副读" in r["note"]
    # 方向提示仍可偏多，但不改阶段
    assert r["bias"] == "bull"


def test_a2_daily_fallback_does_not_drive_verdict_direction():
    """daily_fallback 类二买：可展示，不得改 stage/bias/chan_dir。"""
    w = _wyck("accumulation_b")
    c = _chan(
        "上涨趋势",
        "high",
        {},
        buy_points=[{"type": "类二买", "confidence": 2, "price": 10.0}],
        timeframe="daily_fallback",
    )
    assert chanlun_midline_dir(c) == 1  # 原始方向仍可读
    assert _chan_dir_for_midline_verdict(c) == 0  # 定论闸死
    r = synthesize_midline_verdict(c, w, fallback_stage="蓄势")
    assert r["chan_dir"] == 0
    assert r["stage"] == "吸筹"
    assert r["bias"] == "neutral"
    assert "主升初期" not in r["stage"]
    assert "日线回退仅展示" in r["note"] or "日线回退仅展示" in r["chan_label"]


def test_a1_weekly_chan_bull_no_wyck_stage_uses_无阶段():
    """威科夫无阶段 + 周线上涨：阶段钉无阶段，禁止主升初期/位置分类冒充。"""
    w = _wyck("none", phase_tr_gated=True)
    c = _chan("上涨趋势", "high", {}, timeframe="weekly")
    r = synthesize_midline_verdict(c, w, fallback_stage="走强")
    assert r["stage"] == "无阶段"
    assert r["bias"] == "bull"
    assert r["stage"] != "主升初期"
    assert r["stage"] != "走强"


def test_m6_daily_major_stage_cannot_wash_weekly_ut():
    """M6：日线 major_stage=主升 不得洗周线 UT；除非周线 phase=markup。"""
    w_ut = {
        "phase": "accumulation_b",
        "upthrust_signal": True,
        "upthrust_premature": False,
        "spring_signal": False,
        "bc_signal": False,
        "sow_signal": False,
        "sos_signal": False,
    }
    assert wyckoff_midline_bias(w_ut, major_stage="主升") == "strong_bear"
    assert wyckoff_midline_bias(w_ut, major_stage="蓄势偏强") == "strong_bear"

    w_markup_ut = {**w_ut, "phase": "markup"}
    assert wyckoff_midline_bias(w_markup_ut, major_stage="") == "neutral"
    assert wyckoff_midline_bias(w_markup_ut, major_stage="衰退") == "neutral"


def test_m1_build_conclusion_stage_line_pins_wyckoff_not_major():
    """M1：conclusion.stage_line 钉威科夫短词；日线 major_stage 不得冒充。"""
    from trader_shared.conclusion_block import build_conclusion_block

    c = build_conclusion_block(
        major_stage="主升",
        mistery_gate={"action": "观望", "hard_block": "none", "position_cap_pct": 0},
        key_prices={},
        wyckoff_midline=_wyck("accumulation_d", sos_signal=True),
        chanlun_midline=_chan("上涨趋势", "high", {}, timeframe="weekly"),
    )
    assert c["stage_line"] == "吸筹"
    assert c["stage_line"] != "主升"


def test_m1_renderer_does_not_fallback_to_major_stage():
    """M1：空 stage_line 时面板阶段行不得回落日线 major_stage。"""
    from pathlib import Path
    import trader_shared.report_renderer.short_midline as sm

    src = Path(sm.__file__).read_text(encoding="utf-8")
    assert 'conclusion.get("stage_line") or major_stage' not in src
    assert "禁日线 major_stage 冒充" in src or 'conclusion.get("stage_line") or ""' in src
