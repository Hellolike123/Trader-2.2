"""Trader shared modules — real library (no upward dependency on scripts/).

ADR-001: pipeline / signal_tracker / market_env / calibrator / self_calibration
have been colocated into this package. `trader_shared` is now importable as a
standalone library: no runtime dependence on scripts/, no importlib hacks.

Usage:
    from trader_shared import write_stock, log, assess, run
    from trader_shared.pipeline import write_stock
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── 兼容层（过渡期）：给尚未迁移的 scripts/ 工具留 path ──────────────
_scripts = Path(__file__).resolve().parent.parent / "scripts"
if _scripts.exists() and str(_scripts) not in sys.path:
    sys.path.append(str(_scripts))

# ── 静态导入子模块（ADR-001 收编后，全部在包内，无向上依赖）─────────
import trader_shared.pipeline as _pipeline
import trader_shared.signal_tracker as _tracker
import trader_shared.market_env as _market_env
import trader_shared.calibrator as _calibrator
import trader_shared.signal_contract as _signal_contract
import trader_shared.signal_store as _signal_store
import trader_shared.signal_utils as _signal_utils
import trader_shared.interfaces as _interfaces
import trader_shared.fetchers as _fetchers
import trader_shared.plugin_registry as _plugin_registry
import trader_shared.async_utils as _async_utils

# ── 公开 API：从各模块暴露已知属性（缺失则跳过，不致命）────────────
_PUBLIC_ATTRS = {
    # pipeline
    "write_stock": _pipeline, "write_market": _pipeline, "write_positions": _pipeline,
    "add_warning": _pipeline, "clear_old_warnings": _pipeline, "get_stock_weight": _pipeline,
    "get_market_level": _pipeline, "get_market_note": _pipeline, "get_full_market": _pipeline,
    "conflicting_signals": _pipeline, "read": _pipeline,
    # signal_tracker
    "log": _tracker, "log_safe": _tracker, "fill": _tracker, "fill_by_target": _tracker,
    "load_recent": _tracker, "stats": _tracker, "stats_by_type": _tracker, "stable_id": _tracker,
    # market_env
    "assess": _market_env, "refresh": _market_env, "env_note_for": _market_env,
    "get_env_for_skill": _market_env, "resolve_board_index": _market_env,
    # calibrator
    "run": _calibrator, "generate_suggestions": _calibrator,
}
for _name, _mod in _PUBLIC_ATTRS.items():
    _val = getattr(_mod, _name, None)
    if _val is not None:
        globals()[_name] = _val

# 模块级 re-export（确保 `from trader_shared import signal_contract` 等可用）
signal_contract = _signal_contract
signal_store = _signal_store
signal_utils = _signal_utils
interfaces = _interfaces
fetchers = _fetchers
plugin_registry = _plugin_registry
async_utils = _async_utils

# ── 过渡期裸名别名：tests / 旧脚本仍用 `from signal_tracker import ...` ──
# 收编后这些模块在 trader_shared/ 下，裸名不再可导入。注册 sys.modules 别名续命，
# 统一迁移测试留待后续测试基建步。
for _bare in ("pipeline", "signal_tracker", "market_env", "calibrator", "self_calibration"):
    _mod = sys.modules.get(f"trader_shared.{_bare}")
    if _mod is not None:
        sys.modules.setdefault(_bare, _mod)

__all__ = [
    # pipeline
    "write_stock", "write_market", "write_positions", "add_warning",
    "clear_old_warnings", "get_stock_weight", "get_market_level",
    "get_market_note", "get_full_market", "conflicting_signals", "read",
    # signal_tracker
    "log", "log_safe", "fill", "fill_by_target", "load_recent",
    "stats", "stats_by_type", "stable_id",
    # market_env
    "assess", "refresh", "env_note_for", "get_env_for_skill", "resolve_board_index",
    # calibrator
    "run", "generate_suggestions",
    # signal modules
    "signal_contract", "signal_store", "signal_utils",
    # DI & plugins
    "interfaces", "fetchers", "plugin_registry", "async_utils",
    # version
    "__version__",
]

__version__ = "0.6.0"
