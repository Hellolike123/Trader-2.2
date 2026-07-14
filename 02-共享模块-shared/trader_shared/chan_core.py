"""Chan core facade: public engine API + re-export of split submodules."""
from __future__ import annotations
import math
from typing import Any
from trader_shared.light_data import to_float
from trader_shared.signal_utils import normalize_signal_id
try:
    from trader_shared.config import (
        CHANLUN_MIN_BARS,
        CHANLUN_MIN_BARS_PER_STROKE,
        CHANLUN_MIN_STROKES_PER_SEGMENT,
        CHAN_MULTILEVEL_ENABLED,
        CHAN_MULTILEVEL_CHUNK,
        CHAN_MULTILEVEL_MIN_BARS,
        CHAN_ZONE_MERGE_ENABLED,
        CHAN_SEGMENT_RELAX_OVERLAP,
        CHAN_ZONE_MERGE_GAP_PCT,
        CHAN_SIGNAL_ID_ENABLED,
        CHAN_DAILY_TREND_SEGS_HIGH,
        CHAN_DAILY_TREND_SEGS_MID,
        CHAN_DAILY_CONSOL_SEGS_HIGH,
        CHAN_DAILY_CONSOL_SEGS_MID,
        CHAN_WEEKLY_TREND_SEGS_HIGH,
        CHAN_WEEKLY_TREND_SEGS_MID,
        CHAN_WEEKLY_CONSOL_SEGS_HIGH,
        CHAN_WEEKLY_CONSOL_SEGS_MID,
        CHAN_DIVERGENCE_FALLBACK_WINDOW,
        CHAN_DROP_LEADING_DANGLING_STROKE,
        CHAN_DIVERGENCE_ANCHOR_LAST_PIVOT,
    )
except ImportError:
    CHANLUN_MIN_BARS = 20
    CHANLUN_MIN_BARS_PER_STROKE = 5
    CHANLUN_MIN_STROKES_PER_SEGMENT = 3
    CHAN_MULTILEVEL_ENABLED = True
    CHAN_MULTILEVEL_CHUNK = 5
    CHAN_MULTILEVEL_MIN_BARS = 15
    CHAN_ZONE_MERGE_ENABLED = True
    CHAN_SEGMENT_RELAX_OVERLAP = True
    CHAN_ZONE_MERGE_GAP_PCT = 0.015
    CHAN_SIGNAL_ID_ENABLED = True
    CHAN_DAILY_TREND_SEGS_HIGH = 8
    CHAN_DAILY_TREND_SEGS_MID = 5
    CHAN_DAILY_CONSOL_SEGS_HIGH = 5
    CHAN_DAILY_CONSOL_SEGS_MID = 3
    CHAN_WEEKLY_TREND_SEGS_HIGH = 5
    CHAN_WEEKLY_TREND_SEGS_MID = 3
    CHAN_WEEKLY_CONSOL_SEGS_HIGH = 3
    CHAN_WEEKLY_CONSOL_SEGS_MID = 2
    CHAN_DIVERGENCE_FALLBACK_WINDOW = 120
    CHAN_DROP_LEADING_DANGLING_STROKE = True
    CHAN_DIVERGENCE_ANCHOR_LAST_PIVOT = True

from .chan_structure import (
    _THIRD_POINT_MAX_LEAVE_PCT,
    _check_macd_for_2nd_buy,
    _check_macd_for_2nd_sell,
    _stroke_force_not_much_stronger,
    _stroke_force_weaker,
    _stroke_force_weaker_multi,
    _stroke_macd_area,
    _structure_conf_thresholds,
    _structure_confidence,
    _zone_last_end_index,
    classify_structure,
    detect_buy_points,
    detect_divergence,
    detect_sell_points
)

from .chan_geometry import (
    _aggregate_bars,
    _calc_macd,
    _detect_unilateral,
    _drop_leading_dangling_strokes,
    _has_entry_exit_segments,
    _higher_level_trend,
    _last_pivot_anchor_bar,
    _merge_char_element,
    _merge_zones,
    _valid_strokes,
    build_segments,
    build_strokes,
    build_zones,
    find_fractions,
    handle_inclusion,
    unwrap_chan
)

