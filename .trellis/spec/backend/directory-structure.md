# Directory Structure

> How backend code is organized in this project.

---

## Overview

This is an A-stock trading decision support system (Trader 2.4). The codebase is organized into two top-level numbered directories: **shared modules** (`02-共享模块-shared/`) and **skill packages** (`01-功能包-packages/`). All core computation lives in the shared `trader_shared/` Python package; each skill (trader, t0, review) is a thin wrapper that imports from it.

---

## Directory Layout

```
Trader 2.4/
├── 01-功能包-packages/                    # Skill packages (Hermes-compatible)
│   ├── 00-系统工具/                       # System-level tooling (pack_all tests)
│   ├── trader/                            # Single-stock analysis + pool management
│   │   ├── SKILL.md                       # LLM prompt (injected into context)
│   │   ├── HERMES.md                      # Hermes framework instructions
│   │   ├── _meta.json                     # Skill metadata (name/version)
│   │   ├── references/                    # commands.md, output-contract.md (absolute truth)
│   │   ├── scripts/                       # Entry points + local config
│   │   │   ├── final_report.py            # Single-stock analysis entry
│   │   │   ├── final_pool.py              # Pool management entry
│   │   │   ├── run_analysis.py            # Core analysis model (build_report)
│   │   │   ├── config.py                  # Per-skill config overrides
│   │   │   ├── validate_output.py         # Output contract validator
│   │   │   └── self_check.py              # Format + logic self-check
│   │   └── tests/                         # Skill-specific tests
│   ├── t0/                                # Intraday T0 monitoring
│   │   ├── scripts/final_t0.py            # T0 entry point
│   │   └── tests/
│   └── review/                            # Post-market review + portfolio rotation
│       ├── scripts/
│       │   ├── final_review.py            # Single-stock review entry
│       │   ├── final_portfolio.py         # Portfolio rotation entry
│       │   └── final_tracker.py           # Signal tracking entry
│       └── tests/
├── 02-共享模块-shared/                     # Shared computation modules
│   ├── 01-行情数据-market-data/            # Data layer
│   │   └── light_data.py                  # THE ONLY data fetch entry point
│   ├── 02-候选逻辑-candidate/              # Candidate analysis stubs
│   │   └── candidate_core.py              # Thin re-export (actual impl in trader_shared/)
│   ├── 03-输出校验-contracts/              # Signal contract validation
│   │   ├── signal_contract.py             # v1 signal schema validator
│   │   └── signal_store.py               # JSONL signal persistence
│   ├── trader_shared/                     # THE core Python package (pip install -e .)
│   │   ├── __init__.py                    # Lazy-load router (pipeline/tracker/market_env)
│   │   ├── config.py                      # ALL system constants centralized here
│   │   ├── models.py                      # TypedDict data models (BarData, QuoteData, etc.)
│   │   ├── light_data.py                  # Data fetch + HA failover (canonical copy)
│   │   ├── structure_core.py              # Price structure analysis (build_structure_context)
│   │   ├── decision_core.py               # Status determination (status_layers, score_for)
│   │   ├── chan_core.py                   # Chanlun analysis (fractals/strokes/zones)
│   │   ├── wyckoff_core.py               # Wyckoff analysis (Spring/Upthrust)
│   │   ├── momentum_core.py              # RSI/MACD/ADX/Bollinger
│   │   ├── fusion_core.py                # Decision fusion layer (merge_decisions)
│   │   ├── candidate_core.py             # Thin re-export stub
│   │   ├── signal_contract.py            # Signal schema + validation
│   │   ├── signal_store.py              # Atomic JSONL persistence
│   │   ├── signal_utils.py              # UUID generation, normalization
│   │   ├── cache_utils.py               # File-based cache with TTL
│   │   ├── data_provider.py             # Pluggable DataProvider protocol
│   │   ├── safe_cast.py                 # Safe data extraction primitives
│   │   ├── hmm_regime.py                # HMM regime detection (numpy-only)
│   │   ├── bayesian_fusion.py           # Bayesian product-rule fusion
│   │   ├── volume_profile.py            # Intraday volume profile (POC/VA)
│   │   ├── chip_distribution.py         # Dynamic chip distribution
│   │   ├── stage_positioning.py         # Four-stage positioning model
│   │   ├── schema/v1.py                 # Output contract JSON Schema
│   │   └── ... (40+ modules total)
│   ├── scripts/                           # Cross-skill pipeline scripts
│   │   ├── pipeline.py                    # State pipeline (write_stock, read, etc.)
│   │   ├── market_env.py                 # Market environment assessment
│   │   ├── signal_tracker.py             # Signal lifecycle tracker
│   │   ├── self_calibration.py           # Offline parameter calibration
│   │   ├── calibrator.py                 # Backtest calibration
│   │   ├── signal_migration_tool.py      # Legacy signal migration
│   │   └── pack_all.py                   # Build + package all skill zips
│   └── tests/                             # 485+ core computation tests
├── docs/                                  # Design docs, issue tracking
├── scripts/                               # Top-level utility scripts
├── trader.py                              # CLI entry point
└── pyproject.toml                         # Package config (pip install -e .)
```

