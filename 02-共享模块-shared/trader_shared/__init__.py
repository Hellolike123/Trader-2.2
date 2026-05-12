"""Trader shared modules - lazy load from scripts/ or from installed package.

Usage:
    from trader_shared import write_stock, log, assess, run
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

# ── path helpers ──

def _find_scripts_dir() -> Path | None:
    """Find the scripts/ directory at runtime across repo/zip/Hermes layouts."""
    _here = Path(__file__).resolve().parent

    candidates = [
        # Hermes/zip layout: .../<skill>/scripts/trader_shared/__init__.py
        _here.parent,
        # repo layout: .../02-共享模块-shared/trader_shared/__init__.py
        _here.parent.parent / "scripts",
        # current working dir guesses
        Path.cwd() / "scripts",
        Path.cwd() / "02-共享模块-shared" / "scripts",
    ]

    # walk upwards and try sibling scripts directories
    p = _here
    for _ in range(8):
        candidates.append(p / "scripts")
        candidates.append(p.parent / "scripts")
        p = p.parent

    seen: set[str] = set()
    for c in candidates:
        try:
            scripts = c.resolve()
        except Exception:
            continue
        key = str(scripts)
        if key in seen:
            continue
        seen.add(key)
        if scripts.exists() and (scripts / "pipeline.py").exists() and (scripts / "market_env.py").exists():
            return scripts

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
        mod = get_pipeline()
        if mod is None:
            raise AttributeError(f"trader_shared.{name}: pipeline module not loaded")
        return getattr(mod, name)
    # signal_tracker
    if name in _TRACKER_ATTRS:
        mod = get_signal_tracker()
        if mod is None:
            raise AttributeError(f"trader_shared.{name}: signal_tracker module not loaded")
        return getattr(mod, name)
    # market_env
    if name in _MARKET_ATTRS:
        mod = get_market_env()
        if mod is None:
            raise AttributeError(f"trader_shared.{name}: market_env module not loaded")
        return getattr(mod, name)
    # calibrator
    if name in _CALIBRATOR_ATTRS:
        mod = get_calibrator()
        if mod is None:
            raise AttributeError(f"trader_shared.{name}: calibrator module not loaded")
        return getattr(mod, name)
    raise AttributeError(f"module 'trader_shared' has no attribute '{name}'")


# ── version ──

__version__ = "0.6.0"