def _chanlun_compute(
    cleaned: list[dict],
    current: float,
    higher_trend: dict | None = None,
    symbol: str | None = None,
    analysis_date: str | None = None,
    weekly_bars: list[dict] | None = None,
    timeframe: str = "daily",
    raw_bars: list[dict] | None = None,
) -> dict:
    """缠论分析共享内核（批量接口与增量引擎共用）。

    `cleaned` 为「已包含处理 + 已带 MACD」的 K 线序列。本函数只跑结构层与后处理，
    不触碰包含/MACD 计算，确保批量（chanlun_analysis）与增量（ChanlunEngine）两条路径
    由同一份代码驱动、字节级一致。

    注意：`cleaned` 必带 `macd_histogram`（由 _calc_macd 写入），故买卖点力度一律取自
    cleaned，不再回退 raw 入参（raw 入参不再传入本内核）。
    """
    fractions = find_fractions(cleaned)
    raw_strokes = build_strokes(fractions, min_bars_per_stroke=CHANLUN_MIN_BARS_PER_STROKE, bars=cleaned)
    # P2：丢弃左端悬空笔（数据起点无左支点，永远不可信），从第一个完整支点起读。
    # 影响：strokes / segments / zones / divergence / 趋势标签全部基于「去悬空」序列，
    # 消除前导脏数据对整条走势的污染。
    strokes = _drop_leading_dangling_strokes(raw_strokes) if CHAN_DROP_LEADING_DANGLING_STROKE else raw_strokes
    segments = build_segments(strokes, min_strokes=CHANLUN_MIN_STROKES_PER_SEGMENT)

    # --- E2: build raw zones for zones_count (兼容)，merged zones for 分类 ---
    if len(segments) >= 3:
        items, lvl = segments, "segment"
    else:
        items, lvl = strokes, "stroke"
    raw_zones = build_zones(items, level=lvl, merge=False)
    zones = build_zones(items, level=lvl, merge=True)  # merged if CHAN_ZONE_MERGE_ENABLED
    zones_count = len(raw_zones)  # 保留原始滑动窗口数量，向后兼容

    # timeframe: daily 用日线 conf 门槛；weekly 用周线门槛（段数只调 conf）
    structure = classify_structure(zones, segments, strokes, timeframe=timeframe)
    merged_zones = structure.get("merged_zones", [])
    pivot_count = structure.get("pivot_count", 0)

    # 一类 conf=1 等 bar 级 fallback：优先用 cleaned 末两根，与笔级力度同坐标系
    # cleaned 必带 macd_histogram（由 _calc_macd 写入），故一律用 cleaned，不回退 raw 入参
    cleaned_macd_curr = to_float(cleaned[-1].get("macd_histogram")) if cleaned else None
    cleaned_macd_prev = to_float(cleaned[-2].get("macd_histogram")) if len(cleaned) >= 2 else None
    macd_for_buy_sell_curr = cleaned_macd_curr
    macd_for_buy_sell_prev = cleaned_macd_prev

    # 笔 start_index/end_index 相对 cleaned；背驰/二类确认/买卖点一律吃 cleaned
    # P3：背驰锚定最后中枢（而非固定窗口），只比较多级中枢之后的趋势 legs。
    _anchor_bar = None
    if CHAN_DIVERGENCE_ANCHOR_LAST_PIVOT:
        _anchor_bar = _last_pivot_anchor_bar(segments, strokes, merged_zones)
    divergence = detect_divergence(cleaned, strokes, anchor_bar=_anchor_bar)
    macd_divergence_buy = _check_macd_for_2nd_buy(cleaned, strokes)
    macd_divergence_sell = _check_macd_for_2nd_sell(cleaned, strokes)

    buy_points = detect_buy_points(
        strokes, zones, current, macd_for_buy_sell_curr, macd_for_buy_sell_prev,
        macd_divergence_buy, bars=cleaned,
    )
    sell_points = detect_sell_points(
        strokes, zones, current, macd_for_buy_sell_curr, macd_for_buy_sell_prev,
        macd_divergence_sell, bars=cleaned,
    )

    # --- E1: 多级别区间套确认 ---
    # N1 加固：还原预重构行为——higher_trend 源在 chunk 回退路径（weekly_bars=None）下
    # 必须是「原始 raw bars」而非「包含处理后的 cleaned」，否则聚合分组边界可能偏移。
    # weekly_bars 优先路径忽略首个入参，故此处选择不影响其输出。
    if higher_trend is None and CHAN_MULTILEVEL_ENABLED:
        _ht_src = raw_bars if raw_bars is not None else cleaned
        higher_trend = _higher_level_trend(_ht_src, chunk=CHAN_MULTILEVEL_CHUNK, weekly_bars=weekly_bars)
    ht: str | None = None
    hc: float = 0.0
    if isinstance(higher_trend, dict):
        ht = higher_trend.get("trend")
        hc = to_float(higher_trend.get("confidence")) or 0.0
    confident = hc >= 0.66

    # 多级别过滤（P1 裁定）：上级明确反向时保留「一类」背驰点，去掉二/三类粘滞点；
    # 同步清理无对应一类时的 divergence，避免过滤买点却仍报底/顶背驰。
    if isinstance(divergence, dict):
        divergence = dict(divergence)
    else:
        divergence = {"top_divergence": False, "bottom_divergence": False}

    if confident and ht == "down":
        buy_points = [bp for bp in buy_points if bp["type"] == "一类买"]
        if not buy_points:
            divergence["bottom_divergence"] = False
    if confident and ht == "up":
        sell_points = [sp for sp in sell_points if sp["type"] == "一类卖"]
        if not sell_points:
            divergence["top_divergence"] = False

    # 顺向增强：买点与上级 up 同向 → confidence +1（cap 3）
    if confident and ht == "up":
        for bp in buy_points:
            bp["confidence"] = min(3, bp["confidence"] + 1)
            bp["multi_level_confirm"] = True
    if confident and ht == "down":
        for sp in sell_points:
            sp["confidence"] = min(3, sp["confidence"] + 1)
            sp["multi_level_confirm"] = True

    # --- E4: 买卖点信号标准化（Signal Contract v2 signal_id）---
    if CHAN_SIGNAL_ID_ENABLED and symbol and analysis_date:
        for bp in buy_points:
            bp["signal_id"] = normalize_signal_id(
                symbol, analysis_date, _chan_type_canonical(bp["type"]), bp["price"],
                source_skill="chanlun",
            )
        for sp in sell_points:
            sp["signal_id"] = normalize_signal_id(
                symbol, analysis_date, _chan_type_canonical(sp["type"]), sp["price"],
                source_skill="chanlun",
            )

    strokes_count = len(strokes)

    # 优先用线段投票，不足时 fallback 到笔级别
    if len(segments) >= 3:
        recent3 = [seg["direction"] for seg in segments[-3:]]
        up_count = recent3.count("up")
        down_count = recent3.count("down")
        if up_count >= 2:
            trend_label = "拉升段"
        elif down_count >= 2:
            trend_label = "回调段"
        else:
            trend_label = "震荡段"
    elif strokes_count >= 3:
        recent3 = [s["direction"] for s in strokes[-3:]]
        up_count = recent3.count("up")
        down_count = recent3.count("down")
        if up_count >= 2:
            trend_label = "拉升段"
        elif down_count >= 2:
            trend_label = "回调段"
        else:
            trend_label = "震荡段"
    else:
        trend_label = "数据不足"

    buy_point_text = "、".join([bp["type"] for bp in buy_points]) if buy_points else "无"
    sell_point_text = "、".join([sp["type"] for sp in sell_points]) if sell_points else "无"

    last_valid_zone_last_price = None
    last_valid_zone_first_price = None
    for z in reversed(zones):
        if z["valid"]:
            last_valid_zone_last_price = z["zh_center"]
            break
    for z in zones:
        if z["valid"]:
            last_valid_zone_first_price = z["zh_center"]
            break

    return {
        "strokes": strokes,
        "zones": zones,
        "buy_points": buy_points,
        "sell_points": sell_points,
        "trend_label": trend_label,
        "buy_point_text": buy_point_text,
        "sell_point_text": sell_point_text,
        "strokes_count": strokes_count,
        "zones_count": zones_count,
        "divergence": divergence,
        "last_valid_zone_last_price": last_valid_zone_last_price,
        "last_valid_zone_first_price": last_valid_zone_first_price,
        "segments": segments,
        "segments_count": len(segments),
        "structure_type": structure["structure_type"],
        "structure_segments_count": structure["structure_segments_count"],
        "structure_confidence": structure.get("structure_confidence", "mid"),
        "structure_evidence": structure.get("structure_evidence", ""),
        # E1 新增字段
        "higher_trend": ht,
        # 真冲突：上级趋势明确，且本级仍留有对立方向买卖点/背驰时为 True
        "higher_trend_conflict": bool(
            confident
            and (
                (ht == "down" and (buy_points or divergence.get("bottom_divergence")))
                or (ht == "up" and (sell_points or divergence.get("top_divergence")))
            )
        ),
        # E3 新增字段：fractions（修复 time_window_detector 死代码 bug）
        "fractions": fractions,
        # E2 新增字段：合并中枢信息
        "merged_zones": merged_zones,
        "pivot_count": pivot_count,
    }

