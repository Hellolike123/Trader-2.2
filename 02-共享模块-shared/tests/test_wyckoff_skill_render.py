"""威科夫 Skill 渲染合同（无网络）。

法源验收：docs/plans/wyckoff-skill-deep-card-handoff.md §4 W-D1..W-D11
"""
from __future__ import annotations

import copy
import re

import pytest

from trader_shared.wyckoff_chain import extract_accum_events
from trader_shared.wyckoff_render import (
    build_light_snapshot_entry,
    format_light_change,
    render_wyckoff_card,
    render_wyckoff_detail,
    render_wyckoff_slim,
    render_wyckoff_rank,
)
from trader_shared.wyckoff_run import build_wyckoff_rank_rows


def _sample_plan() -> dict:
    return {
        "name": "测试股",
        "code": "600000",
        "price": 10.5,
        "data_ok": True,
        "chain_plain": "威：SC→AR→ST→LPS，还差SOS",
        "event_line": "SC / AR / ST / LPS",
        "change_line": "首次记录，暂无对比",
        "daily_raw": {
            "sc_signal": True,
            "ar_signal": True,
            "secondary_test_sc_signal": True,
            "st_signal": True,
            "lps_signal": True,
            "sc_price": 9.5,
            "sc_low": 9.5,
            "ar_price": 11.0,
            "ar_high": 11.0,
            "secondary_test_sc_price": 9.6,
            "lps_price": 10.2,
            "tr_maturity": "L2",
            "box_display_mode": "box",
            "measure_allowed": False,
            "tr_seed_source": "phase_a_seed",
            "phase_a_status": "established",
        },
        "weekly_raw": {
            "sc_signal": True,
            "ar_signal": True,
            "sc_low": 8.0,
            "ar_high": 12.0,
            "tr_maturity": "L1",
            "box_display_mode": "proto",
            "measure_allowed": False,
            "tr_seed_source": "phase_a_seed",
        },
        "daily_view": {
            "phase": "accumulation_c",
            "phase_label": "吸筹C",
            "bias": "bull",
            "tr": {"lower": 9.5, "upper": 11.0, "quality": 0.62},
            "tr_maturity": "L2",
            "box_display_mode": "box",
            "measure_allowed": False,
            "active_events": ["sc", "ar", "secondary_test_sc", "lps"],
            "event_detail": {
                "sc": {"id": "sc", "price": 9.5, "reason": "SC"},
                "ar": {"id": "ar", "price": 11.0, "reason": "AR"},
                "secondary_test_sc": {"id": "secondary_test_sc", "price": 9.6, "reason": "ST"},
                "lps": {"id": "lps", "price": 10.2, "reason": "LPS"},
            },
            "invalidation_hint": "收盘有效跌破 TR 下沿 9.50 则偏多结构受损",
            "summary_oneline": "吸筹推进中，关注 LPS 后 SOS",
            "cause_effect": {"up_target": None, "down_target": None},
        },
        "weekly_view": {
            "phase": "accumulation_b",
            "phase_label": "吸筹B",
            "bias": "bull",
            "tr_maturity": "L1",
            "box_display_mode": "proto",
            "measure_allowed": False,
            "active_events": ["sc", "ar"],
            "event_detail": {
                "sc": {"id": "sc", "price": 8.0, "reason": "SC"},
                "ar": {"id": "ar", "price": 12.0, "reason": "AR"},
            },
            "invalidation_hint": "暂无明确失效价",
            "summary_oneline": "周线吸筹推进",
            "tr": {"lower": 8.0, "upper": 12.0},
        },
    }


def _l0_percentile_plan() -> dict:
    """天奈类：有分位 tr_lower/tr_upper 但 maturity L0 — 区间不得上屏这些数字。"""
    return {
        "name": "天奈样",
        "code": "688116",
        "price": 50.0,
        "data_ok": True,
        "chain_plain": "威：吸筹链未成型",
        "change_line": "首次记录，暂无对比",
        "daily_raw": {
            "tr_lower": 41.23,
            "tr_upper": 58.77,
            "tr_seed_source": "percentile",
            "tr_maturity": "L0",
            "box_display_mode": "none",
            "measure_allowed": False,
            "phase_a_status": "none",
        },
        "weekly_raw": {
            "tr_lower": 40.0,
            "tr_upper": 60.0,
            "tr_seed_source": "percentile",
            "tr_maturity": "L0",
            "box_display_mode": "none",
            "measure_allowed": False,
        },
        "daily_view": {
            "phase": "none",
            "phase_label": "",
            "bias": "neutral",
            "tr": {"lower": 41.23, "upper": 58.77, "quality": 0.5},
            "tr_maturity": "L0",
            "box_display_mode": "none",
            "measure_allowed": False,
            "active_events": [],
            "event_detail": {},
            "invalidation_hint": "收盘有效跌破 TR 下沿 41.23 则偏多结构受损",
            "summary_oneline": "暂无明确结构",
        },
        "weekly_view": {
            "phase": "none",
            "bias": "neutral",
            "tr": {"lower": 40.0, "upper": 60.0},
            "tr_maturity": "L0",
            "box_display_mode": "none",
            "measure_allowed": False,
            "active_events": [],
            "event_detail": {},
            "invalidation_hint": "收盘有效跌破 TR 下沿 40.00 则偏多结构受损",
            "summary_oneline": "暂无",
        },
    }


