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
            # 样例只亮广义 ST；Spring 确认另测（禁止与 ST（SC区回测）并灌）
            "st_signal": False,
            "spring_test_signal": False,
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


def test_a_r3_rank_failed_phase_label_sanitized():
    """A-R3/A-R4：rank 渲染 failed fixture 禁「Phase A失败」类词，含「Phase A 失效」。"""
    text = render_wyckoff_rank(
        [
            {
                "name": "败票",
                "chain_plain": "威：SC（Phase A 失效）",
                "phase_label": "无明确阶段（Phase A 失败，破位未收回）",
            },
            {
                "name": "紧凑",
                "chain_plain": "威：吸筹链未成型",
                "phase_label": "Phase A失败",
            },
        ]
    )
    for bad in ("Phase A失败", "Phase A 失败"):
        assert bad not in text, f"rank leaked {bad!r}"
    assert "Phase A 失效" in text
    assert "Phase A失效" in text
    assert "1. 败票｜威：SC（Phase A 失效）｜无明确阶段（Phase A 失效，破位未收回）" in text
    assert "2. 紧凑｜威：吸筹链未成型｜Phase A失效" in text


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
    """S-B1/S-B4/S-B13/S-B17/S-B20/S-B21：默认 B 新骨架（局/姿态 + 现在变好变差）。"""
    text = render_wyckoff_slim(_sample_plan())
    lines = text.splitlines()
    assert lines[0] == "测试股（600000）｜现价 10.50"
    assert lines[1].startswith("趋势：")
    assert lines[2].startswith("状态：")
    assert any(ln.startswith("动作：") for ln in lines[:8])
    assert "周线：吸筹中｜偏多｜SC后反弹，雏形 8.00～12.00（待SC区回测）" in text
    assert "日线本波：Phase C · 试盘｜LPS 修复｜箱体 9.50～11.00" in text
    assert "入池：建议入池（日线已见 LPS/SOS，周线非偏空）" in text
    assert "🧭 周线 · 吸筹中" in text
    assert "⚡ 日线 · 链推进中" in text
    assert "📌 现在 / 变好 / 变差" in text
    assert "  现在：" in text
    assert "  变好：" in text
    assert "  变差：" in text
    assert "🔮 推演" not in text
    assert "若变好" not in text
    assert "⭐ 盯" not in text
    assert "本卡不下单" not in text
    assert "周线量度：" not in text
    assert "威科夫 —" not in text
    assert "威科夫详析 —" not in text
    assert "日+周" not in lines[0]
    assert "📊 现况" not in text
    assert "🔮 故事链" not in text
    assert "💬 综述" not in text
    for bad in ("舞台", "换幕", "当前幕", "上一幕"):
        assert bad not in text


def test_sb17_failed_slim_story_no_healthy_advance():
    """S-B17：现在/变好/变差保留；failed 不得健康还差/链可推进。"""
    text = render_wyckoff_slim(_failed_phase_a_plan())
    assert "日线本波：Phase A 失效｜本波无新SC" in text
    story = text.split("📌 现在 / 变好 / 变差", 1)[1]
    assert "  现在：" in story
    assert "  变好：" in story
    assert "  变差：" in story
    assert "本波无新SC" in story or "出现本波新SC" in story
    assert "还差" not in story
    assert "链可推进" not in story
    assert "SC→SOS（Phase A 已失效）" not in story
    assert "本卡不下单" not in text


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
    changed["change_line"] = "新亮：周AR（自动反弹）｜仍亮：SC（卖力高潮）｜熄灭：日ST（SC区回测）"
    text = render_wyckoff_slim(changed)
    assert "🔔 变化" in text
    assert "新亮：周AR（自动反弹）；熄灭：日ST（SC区回测）" in text
    assert "仍亮：" not in text


