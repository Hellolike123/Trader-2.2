"""Trader shared modules - lazy load from scripts/ or from installed package.

Usage:
    from trader_shared import write_stock, log, assess, run
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# ── path helpers ──

def _find_scripts_dir() -> Path | None:
    """Find the scripts/ directory at runtime."""
    candidates: list[Path] = []
    # 1. scripts relative to this __file__ (installed: scripts is not here)
    _here = Path(__file__).resolve().parent
    for _base in (
        _here,
        _here.parent.parent.parent.parent.parent,
        Path.cwd(),
        Path.cwd() / "02-共享模块-shared",
        _here / ".." / ".." / ".." / "..",
    ):
        _b = _base.resolve() if hasattr(_base, "resolve") else _base
        scripts = _b / "scripts"
        if scripts.exists() and (scripts / "pipeline.py").exists():
            return scripts
    # 2. sibling scripts dirs
    for p in (
        Path.cwd() / "02-共享模块-shared",
    ):
        s = p / "scripts"
        if s.exists():
            return s
    # 3. relative to __file__ going up 4 levels (src layout)
    _base = Path(__file__).resolve()
    for _ in range(5):
        scripts = _base / "scripts"
        if scripts.exists() and (scripts / "pipeline.py").exists():
            return scripts
        _base = _base.parent
    return None


# ── pip-installed package check ──

def _load_from_installed(name: str):
    """Try loading from a pip-installed trader_shared package."""
    try:
        mod = importlib.import_module(f".{name}", __name__)
        return mod
    except (ImportError, ModuleNotFoundError):
        return None


# ── caches ──

_pipelines: dict[str, object] = {}
_tracker: object | None = None
_market_env: object | None = None
_calibrator: object | None = None

# ── lazy loaders ──

def _load_script(name: str):
    """Load a module from scripts/ via importlib."""
    cache_key = name
    if cache_key in _pipelines:
        return _pipelines[cache_key]
    scripts = _find_scripts_dir()
    if scripts is None:
        raise RuntimeError(f"trader_shared: cannot find scripts/ directory for module '{name}'")
    mod_path = scripts / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"trader_shared_{name}", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"trader_shared: cannot load module '{name}' from {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    # Pre-register in sys.modules so intra-module imports work
    sys.modules[f"trader_shared_{name}"] = mod
    spec.loader.exec_module(mod)
    _pipelines[cache_key] = mod
    return mod


def get_pipeline() -> object:
    """Lazy load pipeline module (from scripts/)."""
    if "pipeline" not in _pipelines:
        _pipelines["pipeline"] = _load_script("pipeline")
    return _pipelines["pipeline"]


def get_signal_tracker() -> object:
    """Lazy load signal_tracker module (from scripts/)."""
    global _tracker
    if _tracker is None:
        _tracker = _load_script("signal_tracker")
    return _tracker


def get_market_env() -> object:
    """Lazy load market_env module (from scripts/)."""
    global _market_env
    if _market_env is None:
        _market_env = _load_script("market_env")
    return _market_env


def get_calibrator() -> object:
    """Lazy load calibrator module (from scripts/)."""
    global _calibrator
    if _calibrator is None:
        _calibrator = _load_script("calibrator")
    return _calibrator


# ── public attribute access via __getattr__ ──

__all__ = [
    # config
    "LOOKBACK_DAYS", "RECENT_WINDOW", "CONFIRM_BUFFER", "STOP_BUFFER", "TAKE_PROFIT_BUFFER",
    # pipeline
    "write_stock", "write_market", "write_positions", "add_warning",
    "clear_old_warnings", "get_stock_weight", "get_market_level",
    "get_market_note", "get_full_market", "conflicting_signals", "read",
    # signal_tracker
    "log", "log_safe", "fill", "fill_by_target", "load_recent",
    "stats", "stats_by_type", "stable_id",
    # market_env
    "assess", "refresh", "env_note_for", "get_env_for_skill",
    # calibrator
    "run", "generate_suggestions",
    # version
    "__version__",
]

_PIPELINE_ATTRS = {
    "write_stock", "write_market", "write_positions", "add_warning",
    "clear_old_warnings", "get_stock_weight", "get_market_level",
    "get_market_note", "get_full_market", "conflicting_signals", "read",
    # internal
    "_load", "_save",
}

_TRACKER_ATTRS = {
    "log", "log_safe", "fill", "fill_by_target", "load_recent",
    "stats", "stats_by_type", "stable_id",
    "_load_all",
}

_MARKET_ATTRS = {
    "assess", "refresh", "env_note_for", "get_env_for_skill",
}

_CALIBRATOR_ATTRS = {
    "run", "generate_suggestions",
}


def __getattr__(name: str):
    # pipeline
    if name in _PIPELINE_ATTRS:
        return getattr(get_pipeline(), name, None)
    # signal_tracker
    if name in _TRACKER_ATTRS:
        return getattr(get_signal_tracker(), name, None)
    # market_env
    if name in _MARKET_ATTRS:
        return getattr(get_market_env(), name, None)
    # calibrator
    if name in _CALIBRATOR_ATTRS:
        return getattr(get_calibrator(), name, None)
    raise AttributeError(f"module 'trader_shared' has no attribute '{name}'")


# ── version ──

__version__ = "0.6.0"