def chanlun_analysis(
    bars: list[dict],
    current: float,
    macd_hist_current: float | None = None,
    macd_hist_prev: float | None = None,
    higher_trend: dict | None = None,
    symbol: str | None = None,
    analysis_date: str | None = None,
    weekly_bars: list[dict] | None = None,
    timeframe: str = "daily",
) -> dict:
    """缠论批量分析（无状态接口，向后兼容）。

    委托共享内核 `_chanlun_compute`：先算「包含处理 + MACD」，再交给内核。
    输出与重构前字节级一致（仅把结构层/后处理抽取为共享函数，算法行为未改）。
    """
    if len(bars) < CHANLUN_MIN_BARS:
        return {}

    # 结构层：包含处理（拷贝 OHLC，不修改入参 bars）
    cleaned = handle_inclusion(bars)
    # 力度层：在 inclusion 后序列上重算 MACD，使笔 index 与 histogram 同坐标系。
    # _calc_macd 内部 dict 拷贝，只写 cleaned，绝不写回调用方 raw bars。
    cleaned = _calc_macd(cleaned)

    return _chanlun_compute(
        cleaned, current,
        higher_trend=higher_trend, symbol=symbol,
        analysis_date=analysis_date, weekly_bars=weekly_bars, timeframe=timeframe,
        raw_bars=bars,
    )