def test_sb6_sb7_slim_lights_vertical_and_one_next_watch():
    """S-B6/S-B7/S-B8/S-B22/S-B26：灯竖排、满灯、带中文释义。"""
    text = render_wyckoff_slim(_sample_plan())
    assert "● SC｜● AR" not in text
    assert "● SC / ● AR" not in text
    weekly_block = text.split("🧭 周线 · ", 1)[1].split("⚡ 日线 · ", 1)[0]
    daily_block = text.split("⚡ 日线 · ", 1)[1].split("📌 现在 / 变好 / 变差", 1)[0]
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
    """S-B9/S-B10 / P-C1/P-C2：failed 无强势 → Phase A 失效｜本波无新SC + 旧SC对照。"""
    text = render_wyckoff_slim(_failed_phase_a_plan())
    short_block = text.split("⚡ 日线 · ", 1)[1].split("📌 现在 / 变好 / 变差", 1)[0]
    assert "Phase A 失效｜本波无新SC｜旧SC 9.50（对照）" in short_block
    assert "雏形" not in short_block  # failed 不得健康雏形
    assert "箱体" not in short_block
    assert "● SC（卖力高潮）9.50" in short_block
    assert "○ AR（自动反弹）" in short_block
    assert "还差" not in text
    assert "链可推进" not in text
    assert "下一盯" not in short_block


def test_sb28_overview_writes_proto_prices_and_failed_anchor_ref():
    """S-B28：总览写出雏形价；failed 写旧SC对照，不写健康箱体。"""
    text = render_wyckoff_slim(_sample_plan())
    assert "周线：吸筹中｜偏多｜SC后反弹，雏形 8.00～12.00（待SC区回测）" in text
    failed = render_wyckoff_slim(_failed_phase_a_plan())
    daily = failed.split("⚡ 日线 · ", 1)[1].split("📌 现在 / 变好 / 变差", 1)[0]
    assert "旧SC 9.50（对照）" in daily
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
    assert "⚡ 日线 · " in text
    assert "说明：●SC 是旧底事实，●SOS 是本波强势事实；不按顺序推进读。" in text
    assert "SC→SOS（Phase A 已失效）" not in text
    daily = text.split("⚡ 日线 · ", 1)[1].split("📌 现在 / 变好 / 变差", 1)[0]
    assert "Phase A 失效 · 破后强势｜本波 SOS 强｜旧SC 9.50（对照）" in daily
    assert "● SC（卖力高潮）9.50" in daily or "● SC（卖力高潮）9.50（对照）" in daily
    assert "● SOS（强势信号）11.20" in daily
    for bad in ("日偏空", "换幕", "当前幕", "上一幕"):
        assert bad not in text
    mid = text.split("🧭 周线 · ", 1)[1].split("⚡ 日线 · ", 1)[0]
    assert "○ SC（卖力高潮）" not in mid
    assert "派发未确认" in mid or "中线观望" in mid
    assert "还差" not in text
    assert "链可推进" not in text


def test_pc4_failed_plus_lps_copy():
    """P-C4：failed+LPS → Phase A 失效｜本波 LPS 修复。"""
    text = render_wyckoff_slim(_failed_plus_lps_plan())
    assert "日线本波：Phase A 失效｜本波 LPS 修复" in text
    daily = text.split("⚡ 日线 · ", 1)[1].split("📌 现在 / 变好 / 变差", 1)[0]
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
        story_now = text.split("📌 现在 / 变好 / 变差", 1)[1].split("  变好：", 1)[0]
        # 现在行 = 姿态｜局面；与日线本波同语义关键词对齐
        assert "  现在：" in story_now
        if "本波无新SC" in wave:
            assert "本波无新SC" in story_now
        elif "破后强势" in wave:
            assert "破后强势" in story_now or "SOS" in text
        elif "LPS 修复" in wave:
            assert "修复" in story_now or "LPS" in text

    sample = render_wyckoff_slim(_sample_plan())
    worse = sample.split("  变差：", 1)[1]
    assert "作废" not in worse
    assert "雏形不成立" in worse or "结构不成立" in worse
    assert "有效" not in next(ln for ln in sample.splitlines() if ln.startswith("日线本波："))


