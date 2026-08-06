"""板块：有真实指数才比强弱；概念只作标签/映射线索。"""
from __future__ import annotations

from trader_shared import sector_data as sd


def _idx(name: str, code: str = "885xxx.TI") -> dict:
    return {"name": name, "ts_code": code}


THS = [
    _idx("化学原料", "700101.TI"),
    _idx("商品化工(A股)", "700102.TI"),
    _idx("电池化学品", "700201.TI"),
    _idx("锂电池", "700202.TI"),
    _idx("电池", "700203.TI"),
    _idx("白色家电", "700301.TI"),
]


def test_concept_maps_to_real_ths_not_fake_index():
    matched, via = sd._match_ths_from_concepts(
        ["磷酸铁锂", "宁德时代概念", "储能"], THS
    )
    assert matched is not None
    assert matched["name"] == "电池化学品"  # 磷酸铁锂优先候选第一
    assert via == "磷酸铁锂"


def test_industry_alias_huagong_yuaniao():
    hit = sd._match_ths_industry("化工原料", THS)
    assert hit is not None
    assert hit["name"] in {"化学原料", "商品化工(A股)", "电池化学品"}


def test_pack_without_daily_is_not_normal(monkeypatch):
    monkeypatch.setattr(sd, "get_ths_daily", lambda code: [])
    out = sd._pack_sector_snap(
        industry="化工原料",
        matched=_idx("电池", "700203.TI"),
        concepts=["磷酸铁锂", "储能"],
        match_via="concept:磷酸铁锂",
    )
    assert out["status"] == "无日线"
    assert out["concepts"] == ["磷酸铁锂", "储能"]
    assert out["primary_concept"] == "磷酸铁锂"
    assert "sector_change_pct" not in out or out.get("status") != "正常"


def test_pack_with_daily_normal(monkeypatch):
    monkeypatch.setattr(
        sd,
        "get_ths_daily",
        lambda code: [{"trade_date": "20260806", "pct_change": 1.25}],
    )
    out = sd._pack_sector_snap(
        industry="化工原料",
        matched=_idx("锂电池", "700202.TI"),
        concepts=["磷酸铁锂", "储能"],
        match_via="concept:磷酸铁锂",
    )
    assert out["status"] == "正常"
    assert out["sector_name"] == "锂电池"
    assert out["sector_change_pct"] == 1.25
    assert out["match_via"] == "concept:磷酸铁锂"


def test_short_midline_concept_tags_no_fake_pct():
    from trader_shared.report_renderer.short_midline import render_short_midline

    report = {
        "name": "德方纳米",
        "code": "300769",
        "symbol": "300769.SZ",
        "current_price": 46.55,
        "change_pct": -0.21,
        "ma20": 44.62,
        "ma250": 48.16,
        "ma250_warning": True,
        "short_term_momentum": "修复",
        "market_change_pct": -0.55,
        "volume_ratio": 0.9,
        "atr14": 2.58,
        "turnover_rate": 0,
        "daily_bars": [],
        "extend_sector": {
            "status": "正常",
            "industry": "化工原料",
            "sector_name": "锂电池",
            "sector_change_pct": 0.80,
            "concepts": ["磷酸铁锂", "宁德时代概念", "储能"],
            "primary_concept": "磷酸铁锂",
            "match_via": "concept:磷酸铁锂",
        },
        "conclusion": {
            "midline": "中线观察",
            "shortline": "观察",
            "execution": "现价不买 · 不追",
        },
        "decision_view": {"action": "观望", "recommend": False},
        "short_track": {},
        "mid_track": {},
        "structure": {},
        "chip": {},
        "strategy": {},
        "fusion": {},
    }
    md = render_short_midline(report)
    assert "概念：磷酸铁锂 ｜ 宁德时代概念 ｜ 储能" in md
    assert "概念题材" not in md
    # 强弱只对真实板块指数
    assert "锂电池" in md or "锂电" in md
    assert "强于板块" in md or "弱于板块" in md or "持平板块" in md
    # 不应出现概念假涨幅括号
    assert "磷酸铁锂（涨幅" not in md
    # 概念在量能之上；量能含动能+ATR
    ci = md.index("概念：")
    vi = md.index("量能：")
    assert ci < vi
    assert "动能 修复" in md.split("量能：", 1)[1].splitlines()[0]
    assert "ATR14 2.58" in md.split("量能：", 1)[1].splitlines()[0]