class ChanlunEngine:
    """缠论增量分析引擎（有状态）。

    Phase 1 范围：批量初始化 + 增量 ``update_bar``（append / 当前 bar replace）+
    状态持久化（save/load）。下游结构算法（find_fractions / build_strokes /
    build_segments / detect_*）全部复用既有纯函数，增量结果与批量重算由构造保证一致
    （共享内核 ``_chanlun_compute``）。

    设计取舍（对照评审第七节）：
      - 以 ``self._raw`` 为权威源，``update_bar`` 后通过 ``_calc_macd(handle_inclusion(raw))``
        重算 ``self.cleaned``。纯尾部增量回溯（7.3 inclusion run / 7.4 增量 MACD）为 optional
        性能项；此处以「全量复用纯函数」换取零漂移正确性（300 根 < 1ms，见 7.5/7.9）。
      - 持久化含 MACD EMA 末值（_ema12/_ema26/_dea）、inclusion run 起点、higher_trend
        缓存与最后 bar 身份（7.6）。save 前用 ``to_float`` 归一 numpy 类型，避免 JSON 序列化失败。
    """

    def __init__(self, bars: list[dict] | None = None):
        self._raw: list[dict] = []
        self.cleaned: list[dict] = []
        self.fractions: list[dict] = []
        self.strokes: list[dict] = []
        self.segments: list[dict] = []
        self.zones: list[dict] = []
        # MACD EMA 末值（持久化用；本实现每 tick 全量重算 cleaned，故为派生状态）
        self._ema12: float | None = None
        self._ema26: float | None = None
        self._dea: float | None = None
        # inclusion run 起点（纳入持久化，供后续尾部增量优化使用）
        self._incl_run_start: int = 0
        # higher_trend 缓存（7.7）
        self._higher_trend: dict | None = None
        self._higher_trend_weekly_id: object | None = None
        # 最后 bar 身份（append / replace 判定，7.6）
        self._last_bar_id: object | None = None
        if bars:
            for bar in bars:
                self.update_bar(bar)

    # ---- bar 身份 ----
    @staticmethod
    def _bar_id(bar: dict) -> object:
        if isinstance(bar, dict) and bar.get("date") is not None:
            return ("date", bar["date"])
        # 无 date 时退化为对象 id（同进程内稳定）；跨进程由 save/load 的 last_bar_id 兜底
        return ("idx", id(bar))

    # ---- 核心重算（一致性由纯函数保证）----
    def _recompute(self) -> None:
        if not self._raw:
            self.cleaned = []
            self.fractions = []
            self.strokes = []
            self.segments = []
            self.zones = []
            self._ema12 = self._ema26 = self._dea = None
            return
        self.cleaned = _calc_macd(handle_inclusion(self._raw))
        self.fractions = find_fractions(self.cleaned)
        _raw_strokes = build_strokes(
            self.fractions, min_bars_per_stroke=CHANLUN_MIN_BARS_PER_STROKE, bars=self.cleaned
        )
        # P2：与 _chanlun_compute 一致，引擎存储的 strokes 也裁掉左端悬空笔
        self.strokes = (
            _drop_leading_dangling_strokes(_raw_strokes)
            if CHAN_DROP_LEADING_DANGLING_STROKE
            else _raw_strokes
        )
        self.segments = build_segments(self.strokes, min_strokes=CHANLUN_MIN_STROKES_PER_SEGMENT)
        # 派生 MACD EMA 末值（用于 save/load 保真）
        from trader_shared.indicator_math import calc_macd_series

        closes = [to_float(b.get("close")) for b in self.cleaned]
        macd = calc_macd_series(closes)
        for k in range(len(macd["ema12"]) - 1, -1, -1):
            if (
                macd["ema12"][k] is not None
                and macd["ema26"][k] is not None
                and macd["dea"][k] is not None
            ):
                self._ema12 = to_float(macd["ema12"][k])
                self._ema26 = to_float(macd["ema26"][k])
                self._dea = to_float(macd["dea"][k])
                break

    def update_bar(self, bar: dict) -> None:
        """增量更新。

        - bar 与最后 bar 同 id（同一交易日/同一对象）→ **replace** 当前（进行中）bar；
        - 否则 → **append** 新 bar。
        """
        bar = dict(bar)
        bar_id = self._bar_id(bar)
        if self._last_bar_id is not None and bar_id == self._last_bar_id and self._raw:
            # replace 当前（进行中）bar：覆盖最后一根 raw，再整段重算
            self._raw[-1] = bar
        else:
            self._raw.append(bar)
            self._last_bar_id = bar_id
        self._recompute()

    def get_analysis(
        self,
        current: float,
        symbol: str | None = None,
        analysis_date: str | None = None,
        weekly_bars: list[dict] | None = None,
        timeframe: str = "daily",
        higher_trend: dict | None = None,
    ) -> dict:
        """基于缓存状态计算（不重算历史）。

        全参数透传至 ``_chanlun_compute``；higher_trend 走缓存（7.7）：
        显式传入优先；否则用首次计算并缓存的值（weekly_bars 对象不变则复用，
        避免盘中每次实时调用都重跑 ``_higher_level_trend``）。
        """
        if len(self._raw) < CHANLUN_MIN_BARS:
            return {}
        if higher_trend is not None:
            ht = higher_trend
        elif self._higher_trend is not None and self._higher_trend_weekly_id == id(weekly_bars):
            ht = self._higher_trend
        else:
            ht = _higher_level_trend(
                self._raw, chunk=CHAN_MULTILEVEL_CHUNK, weekly_bars=weekly_bars
            )
            self._higher_trend = ht
            self._higher_trend_weekly_id = id(weekly_bars)
        return _chanlun_compute(
            self.cleaned, current, higher_trend=ht, symbol=symbol,
            analysis_date=analysis_date, weekly_bars=weekly_bars, timeframe=timeframe,
        )

    # ---- 状态持久化 ----
    def save(self, path) -> None:
        import json
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "raw_bars": self._raw,
            "ema12": self._ema12,
            "ema26": self._ema26,
            "dea": self._dea,
            "incl_run_start": self._incl_run_start,
            "higher_trend": self._higher_trend,
            "last_bar_id": self._last_bar_id,
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, default=_chan_json_default)

    @classmethod
    def load(cls, path) -> "ChanlunEngine":
        import json

        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        eng = cls()
        eng._raw = state.get("raw_bars", [])
        eng._ema12 = state.get("ema12")
        eng._ema26 = state.get("ema26")
        eng._dea = state.get("dea")
        eng._incl_run_start = state.get("incl_run_start", 0)
        eng._higher_trend = state.get("higher_trend")
        eng._last_bar_id = state.get("last_bar_id")
        eng._recompute()
        return eng

