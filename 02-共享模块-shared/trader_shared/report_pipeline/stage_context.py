# -*- coding: utf-8 -*-
"""阶段间传递的上下文对象（避免 builder 海量 dict 解包）。"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Mapping


class StageContext(SimpleNamespace):
    """轻量命名空间：支持 dict 构造、update 累积与 .get 兼容。

    build_report 用单一 bag：各 stage 返回后 ``ctx.update(...)``，
    assemble/attach 从 ctx 取 kwargs，禁止平行 locals 双真相。

    关键 bag 字段（文档清单；非严格 TypedDict）：

    种子（builder）
    - target, cost_price, fetcher(=None 兼容签名), provider, snapshot, sec, quote, bars

    context_stage
    - risk_flags, signal_cost_price, signal_win_rate
    - live_bar, intraday_as_of, bars_5m, weekly_bars, monthly_bars
    - atr14_val, atr_ratio_val, atr_level, atr_cap, atr_adjust, atr_data_source
    - data_status, current, recent20, change_pct_val
    - st, st_dir, chan_result, chan_mid_result, wyck_result, wyck_mid_result
    - momentum_result, vwap_res, main_force_env, mf_result
    - fund_flow_features, big_order_result, env, sector_data

    pre_cards / structure
    - fusion_pre_cards, volume_warning, report_fusion（merge 前可为 None）
    - levels, pre_stage, support, resistance, confirm, stop, take
    - weekly_proxy_close, monthly_proxy_close, scene, base_status, theory_status
    - replay, volume_text, high, low, analysis_time, state_label, volume_note
    - market_env_data, position_cap

    chip / stage_positioning
    - chip*, expma*, resonance_result, main_force_score_result
    - stage_result, ma250, bars_date, upward_momentum
    - short_term_momentum, stage（assemble 兼容槽；report["stage"] 别名动能）

    stage_pack 后
    - has_position, suggested；report_fusion 由 run_fusion_merge_stage 覆写
    """

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "StageContext":
        return cls(**dict(data or {}))

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def update(
        self, data: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> "StageContext":
        if data:
            self.__dict__.update(dict(data))
        if kwargs:
            self.__dict__.update(kwargs)
        return self

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)
