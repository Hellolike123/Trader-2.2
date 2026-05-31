# Packaging Script Refactoring

## Overview

Modify `pack_all.py` to comply with Hermes skill spec and include new architecture modules.

## Requirements

### 1. Output Directory
- Keep `03-安装包-dist/releases/MMDD-HHMM/`
- Don't rename

### 2. ZIP Structure (Hermes Spec)

ZIP root must have:
- `_meta.json` — name, version, description, shared_bundle
- `SKILL.md` — skill description
- `HERMES.md` — optional
- `scripts/` — all Python files

Example:
```
trader.zip/
├── _meta.json
├── SKILL.md
├── HERMES.md
└── scripts/
    ├── pipeline.py
    ├── signal_tracker.py
    ├── market_env.py
    ├── calibrator.py
    ├── run_analysis.py
    ├── final_report.py
    ├── final_t0.py
    ├── final_review.py
    └── trader_shared/
        ├── __init__.py
        ├── light_data.py
        ├── config.py
        ├── interfaces.py      ← NEW
        ├── fetchers.py        ← NEW
        ├── async_utils.py     ← NEW
        ├── plugin_registry.py ← NEW
        └── plugins/
            ├── __init__.py
            ├── base.py
            ├── chan_plugin.py
            ├── wyckoff_plugin.py
            └── momentum_plugin.py
```

### 3. _meta.json Format

```json
{
  "name": "trader",
  "version": "2.4.0",
  "description": "A股单票分析 + 选股池管理",
  "shared_bundle": "abc123def456"
}
```

### 4. Post-Packaging Verification

- Check ZIP structure matches Hermes spec
- Check _meta.json exists and is valid
- Check scripts/ contains all required files

## Verification

```bash
python3 02-共享模块-shared/scripts/pack_all.py --no-install
python3 -m pytest 02-共享模块-shared/tests/
```

## Success Criteria

- ZIP structure matches Hermes spec
- _meta.json is valid JSON with required fields
- All new architecture modules included
- All tests pass