def _chan_json_default(o):
    """JSON 序列化兜底：numpy 标量 → 原生 float/int（cleaned 不入库，raw 可能含 numpy）。"""
    try:
        import numpy as np
    except ImportError:
        return str(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)

# 中文买卖点类型 → Signal Contract v2 规范类型名（缺失字典导致历史 NameError）
_CHAN_TYPE_CANONICAL = {
    "一类买": "chan_buy_1",
    "类二买": "chan_buy_like2",
    "二类买": "chan_buy_2",
    "三类买": "chan_buy_3",
    "一类卖": "chan_sell_1",
    "二类卖": "chan_sell_2",
    "三类卖": "chan_sell_3",
}


def _chan_type_canonical(cn_type: str) -> str:
    """将中文买卖点类型映射为 Signal Contract v2 规范类型名。"""
    return _CHAN_TYPE_CANONICAL.get(cn_type, cn_type)

def chanlun_strategy(
    current: float,
    bars: list[dict],
    change_pct: Any = None,
    quote: dict | None = None,
    symbol: str | None = None,
    analysis_date: str | None = None,
    weekly_bars: list[dict] | None = None,
) -> dict:
    """日线缠论（短线 / fusion）。周线仅作 higher_trend 过滤，不是中线主分析。"""
    macd_h_curr = to_float(bars[-1].get("macd_histogram")) if bars else None
    macd_h_prev = to_float(bars[-2].get("macd_histogram")) if len(bars) >= 2 else None
    # 从 quote 派生 symbol/date，供 signal_id 使用（向后兼容：无 quote 时不加 id）
    if symbol is None and isinstance(quote, dict):
        symbol = quote.get("symbol")
    if analysis_date is None and isinstance(quote, dict):
        analysis_date = quote.get("trade_date") or (bars[-1].get("date") if bars else None)
    result = chanlun_analysis(
        bars, current, macd_h_curr, macd_h_prev,
        symbol=symbol, analysis_date=analysis_date,
        weekly_bars=weekly_bars,
        timeframe="daily",
    )
    if isinstance(result, dict):
        result = {**result, "timeframe": "daily"}
    return {"chanlun": result}

