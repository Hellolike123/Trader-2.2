#!/usr/bin/env python3
"""离线参数自校准与强化演化器 (Self-Calibration)

在非交易时段运行，读取历史 signals.jsonl 和 signal_results.jsonl，
并根据中证 1000 历史指数收益率序列计算当日对应的 HMM 大势状态（Bull/Bear/Range）。
采用 WinRate * ProfitFactor Blended 综合效能评分模型作为适应度函数，
分别对 global、bull、bear、range 进行离线参数搜优，并将分层参数结构化写入本地配置。

用法（盘后/周末运行）:
    python3 02-共享模块-shared/scripts/self_calibration.py

输出:
    ~/.trader/calibrated_params.json  — 更新后的嵌套分层最优参数
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# ── 自动补齐共享模块路径（保证在独立/Hermes 环境下能正确 import） ────────────────
_SHARED_ROOT = Path(__file__).resolve().parents[1]
for _p in (_SHARED_ROOT / "scripts", _SHARED_ROOT / "01-行情数据-market-data", _SHARED_ROOT / "02-候选逻辑-candidate"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ── 默认路径 ─────────────────────────────────────────────────────────────────
TRADER_DIR = Path.home() / ".trader"
SIGNALS_FILE = TRADER_DIR / "signals.jsonl"
RESULTS_FILE = TRADER_DIR / "signal_results.jsonl"
CALIBRATED_FILE = TRADER_DIR / "calibrated_params.json"

# ── 参数搜索空间（微幅扰动，不脱离合理范围）────────────────────────────────
PARAM_SPACE = {
    "zone_width":      [0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.25],
    "confirm_buffer":  [0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30],
    "stop_buffer":     [0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00],
}

# ── 默认参数 ─────────────────────────────────────────────────────────────────
DEFAULT_PARAMS = {
    "zone_width": 1.0,
    "confirm_buffer": 1.0,
    "stop_buffer": 1.0,
}


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """安全加载 JSONL 文件。"""
    records = []
    if not path.exists():
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _extract_outcomes(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """从 signal_results.jsonl 提取信号结果字典。

    Returns:
        {signal_id: {"won": bool, "return_pct": float, ...}}
    """
    outcomes: Dict[str, Dict[str, Any]] = {}
    for r in results:
        sid = r.get("signal_id") or r.get("id")
        if not sid:
            continue
        outcome = r.get("outcome", r.get("status", ""))
        return_pct = float(r.get("return_pct", r.get("pnl_pct", 0.0)) or 0.0)
        won = outcome in ("win", "profit", "triggered_profit") or return_pct > 0
        outcomes[sid] = {"won": won, "return_pct": return_pct, "outcome": outcome}
    return outcomes


def _load_historical_regimes(signals: List[Dict[str, Any]]) -> Dict[str, str]:
    """根据历史大盘 K 线数据，预计算并生成信号发布日期 trade_date -> HMM_Regime 的映射字典。"""
    regimes: Dict[str, str] = {}
    dates = sorted(list(set(sig["trade_date"] for sig in signals if "trade_date" in sig)))
    if not dates:
        return regimes

    try:
        from trader_shared.config import INDEX_CODE
        from trader_shared.data_provider import get_provider
        from light_data import normalize_bars
        from hmm_regime import detect_regime

        provider = get_provider()
        sec = provider.resolve_security(INDEX_CODE)
        # 拉取 250 日（约一年）日线数据以完全覆盖回测周期
        raw_bars = provider.fetch_kline(sec, scale="240", datalen=250)
        bars = normalize_bars(raw_bars) if raw_bars else []
    except Exception:
        bars = []

    if not bars:
        for d in dates:
            regimes[d] = "range"
        return regimes

    closes = [float(b["close"]) for b in bars if b.get("close") is not None]
    dates_index = [b["date"] for b in bars if b.get("close") is not None]

    for d in dates:
        if d not in dates_index:
            regimes[d] = "range"
            continue

        idx = dates_index.index(d)
        # 回看该交易日前 90 个交易日的收盘价算大势收益率
        slice_closes = closes[max(0, idx - 90):idx + 1]
        if len(slice_closes) >= 5:
            returns = [(slice_closes[i] - slice_closes[i-1]) / slice_closes[i-1] for i in range(1, len(slice_closes))]
            try:
                hmm_res = detect_regime(returns)
                regimes[d] = hmm_res.get("state_en", "range")
            except Exception:
                regimes[d] = "range"
        else:
            regimes[d] = "range"

    return regimes


def _simulate_performance(
    signals: List[Dict[str, Any]],
    outcomes: Dict[str, Dict[str, Any]],
    params: Dict[str, float],
    target_regime: Optional[str] = None,
    historical_regimes: Optional[Dict[str, str]] = None,
) -> float:
    """模拟给定参数组合下的历史综合效能得分。

    采用 WinRate * ProfitFactor 作为 blended 评估指标，
    综合拦截亏损信号与放行盈利信号的模拟 PnL。
    """
    if not outcomes:
        return 0.5

    zone_w = params["zone_width"]
    conf_b = params["confirm_buffer"]
    stop_b = params["stop_buffer"]

    sim_returns: List[float] = []

    for sig in signals:
        sid = sig.get("signal_id") or sig.get("id")
        if not sid or sid not in outcomes:
            continue

        # 大势状态隔离校验
        if target_regime and historical_regimes:
            date = sig.get("trade_date")
            if not date or historical_regimes.get(date) != target_regime:
                continue

        outcome = outcomes[sid]
        r_actual = outcome["return_pct"]

        trigger_pct = float(sig.get("trigger_price_pct", 0.0) or 0.0)

        # 模拟过滤逻辑
        # A. 高触发价位 + 宽 confirm_buffer = 拦截高位假突破信号
        if trigger_pct > 0.05 and conf_b > 1.05:
            # 过滤成功，计为 0.0（避免亏损或错失盈利）
            sim_returns.append(0.0)
            continue

        # B. 低触发价位 + 宽 zone_width = 低吸区域放大捕获
        if trigger_pct < -0.03 and zone_w > 1.05:
            sim_returns.append(r_actual)
            continue

        # C. 正常状态：原样计入
        sim_returns.append(r_actual)

    if not sim_returns:
        return 0.0

    # 统计指标
    wins = [r for r in sim_returns if r > 0.0]
    losses = [abs(r) for r in sim_returns if r < 0.0]

    win_rate = len(wins) / len(sim_returns)
    total_gains = sum(wins)
    total_losses = sum(losses)

    # 加上平滑项 eps，在极小样本下防分母为零，同时惩罚样本不足的情况
    eps = 0.5
    profit_factor = (total_gains + eps) / (total_losses + eps)

    # Blended Score = 胜率 * 盈亏比
    return win_rate * profit_factor


def calibrate(
    n_trials: int = 150,
    verbose: bool = True,
) -> Dict[str, Dict[str, float]]:
    """执行离线多大势分层参数校准。

    Args:
        n_trials: 随机搜索试验次数
        verbose:  是否打印进度

    Returns:
        {regime_name: {zone_width, confirm_buffer, stop_buffer}}
    """
    signals = _load_jsonl(SIGNALS_FILE)
    results = _load_jsonl(RESULTS_FILE)
    outcomes = _extract_outcomes(results)

    if verbose:
        print(f"🔍 自校准开始：读取 {len(signals)} 个信号，{len(outcomes)} 个已结算结果")

    if not signals or not outcomes:
        if verbose:
            print("⚠️ 历史数据不足，所有状态初始化为默认参数")
        return {
            "global": DEFAULT_PARAMS.copy(),
            "bull": DEFAULT_PARAMS.copy(),
            "bear": DEFAULT_PARAMS.copy(),
            "range": DEFAULT_PARAMS.copy(),
        }

    # 预加载大势状态映射表
    regimes_map = _load_historical_regimes(signals)

    calibrated_results: Dict[str, Dict[str, float]] = {}

    # 需要寻优的分层大势桶
    targets = [
        ("global", None),
        ("bull", "bull"),
        ("bear", "bear"),
        ("range", "range"),
    ]

    for regime_name, target_regime in targets:
        if target_regime:
            sub_count = sum(1 for sig in signals if regimes_map.get(sig.get("trade_date")) == target_regime)
        else:
            sub_count = len(signals)

        if sub_count == 0:
            if verbose:
                print(f"  -> 大势 {regime_name:6}: 暂无样本数据，继承默认配置")
            calibrated_results[regime_name] = DEFAULT_PARAMS.copy()
            continue

        best_params = DEFAULT_PARAMS.copy()
        best_score = _simulate_performance(signals, outcomes, best_params, target_regime, regimes_map)

        for trial in range(n_trials):
            candidate = {
                "zone_width": random.choice(PARAM_SPACE["zone_width"]),
                "confirm_buffer": random.choice(PARAM_SPACE["confirm_buffer"]),
                "stop_buffer": random.choice(PARAM_SPACE["stop_buffer"]),
            }
            score = _simulate_performance(signals, outcomes, candidate, target_regime, regimes_map)
            if score > best_score:
                best_score = score
                best_params = candidate.copy()

        calibrated_results[regime_name] = best_params.copy()
        if verbose:
            print(f"  -> 大势 {regime_name:6} (样本:{sub_count:2}): 性能评分 {best_score:.3f} | zone_width={best_params['zone_width']:.2f}, confirm_buffer={best_params['confirm_buffer']:.2f}, stop_buffer={best_params['stop_buffer']:.2f}")

    return calibrated_results


def save_params(params: Dict[str, Dict[str, float]]) -> None:
    """将分层校准后的参数写入持久化配置文件。"""
    TRADER_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "version": "2.3",
        "params": params,
        "source": "self_calibration",
    }
    with open(CALIBRATED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 分层自校准参数已写入 {CALIBRATED_FILE}")


def load_calibrated_params() -> Dict[str, Any]:
    """加载已校准参数（供 structure_core.py 调用）。

    若未找到校准文件，返回默认参数字典。
    """
    if not CALIBRATED_FILE.exists():
        return {"global": DEFAULT_PARAMS.copy()}
    try:
        with open(CALIBRATED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("params", {"global": DEFAULT_PARAMS.copy()})
    except (json.JSONDecodeError, IOError):
        return {"global": DEFAULT_PARAMS.copy()}


def main() -> None:
    """CLI 入口：盘后/周末离线执行。"""
    print("=" * 60)
    print("Trader 2.3 — 嵌套分层自校准引擎")
    print("=" * 60)
    best = calibrate(n_trials=200, verbose=True)
    save_params(best)
    print("=" * 60)
    print("校准完成，交易系统将根据当前 HMM 大势自适应采用对应参数。")


if __name__ == "__main__":
    main()