def test_sb19_weekly_are_without_bc_no_accum_sc_next():
    """S-B19/S-B22/S-B24：周线 ARE 无 BC 用派发满灯，不能接吸筹 SC。"""
    plan = _weekly_are_without_bc_plan()
    text = render_wyckoff_slim(plan)
    assert "周线：派发未确认｜偏空｜ARE 先亮但缺 BC，派发未确认" in text
    mid = text.split("🧭 周线 · ", 1)[1].split("⚡ 日线 · ", 1)[0]
    assert "○ BC（买力高潮）" in mid
    assert "● ARE（自动回落）31.78" in mid
    assert "○ SOW（弱势信号）" in mid
    assert "○ LPSY（最后供应点）" in mid
    assert "○ UTAD（派发后上冲）" in mid
    assert "○ SC（卖力高潮）" not in mid
    assert "派发未确认" in mid


def test_weekly_failed_with_are_lamp_writes_phase_a_failed_side():
    """B 卡 #5：周线 phase_a=failed 且有真实派发灯（ARE 无 BC）→
    不得空「派发未确认」盖住失效；须写 Phase A 失效…｜派发侧另察。"""
    plan = _weekly_are_without_bc_plan()
    plan["weekly_raw"].update(
        {
            "phase_a_status": "failed",
            "phase_a_range": {"status": "failed", "sc_low": 30.0},
        }
    )
    plan["weekly_view"].update(
        {
            "phase_a_status": "failed",
            "phase_a_range": {"status": "failed", "sc_low": 30.0},
        }
    )
    text = render_wyckoff_slim(plan)
    mid = text.split("🧭 周线 · ", 1)[1].split("⚡ 日线 · ", 1)[0]
    assert "Phase A 失效" in mid
    assert "派发侧另察" in mid
    # 不得只剩空「派发未确认」盖住失效：失效词须打头
    assert "Phase A 失效" in mid
    assert any(ln.strip().startswith("Phase A 失效") for ln in mid.splitlines())
    # 派发满灯仍保留（ARE 灯事实不灭）
    assert "● ARE（自动回落）31.78" in mid


def test_weekly_failed_without_dist_lamp_writes_phase_a_failed_side():
    """B 卡 #5 对称：周线 failed + 无派发灯（无 BC/ARE/SOW…）→ 直接 Phase A 失效，不写空派发。"""
    plan = _sample_plan()
    plan["weekly_raw"].update(
        {
            "phase_a_status": "failed",
            "phase_a_range": {"status": "failed", "sc_low": 30.0},
            "are_signal": False,
            "bc_signal": False,
        }
    )
    plan["weekly_view"].update(
        {
            "phase_a_status": "failed",
            "phase_a_range": {"status": "failed", "sc_low": 30.0},
            "bias": "bear",
            "active_events": [],
        }
    )
    text = render_wyckoff_slim(plan)
    mid = text.split("🧭 周线 · ", 1)[1].split("⚡ 日线 · ", 1)[0]
    assert "Phase A 失效" in mid
    assert "派发未确认" not in mid


def test_sb11_l0_slim_does_not_show_percentile_box_numbers():
    """S-B11：L0 不展示分位上下沿当箱体/雏形。"""
    text = render_wyckoff_slim(_l0_percentile_plan())
    mid_short = text.split("🧭 周线 · ", 1)[1].split("📌 现在 / 变好 / 变差", 1)[0]
    for forbidden in ("41.23", "58.77", "40.00", "60.00"):
        assert forbidden not in mid_short
    assert "无箱｜未达 L3" in mid_short
    assert "雏形 41.23" not in mid_short
    assert "箱体 41.23" not in mid_short


