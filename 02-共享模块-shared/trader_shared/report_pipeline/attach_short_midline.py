# -*- coding: utf-8 -*-
"""短中线关键价/纪律/结论挂接。"""
from __future__ import annotations

from typing import Any

from trader_shared._logging import get_logger
from trader_shared.report_pipeline._common import MarkFn, _noop_mark
from trader_shared.report_pipeline.attach_buy_point import apply_buy_point_lifecycle
from trader_shared.report_pipeline.attach_decision_stack import (
    attach_analysis_decision_stack,
)

_logger = get_logger(__name__)


def _positive_float(value: Any) -> float | None:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    return val


def _select_key_price_stop(
    report: dict[str, Any],
    *,
    current: float,
    has_position: bool,
) -> float | None:
    """Stop fed into key_prices: empty position uses hard stop only."""
    hard = _positive_float(report.get("stop"))
    if not has_position:
        return hard

    trailing = _positive_float(report.get("trailing_stop"))
    if trailing is not None and current > 0 and trailing < current:
        from trader_shared.structure_core import effective_stop_price

        return effective_stop_price(hard, trailing)
    return hard


def attach_short_midline_and_decision(
    report: dict[str, Any],
    ctx: Any,
    *,
    mark: MarkFn | None = None,
) -> dict[str, Any]:
    """Thin：短中线 + 决策栈；字段从 StageContext 取。"""
    _fusion = ctx.get("report_fusion")
    if not isinstance(_fusion, dict):
        _fusion = report.get("fusion") if isinstance(report.get("fusion"), dict) else {}
    return _attach_short_midline_and_decision_impl(
        report,
        current=float(ctx.get("current") or 0),
        scene=str(ctx.get("scene") or ""),
        report_fusion=_fusion if isinstance(_fusion, dict) else {},
        stage_result=ctx.get("stage_result") if isinstance(ctx.get("stage_result"), dict) else {},
        weekly_bars=ctx.get("weekly_bars") or [],
        suggested=ctx.get("suggested") if ctx.get("suggested") is not None else 0,
        theory_status=str(ctx.get("theory_status") or ""),
        market_env_data=ctx.get("market_env_data") if isinstance(ctx.get("market_env_data"), dict) else {},
        has_position=bool(ctx.get("has_position")),
        data_status=str(ctx.get("data_status") or report.get("data_status") or ""),
        chip_resistance_lower=ctx.get("chip_resistance_lower"),
        chip_resistance_upper=ctx.get("chip_resistance_upper"),
        stage=str(ctx.get("short_term_momentum") or ctx.get("stage") or ""),
        mark=mark,
    )