def _failed_phase_a_plan() -> dict:
    plan = copy.deepcopy(_sample_plan())
    plan["chain_plain"] = "威：SC，还差AR"  # 故意放旧缓存，render 应按 failed raw 收口。
    plan["daily_raw"].update(
        {
            "ar_signal": False,
            "secondary_test_sc_signal": False,
            "st_signal": False,
            "lps_signal": False,
            "phase_a_status": "failed",
            "phase_a_range": {"status": "failed", "sc_low": 9.5},
            "tr_maturity": "L0",
            "box_display_mode": "none",
            "measure_allowed": False,
        }
    )
    plan["daily_view"].update(
        {
            "phase_label": "Phase A失败",
            "bias": "neutral",
            "active_events": ["sc"],
            "tr_maturity": "L0",
            "box_display_mode": "none",
            "measure_allowed": False,
            "phase_a_status": "failed",
            "phase_a_range": {"status": "failed", "sc_low": 9.5},
            "invalidation_hint": "Phase A失败：有效跌破 SC 低点",
            "summary_oneline": "Phase A失败，等待新结构",
        }
    )
    plan["daily_view"]["event_detail"] = {"sc": {"id": "sc", "price": 9.5, "reason": "SC"}}
    return plan


def _failed_plus_sos_plan() -> dict:
    plan = _failed_phase_a_plan()
    plan["daily_raw"]["sos_signal"] = True
    plan["daily_raw"]["sos_price"] = 11.2
    plan["daily_view"]["active_events"] = ["sc", "sos"]
    plan["daily_view"]["event_detail"]["sos"] = {"id": "sos", "price": 11.2}
    return plan


def _failed_plus_lps_plan() -> dict:
    plan = _failed_phase_a_plan()
    plan["daily_raw"]["lps_signal"] = True
    plan["daily_raw"]["lps_price"] = 10.1
    plan["daily_view"]["active_events"] = ["sc", "lps"]
    plan["daily_view"]["event_detail"]["lps"] = {"id": "lps", "price": 10.1}
    return plan


def _weekly_are_without_bc_plan() -> dict:
    plan = _sample_plan()
    plan["weekly_view"]["active_events"] = ["are"]
    plan["weekly_view"]["bias"] = "bear"
    plan["weekly_view"]["event_detail"] = {"are": {"id": "are", "price": 31.78}}
    plan["weekly_raw"] = {
        "are_signal": True,
        "are_price": 31.78,
        "bc_signal": False,
    }
    return plan


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
    assert "威科夫详析" in out or "数据不足" in out


def test_main_exits_0_when_card_ok(monkeypatch, capsys, tmp_path):
    from trader_shared import wyckoff_run as wr

    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    monkeypatch.setattr(wr, "build_wyckoff_plan", lambda target: _sample_plan())
    code = wr.main(["--target", "测试股"])
    assert code == 0
    out = capsys.readouterr().out
    assert "测试股（600000）｜现价 10.50" in out
    assert "威科夫详析" not in out


# ── S-B1..S-B13（默认 slim-B）────────────────────────────────


def test_sb1_default_slim_skeleton_no_long_blocks():
    """S-B1/S-B4/S-B13/S-B17/S-B20/S-B21：默认 B 新骨架。"""
    text = render_wyckoff_slim(_sample_plan())
    lines = text.splitlines()
    assert lines[:4] == [
        "测试股（600000）｜现价 10.50",
        "周线：偏多｜SC后反弹，雏形 8.00～12.00（待 ST）｜慎做",
        "日线本波：Phase C · 试盘｜LPS 修复｜箱体 9.50～11.00",
        "入池：建议入池（日线已见 LPS/SOS，周线非偏空）",
    ]
    assert "🧭 周线 · 大阶段" in text
    assert "⚡ 日线 · 本波" in text
    assert "🔮 推演" in text
    assert "\n  现在\n" in text
    assert "\n    周线：" in text
    assert "\n    日线：" in text
    assert "\n    周线量度：" in text
    assert "\n    日线量度：" in text
    assert "\n  若变好\n" in text
    assert "\n  若变坏\n" in text
    assert "\n  ⭐ 盯\n" in text
    assert "    本卡不下单；出手/分道看 trader" in text
    assert "威科夫 —" not in text
    assert "威科夫详析 —" not in text
    assert "日+周" not in lines[0]
    assert "📊 现况" not in text
    assert "🔮 故事链" not in text
    assert "💬 综述" not in text
    assert "说明：本卡不下单；买卖看 trader 门禁" not in text
    for bad in ("舞台", "换幕", "当前幕", "上一幕"):
        assert bad not in text


def test_sb17_failed_slim_story_no_healthy_advance():
    """S-B17：短推演保留；failed 不得健康还差/链可推进。"""
    text = render_wyckoff_slim(_failed_phase_a_plan())
    assert "日线本波：Phase A 失效｜须重新寻底" in text
    story = text.split("🔮 推演", 1)[1]
    assert "\n  现在\n" in story
    assert "\n  若变好\n" in story
    assert "\n  若变坏\n" in story
    assert "\n  ⭐ 盯\n" in story
    assert "Phase A 失效｜须重新寻底" in story
    assert "还差" not in story
    assert "链可推进" not in story
    assert "SC→SOS（Phase A 已失效）" not in story