def test_sb27_story_measure_l3_gate():
    """S-B27：B 卡姿态块不再堆量度行；假目标不得出现在姿态块。"""
    text = render_wyckoff_slim(_sample_plan())
    story = text.split("📌 现在 / 变好 / 变差", 1)[1]
    assert "周线量度：" not in story
    assert "日线量度：" not in story
    assert "量度目标" not in story
    assert "未达 L3" in text

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
    dirty_text = render_wyckoff_slim(dirty)
    dirty_story = dirty_text.split("📌 现在 / 变好 / 变差", 1)[1]
    assert "99.00" not in dirty_story
    assert "量度目标" not in dirty_story

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
    story3 = t3.split("📌 现在 / 变好 / 变差", 1)[1]
    # B 卡姿态块仍不堆量度；L3 目标若展示只允许在周/日结构句，不得进姿态块假目标噪音
    assert "周线量度：" not in story3
    assert "日线量度：" not in story3
    assert "99.00" not in t3  # dirty leftover not relevant; ensure no junk
    # L3 合法目标可出现在日线结构句（若引擎/渲染接入）；姿态块禁止
    assert "  现在：" in story3


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
    assert "📌 现在 / 变好 / 变差" in text or "⭐ 盯" in text
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
    assert "● ST（SC区回测）9.60" in text
    assert "● LPS（最后支撑点）10.20" in text
    assert "○ SOS（强势信号）未亮" in text
    # 一行一灯：每个 ●/○ 独占一行
    lamp_lines = [ln for ln in text.splitlines() if re.match(r"\s*[●○]\s", ln)]
    assert len(lamp_lines) >= 5
    for ln in lamp_lines:
        assert ln.count("●") + ln.count("○") == 1


def test_p0_spring_confirm_not_labeled_as_st_secondary_test():
    """P0：Spring 确认不得渲染成 ST（SC区回测）。

    法源：phase-a §4.4.2 禁止改名；slim-b §4.4 ST=SC区回测 / Spring=弹簧确认；
    tr-maturity：广义 ST 与 spring_test 分离。
    """
    plan = _sample_plan()
    plan["daily_raw"] = {
        "sc_signal": False,
        "ar_signal": False,
        "secondary_test_sc_signal": False,
        "st_signal": True,
        "spring_test_signal": True,
        "spring_test_price": 29.03,
        "st_price": 29.03,
        "lps_signal": False,
        "sos_signal": False,
        "tr_maturity": "L0",
        "box_display_mode": "none",
        "measure_allowed": False,
        "phase_a_status": "none",
    }
    plan["daily_view"] = {
        "phase": "none",
        "phase_label": "无明确阶段",
        "bias": "neutral",
        "tr_maturity": "L0",
        "box_display_mode": "none",
        "measure_allowed": False,
        "active_events": ["spring_test"],
        "event_detail": {
            "spring_test": {"id": "spring_test", "price": 29.03, "reason": "Spring确认"},
        },
        "invalidation_hint": "",
        "summary_oneline": "Spring确认，还差SC",
        "cause_effect": {"up_target": None, "down_target": None},
    }
    plan["chain_plain"] = "威：Spring确认，还差SC"

    slim = render_wyckoff_slim(plan)
    assert "○ ST（SC区回测）" in slim
    assert "● ST（SC区回测）" not in slim
    assert "● Spring（弹簧确认）29.03" in slim
    assert "ST 已现" not in slim
    assert "Spring 确认" in slim
    assert "ST，待 SC" not in slim
    assert ("出现本波新SC" in slim or "本波新SC" in slim)
    assert "Spring 确认" in slim

    detail = render_wyckoff_detail(plan)
    assert "○ ST（SC区回测）未亮" in detail or "○ ST（SC区回测）" in detail
    assert "● ST（SC区回测）" not in detail
    assert "● Spring（弹簧确认）29.03" in detail