def _attach_short_midline_and_decision_impl(
    report: dict[str, Any],
    *,
    current: float,
    scene: str,
    report_fusion: dict[str, Any] | None,
    stage_result: dict[str, Any],
    weekly_bars: list | None,
    suggested: float | int,
    theory_status: str,
    market_env_data: dict[str, Any] | None,
    has_position: bool,
    data_status: str,
    chip_resistance_lower: float | None,
    chip_resistance_upper: float | None,
    stage: str,
    mark: MarkFn | None = None,
) -> dict[str, Any]:
    """关键价 + 周框 + 纪律 + 结论 + 买点盖 + 卡/共振/策略/决策。

    从 build_report 整段迁出；失败时写占位字段（与原 except 一致）。
    """
    _mark = mark or _noop_mark
    report_fusion = report_fusion if isinstance(report_fusion, dict) else {}
    market_env_data = market_env_data if isinstance(market_env_data, dict) else {}
    weekly_bars = weekly_bars or []
    stage_result = stage_result if isinstance(stage_result, dict) else {}
    if not isinstance(report, dict):
        return report

    # ── 短中线：关键价 + 纪律门控 + 结论块（只读，不改写 stage/fusion/stop）──
    # weekly_frame 在 mid_key_prices 算出后由 compute_weekly_frame 填充
    report["weekly_frame"] = None
    try:
        from trader_shared.key_prices import build_key_prices
        from trader_shared.mid_key_prices import build_mid_key_prices
        from trader_shared.mistery_gate import compute_mistery_gate
        from trader_shared.conclusion_block import build_conclusion_block, build_daily_ruling
        from trader_shared.config import MISTERY_MIN_RR
        from trader_shared.chan_discipline import (
            apply_chan_discipline,
            merge_discipline,
            compute_weekly_frame,
            compute_pivot_position,
        )

        _ma5 = _ma10 = _ma20 = None
        for _ma_src in (report.get("ma_raw"), report.get("ma"), report.get("mas")):
            if not isinstance(_ma_src, dict):
                continue
            try:
                _ma5 = float(_ma_src.get("ma5") or 0) or None
                _ma10 = float(_ma_src.get("ma10") or 0) or None
                _ma20 = float(_ma_src.get("ma20") or 0) or None
            except (TypeError, ValueError):
                _ma5 = _ma10 = _ma20 = None
            if _ma20:
                break

        # key_prices 不吃空仓 trailing；有仓也只接低于现价的移动止损。
        _key_price_stop = _select_key_price_stop(
            report,
            current=current,
            has_position=has_position,
        )
        key_prices = build_key_prices(
            current=current,
            support=float(report.get("support") or 0) or None,
            stop=_key_price_stop,
            confirm=float(report.get("confirm") or 0) or None,
            resistance=float(report.get("resistance") or 0) or None,
            ma20=_ma20,
            ma10=_ma10,
            ma5=_ma5,
            low_zone_lower=float(report.get("low_zone_lower") or 0) or None,
            low_zone_upper=float(report.get("low_zone_upper") or 0) or None,
            key_levels=report.get("key_levels") or {},
            take=float(report.get("take") or 0) or None,
        )
        # 场景偏空时强制「不追」；fusion.action 仅仪表，不再改 chase
        _sc = str(report.get("scene") or scene or "")
        _force_no_chase = any(k in _sc for k in ("冲高", "减仓", "高抛", "暂不碰"))
        if _force_no_chase and key_prices.get("line_chase"):
            key_prices["chase_ok"] = False
            _lc = str(key_prices["line_chase"])
            if "→" in _lc:
                key_prices["line_chase"] = _lc.split("→")[0].rstrip() + " → 不追"
            else:
                key_prices["line_chase"] = _lc + " → 不追"
        report["key_prices"] = key_prices

        # 中线关键价（独立周线引擎；与短线 key_prices 分轨）
        # 禁止日 K key_levels 作 mid 主参（默认忽略；仅 MIDLINE_PRICE_DAILY_FALLBACK）
        mid_key_prices = build_mid_key_prices(
            current=current,
            weekly_bars=weekly_bars or [],
            chanlun_midline=report.get("chanlun_midline"),
            wyckoff_midline=report.get("wyckoff_midline"),
        )
        report["mid_key_prices"] = mid_key_prices
        _mark("key_prices")

        # R9 weekly_frame + R6 中枢位置（周/日）
        _life = None
        try:
            _life = float(mid_key_prices.get("life_line") or 0) or None
        except (TypeError, ValueError):
            _life = None
        _zones_weekly = []
        _zones_daily = []
        try:
            _cmid = report.get("chanlun_midline") or {}
            if isinstance(_cmid, dict) and "chanlun" in _cmid:
                _cmid_inner = _cmid.get("chanlun") or {}
            else:
                _cmid_inner = _cmid if isinstance(_cmid, dict) else {}
            # A3 / BUSINESS §2.0：仅真周线缠论 zones 可进 weekly_frame / pivot_position_weekly；
            # daily_fallback 与 mid_key_prices 同构——不得冒充周中枢。
            _cmid_tf = str((_cmid_inner or {}).get("timeframe") or "").strip()
            if _cmid_tf == "weekly":
                _zones_weekly = list(_cmid_inner.get("zones") or [])
                _st_weekly = str(_cmid_inner.get("structure_type") or "")
            else:
                _zones_weekly = []
                _st_weekly = ""
        except Exception:
            _st_weekly = ""
            _zones_weekly = []
        try:
            _cday0 = report.get("chanlun") or report.get("chan") or {}
            if isinstance(_cday0, dict) and "chanlun" in _cday0:
                _cday_inner0 = _cday0.get("chanlun") or {}
            else:
                _cday_inner0 = _cday0 if isinstance(_cday0, dict) else {}
            _zones_daily = list(_cday_inner0.get("zones") or [])
            _st_daily = str(
                _cday_inner0.get("structure_type")
                or report.get("chan_structure_type")
                or ""
            )
        except Exception:
            _st_daily = str(report.get("chan_structure_type") or "")
            _zones_daily = []
        _zh_bottom_w = None
        for _z in reversed(_zones_weekly):
            if isinstance(_z, dict) and _z.get("valid") is not False:
                try:
                    _zb = float(_z.get("zh_bottom") or 0) or None
                except (TypeError, ValueError):
                    _zb = None
                if _zb:
                    _zh_bottom_w = _zb
                    break
        report["weekly_frame"] = compute_weekly_frame(
            current, _life, zh_bottom=_zh_bottom_w, zones=_zones_weekly,
            weekly_bars=weekly_bars or [],
        )
        report["pivot_position_weekly"] = compute_pivot_position(current, _zones_weekly)
        report["pivot_position_daily"] = compute_pivot_position(current, _zones_daily)

        _regime = ""
        if isinstance(market_env_data, dict):
            _regime = str(market_env_data.get("level") or "")
        if not _regime:
            _regime = str((report_fusion or {}).get("regime") or "")

        # 中线看法文案（与 conclusion 同源）供纪律：偏空则禁止以短线买点主开仓
        from trader_shared.conclusion_block import _midline_view_from_theory, synthesize_midline_verdict
        _mid_view_txt = _midline_view_from_theory(
            chanlun_midline=report.get("chanlun_midline"),
            wyckoff_midline=report.get("wyckoff_midline"),
            weekly_frame=report.get("weekly_frame"),
        )
        # 中线定论：威科夫中线 + 缠论中线 各自独立判定后合成（L586 的 position 分类作兜底）
        _midline_verdict = synthesize_midline_verdict(
            report.get("chanlun_midline"),
            report.get("wyckoff_midline"),
            fallback_stage=stage,
        )
        report["midline_verdict"] = _midline_verdict
        report["midline_stage"] = _midline_verdict["stage"]
        report["midline_bias"] = _midline_verdict["bias"]
        _chan_u = report.get("chanlun_midline") or {}
        if isinstance(_chan_u, dict) and "chanlun" in _chan_u:
            _chan_inner = _chan_u.get("chanlun") or {}
        else:
            _chan_inner = _chan_u if isinstance(_chan_u, dict) else {}
        _mid_struct_conf = str(
            (_chan_inner or {}).get("structure_confidence")
            or (report.get("chanlun_midline") or {}).get("structure_confidence")
            or ""
        )
        _cm = report.get("chip_migration") if isinstance(report.get("chip_migration"), dict) else {}
        _chip_warn = str(_cm.get("warning_level") or "") not in ("", "none", "None")
        _fund_veto = bool((report_fusion or {}).get("fund_flow_outflow_veto"))
        try:
            _fusion_dis = (report_fusion or {}).get("disagreement")
            _fusion_dis = int(_fusion_dis) if _fusion_dis is not None else 0
        except (TypeError, ValueError):
            _fusion_dis = 0
        # 专家 conf 均值
        _fconf = None
        try:
            _sd = (report_fusion or {}).get("signals_detail") or {}
            _cs = []
            # 法源 BUSINESS.md §2.4：短线第三席 = VPF（非日线威科夫 stub）
            for _n in ("chan", "momentum", "vpf"):
                _s = _sd.get(_n) if isinstance(_sd.get(_n), dict) else {}
                if _s.get("confidence") is not None:
                    _cs.append(float(_s["confidence"]))
            if _cs:
                _fconf = sum(_cs) / len(_cs)
        except (TypeError, ValueError):
            _fconf = None

        # 通用门控（瘦身：无回踩/mid_view/筹码缠侧规则；weekly_frame 破坏由 chan 主裁）
        mistery_gate = compute_mistery_gate({
            "major_stage": stage_result["major_stage"],
            "short_term_momentum": stage_result["momentum"],
            "theory_status": theory_status,
            "scene": str(report.get("scene") or scene),
            "regime": _regime,
            "current": current,
            "support": report.get("support"),
            "stop": _eff_stop if _eff_stop is not None else report.get("stop"),
            "confirm": report.get("confirm"),
            "suggested_pct": suggested,
            "ma20": _ma20,
            "buy_ref": key_prices.get("buy_ref"),
            "risk": key_prices.get("risk"),
            "reward_near": key_prices.get("reward_near"),
            "turnover_rate": report.get("turnover_rate"),
            "volume_ratio": report.get("volume_ratio"),
            "change_pct": report.get("change_pct"),
            "min_rr": MISTERY_MIN_RR,
            "weekly_frame": report.get("weekly_frame"),
            "data_status": report.get("data_status") or data_status,
            "fusion_disagreement": _fusion_dis,
            "fusion_confidence": _fconf,
        })
        report["mistery_gate"] = mistery_gate

        # 日线买点类型（若有）供缠纪律冲突 notes
        _buy_point_types = []
        try:
            _chan_day = report.get("chanlun") or report.get("chan") or {}
            if isinstance(_chan_day, dict) and "chanlun" in _chan_day:
                _chan_day = _chan_day.get("chanlun") or {}
            for _bp in (_chan_day.get("buy_points") or []):
                if isinstance(_bp, dict) and _bp.get("type"):
                    _buy_point_types.append(str(_bp["type"]))
        except Exception:
            _buy_point_types = []

        chan_d = apply_chan_discipline({
            "current": current,
            "mid_pullback_low": mid_key_prices.get("pullback_low"),
            "mid_pullback_high": mid_key_prices.get("pullback_high"),
            "mid_view": _mid_view_txt,
            "mid_quality": mid_key_prices.get("quality"),
            "structure_confidence": _mid_struct_conf,
            "buy_point_types": _buy_point_types,
            "structure_type_daily": _st_daily,
            "structure_type_weekly": _st_weekly,
            "low_zone_lower": report.get("low_zone_lower"),
            "low_zone_upper": report.get("low_zone_upper"),
            "life_line": _life,
            "zh_bottom": _zh_bottom_w,
            "zones": _zones_weekly,
            "weekly_frame": report.get("weekly_frame"),
            "data_status": report.get("data_status") or data_status,
            "fusion_disagreement": _fusion_dis,
            "fusion_confidence": _fconf,
            "major_stage": stage_result["major_stage"],
            "chip_migration_warning": _chip_warn,
            "fund_flow_outflow_veto": _fund_veto,
            "has_position": has_position,
            "suggested_pct": suggested,
            "max_position_pct": 50,
            "chip_resistance_lower": chip_resistance_lower,
            "chip_resistance_upper": chip_resistance_upper,
        })
        report["chan_discipline"] = chan_d

        discipline = merge_discipline(mistery_gate, chan_d, max_position_pct=50)
        report["discipline"] = discipline
        _mark("discipline")

        # NOTE: 箱体(box_detect) / 组合共振(combo_strategy) 作为独立可测模块保留，
        #       暂不接入本报告渲染。用户决策：箱体优先做独立模块，先不进报告；
        #       组合报告亦暂缓。模块与单测保留，后续如需在报告呈现再接回。

        # 出手语义：纪律 action（caps/suggested_pct 统一由 decision_view 后 apply_execution_caps 收口）
        _disc_action = str(discipline.get("action") or mistery_gate.get("action") or "观望")
        _disc_cap = discipline.get("suggested_pct_cap")
        if _disc_cap is None:
            _disc_cap = discipline.get("position_cap_pct")
        try:
            _disc_cap_f = float(_disc_cap if _disc_cap is not None else 0)
        except (TypeError, ValueError):
            _disc_cap_f = 0.0

        # 买点盖须在结论块之前：失败只收紧 discipline C1；caps 同步留给 decision stack
        try:
            apply_buy_point_lifecycle(report, mark=_mark)
            discipline = (
                report.get("discipline")
                if isinstance(report.get("discipline"), dict)
                else discipline
            )
            if not discipline.get("allow_new_entry", True):
                _disc_action = str(discipline.get("action") or _disc_action)
        except Exception as _bp_exc:
            _logger.debug("buy_point_lifecycle pre-conclusion: %s", _bp_exc)

        daily_ruling = build_daily_ruling(
            report_fusion,
            scene=str(report.get("scene") or scene),
            theory_status=theory_status,
            chase_ok=bool(key_prices.get("chase_ok")),
            gate_action=_disc_action,
        )
        # 结论块：优先读 merge 后的 discipline（兼容仍传 mistery_gate 字段）
        _gate_for_conclusion = dict(mistery_gate)
        _gate_for_conclusion["action"] = _disc_action
        _gate_for_conclusion["position_cap_pct"] = _disc_cap_f
        _gate_for_conclusion["notes"] = discipline.get("notes") or mistery_gate.get("notes") or ""
        _gate_for_conclusion["hard_block"] = discipline.get("hard_block") or mistery_gate.get("hard_block")
        _gate_for_conclusion["invalidation"] = discipline.get("invalidation") or mistery_gate.get("invalidation")

        conclusion = build_conclusion_block(
            major_stage=stage_result["major_stage"],
            short_term_momentum=stage_result["momentum"],
            scene=str(report.get("scene") or scene),
            theory_status=theory_status,
            regime=_regime,
            mistery_gate=_gate_for_conclusion,
            discipline=discipline,
            key_prices=key_prices,
            fusion=report_fusion,
            has_position=has_position,
            daily_ruling=daily_ruling,
            weekly_frame=report.get("weekly_frame"),
            chanlun_midline=report.get("chanlun_midline"),
            wyckoff_midline=report.get("wyckoff_midline"),
            chanlun_daily=report.get("chanlun_daily"),
            current_price=current,
            chip_migration=report.get("chip_migration"),
            chip_migration_warning=_chip_warn,
            fund_flow_outflow_veto=_fund_veto,
        )
        report["conclusion"] = conclusion
        report["daily_ruling"] = daily_ruling
        # 中线定论：把合成阶段写入阶段行（覆盖 build_conclusion_block 的兜底），
        # 并附双源合成注记（report_core 渲染为「定论：」行）。
        conclusion["stage_line"] = _midline_verdict["stage"]
        conclusion["midline_verdict_note"] = _midline_verdict["note"]
        _mark("conclusion")

        # pipeline：卡/共振/策略/决策（买点盖已在结论前执行）
        try:
            attach_analysis_decision_stack(report, mark=_mark)
            # 日线裁定重算：出手听 decision_view/纪律/共振，fusion 仅偏多偏空仪表
            _dv = report.get("decision_view") if isinstance(report.get("decision_view"), dict) else {}
            _res = report.get("resonance") if isinstance(report.get("resonance"), dict) else {}
            _disc = report.get("discipline") if isinstance(report.get("discipline"), dict) else {}
            daily_ruling = build_daily_ruling(
                report.get("fusion") if isinstance(report.get("fusion"), dict) else report_fusion,
                scene=str(report.get("scene") or scene),
                theory_status=theory_status,
                chase_ok=bool(key_prices.get("chase_ok")),
                gate_action=str(_disc.get("action") or _disc_action or ""),
                decision_view=_dv,
                resonance=_res,
            )
            report["daily_ruling"] = daily_ruling
            _conc = report.get("conclusion") if isinstance(report.get("conclusion"), dict) else None
            if _conc is not None:
                _conc["daily_ruling"] = daily_ruling
            try:
                from trader_shared.stage_positioning import action_for_holding_state

                # 持仓提示只听纪律/DV，不回退 fusion.action
                _hint_action = str(_disc.get("action") or "").strip()
                _hs = action_for_holding_state(_hint_action, bool(report.get("has_position")))
                report["fusion_holding_hint"] = _hs.get(
                    "holding_hint", report.get("fusion_holding_hint", "待定")
                )
            except Exception:
                pass
            _mark("daily_ruling_dv")
        except Exception as _pipe_exc:
            _logger.debug("report_pipeline skip: %s", _pipe_exc)
            report.setdefault("analysis_cards", {})
            try:
                from trader_shared.resonance import ensure_pullback_resonance_placeholder

                ensure_pullback_resonance_placeholder(report)
            except Exception:
                # 与 ensure_pullback_resonance_placeholder 同形，避免异源/残缺 schema
                report["resonance"] = {
                    "schema_version": "resonance_v1",
                    "scene": "pullback_probe",
                    "grade": "empty",
                    "posts": {
                        "background": {"ok": False, "note": "跳过"},
                        "structure": {"ok": False, "note": "跳过"},
                        "chip": {"ok": False, "note": "跳过"},
                        "momentum": {"ok": False, "note": "跳过"},
                    },
                    "missing": ["background", "structure", "chip", "momentum"],
                    "conflict": False,
                    "summary_line": "共振：跳过",
                }
            report.setdefault("buy_point_lifecycle", {"status": "none", "display_line": ""})
            # 栈后异常：仍 fail-closed DV + 单一 caps 出口（防 suggested_pct 残留）
            report["decision_view"] = {
                "schema_version": "decision_view_v1",
                "allow_new_recommend": False,
                "summary_line": f"决策：管道失败·不新开（{_pipe_exc}）",
            }
            try:
                from trader_shared.decision_view import apply_execution_caps

                apply_execution_caps(report)
            except Exception:
                pass
    except Exception as _sm_exc:
        # 短中线组装失败不阻断主报告；保留原字段
        report.setdefault("key_prices", {})
        report.setdefault("mid_key_prices", {})
        report.setdefault("mistery_gate", {
            "hard_block": "none", "style": "不明", "action": "观望",
            "invalidation": "", "position_cap_pct": 0.0, "notes": f"gate_error:{_sm_exc}",
        })
        report.setdefault("chan_discipline", {
            "allow_new_entry": False, "entry_block_reason": f"gate_error:{_sm_exc}",
            "suggested_pct_cap": 0, "action_override": "观望",
            "discipline_notes": [], "rules_fired": [],
        })
        report.setdefault("discipline", {
            "allow_new_entry": False, "action": "观望", "suggested_pct_cap": 0,
            "position_cap_pct": 0.0, "entry_block_reason": f"gate_error:{_sm_exc}",
            "discipline_notes": [], "notes": f"gate_error:{_sm_exc}",
            "hard_block": "none", "invalidation": "",
        })
        report.setdefault("conclusion", {
            "midline": "数据组装异常", "stage_line": "", "shortline": "观察",
            "execution": "现价不买 · 不追", "reason": "门控组装失败",
            "this_week": "观察", "conflict": "", "daily_ruling": "中性，观望",
        })
        try:
            from trader_shared.analysis_cards import ensure_report_analysis_cards
            ensure_report_analysis_cards(report)
        except Exception:
            report.setdefault("analysis_cards", {})
        # fail-closed DV + 单一 caps 出口（清零 stage_pack 残留 suggested_pct）
        report["decision_view"] = {
            "schema_version": "decision_view_v1",
            "allow_new_recommend": False,
            "summary_line": f"决策：短中线失败·不新开（{_sm_exc}）",
        }
        try:
            from trader_shared.decision_view import apply_execution_caps

            apply_execution_caps(report)
        except Exception:
            pass
        _mark("conclusion")

    return report