def test_sb1_cli_default_uses_slim(monkeypatch, capsys, tmp_path):
    """S-B1：CLI --target 默认输出 slim-B。"""
    from trader_shared import wyckoff_run as wr

    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    monkeypatch.setattr(wr, "build_wyckoff_plan", lambda target: _sample_plan())
    code = wr.main(["--target", "测试股"])
    assert code == 0
    out = capsys.readouterr().out
    assert out.startswith("测试股（600000）｜现价 10.50")
    assert "威科夫详析 —" not in out
    assert "威科夫 —" not in out
    assert "📊 现况" not in out


def test_sb2_full_cli_keeps_legacy_detail(monkeypatch, capsys, tmp_path):
    """S-B2：--full 仍输出旧完整详析。"""
    from trader_shared import wyckoff_run as wr

    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    monkeypatch.setattr(wr, "build_wyckoff_plan", lambda target: _sample_plan())
    code = wr.main(["--target", "测试股", "--full"])
    assert code == 0
    out = capsys.readouterr().out
    assert out.startswith("威科夫详析 — 测试股（600000）｜日线+周线")
    assert "📊 现况" in out
    assert "🔮 故事链" in out
    assert "💬 综述" in out


def test_sb2_brief_full_conflict_reports_argparse_error():
    """S-B2：--brief / --full 不可同时使用。"""
    from trader_shared import wyckoff_run as wr

    with pytest.raises(SystemExit) as exc:
        wr.parse_args(["--target", "测试股", "--brief", "--full"])
    assert exc.value.code == 2


def test_sb5_change_folded_unless_new_or_gone():
    """S-B5：无新亮/熄灭时省略变化块；有变化时仅短行。"""
    first = _sample_plan()
    first["change_line"] = "首次记录，暂无对比"
    assert "🔔 变化" not in render_wyckoff_slim(first)

    still_only = _sample_plan()
    still_only["change_line"] = "新亮：无｜仍亮：SC（卖力高潮）｜熄灭：无"
    assert "🔔 变化" not in render_wyckoff_slim(still_only)

    changed = _sample_plan()
    changed["change_line"] = "新亮：周AR（自动反弹）｜仍亮：SC（卖力高潮）｜熄灭：日ST（二次测试）"
    text = render_wyckoff_slim(changed)
    assert "🔔 变化" in text
    assert "新亮：周AR（自动反弹）；熄灭：日ST（二次测试）" in text
    assert "仍亮：" not in text


def test_sb6_sb7_slim_lights_vertical_and_one_next_watch():
    """S-B6/S-B7/S-B8/S-B22/S-B26：灯竖排、满灯、带中文释义。"""
    text = render_wyckoff_slim(_sample_plan())
    assert "● SC｜● AR" not in text
    assert "● SC / ● AR" not in text
    weekly_block = text.split("🧭 周线 · 大阶段", 1)[1].split("⚡ 日线 · 本波", 1)[0]
    daily_block = text.split("⚡ 日线 · 本波", 1)[1].split("🔮 推演", 1)[0]
    weekly_lamps = [ln for ln in weekly_block.splitlines() if re.match(r"\s*[●○]\s", ln)]
    daily_lamps = [ln for ln in daily_block.splitlines() if re.match(r"\s*[●○]\s", ln)]
    def _lamp_codes(lines: list[str]) -> list[str]:
        out: list[str] = []
        for ln in lines:
            m = re.search(r"[●○]\s+([A-Za-z]+)", ln)
            assert m is not None
            out.append(m.group(1))
        return out

    assert len(weekly_lamps) == 5
    assert len(daily_lamps) == 5
    assert _lamp_codes(weekly_lamps) == ["SC", "AR", "ST", "LPS", "SOS"]
    assert _lamp_codes(daily_lamps) == ["SC", "AR", "ST", "LPS", "SOS"]
    for ln in weekly_lamps + daily_lamps:
        assert ln.count("●") + ln.count("○") == 1
        if "SC" in ln or "AR" in ln or "ST" in ln or "LPS" in ln or "SOS" in ln:
            assert "（" in ln and "）" in ln
    assert "○ SOS（强势信号）" in daily_block
    assert "○ SOS（强势信号）未亮" not in daily_block
    assert "下一盯" not in weekly_block + daily_block


def test_sb9_failed_slim_resets_next_watch_without_healthy_gap():
    """S-B9/S-B10 / P-C1/P-C2：failed 无强势 → Phase A 失效｜须重新寻底 + 旧SC仅对照。"""
    text = render_wyckoff_slim(_failed_phase_a_plan())
    short_block = text.split("⚡ 日线 · 本波", 1)[1].split("🔮 推演", 1)[0]
    assert "Phase A 失效｜须重新寻底｜旧SC 9.50（仅对照）" in short_block
    assert "雏形" not in short_block  # failed 不得健康雏形
    assert "箱体" not in short_block
    assert "● SC（卖力高潮）9.50" in short_block
    assert "○ AR（自动反弹）" in short_block
    assert "还差" not in text
    assert "链可推进" not in text
    assert "下一盯" not in short_block


