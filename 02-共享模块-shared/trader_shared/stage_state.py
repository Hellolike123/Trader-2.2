"""Stage state persistence + portfolio correlation (leaf)."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import numpy as np
from trader_shared._logging import get_logger
from trader_shared.safe_cast import safe_float
from trader_shared.config import (
    ACCUMULATION_DAYS_LIMIT, MARKUP_DAYS_LIMIT,
    RALLY_REDUCE_FULL_SCORE, RALLY_REDUCE_MIN_SCORE,
    RALLY_REDUCE_POSITION_PCT, RALLY_REDUCE_LITE_POSITION_PCT,
    CORRELATION_THRESHOLD, CORRELATION_LOOKBACK_DAYS,
)

from trader_shared.trader_paths import KeyedPath

_STATE_FILE = KeyedPath("stage_state")

_logger = get_logger(__name__)

def calc_portfolio_correlation(
    positions: list[dict[str, Any]],
    bars_map: dict[str, list[dict[str, Any]]],
    threshold: float = CORRELATION_THRESHOLD,
    lookback: int = CORRELATION_LOOKBACK_DAYS,
) -> dict[str, Any]:
    """计算持仓个股两两相关性，识别集中风险暴露。

    当任意两只持仓的相关系数 R > threshold 时，将它们合并为同一风险组。
    触发熔断后，该风险组的总仓位上限 = 单票上限（降为最保守值）。

    Args:
        positions: 持仓列表，每个 dict 至少含 "code" 和 "position_pct" 键。
                   code 为股票代码，position_pct 为仓位百分比。
        bars_map:  {code: bars} 字典，bars 为 K 线列表（含 "close" 键）。
        threshold: 相关系数阈值，默认 0.7。
        lookback:  收益率回溯天数，默认 20（需 lookback+1 根收盘）。

    Returns:
        {
            "correlation_matrix": dict,       # {("A","B"): r, ...} 两两相关系数
            "risk_groups": list[list[str]],   # 合并后的风险组（相关 > 阈值的股票归为一组）
            "triggered": bool,                # 是否触发熔断
            "adjusted_total_limit": int|None, # 触发时降为单票上限，否则 None
        }
    """
    if not positions or len(positions) < 2:
        return {
            "correlation_matrix": {},
            "risk_groups": [[p.get("code", "")] for p in positions] if positions else [],
            "triggered": False,
            "adjusted_total_limit": None,
        }

    # 提取各持仓近 lookback 日收益率（非价格水平，避免共趋势抬高 R）
    codes: list[str] = []
    return_arrays: list[list[float]] = []
    for pos in positions:
        code = pos.get("code", "")
        bars = bars_map.get(code, [])
        if not bars or len(bars) < 3:
            # 数据不足，跳过该票（不参与相关性计算）
            _logger.debug("correlation: %s bars不足，跳过", code)
            continue
        recent = bars[-(lookback + 1):]
        closes = [float(b.get("close") or 0) for b in recent if float(b.get("close") or 0) > 0]
        if len(closes) < 3:
            continue
        rets = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
            if closes[i - 1] > 0
        ]
        if len(rets) < 2:
            continue
        codes.append(code)
        return_arrays.append(rets)

    if len(codes) < 2:
        return {
            "correlation_matrix": {},
            "risk_groups": [[c] for c in codes] if codes else [],
            "triggered": False,
            "adjusted_total_limit": None,
        }

    # 对齐长度（取最短序列长度）
    min_len = min(len(arr) for arr in return_arrays)
    aligned = [arr[-min_len:] for arr in return_arrays]

    # 计算两两相关系数矩阵（收益率）
    n = len(codes)
    matrix = np.array(aligned, dtype=np.float64)  # shape: (n, min_len)
    corr = np.corrcoef(matrix)  # shape: (n, n)

    # 提取相关系数 > 阈值的配对
    correlation_pairs: dict[tuple[str, str], float] = {}
    high_corr_pairs: list[tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            r = float(corr[i, j])
            correlation_pairs[(codes[i], codes[j])] = round(r, 4)
            if r > threshold:
                high_corr_pairs.append((i, j))

    # 合并高相关股票为风险组（Union-Find）
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i, j in high_corr_pairs:
        union(i, j)

    # 按根节点分组
    groups_map: dict[int, list[str]] = {}
    for idx in range(n):
        root = find(idx)
        groups_map.setdefault(root, []).append(codes[idx])
    risk_groups = list(groups_map.values())

    # 是否触发熔断（存在至少一个组含 2 只以上股票）
    triggered = any(len(g) > 1 for g in risk_groups)

    # 触发时：将触发组的总仓位上限降为单票上限
    # 这里返回单票上限提示，调用方负责实际仓位调整
    adjusted_total_limit: int | None = None
    if triggered:
        # 默认单票上限 30%（震荡市），调用方可根据 market_env 覆盖
        adjusted_total_limit = 30
        for group in risk_groups:
            if len(group) > 1:
                _logger.info(
                    "correlation: 风险暴露熔断触发，组 %s 相关系数 > %.2f，"
                    "总仓位上限降为 %d%%",
                    group, threshold, adjusted_total_limit,
                )

    return {
        "correlation_matrix": correlation_pairs,
        "risk_groups": risk_groups,
        "triggered": triggered,
        "adjusted_total_limit": adjusted_total_limit,
    }

def _load_stage_state(symbol: str = "") -> dict[str, Any]:
    """加载阶段状态（用于多日确认和锁定期）。

    P0 Fix: 按 symbol 隔离，避免多票分析时状态互相覆盖。
    存储格式: {"<symbol>": {...state...}, ...}
    """
    try:
        if _STATE_FILE.exists():
            raw = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                # 兼容旧格式（无 symbol 维度）：旧 dict 没有 symbol key 时视为全局
                if symbol and symbol in raw:
                    return raw[symbol]
                # 旧格式迁移：如果顶层没有 symbol key 且不含嵌套 dict，视为全局状态
                if symbol and not any(isinstance(v, dict) and k != symbol for k, v in raw.items()):
                    return raw
                return raw.get(symbol, {}) if symbol else raw
    except (json.JSONDecodeError, OSError) as exc:
        _logger.debug("Stage state load failed: %s", exc)
    return {}

def _save_stage_state(state: dict[str, Any], symbol: str = "") -> None:
    """保存阶段状态。

    P0 Fix: 按 symbol 隔离存储。
    """
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if symbol:
            # 读取现有完整状态，更新当前 symbol 的部分
            all_states: dict[str, Any] = {}
            if _STATE_FILE.exists():
                try:
                    all_states = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                    if not isinstance(all_states, dict):
                        all_states = {}
                except (json.JSONDecodeError, OSError):
                    all_states = {}
            all_states[symbol] = state
            _STATE_FILE.write_text(json.dumps(all_states, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        _logger.debug("Stage state save failed: %s", exc)
