"""威科夫 Skill 渲染合同（无网络）。"""
from __future__ import annotations

from trader_shared.wyckoff_render import render_wyckoff_card, render_wyckoff_rank
from trader_shared.wyckoff_run import build_wyckoff_rank_rows


def _sample_plan() -> dict:
    return {
        "name": "测试股",
        "code": "600000",
        "price": 10.5,
        "data_ok": True,
        "chain_plain": "威：SC→AR→ST→LPS，还差SOS",
        "event_line": "SC / AR / ST / LPS",
        "daily_view": {
            "phase": "accumulation_c",
            "phase_label": "吸筹C",
            "bias": "bull",
            "tr": {"lower": 9.8, "upper": 11.2, "quality": 0.62},
            "active_events": ["sc", "ar", "st", "lps"],
            "invalidation_hint": "收盘有效跌破 TR 下沿 9.80 则偏多结构受损",
            "summary_oneline": "吸筹推进中，关注 LPS 后 SOS",
        },
        "weekly_view": {
            "phase": "accumulation_b",
            "phase_label": "吸筹B",
            "bias": "bull",
        },
    }


def test_render_card_skeleton_wechat_safe():
    text = render_wyckoff_card(_sample_plan())
    assert text.startswith("威科夫 — 测试股（600000）")
    assert "🧭 阶段：吸筹C｜偏向 偏多" in text
    assert "📎 链：威：SC→AR→ST→LPS，还差SOS" in text
    assert "📌 事件：" in text
    assert "📐 TR：" in text
    assert "⚠ 失效：" in text
    assert "🧭 中线阶段：吸筹B｜偏向 偏多" in text
    assert "💬 一句：" in text
    # 微信红线
    assert "#" not in text
    assert "**" not in text
    assert "---" not in text
    assert "|" not in text  # 并列须用全角｜
    assert "｜" in text
    # 禁止买卖指令词
    for bad in ("可执行", "宜买", "可低吸", "三重共振买", "去买"):
        assert bad not in text


def test_render_card_data_insufficient():
    text = render_wyckoff_card(
        {"name": "测试股", "code": "600000", "error": "日线不足", "data_ok": False}
    )
    assert "⚠ 日线不足" in text
    assert "数据不足，仅现价" in text


def test_render_rank_rows():
    text = render_wyckoff_rank(
        [
            {
                "name": "甲",
                "chain_plain": "威：SC→AR→ST",
                "phase_label": "吸筹C",
            },
            {
                "name": "乙",
                "chain_plain": "威：吸筹链未成型",
                "phase_label": "—",
            },
        ]
    )
    assert text.startswith("威科夫池排序")
    assert "1. 甲｜威：SC→AR→ST｜吸筹C" in text
    assert "2. 乙｜威：吸筹链未成型｜—" in text
    assert "非分道" in text
    assert "#" not in text
    assert "**" not in text


def test_build_rank_rows_sort_by_chain():
    items = [
        {"name": "弱", "wyckoff": {"sc_signal": True}},
        {
            "name": "强",
            "wyckoff": {
                "sc_signal": True,
                "ar_signal": True,
                "st_signal": True,
                "lps_signal": True,
            },
        },
    ]
    rows = build_wyckoff_rank_rows(items)
    assert rows[0]["name"] == "强"
    assert rows[0]["chain_rank"] >= rows[1]["chain_rank"]


def test_main_exits_1_when_card_data_fails(monkeypatch, capsys):
    from trader_shared import wyckoff_run as wr

    monkeypatch.setattr(
        wr,
        "build_wyckoff_plan",
        lambda target: {
            "target": target,
            "name": target,
            "data_ok": False,
            "error": "取数失败：无法解析股票名称",
        },
    )
    code = wr.main(["--target", "__NO_SUCH__"])
    assert code == 1
    out = capsys.readouterr().out
    assert "取数失败" in out
    assert "数据不足" in out


def test_main_exits_0_when_card_ok(monkeypatch, capsys):
    from trader_shared import wyckoff_run as wr

    monkeypatch.setattr(wr, "build_wyckoff_plan", lambda target: _sample_plan())
    code = wr.main(["--target", "测试股"])
    assert code == 0
    assert "威科夫 — 测试股" in capsys.readouterr().out