def test_sb28_overview_writes_proto_prices_and_failed_anchor_ref():
    """S-B28：总览写出雏形价；failed 写旧SC仅对照，不写健康箱体。"""
    text = render_wyckoff_slim(_sample_plan())
    assert "周线：偏多｜SC后反弹，雏形 8.00～12.00（待 ST）｜慎做" in text
    failed = render_wyckoff_slim(_failed_phase_a_plan())
    daily = failed.split("⚡ 日线 · 本波", 1)[1].split("🔮 推演", 1)[0]
    assert "旧SC 9.50（仅对照）" in daily
    assert "雏形 9.50" not in daily
    assert "箱体 9.50" not in daily


def test_sb18_sb23_failed_plus_sos_keeps_full_lights_and_explains():
    """S-B18/S-B23/S-B24 / P-C3：failed+SOS 写破后强势，SC/SOS 同亮并解释。"""
    plan = _failed_plus_sos_plan()
    plan["weekly_view"]["active_events"] = ["are"]
    plan["weekly_view"]["bias"] = "bear"
    plan["weekly_raw"]["are_signal"] = True
    plan["weekly_raw"]["are_price"] = 12.0
    plan["weekly_raw"]["bc_signal"] = False
    text = render_wyckoff_slim(plan)
    assert "日线本波：Phase A 失效 · 破后强势｜本波 SOS 强" in text
    assert "⚡ 日线 · 本波" in text
    assert "说明：●SC 是旧底事实，●SOS 是本波强势事实；不按顺序推进读。" in text
    assert "SC→SOS（Phase A 已失效）" not in text
    daily = text.split("⚡ 日线 · 本波", 1)[1].split("🔮 推演", 1)[0]
    assert "Phase A 失效 · 破后强势｜本波 SOS 强｜旧SC 9.50（仅对照）" in daily
    assert "● SC（卖力高潮）9.50" in daily
    assert "● SOS（强势信号）11.20" in daily
    for bad in ("日偏空", "换幕", "当前幕", "上一幕"):
        assert bad not in text
    mid = text.split("🧭 周线 · 大阶段", 1)[1].split("⚡ 日线 · 本波", 1)[0]
    assert "○ SC（卖力高潮）" not in mid
    assert "派发未确认" in mid or "中线观望" in mid
    assert "还差" not in text
    assert "链可推进" not in text


def test_pc4_failed_plus_lps_copy():
    """P-C4：failed+LPS → Phase A 失效｜本波 LPS 修复。"""
    text = render_wyckoff_slim(_failed_plus_lps_plan())
    assert "日线本波：Phase A 失效｜本波 LPS 修复" in text
    daily = text.split("⚡ 日线 · 本波", 1)[1].split("🔮 推演", 1)[0]
    assert "Phase A 失效｜本波 LPS 修复" in daily
    assert "说明：旧底事实与本波修复事实并列；不按顺序推进读。" in daily
    assert "还差" not in text
    assert "链可推进" not in text


def test_pc5_pc6_failed_slim_banned_words_and_story_aligns():
    """P-C5/P-C6：默认 B 失败路径禁旧词；推演现在日线与总览同语义。"""
    for plan in (_failed_phase_a_plan(), _failed_plus_sos_plan(), _failed_plus_lps_plan()):
        text = render_wyckoff_slim(plan)
        for bad in ("旧底已废", "废锚", "Phase A failed", "（已废）", "待新寻底"):
            assert bad not in text
        overview = next(ln for ln in text.splitlines() if ln.startswith("日线本波："))
        wave = overview.split("日线本波：", 1)[1]
        story_now = text.split("🔮 推演", 1)[1].split("若变好", 1)[0]
        assert f"日线：{wave}" in story_now

    sample = render_wyckoff_slim(_sample_plan())
    worse = sample.split("若变坏", 1)[1].split("⭐ 盯", 1)[0]
    assert "作废" not in worse
    assert "雏形不成立" in worse or "结构不成立" in worse
    assert "有效" not in next(ln for ln in sample.splitlines() if ln.startswith("日线本波："))


def test_sb19_weekly_are_without_bc_no_accum_sc_next():
    """S-B19/S-B22/S-B24：周线 ARE 无 BC 用派发满灯，不能接吸筹 SC。"""
    plan = _weekly_are_without_bc_plan()
    text = render_wyckoff_slim(plan)
    assert "周线：偏空｜ARE 先亮但缺 BC，派发未确认｜先别做" in text
    mid = text.split("🧭 周线 · 大阶段", 1)[1].split("⚡ 日线 · 本波", 1)[0]
    assert "○ BC（购买高潮）" in mid
    assert "● ARE（自动回落）31.78" in mid
    assert "○ SOW（弱势信号）" in mid
    assert "○ LPSY（最后供应点）" in mid
    assert "○ UTAD（派发后上冲）" in mid
    assert "○ SC（卖力高潮）" not in mid
    assert "派发未确认" in mid


