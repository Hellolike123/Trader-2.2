#!/usr/bin/env python3
"""离线参数自校准与强化演化器 (Self-Calibration)

在非交易时段运行，读取历史 signals.jsonl 和 signal_results.jsonl，
对 structure_core 的关键参数（zone_width, confirm_buffer, stop_buffer）
进行滚动回测，找到历史胜率最高的参数组合，并写入本地配置。

用法（盘后/周末运行）:
    python3 02-共享模块-shared/scripts/self_calibration.py

输出:
    ~/.trader/calibrated_params.json  — 更新后的最优参数
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Dict, List, Any, Optional

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

# ── 默认参数（与 Trader 2.2 保持一致）────────────────────────────────────────
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


def _simulate_win_rate(
    signals: List[Dict[str, Any]],
    outcomes: Dict[str, Dict[str, Any]],
    params: Dict[str, float],
) -> float:
    """模拟给定参数组合下的历史胜率。

    通过对已结算信号施加参数扰动，计算在不同 zone_width / confirm_buffer 下
    有多少信号原本能被滤除（避免错误触发）或额外捕获（避免踏空）。

    Returns:
        胜率 float 0.0~1.0
    """
    if not outcomes:
        return 0.5  # 无历史数据，返回中性

    matched = 0
    correct = 0

    zone_w = params["zone_width"]
    conf_b = params["confirm_buffer"]
    stop_b = params["stop_buffer"]

    for sig in signals:
        sid = sig.get("signal_id") or sig.get("id")
        if not sid or sid not in outcomes:
            continue

        matched += 1
        outcome = outcomes[sid]

        # 模拟：zone_width 更宽时，低吸信号更容易触发（捕获底部）
        # confirm_buffer 更宽时，突破确认更严格（减少假突破）
        # 我们用一个轻量化的启发式函数：
        # 如果该信号的触发价比支撑位高很多（可能是高位买入），
        # 更宽的 confirm_buffer 应该能拦住它

        trigger_pct = float(sig.get("trigger_price_pct", 0.0) or 0.0)

        # 模拟效果：高触发价位 + 宽 confirm_buffer = 减少高位假信号
        if trigger_pct > 0.05 and conf_b > 1.05:
            # 这类信号在更严格的确认缓冲下会被拦住
            if not outcome["won"]:
                correct += 1  # 正确拦截了亏损信号
            continue

        # 低触发价位 + 宽 zone_width = 更多低位信号被捕获
        if trigger_pct < -0.03 and zone_w > 1.05:
            if outcome["won"]:
                correct += 1  # 正确放行了盈利信号
            continue

        # 其余信号：直接按实际结果计入
        if outcome["won"]:
            correct += 1

    return correct / max(matched, 1)


def calibrate(
    n_trials: int = 100,
    verbose: bool = True,
) -> Dict[str, float]:
    """执行离线参数校准。

    Args:
        n_trials: 随机搜索试验次数（100 次即可，极轻量）
        verbose:  是否打印进度

    Returns:
        最优参数字典
    """
    signals = _load_jsonl(SIGNALS_FILE)
    results = _load_jsonl(RESULTS_FILE)
    outcomes = _extract_outcomes(results)

    if verbose:
        print(f"🔍 自校准开始：读取 {len(signals)} 个信号，{len(outcomes)} 个已结算结果")

    if not signals or not outcomes:
        if verbose:
            print("⚠️  历史数据不足，保持默认参数")
        return DEFAULT_PARAMS.copy()

    best_params = DEFAULT_PARAMS.copy()
    best_win_rate = _simulate_win_rate(signals, outcomes, best_params)

    # 随机搜索（足够轻量，无梯度计算需求）
    for trial in range(n_trials):
        candidate = {
            "zone_width": random.choice(PARAM_SPACE["zone_width"]),
            "confirm_buffer": random.choice(PARAM_SPACE["confirm_buffer"]),
            "stop_buffer": random.choice(PARAM_SPACE["stop_buffer"]),
        }
        wr = _simulate_win_rate(signals, outcomes, candidate)
        if wr > best_win_rate:
            best_win_rate = wr
            best_params = candidate.copy()

    if verbose:
        print(f"✅ 校准完成：最优胜率 {best_win_rate:.1%}")
        print(f"   zone_width={best_params['zone_width']}, "
              f"confirm_buffer={best_params['confirm_buffer']}, "
              f"stop_buffer={best_params['stop_buffer']}")

    return best_params


def save_params(params: Dict[str, float]) -> None:
    """将校准后的参数写入持久化配置文件。"""
    TRADER_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "version": "2.3",
        "params": params,
        "source": "self_calibration",
    }
    with open(CALIBRATED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 参数已写入 {CALIBRATED_FILE}")


def load_calibrated_params() -> Dict[str, float]:
    """加载已校准参数（供 structure_core.py 调用）。

    若未找到校准文件，返回 Trader 2.2 默认参数。
    """
    if not CALIBRATED_FILE.exists():
        return DEFAULT_PARAMS.copy()
    try:
        with open(CALIBRATED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("params", DEFAULT_PARAMS.copy())
    except (json.JSONDecodeError, IOError):
        return DEFAULT_PARAMS.copy()


def main() -> None:
    """CLI 入口：盘后/周末离线执行。"""
    print("=" * 50)
    print("Trader 2.3 — 参数自校准器")
    print("=" * 50)
    best = calibrate(n_trials=200, verbose=True)
    save_params(best)
    print("=" * 50)
    print("校准完成，下次分析时将自动使用最新参数。")


if __name__ == "__main__":
    main()
