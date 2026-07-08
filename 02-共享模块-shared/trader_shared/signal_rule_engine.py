"""信号组合规则引擎（YAML 驱动）。

加载 signal_rules.yml，在融合层统一信号之上叠加组合规则。
默认关闭（SIGNAL_RULES_ENABLED=False），安全过渡。

Usage:
    from trader_shared.signal_rule_engine import load_rules, apply_rules
    rules = load_rules()
    adjusted = apply_rules(rules, signals_detail)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_RULES_PATH: str | None = None  # lazy calc
_RULES_CACHE: list[dict[str, Any]] | None = None


def _rules_file() -> str:
    global _RULES_PATH
    if _RULES_PATH is None:
        _RULES_PATH = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "signal_rules.yml",
        )
    return _RULES_PATH


def load_rules() -> list[dict[str, Any]]:
    """加载 signal_rules.yml，返回已启用的规则列表（按 priority 降序）。"""
    global _RULES_CACHE
    if _RULES_CACHE is not None:
        return _RULES_CACHE

    path = _rules_file()
    if not os.path.exists(path):
        _RULES_CACHE = []
        return _RULES_CACHE

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    all_rules = raw.get("rules", [])
    _RULES_CACHE = sorted(
        [r for r in all_rules if r.get("enabled", True)],
        key=lambda r: r.get("priority", 0),
        reverse=True,
    )
    return _RULES_CACHE


def _active_signal_types(signals_detail: dict[str, Any]) -> list[str]:
    """从 signals_detail 提取活跃信号类型列表。"""
    types: list[str] = []
    for key, sig in signals_detail.items():
        if not isinstance(sig, dict):
            continue
        st = sig.get("signal_type", "")
        if st:
            types.append(st)
    return types


def apply_rules(
    rules: list[dict[str, Any]],
    signals_detail: dict[str, Any],
) -> dict[str, Any]:
    """以当前活跃信号匹配规则，返回需应用的调整。

    Returns:
        {"direction_override": int|None, "confidence_delta": float, "matched": [str]}
        matched 记录触发规则名，供日志使用。
    """
    active = _active_signal_types(signals_detail)
    result: dict[str, Any] = {
        "direction_override": None,
        "confidence_delta": 0.0,
        "matched": [],
    }

    for rule in rules:
        condition = rule.get("condition", {})
        all_of = condition.get("all_of", [])
        any_of = condition.get("any_of", [])

        if all_of:
            if not set(all_of).issubset(set(active)):
                continue
        if any_of:
            if not set(any_of).intersection(set(active)):
                continue
        # 既无 all_of 也无 any_of → 跳过无效规则
        if not all_of and not any_of:
            continue

        action = rule.get("action", {})
        if "direction_override" in action and action["direction_override"] is not None:
            result["direction_override"] = action["direction_override"]
        result["confidence_delta"] += action.get("confidence_delta", 0.0)
        result["matched"].append(rule.get("name", "unnamed"))

    # clamp confidence delta
    result["confidence_delta"] = max(-0.3, min(0.3, result["confidence_delta"]))
    return result


def clear_cache() -> None:
    """清除规则缓存（测试用）。"""
    global _RULES_CACHE
    _RULES_CACHE = None
