"""中线定论合成：威科夫中线 + 缠论中线 各自独立判定后合成。

锁定 synthesize_midline_verdict 的合成矩阵、bias、兜底与注记。
"""
import pytest
from trader_shared.conclusion_block import synthesize_midline_verdict


def _wyck(phase, **kw):
    base = {"phase": phase, "phase_label": f"phase:{phase}"}
    base.update(kw)
    return base


def _chan(structure_type, structure_confidence="mid", divergence=None, buy_points=None, sell_points=None):
    return {
        "structure_type": structure_type,
        "structure_confidence": structure_confidence,
        "divergence": divergence or {},
        "buy_points": buy_points or [],
        "sell_points": sell_points or [],
    }


# (wyck_phase, wyck_signal, chan_type, chan_conf, chan_div, expected_stage, expected_bias, expected_conf)
CASES = [
    # 共振：双 bullish / 双 bearish
    ("accumulation_d", {"sos_signal": True}, "上涨趋势", "high", {}, "主升", "bull", "high"),
    ("distribution_a", {"bc_signal": True}, "下跌趋势", "high", {"top_divergence": True}, "衰退", "bear", "high"),
    # 威科夫领先 + 缠论中性
    ("accumulation_c", {"spring_signal": True}, "盘整趋势", "mid", {}, "蓄势", "bull", "mid"),
    ("distribution_a", {"bc_signal": True}, "盘整趋势", "mid", {}, "派发", "bear", "mid"),
    # 缠论领先 + 威科夫中性
    ("none", {}, "上涨趋势", "high", {}, "主升初期", "bull", "mid"),
    ("none", {}, "下跌趋势", "high", {"top_divergence": True}, "转弱", "bear", "mid"),
    # 冲突：降置信
    ("accumulation_c", {"spring_signal": True}, "下跌趋势", "high", {"top_divergence": True}, "蓄势·警惕转弱", "bull", "low"),
    ("distribution_a", {"bc_signal": True}, "上涨趋势", "high", {}, "派发·警惕", "bear", "low"),
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


def test_fallback_when_both_neutral():
    r = synthesize_midline_verdict({}, {}, fallback_stage="走强")
    assert r["source"] == "fallback_position"
    assert r["bias"] == "neutral"
    assert r["confidence"] == "low"
    assert r["stage"] == "走强"


def test_fallback_defaults_to_震荡():
    r = synthesize_midline_verdict({}, {}, fallback_stage="")
    assert r["stage"] == "震荡"
    assert "回退位置分类" in r["note"]


def test_low_chan_conf_downgrades_resonance():
    # 双 bullish 但缠论低置信 → 共振档从 high 降到 mid
    w = _wyck("accumulation_d", sos_signal=True)
    c = _chan("上涨趋势", "low", {}, buy_points=[{"type": "二类买", "confidence": 3}])
    r = synthesize_midline_verdict(c, w, fallback_stage="震荡")
    assert r["stage"] == "主升"
    assert r["confidence"] == "mid"


def test_independent_labels_preserved():
    # 两源各自独立输出必须在返回中保留（供报告分别渲染 + 调试）
    w = _wyck("accumulation_c", phase_label="积累期 C（测试：Spring）", spring_signal=True)
    c = _chan("盘整趋势", "mid", {}, buy_points=[], sell_points=[])
    r = synthesize_midline_verdict(c, w, fallback_stage="震荡")
    assert "积累期 C" in r["wyck_label"]
    assert "盘整趋势" in r["chan_label"]
    assert r["wyck_dir"] == 1 and r["chan_dir"] == 0
