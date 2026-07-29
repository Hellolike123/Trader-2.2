# -*- coding: utf-8 -*-
"""单票报告阶段函数（从 build_report 抽出，行为不变）。

分支：refactor/build-report-pipeline — 持续把总管拆成可调度阶段。
编排只排队；禁止写加权公式/缠威检测实现。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

_logger = logging.getLogger(__name__)

MarkFn = Callable[[str], None]


def _noop_mark(_label: str) -> None:
    return None


def detect_risk_flags(
    stock_name: str,
    quote: dict[str, Any] | None,
    bars: list | None,
) -> list[str]:
    """ST / 停牌 / 新股 风险旗（自 build_report 迁出，行为不变）。"""
    from trader_shared.light_data import to_float

    quote = quote if isinstance(quote, dict) else {}
    bars = bars or []
    risk_flags: list[str] = []
    name = str(stock_name or quote.get("name") or "")
    if "ST" in name or "*ST" in name:
        risk_flags.append("ST")
    cp = to_float(quote.get("current_price"))
    pc = to_float(quote.get("pre_close"))
    vol = to_float(quote.get("volume"))
    is_suspended = (
        cp is not None
        and pc is not None
        and vol is not None
        and cp > 0
        and abs(cp - pc) < 1e-6
        and vol < 1
    )
    if is_suspended:
        risk_flags.append("停牌")
    if len(bars) < 60:
        risk_flags.append("新股")
    return risk_flags


def build_live_bar_anchor(
    quote: dict[str, Any] | None,
    bars: list | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """盘中实时价锚点 live_bar（不并入 bars）与 intraday_as_of。"""
    quote = quote if isinstance(quote, dict) else {}
    bars = bars or []
    _today = str(quote.get("trade_date") or "")[:10]
    _last_date = (
        str(bars[-1].get("date") or bars[-1].get("trade_date") or "")[:10] if bars else ""
    )
    _cp = quote.get("current_price")
    live_bar = None
    if _today and _last_date != _today and _cp is not None and float(_cp) > 0:
        _cp_f = float(_cp)
        _pre = quote.get("pre_close")
        try:
            _prev_close = float(_pre) if _pre is not None and float(_pre) > 0 else None
        except (TypeError, ValueError):
            _prev_close = None
        if _prev_close is None:
            _chg = float(quote.get("current_change_pct") or 0)
            _prev_close = _cp_f / (1 + _chg / 100) if _chg != 0 else _cp_f
        def _qf(key: str, default: float) -> float:
            v = quote.get(key)
            try:
                f = float(v) if v is not None else default
                return f if f > 0 else default
            except (TypeError, ValueError):
                return default
        _open = _qf("open", _prev_close)
        _high = _qf("high", max(_cp_f, _open))
        _low = _qf("low", min(_cp_f, _open))
        # 保证 high/low 包住现价
        _high = max(_high, _cp_f, _open)
        _low = min(_low, _cp_f, _open)
        _prev_bar = bars[-1] if bars else {}
        _vol = quote.get("volume")
        try:
            _vol_f = float(_vol) if _vol is not None else 0.0
        except (TypeError, ValueError):
            _vol_f = 0.0
        live_bar = {
            "date": _today,
            "open": _open,
            "close": _cp_f,
            "high": _high,
            "low": _low,
            "volume": _vol_f,
            "data_source": "quote-today",
            "data_status": "partial",
            "atr14": _prev_bar.get("atr14", 0),
            "atr_ratio": _prev_bar.get("atr_ratio", 0),
            "atr7": _prev_bar.get("atr7", 0),
            "tr": _prev_bar.get("tr", 0),
            "is_synthetic": True,
        }
    intraday_as_of = _last_date if live_bar else None
    return live_bar, intraday_as_of


def tag_fusion_as_instrument(fusion: dict[str, Any] | None) -> dict[str, Any]:
    """标记 fusion 产品角色为仪表（不改分数/动作计算）。"""
    if not isinstance(fusion, dict):
        return {}
    fusion = dict(fusion)
    fusion["product_role"] = "instrument"
    fusion["product_role_note"] = "仅参考；出手以 decision_view（共振∧策略∧纪律）为准"
    return fusion


def apply_buy_point_lifecycle(
    report: dict[str, Any],
    *,
    mark: MarkFn | None = None,
) -> dict[str, Any]:
    """L1 买点盖生命周期：写 buy_point_lifecycle；失败则只收紧 discipline 新开。

    与 build_report 原逻辑一致；失败不抛。
    """
    _mark = mark or _noop_mark
    if not isinstance(report, dict):
        return report
    try:
        from trader_shared.buy_point_lifecycle import build_buy_point_lifecycle_for_report
        from trader_shared.chan_discipline import format_entry_line_c1

        _life = build_buy_point_lifecycle_for_report(report)
        report["buy_point_lifecycle"] = _life
        if _life.get("status") == "failed":
            _disc = report.get("discipline") if isinstance(report.get("discipline"), dict) else {}
            _disc["allow_new_entry"] = False
            _cl = _disc.get("entry_checklist") if isinstance(_disc.get("entry_checklist"), dict) else {}
            if _cl:
                _cl["all_green"] = False
                _flags = _cl.get("flags") if isinstance(_cl.get("flags"), dict) else {}
                _flags["short_trigger"] = False
                _cl["flags"] = _flags
                _items = _cl.get("items") if isinstance(_cl.get("items"), dict) else {}
                _items["short_trigger"] = False
                _cl["items"] = _items
                _miss = list(_cl.get("missing_labels") or [])
                if "买点已失效" not in _miss:
                    _miss.append("买点已失效")
                _cl["missing_labels"] = _miss
                _cl["entry_line"] = format_entry_line_c1(
                    all_green=False, missing=_miss
                )
                _disc["entry_checklist"] = _cl
                _disc["entry_line"] = _cl["entry_line"]
            report["discipline"] = _disc
        _mark("buy_point_lifecycle")
    except Exception as _life_exc:
        _logger.debug("buy_point_lifecycle skip: %s", _life_exc)
        report.setdefault("buy_point_lifecycle", {"status": "none", "display_line": ""})
    return report


def attach_analysis_decision_stack(
    report: dict[str, Any],
    *,
    mark: MarkFn | None = None,
) -> dict[str, Any]:
    """意见卡 → 共振 → 策略匹配 → decision_view（只收紧）。

    失败不抛：尽量写占位字段，与 build_report 原行为一致。
    """
    _mark = mark or _noop_mark
    if not isinstance(report, dict):
        return report

    try:
        from trader_shared.analysis_cards import ensure_report_analysis_cards
        from trader_shared.strategy_match import match_strategies

        _pre = report.pop("_fusion_pre_cards", None)
        if isinstance(_pre, dict):
            ac = report.get("analysis_cards") if isinstance(report.get("analysis_cards"), dict) else {}
            ac.update(_pre)
            report["analysis_cards"] = ac
        ensure_report_analysis_cards(report)

        try:
            from trader_shared.resonance import attach_resonance

            attach_resonance(report)
            _mark("resonance")
        except Exception as _res_exc:
            _logger.debug("resonance skip: %s", _res_exc)
            report.setdefault(
                "resonance",
                {
                    "schema_version": "resonance_v1",
                    "scene": "pullback_probe",
                    "grade": "empty",
                    "posts": {},
                    "missing": [],
                    "conflict": False,
                    "summary_line": "共振：跳过",
                },
            )

        report["strategy_match"] = match_strategies(report)
        _mark("strategy_match")

        try:
            from trader_shared.decision_view import apply_decision_view

            apply_decision_view(report, tighten_discipline=True)
            _mark("decision_view")
        except Exception as _dv_exc:
            _logger.debug("decision_view skip: %s", _dv_exc)
            report.setdefault(
                "decision_view",
                {
                    "schema_version": "decision_view_v1",
                    "allow_new_recommend": False,
                    "summary_line": "决策：跳过",
                },
            )
    except Exception as _st_exc:
        _logger.debug("analysis_decision_stack skip: %s", _st_exc)
        try:
            from trader_shared.analysis_cards import ensure_report_analysis_cards

            report.pop("_fusion_pre_cards", None)
            ensure_report_analysis_cards(report)
        except Exception:
            report.setdefault("analysis_cards", {})
        try:
            from trader_shared.resonance import attach_resonance

            attach_resonance(report)
        except Exception:
            report.setdefault("resonance", {"schema_version": "resonance_v1", "grade": "empty"})

    return report


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

        # pipeline：买点盖 → 卡/共振/策略/决策（行为不变）
        try:
            apply_buy_point_lifecycle(report, mark=_mark)
            attach_analysis_decision_stack(report, mark=_mark)
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


def sync_report_with_data(report: dict, levels: dict) -> dict:
    """脚本自洽校验：修正数据与文字标签的矛盾（自 report_builder 迁出）。"""
    from trader_shared.light_data import to_float
    """脚本自洽校验：修正数据与文字标签的矛盾"""
    current  = float(report.get("current") or 0)
    support  = float(report.get("support") or 0)
    resistance = float(report.get("resistance") or 0)
    confirm  = float(report.get("confirm") or 0)
    stop     = float(report.get("stop") or 0)
    take     = float(report.get("take") or 0)
    scene    = str(report.get("scene") or "")
    state_label  = str(report.get("state_label") or "")
    ma5  = to_float(levels.get("ma_values", {}).get("ma5"))
    ma10 = to_float(levels.get("ma_values", {}).get("ma10"))
    # MA 趋势与文字标签
    if ma5 is not None and ma10 is not None and current > 0:
        if ma5 > ma10 and "空头" in state_label:
            report["state_label"] = state_label.replace("空头", "多头")
        elif ma5 < ma10 and "多头" in state_label:
            report["state_label"] = state_label.replace("多头", "空头")
    # support > resistance → 筹码与 ATR 模块打架
    if support > 0 and resistance > 0 and support >= resistance:
        report["resistance"] = support * 1.03
        report["support"]    = resistance * 0.97
    # stop < support（止损永远在支撑下方）
    if stop > 0 and support > 0 and stop >= support:
        report["stop"] = round(support * 0.97, 2)
    # take < confirm（止盈永远高于确认位）
    if take > 0 and confirm > 0 and take <= confirm:
        _zw = float(levels.get("zone_width_pct", 0.02) or 0.02)
        report["take"] = round(confirm * (1 + _zw), 2)
    # 场景与数值的逻辑一致性
    if scene in ("突破确认", "突破观察") and round(current, 2) < round(confirm, 2):
        report["scene"]        = "观望"
        report["state_label"]  = "未确认"
    elif scene in ("低吸观察", "防守观察") and current < support and support > 0:
        report["scene"]        = "破位下行"
        report["state_label"]  = "破位下行"
    elif scene == "冲高减仓" and current < support and support > 0:
        report["scene"]        = "低吸观察"
        report["state_label"]  = "低吸观察"
    elif scene == "突破观察" and current >= confirm and confirm > 0:
        report["scene"]        = "突破确认"
        report["state_label"]  = "趋势走强"
    elif scene in ("空间不足",) and current < support and support > 0:
        report["scene"]        = "修复观察"
        report["state_label"]  = "修复观察"
    return report



def attach_stage_position_pack(
    report: dict[str, Any],
    *,
    cost_price: float,
    current: float,
    market_env_data: dict[str, Any] | None,
    stage_result: dict[str, Any],
    atr14_val: float | None,
    bars: list,
    wyck_result: Any,
    support: float | None,
    confirm: float | None,
    expma10_val: Any,
    expma20_val: Any,
    chip_migration: Any,
    levels: dict[str, Any],
    bars_date: Any,
    base_status: str,
    theory_status: str,
    scene: str,
    report_fusion: dict[str, Any] | None,
    signal_win_rate: Any,
    signal_cost_price: float = 0.0,
    stage: str = "",
    mark: MarkFn | None = None,
) -> tuple[dict[str, Any], float, bool, int]:
    """持仓/仓位/止盈/stage 展示字段。返回 (report, cost_price, has_position, suggested)。"""
    _mark = mark or _noop_mark
    market_env_data = market_env_data if isinstance(market_env_data, dict) else {}
    stage_result = stage_result if isinstance(stage_result, dict) else {"major_stage": stage or "蓄势", "momentum": "震荡"}
    report_fusion = report_fusion if isinstance(report_fusion, dict) else {}
    levels = levels if isinstance(levels, dict) else {}
    bars = bars or []
    if not isinstance(report, dict):
        return report, float(cost_price or 0), False, 0

    from trader_shared.stage_positioning import (
        compute_exit_plan,
        compute_stage_stop,
        evaluate_position_state,
        compute_position_with_env,
        action_for_holding_state,
    )
    from trader_shared.signal_core import one_sentence
    from trader_shared.report_presentation import structure_view

    # 已有持仓模式：确定成本价和持仓状态
    # 必须在 compute_position_with_env() 之前，以便传入正确的 pnl_pct
    # 成本价已在 bars 获取后从 signals.jsonl 读取（与胜率合并为一次 I/O）
    if cost_price <= 0:
        cost_price = float(signal_cost_price or 0)
    
    has_position = cost_price > 0
    report["has_position"] = has_position
    report["cost_price"] = cost_price
    
    # 如果有持仓，计算盈亏比例
    pnl_pct = 0.0
    if has_position and cost_price > 0:
        pnl_pct = (current - cost_price) / cost_price * 100
        report["pnl_pct"] = pnl_pct
        report["pnl_text"] = f"盈 {pnl_pct:+.1f}%" if pnl_pct >= 0 else f"亏 {abs(pnl_pct):.1f}%"

    # 仓位计算（阶段 + 大盘环境）
    from trader_shared.stage_positioning import compute_position_with_env
    market_env_level = market_env_data.get("level", "震荡市")
    env_map = {"正常": "牛市", "偏弱": "震荡市", "很差": "熊市"}
    mapped_env = env_map.get(market_env_level, "震荡市")
    position_info = compute_position_with_env(
        stage=stage_result["major_stage"],
        momentum=stage_result["momentum"],
        market_env=mapped_env,
        pnl_pct=pnl_pct,
        total_position_pct=0.0,
    )
    report["position_info"] = position_info

    # 波动率风控：高波动自动减仓（只减不加）
    # 目标日 ATR 2.5%（A 股中位水平），实际 ATR 越高仓位越轻
    _atr_pct = (atr14_val / current * 100) if atr14_val and current and current > 0 else None
    if _atr_pct and _atr_pct > 0.5:
        _vol_ratio = min(1.0, 2.5 / _atr_pct)  # 只减不加
        _orig = int(position_info.get("suggested_pct") or 0)
        position_info["suggested_pct"] = max(0, int(round(_orig * _vol_ratio)))
        position_info["vol_adj_ratio"] = round(_vol_ratio, 2)

    # 分批止盈计划（仅在有持仓参考价时计算）
    entry_price = float(report.get("support") or current)  # 默认用支撑位作为参考买入价
    stop_price = float(report.get("stop") or 0)
    resistance_val = float(report.get("resistance") or 0)
    exit_plan = compute_exit_plan(
        entry_price=entry_price,
        stop_price=stop_price,
        resistance_price=resistance_val if resistance_val > 0 else None,
        current_stage=stage_result["major_stage"],
        bars=bars,
        wyckoff_result=wyck_result,
        atr14=atr14_val,
    )
    report["exit_plan"] = exit_plan
    report["chip_migration"] = chip_migration

    # 使用成本价作为 entry_price（有持仓时），否则用支撑位
    entry_price_for_state = cost_price if has_position else float(report.get("support") or current)

    position_state = evaluate_position_state(
        current_price=current,
        support=support,
        resistance=float(report.get("resistance") or 0),
        stop_price=float(report.get("stop") or 0),
        confirm_price=confirm,
        atr14=atr14_val,
        major_stage=stage_result["major_stage"],
        momentum=stage_result["momentum"],
        bars=bars,
        wyckoff_result=wyck_result,
        has_position=has_position,
        entry_price=entry_price_for_state,
        highest_close=max([float(b.get("close") or 0) for b in bars[-20:]]) if bars else current,
        expma10=expma10_val,
        chip_migration=chip_migration,
        high_zone_lower=float(levels.get("high_zone_lower") or 0),
        trailing_stop=levels.get("trailing_stop"),
        last_add_date=bars_date,
    )
    report["position_state"] = position_state

    # 阶段止损
    ma20_val = levels["ma_values"].get("ma20")
    stage_stop_info = compute_stage_stop(
        stage=stage_result["major_stage"],
        ma20=ma20_val,
        range_low=float(report.get("range_low") or 0),
        atr_pct=float(levels.get("atr_pct") or 0.02),
        expma20=expma20_val,
    )
    report["stage_stop"] = stage_stop_info
    
    # 补全 JSON 输出需要的字段
    report = sync_report_with_data(report, levels)

    # structure_note: 在 sync_report_with_data 之后计算，使用已修正的 scene
    structure_note = structure_view({
        "current": current, "confirm": confirm, "stage": stage,
        "base_status": base_status, "theory_status": theory_status,
        "scene": str(report.get("scene") or scene),
    })
    report["structure_note"] = structure_note

    # one_liner: 一句话总结
    _support = report.get("support")
    low_zone = str(report.get("low_zone") or (f"{_support*0.98:.2f}-{_support*1.02:.2f}元" if _support else "数据不足"))
    report["one_liner"] = one_sentence(report, low_zone)

    # t0_ref: T0 参考价位（high_sell 用阻力位而非 confirm，避免 T0 卖价高于报告显示的压力位）
    report["t0_ref"] = {
        "low_buy": float(report.get("support") or 0),
        "high_sell": float(report.get("resistance") or 0),
        "stop": float(report.get("stop") or 0),
    }

    # macd_status: MACD 方向
    mom = levels.get("momentum", {})
    if isinstance(mom, dict):
        macd = mom.get("macd", {})
        if isinstance(macd, dict):
            report["macd_status"] = {
                "histogram": macd.get("histogram"),
                "golden_cross": macd.get("golden_cross", False),
                "death_cross": macd.get("death_cross", False),
                "positive": macd.get("positive", False),
            }

    # ── [2.5] 量能真空区检查 ──
    try:
        from trader_shared.volume_profile import check_volume_vacuum
        volume_vacuum = check_volume_vacuum(bars, current)
        report["volume_vacuum"] = volume_vacuum
    except Exception:
        report["volume_vacuum"] = {"vacuum_warning": False, "warning_text": ""}

    # 个股股性透视卡：历史胜率（与成本推断合并为一次 I/O，已在上面读取）
    report["win_rate_data"] = signal_win_rate

    # ── 一致性仲裁：给 fusion action + suggested_pct 加持仓场景标签 ──
    # 四个字段（theory_status / fusion.action / suggested_pct / stop）来自独立模块，
    # 可能互斥（如 fusion 说「减仓」但 suggested_pct=0%）。
    # 通过 holding_hint + suggested_pct_context 消除互斥语义，让 AI 事实表不再打架。
    from trader_shared.stage_positioning import action_for_holding_state
    fusion_action_str = str((report_fusion or {}).get("action") or "").strip()
    holding_state = action_for_holding_state(fusion_action_str, has_position)
    report["fusion_holding_hint"] = holding_state.get("holding_hint", "待定")

    suggested = int((report.get("position_info") or {}).get("suggested_pct") or 0)
    _reduce_set = {"减仓", "空仓/止损", "空仓 (大盘很差, 一票否决)"}
    if suggested == 0:
        if fusion_action_str in _reduce_set:
            report["suggested_pct_context"] = "0%（未持仓者不参与；已有仓位者执行减仓）"
        else:
            report["suggested_pct_context"] = "0%（阶段建议空仓观望）"
    else:
        report["suggested_pct_context"] = f"{suggested}%（阶段×大盘环境建议）"

    _mark("stage_pack")

    has_position = bool(report.get("has_position"))
    cost_out = float(report.get("cost_price") or cost_price or 0)
    suggested_out = int((report.get("position_info") or {}).get("suggested_pct") or 0)
    return report, cost_out, has_position, suggested_out