def test_wd5_secondary_test_sc_lights_st_without_st_signal():
    """W-D5：详析灯认 secondary_test_sc 为 ST（SC区回测）；链槽不进（W-02）。"""
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
        "phase_label": "SC区回测",
        "sc_signal": False,
        "ar_signal": False,
        "st_signal": False,
        "secondary_test_sc_signal": False,
        "spring_test_signal": False,
        "lps_signal": False,
        "sos_signal": False,
    }
    assert extract_accum_events(phase_only) == []

    # 详析：L2 箱 + secondary_test_sc → ST●（SC区回测，非 Spring确认）
    plan = _sample_plan()
    plan["daily_raw"]["st_signal"] = False
    plan["daily_raw"]["spring_test_signal"] = False
    plan["daily_raw"]["secondary_test_sc_signal"] = True
    plan["daily_raw"]["lps_signal"] = False
    plan["daily_view"]["active_events"] = ["sc", "ar", "secondary_test_sc"]
    plan["daily_view"]["event_detail"].pop("lps", None)
    text = render_wyckoff_detail(plan)
    assert "● ST（SC区回测）9.60" in text
    assert "○ LPS（最后支撑点）未亮" in text


def test_c_f4_c_f5_c_f7_failed_detail_story_resets_phase_a_copy():
    """C-F4/C-F5/C-F7：详析 failed 时若变好/现在收口，灯仍保留 SC。"""
    text = render_wyckoff_detail(_failed_phase_a_plan())
    story = text.split("🔮 故事链（以日线推进；周线作背景）", 1)[1].split("💬 综述", 1)[0]
    better = story.split("若变好", 1)[1].split("若变坏", 1)[0]
    watch = story.split("⭐ 盯", 1)[1].split("入池：", 1)[0]

    assert "现在\n威：SC（Phase A 失效）" in story
    assert "Phase A 失效｜本波无新SC" in better
    assert "本波无新SC" in better or "本波新SC" in better
    assert "Phase A 已失效" not in better
    assert "旧故事作废" not in story
    assert "● SC（卖力高潮）9.50" in text
    assert "链可推进" not in better
    assert "还差" not in story
    assert "盯下一灯" not in watch
    assert "本波新SC" in watch or "本波无新SC" in watch


def test_c_f6_failed_short_card_uses_failed_chain_copy():
    """C-F6：短卡链行吃到 failed chain_plain，不保留旧「还差」。"""
    text = render_wyckoff_card(_failed_phase_a_plan())
    assert "📎 链：威：SC（Phase A 失效）" in text
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
    assert "威：SC（Phase A 失效）" in detail
    assert "威：SC，还差AR" not in detail
    assert "📎 链：威：SC（Phase A 失效）" in card
    assert "还差" not in card
    story = detail.split("🔮 故事链", 1)[1]
    assert "链可推进" not in story


def test_pc10_full_failed_story_uses_invalid_copy():
    """P-C10：--full failed 故事链/综述无「失败/已失效/旧故事作废」，含失效+本波无新SC。"""
    text = render_wyckoff_detail(_failed_phase_a_plan())
    story = text.split("🔮 故事链（以日线推进；周线作背景）", 1)[1]
    summary = text.split("💬 综述", 1)[1]
    visible = story + summary
    for bad in ("Phase A 失败", "Phase A失败", "Phase A 已失效", "旧故事作废"):
        assert bad not in visible
    assert "Phase A 失效" in visible
    assert "本波无新SC" in visible or "本波新SC" in visible
    assert "威：SC（Phase A 失效）" in story
    assert "Phase A 失效｜本波无新SC" in story


def test_pc11_brief_failed_maps_fail_to_invalid():
    """P-C11：--brief failed 阶段/链/事件/一句无「Phase A 失败」主展示；链为失效语义。"""
    text = render_wyckoff_card(_failed_phase_a_plan())
    assert "📎 链：威：SC（Phase A 失效）" in text
    assert "Phase A 失效" in text
    for bad in ("Phase A 失败", "Phase A失败", "Phase A 已失效"):
        assert bad not in text
    assert "🧭 阶段：" in text
    assert "📌 事件：" in text
    assert "💬 一句：" in text
    assert "还差" not in text