def test_sb11_l0_slim_does_not_show_percentile_box_numbers():
    """S-B11：L0 不展示分位上下沿当箱体/雏形。"""
    text = render_wyckoff_slim(_l0_percentile_plan())
    mid_short = text.split("🧭 周线 · 大阶段", 1)[1].split("🔮 推演", 1)[0]
    for forbidden in ("41.23", "58.77", "40.00", "60.00"):
        assert forbidden not in mid_short
    assert "无箱｜未达 L3" in mid_short
    assert "雏形 41.23" not in mid_short
    assert "箱体 41.23" not in mid_short


def test_sb27_story_measure_l3_gate():
    """S-B27：推演量度仅 L3；未达写暂不测算，禁止假目标。"""
    text = render_wyckoff_slim(_sample_plan())
    story = text.split("🔮 推演", 1)[1].split("若变好", 1)[0]
    assert "周线量度：未达 L3，暂不测算" in story
    assert "日线量度：未达 L3，暂不测算" in story
    assert "量度目标" not in story

    # 残留目标 + measure_allowed=False → 仍不得展示
    dirty = copy.deepcopy(_sample_plan())
    dirty["daily_raw"]["cause_effect_up_target"] = 99.0
    dirty["daily_raw"]["cause_effect_down_target"] = 1.0
    dirty["daily_raw"]["measure_allowed"] = False
    dirty["daily_view"]["measure_allowed"] = False
    dirty["daily_view"]["cause_effect"] = {
        "up_target": 99.0,
        "down_target": 1.0,
        "measure_allowed": False,
    }
    dirty_story = render_wyckoff_slim(dirty).split("🔮 推演", 1)[1].split("若变好", 1)[0]
    assert "99.00" not in dirty_story
    assert "量度目标" not in dirty_story
    assert "日线量度：未达 L3，暂不测算" in dirty_story

    # L3 + 上下目标 → 日线量度出数字
    p3 = copy.deepcopy(_sample_plan())
    p3["daily_raw"]["tr_maturity"] = "L3"
    p3["daily_raw"]["measure_allowed"] = True
    p3["daily_raw"]["cause_effect_up_target"] = 15.0
    p3["daily_raw"]["cause_effect_down_target"] = 8.0
    p3["daily_raw"]["pnf_method"] = "horizontal"
    p3["daily_view"]["tr_maturity"] = "L3"
    p3["daily_view"]["measure_allowed"] = True
    p3["daily_view"]["box_display_mode"] = "box"
    p3["daily_view"]["cause_effect"] = {
        "up_target": 15.0,
        "down_target": 8.0,
        "pnf_method": "horizontal",
        "measure_allowed": True,
        "tr_maturity": "L3",
    }
    t3 = render_wyckoff_slim(p3)
    story3 = t3.split("🔮 推演", 1)[1].split("若变好", 1)[0]
    assert "周线量度：未达 L3，暂不测算" in story3
    assert "日线量度：量度目标：上 15.00｜下 8.00（P&F，非出手）" in story3


# ── W-D1..W-D9（旧完整详析，--full）───────────────────────────


def test_wd1_detail_default_skeleton():
    """W-D1：详析含 现况/变化/中线/短线/故事链/综述。"""
    text = render_wyckoff_detail(_sample_plan())
    assert text.startswith("威科夫详析 — 测试股（600000）｜日线+周线")
    assert "📊 现况" in text
    assert "🔔 变化" in text
    assert "🧭 中线（周线 · 入池看这里）" in text
    assert "⚡ 短线（日线 · 盯触发看这里）" in text
    assert "🔮 故事链（以日线推进；周线作背景）" in text
    assert "⭐ 盯" in text
    assert "💬 综述" in text
    assert "#" not in text
    assert "**" not in text
    assert "---" not in text
    assert "|" not in text


def test_wd2_brief_old_card(monkeypatch, capsys, tmp_path):
    """W-D2：--brief 仍为旧短卡骨架。"""
    from trader_shared import wyckoff_run as wr

    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    monkeypatch.setattr(wr, "build_wyckoff_plan", lambda target: _sample_plan())
    code = wr.main(["--target", "测试股", "--brief"])
    assert code == 0
    out = capsys.readouterr().out
    assert out.startswith("威科夫 — 测试股（600000）")
    assert "威科夫详析" not in out
    assert "📎 链：" in out
    assert "📐 TR：" in out


def test_wd3_l0_percentile_no_box_numbers_on_range():
    """W-D3：L0+percentile 区间不得出现分位上下沿数字当箱/雏形。"""
    plan = _l0_percentile_plan()
    text = render_wyckoff_detail(plan)
    # 抓「区间：」行
    range_lines = [ln for ln in text.splitlines() if "区间：" in ln]
    assert range_lines
    for ln in range_lines:
        assert "41.23" not in ln
        assert "58.77" not in ln
        assert "40.00" not in ln and "40.0" not in ln
        assert "60.00" not in ln and "60.0" not in ln
        assert "箱体" not in ln
        assert "雏形" not in ln or "无雏形" in ln
        assert "无成熟箱" in ln or "无雏形" in ln
    # 失效也不得用分位沿冒充箱沿
    inv_lines = [ln for ln in text.splitlines() if "失效：" in ln]
    for ln in inv_lines:
        assert "41.23" not in ln
        assert "40.00" not in ln