def chanlun_strategy_midline(
    current: float,
    weekly_bars: list[dict] | None = None,
    daily_bars: list[dict] | None = None,
    change_pct: Any = None,
    quote: dict | None = None,
    symbol: str | None = None,
    analysis_date: str | None = None,
) -> dict:
    """中线缠论独立判断：优先在周 K 上完整跑笔段/结构，不足则回退日 K。

    与日线 chanlun_strategy 分离：
    - 中线：本函数 → 报告「理论：缠论 …」
    - 短线：chanlun_strategy(日线) → fusion / 短线专家
    """
    weekly_bars = weekly_bars or []
    daily_bars = daily_bars or []
    if symbol is None and isinstance(quote, dict):
        symbol = quote.get("symbol")
    if analysis_date is None and isinstance(quote, dict):
        analysis_date = quote.get("trade_date")

    if len(weekly_bars) >= CHANLUN_MIN_BARS:
        bars = weekly_bars
        tf = "weekly"
        conf_tf = "weekly"
        # 周线主分析不再叠 higher_trend 周线（避免双重周线）
        extra_weekly = None
    elif len(daily_bars) >= CHANLUN_MIN_BARS:
        bars = daily_bars
        tf = "daily_fallback"
        conf_tf = "daily"
        extra_weekly = weekly_bars if weekly_bars else None
    else:
        return {
            "chanlun": {
                "timeframe": "insufficient",
                "structure_type": "",
                "structure_confidence": "low",
                "trend_label": "数据不足",
                "divergence": {},
                "buy_points": [],
                "sell_points": [],
            }
        }

    if analysis_date is None and bars:
        analysis_date = bars[-1].get("date")
    macd_h_curr = to_float(bars[-1].get("macd_histogram")) if bars else None
    macd_h_prev = to_float(bars[-2].get("macd_histogram")) if len(bars) >= 2 else None
    # 现价：周线分析用当前价更贴现价位置
    cur = float(current) if current and current > 0 else float(to_float(bars[-1].get("close")) or 0)
    result = chanlun_analysis(
        bars, cur, macd_h_curr, macd_h_prev,
        symbol=symbol, analysis_date=analysis_date,
        weekly_bars=extra_weekly,
        timeframe=conf_tf,
    )
    if not isinstance(result, dict):
        result = {}
    result = {**result, "timeframe": tf}
    return {"chanlun": result}

