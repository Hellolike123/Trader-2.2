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

def attach_short_midline_and_decision(
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

        key_prices = build_key_prices(
            current=current,
            support=float(report.get("support") or 0) or None,
            stop=float(report.get("stop") or 0) or None,
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
        # 场景/融合偏空时强制「不追」，避免 RR 好看但结论打架
        _sc = str(report.get("scene") or scene or "")
        _fa = str((report_fusion or {}).get("action") or "")
        _force_no_chase = any(k in _sc for k in ("冲高", "减仓", "高抛", "暂不碰")) or any(
            k in _fa for k in ("减仓", "空仓", "止损")
        )
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
            _zones_weekly = list(_cmid_inner.get("zones") or [])
            _st_weekly = str(_cmid_inner.get("structure_type") or "")
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
            major_stage=stage_result["major_stage"],
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
            for _n in ("chan", "momentum", "wyckoff"):
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
            "stop": report.get("stop"),
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

        # 只收紧：禁止新开时裁 suggested_pct / 出手语义；R5 同步 position_info
        _disc_action = str(discipline.get("action") or mistery_gate.get("action") or "观望")

        # 中短仲裁：中线偏多时削弱短线的全仓止损
        # 场景：大盘很差→-0.5默认偏斜→"空仓/止损"，但中线周线显示独立积累行情
        # → 降级为"减1/3"，不平掉中线看好的仓位。
        # 结构化触发：读 synthesize_midline_verdict 产出的 midline_bias（bull/bear/neutral），
        # 不再解析阶段行文字，避免换词后静默失效。
        _mid_positive = report.get("midline_bias") == "bull"
        if _mid_positive and _disc_action in ("空仓/止损", "空仓 (大盘很差, 一票否决)"):
            _disc_action = "减1/3 (中线偏多)"
            # 同步收紧到 discipline 输出（下游消费 _disc_action）
            discipline["action"] = _disc_action
            if "notes" not in discipline or not discipline["notes"]:
                discipline["notes"] = "中线偏多，短线不减至空仓，改减1/3"
            else:
                _n = str(discipline["notes"])
                if "中线偏多" not in _n:
                    discipline["notes"] = f"{_n}；中线偏多，短线不减至空仓"
            if "rules_fired" in discipline and isinstance(discipline["rules_fired"], list):
                discipline["rules_fired"].append("mid_bullish_downgrade")

        _disc_cap = discipline.get("suggested_pct_cap")
        if _disc_cap is None:
            _disc_cap = discipline.get("position_cap_pct")
        try:
            _disc_cap_f = float(_disc_cap if _disc_cap is not None else 0)
        except (TypeError, ValueError):
            _disc_cap_f = 0.0
        try:
            _sug = float(report.get("suggested_pct") if report.get("suggested_pct") is not None else suggested or 0)
        except (TypeError, ValueError):
            _sug = float(suggested or 0) if suggested is not None else 0.0
        if not discipline.get("allow_new_entry", True):
            if has_position:
                _final_sug = min(_sug, _disc_cap_f) if _disc_cap_f > 0 else 0
            else:
                _final_sug = 0
            if _final_sug == 0:
                if has_position:
                    report["suggested_pct_context"] = "0%（纪律禁止加仓；持仓按减仓/观察）"
                else:
                    report["suggested_pct_context"] = "0%（纪律不新开）"
        else:
            if _disc_cap_f >= 0 and _sug > _disc_cap_f:
                _final_sug = _disc_cap_f
                report["suggested_pct_context"] = (
                    f"{int(_final_sug) if _final_sug == int(_final_sug) else _final_sug}%（纪律 cap 收紧）"
                )
            else:
                _final_sug = _sug
        if isinstance(_final_sug, float) and _final_sug == int(_final_sug):
            _final_sug = int(_final_sug)
        report["suggested_pct"] = _final_sug
        if isinstance(report.get("position_info"), dict):
            report["position_info"]["suggested_pct"] = _final_sug

        # 买点盖须在结论块之前：失败只收紧 discipline C1，避免结论/清单滞后
        try:
            apply_buy_point_lifecycle(report, mark=_mark)
            discipline = (
                report.get("discipline")
                if isinstance(report.get("discipline"), dict)
                else discipline
            )
            if not discipline.get("allow_new_entry", True):
                _disc_action = str(discipline.get("action") or _disc_action)
                if not has_position:
                    _final_sug = 0
                    report["suggested_pct"] = _final_sug
                    report["suggested_pct_context"] = "0%（纪律不新开）"
                    if isinstance(report.get("position_info"), dict):
                        report["position_info"]["suggested_pct"] = _final_sug
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

                _hint_action = str(
                    _disc.get("action")
                    or (report.get("fusion") or {}).get("action")
                    or ""
                ).strip()
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
            report.setdefault("resonance", {"schema_version": "resonance_v1", "grade": "empty"})
            report.setdefault("buy_point_lifecycle", {"status": "none", "display_line": ""})
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
        _mark("conclusion")

    return report
