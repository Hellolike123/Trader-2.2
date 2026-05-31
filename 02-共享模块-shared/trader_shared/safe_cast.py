"""安全数据提取原语 — 统一处理 None/空序列/类型转换。

用法:
    from trader_shared.safe_cast import safe_float, safe_dict, safe_max, safe_min, require_positive
"""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


def safe_float(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    """从 dict 安全提取浮点值。

    None/缺失/类型错误时返回 default，合法 0.0 不被吞。

    Args:
        d: 源字典
        key: 要提取的键
        default: 值缺失时的默认值

    Returns:
        float 值
    """
    val = d.get(key)
    if val is None:
        return default
    try:
        result = float(val)
        return result
    except (TypeError, ValueError):
        return default


def safe_dict(d: dict[str, Any], key: str) -> dict[str, Any]:
    """从 dict 安全提取子 dict。

    None/缺失/非 dict 时返回 {}。

    Args:
        d: 源字典
        key: 要提取的键

    Returns:
        dict 值，保证非 None
    """
    val = d.get(key)
    if isinstance(val, dict):
        return val
    return {}


def safe_max(iterable: Any, default: T | None = None) -> Any:
    """安全求最大值，空序列返回 default。

    Args:
        iterable: 可迭代对象
        default: 空序列时的默认值

    Returns:
        最大值或 default
    """
    try:
        items = list(iterable)
        return max(items) if items else default
    except (TypeError, ValueError):
        return default


def safe_min(iterable: Any, default: T | None = None) -> Any:
    """安全求最小值，空序列返回 default。

    Args:
        iterable: 可迭代对象
        default: 空序列时的默认值

    Returns:
        最小值或 default
    """
    try:
        items = list(iterable)
        return min(items) if items else default
    except (TypeError, ValueError):
        return default


def require_positive(value: Any, name: str = "value") -> float | None:
    """要求值为正数，否则返回 None。

    Args:
        value: 要检查的值
        name: 用于日志的变量名（当前未使用，预留）

    Returns:
        float(value) 如果 > 0，否则 None
    """
    if value is None:
        return None
    try:
        v = float(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None
