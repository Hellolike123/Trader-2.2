# -*- coding: utf-8 -*-
"""融合阶段：预产卡（早）与 merge/仪表（晚）。

法源：docs/designs/resonance-and-orchestration.md §6 阶段5；
BUSINESS.md §2.7（fusion 仅仪表）。merge 在 stage_pack 之后、
attach_short_midline 之前挂接；禁止挪到 decision_view 之后（A2 不做）。
"""
from __future__ import annotations

from typing import Any

from trader_shared.report_pipeline._common import MarkFn, _noop_mark, _logger
from trader_shared.report_pipeline.prelude import tag_fusion_as_instrument


def run_pre_cards_stage(
    *,
    chan_result: dict[str, Any],
    momentum_result: dict[str, Any],
    wyck_result: dict[str, Any],
    bars: list,
    quote: dict[str, Any],
    fund_flow_features: dict[str, Any] | None,
    snapshot: Any,
    target: str,
    sector_data: dict[str, Any] | None,
    mark: MarkFn | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """预产分析卡 + 量价警告 + 板块相对标注。

    返回 (pre_cards, volume_warning)。不调用 merge_decisions。
    """
    _mark = mark or _noop_mark
    volume_warning: dict[str, Any] | None = None
    try:
        from trader_shared.volume_price import detect_volume_divergence, volume_snapshot_dict

        vw = detect_volume_divergence(bars)
        if vw:
            volume_warning = volume_snapshot_dict(vw)
    except Exception:
        volume_warning = None

    _stock_chg_pct = float(quote.get("current_change_pct") or 0)
    if sector_data and isinstance(sector_data, dict) and sector_data.get("status") == "正常":
        _sector_chg_pct = float(sector_data.get("sector_change_pct", 0) or 0)
        _vs = _stock_chg_pct - _sector_chg_pct
        if _vs > 0:
            sector_data["stock_vs_sector"] = f"跑赢板块 +{_vs:.2f}%"
        elif _vs < 0:
            sector_data["stock_vs_sector"] = f"跑弱板块 {_vs:.2f}%"
        else:
            sector_data["stock_vs_sector"] = "与板块持平"

    _pre_cards: dict[str, Any] = {}
    try:
        from trader_shared.analysis_cards import (
            build_chan_card,
            build_momentum_card,
            build_vpf_card,
            build_wyckoff_card,
        )
        from trader_shared.vpf_core import build_vpf_signal

        _pre_cards["chan"] = build_chan_card(chan_result, role="daily")
        _pre_cards["momentum"] = build_momentum_card(momentum_result, role="daily")
        _sec = getattr(snapshot, "security", None)
        _pre_cards["wyckoff"] = build_wyckoff_card(
            wyck_result,
            role="daily",
            symbol=str(getattr(_sec, "ts_code", "") or target or ""),
        )
        _avg_to = None
        if bars and len(bars) >= 10:
            _amts = []
            for _b in bars[-20:]:
                _a = _b.get("amount") if isinstance(_b, dict) else None
                if _a is not None:
                    try:
                        _amts.append(float(str(_a).replace(",", "")))
                    except (TypeError, ValueError):
                        pass
            if _amts:
                _avg_to = sum(_amts) / len(_amts) / 10000.0
        _vpf_raw = build_vpf_signal(
            volume_warning if isinstance(volume_warning, dict) else None,
            fund_flow_features if isinstance(fund_flow_features, dict) else None,
            bars=bars,
            avg_daily_turnover_wan=_avg_to,
        )
        _pre_cards["vpf"] = build_vpf_card(_vpf_raw, role="daily")
    except Exception as _pc_exc:
        _logger.debug("pre-fusion analysis_cards skip: %s", _pc_exc)
        _pre_cards = {}

    _mark("pre_cards")
    return _pre_cards, volume_warning


def _attach_fusion_verbatim(report_fusion: dict[str, Any]) -> None:
    """为人读仪表写 fusion_verbatim（不改分数/动作）。"""
    try:
        _ws = float(report_fusion.get("weighted_score") or 0)
        _conf = float(report_fusion.get("confidence") or 0)
        _action = str(report_fusion.get("action") or "未知")
        _regime = str(report_fusion.get("regime") or "未知")
        _dis = float(report_fusion.get("disagreement") or 0)
        if _regime == "很差":
            _emoji = "🔴"
        elif _ws >= 0.25:
            _emoji = "🟢"
        elif _ws >= 0.1:
            _emoji = "🟡"
        elif _ws >= -0.05:
            _emoji = "⚪"
        elif _ws >= -0.12:
            _emoji = "🟡"
        elif _ws >= -0.2:
            _emoji = "🟠"
        else:
            _emoji = "🔴"
        _disclaimer = ""
        if _dis > 1:
            _disclaimer = "（信号冲突，建议等待）"
        elif _conf < 0.3:
            _disclaimer = "（信号弱，轻仓）"
        _action_explain = {
            "高位观望": "不追高，等回调",
            "空仓/止损": "不买，有仓位要走",
            "减仓": "减仓锁定利润",
            "减1/3 (高位松动)": "减仓，高位有风险",
            "持股观望": "持有，等方向",
            "等转强观察": "等突破再买",
            "等转强": "等信号确认",
        }
        _explain = _action_explain.get(_action, "")
        _main_line = f"🎯 {_action}{_disclaimer}"
        if _explain:
            _main_line += f"\n  {_explain}"
        _sd = report_fusion.get("signals_detail") or {}
        _dim_parts = []
        for key, label in [("chan", "缠论"), ("momentum", "动量"), ("vpf", "价量资金")]:
            _sig = _sd.get(key)
            if isinstance(_sig, dict):
                _reason = str(_sig.get("reason", ""))
                _short = _reason.replace("缠论", "").replace("威科夫", "").replace("动量", "").strip()
                if _short.startswith(":"):
                    _short = _short[1:]
                if not _short or _short == "无明确信号":
                    _dim_parts.append(f"{label}:无信号")
                elif key == "momentum" and "、" in _short:
                    _dim_parts.append(f"{label}:{_short.split('、')[-1]}")
                else:
                    _dim_parts.append(f"{label}:{_short}")
        _breakdown = f"  {'｜'.join(_dim_parts)}" if _dim_parts else ""
        report_fusion["fusion_verbatim"] = _main_line + ("\n" + _breakdown if _breakdown else "")
    except Exception:
        report_fusion["fusion_verbatim"] = "🎯 数据异常"


def run_fusion_merge_stage(
    *,
    chan_result: dict[str, Any],
    momentum_result: dict[str, Any],
    wyck_result: dict[str, Any],
    bars: list,
    env: dict[str, Any],
    quote: dict[str, Any],
    current: float,
    main_force_env: str,
    fetcher: Any,
    data_status: str,
    fund_flow_features: dict[str, Any] | None,
    snapshot: Any,
    volume_warning: dict[str, Any] | None,
    analysis_cards: dict[str, Any] | None,
    mark: MarkFn | None = None,
) -> dict[str, Any]:
    """merge_decisions + verbatim + tag instrument。

    挂接点：stage_pack 之后、attach_short_midline 之前。
    返回已标 product_role=instrument 的 fusion dict。
    """
    import traceback

    _mark = mark or _noop_mark
    _stock_chg_pct = float(quote.get("current_change_pct") or 0)
    _pre_cards = analysis_cards if isinstance(analysis_cards, dict) else {}

    try:
        from trader_shared.fusion_core import merge_decisions

        report_fusion = merge_decisions(
            chan_result=chan_result,
            momentum_result=momentum_result,
            wyckoff_result=wyck_result,
            regime=env.get("level", "正常"),
            current_price=current,
            bars=bars,
            hmm_regime=env.get("hmm_regime_en", "range"),
            main_force_env=main_force_env,
            fetcher=fetcher,
            data_status=data_status,
            volume_warning=volume_warning,
            fund_flow_data=fund_flow_features,
            current_change_pct=_stock_chg_pct,
            extend_fundamental=getattr(snapshot, "extend_fundamental", None),
            extend_sentiment=getattr(snapshot, "extend_sentiment", None),
            extend_sector=getattr(snapshot, "extend_sector", None),
            extend_concept=getattr(snapshot, "extend_concept", None),
            extend_northbound=getattr(snapshot, "extend_northbound", None),
            extend_margin=getattr(snapshot, "extend_margin", None),
            analysis_cards=_pre_cards or None,
        )
    except Exception:
        _sec = getattr(snapshot, "security", None)
        _logger.warning(
            "merge_decisions 崩溃 (data_status=%s, symbol=%s):\n%s",
            data_status,
            getattr(_sec, "ts_code", None) or "?",
            traceback.format_exc(),
        )
        report_fusion = {
            "action": "融合层异常",
            "confidence": 0,
            "weighted_score": 0,
            "regime": "",
            "hmm_regime": "range",
            "disagreement": 0,
            "signals_detail": {},
            "weights_used": {},
        }

    _attach_fusion_verbatim(report_fusion)
    report_fusion = tag_fusion_as_instrument(report_fusion)
    _mark("fusion")
    return report_fusion


def run_fusion_stage(
    *,
    chan_result: dict[str, Any],
    momentum_result: dict[str, Any],
    wyck_result: dict[str, Any],
    bars: list,
    env: dict[str, Any],
    quote: dict[str, Any],
    current: float,
    main_force_env: str,
    fetcher: Any,
    data_status: str,
    fund_flow_features: dict[str, Any] | None,
    snapshot: Any,
    target: str,
    sector_data: dict[str, Any] | None,
    mark: MarkFn | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    """兼容旧调用方：pre_cards → merge，返回 (fusion, pre_cards, volume_warning)。"""
    pre_cards, volume_warning = run_pre_cards_stage(
        chan_result=chan_result,
        momentum_result=momentum_result,
        wyck_result=wyck_result,
        bars=bars,
        quote=quote,
        fund_flow_features=fund_flow_features,
        snapshot=snapshot,
        target=target,
        sector_data=sector_data,
        mark=mark,
    )
    report_fusion = run_fusion_merge_stage(
        chan_result=chan_result,
        momentum_result=momentum_result,
        wyck_result=wyck_result,
        bars=bars,
        env=env,
        quote=quote,
        current=current,
        main_force_env=main_force_env,
        fetcher=fetcher,
        data_status=data_status,
        fund_flow_features=fund_flow_features,
        snapshot=snapshot,
        volume_warning=volume_warning,
        analysis_cards=pre_cards,
        mark=mark,
    )
    return report_fusion, pre_cards, volume_warning