def format_chanlun_theory_line(chan_result: Any) -> str:
    """中线理论区用：结构 · 方向（不写「缠论：」前缀，由外层拼接）。

    conf=low 时主名旁注「段偏少」；禁止用线段不足当主显示。
    """
    chan = unwrap_chan(chan_result) if isinstance(chan_result, dict) else {}
    if not isinstance(chan, dict) or not chan:
        return "结构未成型·中性"

    st = str(chan.get("structure_type") or "").strip()
    # 兼容历史缓存中的「线段不足*」主状态；正常路径不再产出该值
    if st.startswith("线段不足"):
        main = "结构未成型"
    elif st and st != "无结构":
        main = st
        conf = str(chan.get("structure_confidence") or "").lower()
        if conf == "low":
            main = f"{st}(段偏少)"
    else:
        main = "暂无明确结构"

    # 方向：买卖点/背驰/trend_label（与 fusion 优先级类似，但只出多空标签）
    buy_points = chan.get("buy_points") if isinstance(chan.get("buy_points"), list) else []
    sell_points = chan.get("sell_points") if isinstance(chan.get("sell_points"), list) else []
    divergence = chan.get("divergence") if isinstance(chan.get("divergence"), dict) else {}
    trend_label = str(chan.get("trend_label") or "")

    direction = 0
    if any(isinstance(p, dict) and p.get("type") in ("一类卖", "二类卖", "三类卖") for p in sell_points):
        direction = -1
    elif divergence.get("top_divergence"):
        direction = -1
    elif any(isinstance(p, dict) and p.get("type") in ("一类买", "二类买", "三类买") for p in buy_points):
        direction = 1
    elif divergence.get("bottom_divergence"):
        direction = 1
    elif "上涨" in trend_label or "多" in trend_label:
        direction = 1
    elif "下跌" in trend_label or "空" in trend_label:
        direction = -1

    dir_label = "看涨" if direction > 0 else ("看跌" if direction < 0 else "中性")
    # 回退标注：周线不足时用日线分析，诚实提示
    _tf_suffix = ""
    if chan.get("timeframe") == "daily_fallback":
        _tf_suffix = "（日线）"
    return f"{main}·{dir_label}{_tf_suffix}"
