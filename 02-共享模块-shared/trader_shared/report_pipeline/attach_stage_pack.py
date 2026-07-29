# -*- coding: utf-8 -*-
"""四阶段仓位包挂接。"""
from __future__ import annotations

from typing import Any

from trader_shared._logging import get_logger
from trader_shared.report_pipeline._common import MarkFn, _noop_mark
from trader_shared.report_pipeline.attach_sync import sync_report_with_data

_logger = get_logger(__name__)

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