def test_wd4_l1_proto_l2_box_l3_measure_only():
    """W-D4：L1 雏形；L2/L3 箱体；量度仅 L3。"""
    # L1
    p1 = _sample_plan()
    p1["daily_raw"]["tr_maturity"] = "L1"
    p1["daily_raw"]["box_display_mode"] = "proto"
    p1["daily_raw"]["measure_allowed"] = False
    p1["daily_raw"]["secondary_test_sc_signal"] = False
    p1["daily_raw"]["st_signal"] = False
    p1["daily_view"]["tr_maturity"] = "L1"
    p1["daily_view"]["box_display_mode"] = "proto"
    p1["daily_view"]["measure_allowed"] = False
    t1 = render_wyckoff_detail(p1)
    short_range = [ln for ln in t1.splitlines() if ln.strip().startswith("区间：")]
    # 短线区间（第二处区间：在 ⚡ 块）
    assert any("雏形" in ln for ln in short_range)
    assert "箱体" not in "\n".join(short_range)
    assert "量度目标" not in t1

    # L2
    p2 = _sample_plan()
    t2 = render_wyckoff_detail(p2)
    assert "箱体" in t2
    assert "量度目标" not in t2
    assert "未达 L3，暂不测算" in t2

    # L3
    p3 = _sample_plan()
    p3["daily_raw"]["tr_maturity"] = "L3"
    p3["daily_raw"]["measure_allowed"] = True
    p3["daily_raw"]["cause_effect_up_target"] = 15.0
    p3["daily_raw"]["cause_effect_down_target"] = 8.0
    p3["daily_raw"]["pnf_method"] = "horizontal"
    p3["daily_view"]["tr_maturity"] = "L3"
    p3["daily_view"]["measure_allowed"] = True
    p3["daily_view"]["box_display_mode"] = "box"
    p3["daily_view"]["cause_effect"] = {
        "up_target": 15.0,
        "down_target": 8.0,
        "pnf_method": "horizontal",
        "measure_allowed": True,
        "tr_maturity": "L3",
    }
    t3 = render_wyckoff_detail(p3)
    assert "箱体" in t3
    assert "量度目标" in t3
    assert "测算已给出" in t3


def test_wd5_lights_bullet_cn_and_price():
    """W-D5：灯 ●/○ 一行一灯；缩写带中文；亮灯价来自 event_detail。"""
    text = render_wyckoff_detail(_sample_plan())
    assert "● SC（卖力高潮）9.50" in text
    assert "● AR（自动反弹）11.00" in text
    assert "● ST（二次测试）9.60" in text
    assert "● LPS（最后支撑点）10.20" in text
    assert "○ SOS（强势信号）未亮" in text
    # 一行一灯：每个 ●/○ 独占一行
    lamp_lines = [ln for ln in text.splitlines() if re.match(r"\s*[●○]\s", ln)]
    assert len(lamp_lines) >= 5
    for ln in lamp_lines:
        assert ln.count("●") + ln.count("○") == 1


def test_wd5_secondary_test_sc_lights_st_without_st_signal():
    """W-D5：详析灯认 secondary_test_sc 为 ST（二次测试）；链槽不进（W-02）。"""
    # 链提取：广义 ST 不进链 ST 槽（phase-a §4.4.2）
    only_st_sc = {
        "sc_signal": True,
        "ar_signal": True,
        "st_signal": False,
        "spring_test_signal": False,
        "secondary_test_sc_signal": True,
        "lps_signal": False,
        "sos_signal": False,
    }
    assert extract_accum_events(only_st_sc) == ["SC", "AR"]

    # 仅 phase 字样、无事件 → 不亮
    phase_only = {
        "phase_label": "二次测试",
        "sc_signal": False,
        "ar_signal": False,
        "st_signal": False,
        "secondary_test_sc_signal": False,
        "spring_test_signal": False,
        "lps_signal": False,
        "sos_signal": False,
    }
    assert extract_accum_events(phase_only) == []

    # 详析：L2 箱 + secondary_test_sc → ST●（二次测试，非 Spring确认）
    plan = _sample_plan()
    plan["daily_raw"]["st_signal"] = False
    plan["daily_raw"]["spring_test_signal"] = False
    plan["daily_raw"]["secondary_test_sc_signal"] = True
    plan["daily_raw"]["lps_signal"] = False
    plan["daily_view"]["active_events"] = ["sc", "ar", "secondary_test_sc"]
    plan["daily_view"]["event_detail"].pop("lps", None)
    text = render_wyckoff_detail(plan)
    assert "● ST（二次测试）9.60" in text
    assert "○ LPS（最后支撑点）未亮" in text


def test_c_f4_c_f5_c_f7_failed_detail_story_resets_phase_a_copy():
    """C-F4/C-F5/C-F7：详析 failed 时若变好/现在收口，灯仍保留 SC。"""
    text = render_wyckoff_detail(_failed_phase_a_plan())
    story = text.split("🔮 故事链（以日线推进；周线作背景）", 1)[1].split("💬 综述", 1)[0]
    better = story.split("若变好", 1)[1].split("若变坏", 1)[0]
    watch = story.split("⭐ 盯", 1)[1].split("入池：", 1)[0]

    assert "现在\n威：SC（Phase A 已失效）" in story
    assert "Phase A 已失效" in better
    assert "重新寻底" in better or "新的 SC" in better
    assert "● SC（卖力高潮）9.50" in text
    assert "链可推进" not in better
    assert "还差" not in story
    assert "盯下一灯" not in watch
    assert "重新寻底" in watch or "新的 SC" in watch