---

## Module Organization Rules

### Where does business logic live?

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Data fetch | `trader_shared/light_data.py` | THE ONLY entry point for market data. All skills call this. |
| Data models | `trader_shared/models.py` | TypedDict definitions (BarData, QuoteData, CandidateLevels, etc.) |
| Core computation | `trader_shared/*.py` | All analysis algorithms (chanlun, wyckoff, momentum, fusion, etc.) |
| State management | `scripts/pipeline.py` | Stock/market/position state read/write |
| Skill entry points | `01-功能包-packages/<skill>/scripts/final_*.py` | CLI entry + output rendering |
| Skill config | `01-功能包-packages/<skill>/scripts/config.py` | Per-skill constant overrides |
| Tests | `02-共享模块-shared/tests/` and `01-功能包-packages/<skill>/tests/` | pytest test files |

### Import path resolution

All skill scripts use `sys.path.insert()` to resolve shared modules. The canonical pattern:

```python
# In any skill script (e.g., run_analysis.py)
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Then import from trader_shared
from trader_shared.light_data import to_float, fetch_quote
from trader_shared.config import LOOKBACK_DAYS
```

For scripts in `02-共享模块-shared/scripts/`, the path resolution walks up the tree:

```python
# In scripts/*.py (e.g., market_env.py)
ROOT = Path(__file__).resolve().parents[2]  # → 02-共享模块-shared/
for p in (ROOT / "01-行情数据-market-data", ROOT / "02-候选逻辑-candidate", ROOT / "scripts"):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))
```

---

## Naming Conventions

### Files

- **Entry points**: `final_*.py` (e.g., `final_report.py`, `final_t0.py`, `final_review.py`)
- **Core modules**: `snake_case.py` (e.g., `light_data.py`, `decision_core.py`, `fusion_core.py`)
- **Tests**: `test_*.py` prefix, matching the module they test
- **Config**: `config.py` per skill, overrides from `trader_shared/config.py`
- **Contracts**: `*_contract.py` for validation, `*_store.py` for persistence

### Directories

- Top-level dirs use numbered Chinese prefixes: `01-功能包-packages/`, `02-共享模块-shared/`
- Subdirs in shared use numbered English-Chinese hybrid: `01-行情数据-market-data/`, `02-候选逻辑-candidate/`
- Skill dirs are plain English: `trader/`, `t0/`, `review/`

### Constants

- All system constants centralized in `trader_shared/config.py`
- Per-skill overrides in `<skill>/scripts/config.py`
- Environment variable overrides use `os.environ.get()` with lowercase boolean parsing

```python
# Pattern for env-var controlled features
FUSION_OVERRIDE_ENABLED: bool = os.environ.get("FUSION_OVERRIDE_ENABLED", "true").lower() in ("true", "1", "yes")
```

---

## Examples

Well-organized modules to reference:

- `trader_shared/config.py` — Centralized constants with per-skill override pattern
- `trader_shared/safe_cast.py` — Clean utility module with docstrings and type hints
- `trader_shared/models.py` — TypedDict data model definitions
- `01-功能包-packages/trader/scripts/run_analysis.py` — Skill entry point with graceful degradation
- `02-共享模块-shared/tests/test_decision_core.py` — Test file following project conventions
