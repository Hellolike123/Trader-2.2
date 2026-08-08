"""Swallowed-exception counter for system observability (handoff D3).

把 ``except Exception: pass`` 的「静默吞掉」变成「按类型+位置计数」，
让一批沉默的错误在报告 ``_exception_summary`` 与日志中可见。

设计约束（来自 handoff §4 / §8）：
- 计数但**绝不抛出**：不改变任何控制流，不破坏数据层容错。
- 默认全局开启计数；``TRADER_EXCEPTION_TRACK=0`` 关闭。
- 只记录，不重抛、不短路业务逻辑。
"""
from __future__ import annotations

import contextlib
import os
import threading
from collections import Counter
from typing import Any

_lock = threading.Lock()
_counts: Counter[tuple[str, str]] = Counter()  # (exc_type, location) -> count

ENABLED = os.environ.get("TRADER_EXCEPTION_TRACK", "1") != "0"


def record(exc: BaseException | type, location: str = "") -> None:
    """记录一次被吞掉的异常。``exc`` 可以是实例或异常类。"""
    if not ENABLED:
        return
    name = exc.__name__ if isinstance(exc, type) else type(exc).__name__
    key = (name, location or "")
    with _lock:
        _counts[key] += 1


def collect() -> list[dict[str, Any]]:
    """返回已计数异常的有序列表（count 降序）。空则 []。"""
    with _lock:
        if not _counts:
            return []
        items = [
            {"type": t, "location": loc, "count": c}
            for (t, loc), c in _counts.items()
        ]
    items.sort(key=lambda d: (-d["count"], d["location"], d["type"]))
    return items


def reset() -> None:
    """清空计数。每次 build_report 开头调用，保证报告级隔离。"""
    with _lock:
        _counts.clear()


@contextlib.contextmanager
def suppress_and_count(location: str):
    """等价 ``contextlib.suppress(Exception)``，但额外计数被吞异常。

    用于新增代码；既有 ``except Exception: pass`` 也可就地改为
    ``except Exception as e: record(e, "module.func")``。
    """
    try:
        yield
    except Exception as e:  # noqa: BLE001 — 故意兜底并计数
        record(e, location)