def test_pc12_chain_plain_failed_no_yi_shixiao():
    """P-C12：format_wyckoff_chain_plain failed → 威：…（Phase A 失效），无「已失效」。"""
    from trader_shared.wyckoff_chain import format_wyckoff_chain_plain

    out = format_wyckoff_chain_plain(
        {"wyckoff": {"sc_signal": True}, "phase_a_status": "failed"}
    )
    assert out == "威：SC（Phase A 失效）"
    assert "已失效" not in out
    empty = format_wyckoff_chain_plain({"phase_a_range": {"status": "failed"}})
    assert empty == "威：结构失效"
    assert "已失效" not in empty


_CL_FAIL_BANNED = (
    "旧底已废",
    "废锚",
    "Phase A failed",
    "（已废）",
    "待新寻底",
    "Phase A 已失效",
    "Phase A 失败",
    "旧故事作废",
    "换幕",
    "当前幕",
    "上一幕",
    "吸筹幕",
)


def test_cl1_cl2_failed_three_renders_banned_words():
    """C-L1/C-L2：三档 failed 面板禁词；默认 B 仍含 Phase A 失效｜本波无新SC。"""
    for plan in (_failed_phase_a_plan(), _failed_plus_sos_plan(), _failed_plus_lps_plan()):
        for render in (render_wyckoff_slim, render_wyckoff_detail, render_wyckoff_card):
            text = render(plan)
            for bad in _CL_FAIL_BANNED:
                assert bad not in text, f"{render.__name__} leaked {bad!r}"
    slim = render_wyckoff_slim(_failed_phase_a_plan())
    assert "Phase A 失效｜本波无新SC" in slim
    assert "日线本波：Phase A 失效｜本波无新SC" in slim


def test_cl3_dead_helper_fail_copy_no_banned_words():
    """C-L3：残留 helper 产出不含幕类词与「待新寻底/作废」主语义。"""
    from trader_shared import wyckoff_render as wr

    plan = _failed_plus_sos_plan()
    d_view, d_raw = plan["daily_view"], plan["daily_raw"]
    w_view, w_raw = plan["weekly_view"], plan["weekly_raw"]
    blobs = [
        wr._slim_structure_sentence(d_view, d_raw),
        wr._slim_chain_token(d_view, d_raw, failed=True, weekly=False),
        "\n".join(wr._slim_story_lines(
            daily_view=d_view,
            weekly_view=w_view,
            daily_raw=d_raw,
            weekly_raw=w_raw,
        )),
        "\n".join(wr._format_slim_lights(d_view, d_raw, weekly=False)),
        "\n".join(wr._slim_prev_act_lines(d_view, d_raw)),
        wr._primary_light_code(d_raw, d_view),
    ]
    joined = "\n".join(blobs)
    for bad in (
        "待新寻底",
        "换幕",
        "当前幕",
        "上一幕",
        "吸筹幕",
        "作废",
        "旧Phase A已破",
    ):
        assert bad not in joined, f"helper leaked {bad!r}"
    assert "破后强势" in joined
    assert "Phase A 失效" in joined
    assert "本波无新SC" in wr._slim_chain_token(
        _failed_phase_a_plan()["daily_view"],
        _failed_phase_a_plan()["daily_raw"],
        failed=True,
        weekly=False,
    )


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


# ── 渲染前防御 check（accumulation_confirmed ∧ phase_a failed）──────────
# 法源：docs/plans/2026-08-04-agent-suggestions-handoff.md 改动 2


def _contradictory_plan() -> dict:
    """矛盾结果：accumulation_confirmed=True 与 phase_a_range.status=failed 并存。"""
    plan = _failed_phase_a_plan()
    plan["daily_raw"]["accumulation_confirmed"] = True
    return plan