def test_c_f6_failed_short_card_uses_failed_chain_copy():
    """C-F6：短卡链行吃到 failed chain_plain，不保留旧「还差」。"""
    text = render_wyckoff_card(_failed_phase_a_plan())
    assert "📎 链：威：SC（Phase A 已失效）" in text
    assert "还差" not in text


def test_c_f7_view_failed_raw_missing_status_still_closes():
    """C-F7 补洞：仅 daily_view=failed、daily_raw 无 status 时仍不得「还差」。"""
    plan = copy.deepcopy(_sample_plan())
    plan["chain_plain"] = "威：SC，还差AR"
    # raw：有 SC 灯，故意不带 failed
    plan["daily_raw"] = {
        "sc_signal": True,
        "sc_price": 9.5,
        "ar_signal": False,
        "phase_a_status": "established",
        "phase_a_range": {"status": "established", "sc_low": 9.5},
    }
    plan["daily_view"].update(
        {
            "phase_a_status": "failed",
            "phase_a_range": {"status": "failed", "sc_low": 9.5},
            "tr_maturity": "L0",
            "box_display_mode": "none",
            "active_events": ["sc"],
            "event_detail": {"sc": {"id": "sc", "price": 9.5}},
            "summary_oneline": "Phase A失败",
        }
    )
    detail = render_wyckoff_detail(plan)
    card = render_wyckoff_card(plan)
    assert "威：SC（Phase A 已失效）" in detail
    assert "威：SC，还差AR" not in detail
    assert "📎 链：威：SC（Phase A 已失效）" in card
    assert "还差" not in card
    story = detail.split("🔮 故事链", 1)[1]
    assert "链可推进" not in story


def test_wd10_phase_label_on_oneline():
    """W-D10：phase_label 须出现在中线/短线一句话，禁止阶段黑洞。"""
    text = render_wyckoff_detail(_sample_plan())
    # 中线块第一句带周线 phase；短线块带日线 phase
    mid_block = text.split("🧭 中线")[1].split("⚡ 短线")[0]
    short_block = text.split("⚡ 短线")[1].split("🔮 故事链")[0]
    assert "吸筹B" in mid_block
    assert "吸筹C" in short_block
    # 一句话行格式：阶段｜…
    assert any(ln.strip().startswith("一句话：吸筹B｜") for ln in mid_block.splitlines())
    assert any(ln.strip().startswith("一句话：吸筹C｜") for ln in short_block.splitlines())


def test_wd10_extra_lit_events_not_silent():
    """W-D10：引擎已亮的非五灯（PS/Spring/JAC/SV 等）不得静默。"""
    plan = _sample_plan()
    plan["daily_raw"]["ps_signal"] = True
    plan["daily_raw"]["ps_price"] = 9.4
    plan["daily_raw"]["spring_signal"] = True
    plan["daily_raw"]["spring_price"] = 9.55
    plan["daily_raw"]["jac_signal"] = True
    plan["daily_raw"]["jac_price"] = 11.2
    plan["daily_raw"]["stopping_volume_signal"] = True
    plan["daily_raw"]["stopping_volume_price"] = 9.45
    plan["daily_view"]["active_events"] = [
        "ps",
        "sc",
        "ar",
        "secondary_test_sc",
        "spring",
        "lps",
        "jac",
        "stopping_volume",
    ]
    plan["daily_view"]["event_detail"]["ps"] = {"id": "ps", "price": 9.4}
    plan["daily_view"]["event_detail"]["spring"] = {"id": "spring", "price": 9.55}
    plan["daily_view"]["event_detail"]["jac"] = {"id": "jac", "price": 11.2}
    plan["daily_view"]["event_detail"]["stopping_volume"] = {
        "id": "stopping_volume",
        "price": 9.45,
    }
    text = render_wyckoff_detail(plan)
    short_block = text.split("⚡ 短线")[1].split("🔮 故事链")[0]
    assert "● PS（初步止跌）9.40" in short_block
    assert "● Spring（弹簧确认）9.55" in short_block
    assert "● JAC（跳溪）11.20" in short_block
    assert "● SV（止跌量）9.45" in short_block
    # 仍保留默认五灯骨架
    assert "○ SOS（强势信号）未亮" in short_block or "● SOS" in short_block


def test_wd6_no_buy_words():
    """W-D6：无买卖指令词。"""
    text = render_wyckoff_detail(_sample_plan())
    for bad in ("宜买", "可低吸", "可执行", "该买了", "立即买入", "去买"):
        assert bad not in text


