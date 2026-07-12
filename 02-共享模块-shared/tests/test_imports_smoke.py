"""Pure import smoke test — no network / market-data dependency.

Validates that `trader_shared` can be imported as a real library
(all submodules resolve via package-relative imports, no upward
dependency on scripts/), and that the public re-export API stays stable.

This is the floor of the test harness introduced alongside ADR-001;
it runs in <1s and guards against accidental import regressions during
the refactor of `refactor/trader-architecture`.
"""
import importlib

SHARED_MODULES = [
    "trader_shared",
    "trader_shared.pipeline",
    "trader_shared.signal_tracker",
    "trader_shared.market_env",
    "trader_shared.calibrator",
    "trader_shared.self_calibration",
    "trader_shared.fusion_core",
    "trader_shared.structure_core",
    "trader_shared.cache_utils",
    "trader_shared.stage_positioning",
    "trader_shared.hmm_regime",
    "trader_shared.volume_profile",
    "trader_shared.time_window_detector",
    "trader_shared.bayesian_fusion",
    "trader_shared.chan_core",
    "trader_shared.wyckoff_core",
    "trader_shared.momentum_core",
    "trader_shared.decision_core",
    "trader_shared.main_force",
    "trader_shared.mid_key_prices",
    "trader_shared.plugin_registry",
    "trader_shared.report_core",
]


def test_shared_modules_importable():
    for mod in SHARED_MODULES:
        importlib.import_module(mod)


def test_public_api_reexported():
    import trader_shared
    for name in ("write_stock", "log", "assess", "run"):
        assert hasattr(trader_shared, name), f"trader_shared.{name} missing (public API broken)"