def test_render_warn_contradictory_accum_confirmed_and_phase_a_failed(caplog):
    """改动2 ①：矛盾结果 → caplog 断言 warning 文案。"""
    import logging

    caplog.set_level(logging.WARNING, logger="trader.wyckoff_render")
    render_wyckoff_slim(_contradictory_plan())
    assert any(
        "矛盾字段: accumulation_confirmed=True 与 phase_a_status=failed 并存"
        in record.getMessage()
        for record in caplog.records
    )


def test_render_no_warn_on_normal_result(caplog):
    """改动2 ②：正常结果（accum=False 或 phase_a 非 failed）→ 不告警。"""
    import logging

    caplog.set_level(logging.WARNING, logger="trader.wyckoff_render")
    render_wyckoff_card(_sample_plan())  # phase_a established，无 accumulation_confirmed
    render_wyckoff_slim(_sample_plan())
    render_wyckoff_detail(_failed_phase_a_plan())  # failed 但无 accumulation_confirmed
    assert not any("矛盾字段" in record.getMessage() for record in caplog.records)


def test_render_warn_does_not_change_output():
    """改动2 ③：渲染输出与告警前一致（只告警不改卡）。"""
    contradictory = _contradictory_plan()
    baseline = copy.deepcopy(contradictory)
    baseline["daily_raw"]["accumulation_confirmed"] = False  # 去掉矛盾条件，输出应不变
    for render in (render_wyckoff_card, render_wyckoff_slim, render_wyckoff_detail):
        assert render(contradictory) == render(baseline)


class TestStScNoteS11:
    """ST 双口径修复单（2026-08-05）改动3：ST（SC区回测）未亮 + Spring 确认亮 →
    追加说明行；ST 亮或双未亮 → 无说明行。"""

    def _raw_st(self, st: bool, spring: bool, sc_price: float = 9.5) -> dict:
        return {
            "secondary_test_sc_signal": st,
            "spring_test_signal": spring,
            "sc_signal": True,
            "sc_low": sc_price,
            "ar_signal": True,
            "ar_high": 11.0,
            "phase_a_range": {"status": "established", "sc_low": sc_price, "ar_high": 11.0},
            "tr_upper": 12.0, "tr_lower": 8.0,
        }

    def test_st_off_spring_on_adds_note(self):
        """ST 未亮 + Spring 亮（南网 688248 场景）→ slim 灯含说明行。"""
        from trader_shared.wyckoff_render import (
            _format_daily_lights, _format_slim_full_lights,
        )
        raw = self._raw_st(st=False, spring=True)
        view = {"bias": "bullish", "active_events": ["sc", "ar", "spring_test", "sos"]}
        slim = _format_slim_full_lights(("SC", "AR", "ST", "LPS", "SOS"), view, raw)
        daily = _format_daily_lights(view, raw)
        for lines in (slim, daily):
            assert any("注：ST=SC区回测" in ln for ln in lines), lines
            assert any("○ ST（SC区回测）" in ln for ln in lines), lines
            assert any("● Spring（弹簧确认）" in ln for ln in lines), lines

    def test_st_on_no_note(self):
        """广义 ST 已亮 → ● ST（SC区回测），无说明行。"""
        from trader_shared.wyckoff_render import _format_daily_lights
        raw = self._raw_st(st=True, spring=False)
        view = {"bias": "neutral", "active_events": ["sc", "ar", "secondary_test_sc"]}
        lines = _format_daily_lights(view, raw)
        assert any("● ST（SC区回测）" in ln for ln in lines), lines
        assert not any("注：ST=SC区回测" in ln for ln in lines), lines

    def test_both_off_no_note(self):
        """ST/Spring 双未亮 → 无说明行（全链最弱样本）。"""
        from trader_shared.wyckoff_render import _format_daily_lights
        raw = self._raw_st(st=False, spring=False)
        view = {"bias": "neutral", "active_events": ["sc", "ar"]}
        lines = _format_daily_lights(view, raw)
        assert any("○ ST（SC区回测）" in ln for ln in lines), lines
        assert not any("注：ST=SC区回测" in ln for ln in lines), lines