def test_wd7_story_prices_whitelist_only():
    """W-D7：故事链价格不出现白名单外数字。"""
    plan = _sample_plan()
    # 注入非白名单噪音价到 summary（不得进故事链主叙事外的瞎造；我们检查故事链段）
    plan["daily_view"]["summary_oneline"] = "吸筹推进"
    text = render_wyckoff_detail(plan)
    # 截取故事链段
    start = text.index("🔮 故事链")
    end = text.index("💬 综述")
    story = text[start:end]
    allowed = {"9.50", "11.00", "9.60", "10.20", "8.00", "12.00", "10.50"}
    # 故事链中出现的 xx.xx 必须在批准源（含现价旁注不应出现在故事；我们未写现价进故事）
    found = set(re.findall(r"\d+\.\d{2}", story))
    assert found <= allowed | {"9.50", "11.00", "9.60", "10.20", "8.00", "12.00"}


def test_wd8_change_first_and_diff(tmp_path, monkeypatch):
    """W-D8：无快照→首次记录；有快照→新亮/熄灭可测。"""
    assert format_light_change(None, {"daily_events": ["SC"], "weekly_events": []}) == (
        "首次记录，暂无对比"
    )
    prev = {
        "daily_events": ["SC", "AR"],
        "weekly_events": ["SC"],
        "daily_prices": {},
        "weekly_prices": {},
    }
    curr = {
        "daily_events": ["SC", "AR", "ST"],
        "weekly_events": [],
        "daily_prices": {"ST": 9.6},
        "weekly_prices": {},
    }
    line = format_light_change(prev, curr)
    assert "新亮：" in line and "ST" in line
    assert "熄灭：" in line and "周SC" in line
    assert "仍亮：" in line and "SC" in line

    # 持久化：run_card 写快照
    from trader_shared import wyckoff_run as wr
    from trader_shared.trader_paths import load_json, path

    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    plan = _sample_plan()
    monkeypatch.setattr(wr, "build_wyckoff_plan", lambda target: dict(plan))
    text, ok = wr.run_card("测试股", brief=False)
    assert ok
    assert text.startswith("测试股（600000）｜现价 10.50")
    assert "🔔 变化" not in text
    store = load_json("wyckoff_light_snapshot")
    assert "600000" in store
    assert path("wyckoff_light_snapshot").name == "wyckoff_light_snapshot.json"

    # 第二次：制造变化（去掉 LPS）
    plan2 = _sample_plan()
    plan2["daily_raw"]["lps_signal"] = False
    plan2["daily_view"]["active_events"] = ["sc", "ar", "secondary_test_sc"]
    plan2["daily_view"]["event_detail"].pop("lps", None)
    plan2["chain_plain"] = "威：SC→AR→ST，还差LPS"
    monkeypatch.setattr(wr, "build_wyckoff_plan", lambda target: dict(plan2))
    text2, ok2 = wr.run_card("测试股", brief=False)
    assert ok2
    assert "🔔 变化" in text2
    assert "熄灭：" in text2
    assert "LPS" in text2


def test_wd9_pool_tiers_no_order():
    """W-D9：入池三档文案出现且无下单句。"""
    # 建议入池：有 LPS + 周线非 bear
    t = render_wyckoff_detail(_sample_plan())
    assert "建议入池" in t
    assert "立即买入" not in t
    assert "本卡不下单" in t

    # 暂不建议：L0 双线
    t0 = render_wyckoff_detail(_l0_percentile_plan())
    assert "暂不建议入池" in t0

    # 结构偏空
    bear = _sample_plan()
    bear["weekly_view"]["bias"] = "bear"
    bear["weekly_view"]["active_events"] = ["bc", "are"]
    bear["weekly_raw"]["bc_signal"] = True
    bear["weekly_raw"]["are_signal"] = True
    tb = render_wyckoff_detail(bear)
    assert "暂不建议入池" in tb
    assert "结构偏空" in tb


def test_build_light_snapshot_entry_shape():
    entry = build_light_snapshot_entry(_sample_plan(), ts="2026-08-01T00:00:00+00:00")
    assert entry["ts"] == "2026-08-01T00:00:00+00:00"
    assert "SC" in entry["daily_events"]
    assert "LPS" in entry["daily_events"]
    assert isinstance(entry["daily_prices"], dict)
    assert isinstance(entry["weekly_events"], list)


def test_wd8_snapshot_includes_extra_lit_for_change():
    """W-D8：非五灯已亮须进快照，才能在 🔔 变化里新亮/熄灭。"""
    plan = _sample_plan()
    plan["daily_raw"]["jac_signal"] = True
    plan["daily_raw"]["jac_price"] = 11.2
    plan["daily_view"]["active_events"] = ["sc", "ar", "secondary_test_sc", "lps", "jac"]
    plan["daily_view"]["event_detail"]["jac"] = {"id": "jac", "price": 11.2}
    entry = build_light_snapshot_entry(plan, ts="2026-08-01T00:00:00+00:00")
    assert "JAC" in entry["daily_events"]
    assert entry["daily_prices"].get("JAC") == 11.2

    prev = {
        "daily_events": ["SC", "AR", "ST", "LPS"],
        "weekly_events": [],
        "daily_prices": {},
        "weekly_prices": {},
    }
    line = format_light_change(prev, entry)
    assert "新亮：" in line and "JAC" in line


def test_trader_paths_wyckoff_light_snapshot(tmp_path, monkeypatch):
    from trader_shared.trader_paths import path

    monkeypatch.setenv("TRADER_ROOT", str(tmp_path))
    assert path("wyckoff_light_snapshot") == tmp_path / "wyckoff_light_snapshot.json"
