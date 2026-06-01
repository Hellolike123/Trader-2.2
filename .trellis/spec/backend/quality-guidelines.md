# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

This project prioritizes **correctness** (financial calculations must be accurate), **resilience** (graceful degradation over crashes), and **simplicity** (no over-engineering). The codebase has 485+ tests covering core computation modules, and all changes must pass the existing test suite.

---

## Forbidden Patterns

### 1. Bare `except:` Clauses

```python
# WRONG — swallows KeyboardInterrupt, SystemExit, everything
try:
    result = float(val)
except:
    return default

# CORRECT — specific exception types
try:
    result = float(val)
except (TypeError, ValueError):
    return default
```

### 2. Direct Dict Access for Numeric Data

```python
# WRONG — can return None, "", "N/A", causing downstream TypeErrors
price = data.get("price")
total = price * quantity

# CORRECT — use safe_cast
from trader_shared.safe_cast import safe_float
price = safe_float(data, "price", default=0.0)
```

### 3. Static Hardcoded Parameters Where Dynamic Exists

```python
# WRONG — ignoring HMM/regime adjustments
stop_buffer = 0.98

# CORRECT — use regime-aware multipliers
multipliers = _theory_multipliers(regime, fusion_result, chan_result, wyckoff_result)
stop_buffer = base_stop * multipliers["stop_buffer"]
```

### 4. `assert` for Runtime Validation

```python
# WRONG — stripped in optimized mode
assert price > 0, "Price must be positive"

# CORRECT — explicit check
if price <= 0:
    return {"error": "invalid_price", "value": price}
```

### 5. Mutable Default Arguments

```python
# WRONG — shared mutable default
def process(items=[]):
    items.append(1)

# CORRECT — None sentinel
def process(items=None):
    if items is None:
        items = []
```

### 6. Importing Heavy Libraries at Module Level

```python
# WRONG — wastes ~0.8s on import even if never called
from mootdx.quotes import Q
import akshare as ak

# CORRECT — lazy load on first use
_MOOTDX_AVAILABLE = None

def _check_mootdx() -> bool:
    global _MOOTDX_AVAILABLE, Quotes
    if _MOOTDX_AVAILABLE is not None:
        return _MOOTDX_AVAILABLE
    try:
        from mootdx.quotes import Q
        Quotes = Q
        _MOOTDX_AVAILABLE = True
    except ImportError:
        _MOOTDX_AVAILABLE = False
    return _MOOTDX_AVAILABLE
```

### 7. Writing Files Without Atomic Guarantees

```python
# WRONG — can corrupt on crash
path.write_text(json.dumps(data))

# CORRECT — temp file + fsync + atomic replace
tmp = path.with_suffix(f".{os.getpid()}.tmp")
tmp.write_text(json.dumps(data), encoding="utf-8")
os.fsync(tmp.open("rb").fileno())
tmp.replace(path)
```

### 8. Using `fetch_kline(scale="240")` for Daily Data

```python
# WRONG — returns Sina minute bars, not daily bars
bars = fetch_kline(target, scale="240")

# CORRECT — use Tencent forward-adjusted daily bars
bars = fetch_qfq_daily(sec, days=300)
```

---

## Required Patterns

### 1. `from __future__ import annotations` in Every File

```python
from __future__ import annotations
```

Every Python file must start with this import. It enables PEP 604 union syntax (`X | Y`) and prevents forward reference issues.

### 2. Type Hints on Public Functions

```python
def safe_float(d: dict[str, Any], key: str, default: float = 0.0) -> float:
    """From dict safely extract float value."""
    ...

def build_structure_context(
    current: float,
    bars: list[BarData],
    change_pct: float,
    quote: QuoteData | None = None,
) -> CandidateLevels:
    ...
```

### 3. Docstrings on Public Functions

```python
def validate_bars(bars: list[dict]) -> bool:
    """Validate bar data before writing to cache.

    Checks:
    - Bar count >= 200 (enough history for MA250)
    - Each bar has close > 0
    - Dates are monotonically increasing
    """
```

### 4. Constants in `config.py`

All system-wide constants must be centralized in `trader_shared/config.py`:

```python
# From trader_shared/config.py
LOOKBACK_DAYS: int = 300
MA_PERIODS: tuple[int, ...] = (5, 10, 20, 30)
TREND_MA_LONG: int = 250
ENABLE_TRAILING_STOP: bool = True
```

Per-skill overrides go in `<skill>/scripts/config.py`:

```python
# From trader/scripts/config.py
from trader_shared.config import *  # import all defaults
LOOKBACK_DAYS = 250  # override for this skill
```

### 5. TypedDict for Data Models

```python
# From trader_shared/models.py
class BarData(TypedDict, total=False):
    """Unified K-line data row (cross-period)."""
    time: str
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: float | None
```

Use `total=False` because data may be partial (source degradation).

### 6. Graceful Degradation for Optional Features

```python
try:
    from volume_profile import assess_vp_breakout as _vp_assess
    _VP_AVAILABLE = True
except ImportError:
    _VP_AVAILABLE = False
    def _vp_assess(price, vp, is_buy_context=True):
        return {"vp_signal": "no_data", "vp_confidence": 0.5}
```

### 7. Env-Var Feature Flags

```python
FUSION_OVERRIDE_ENABLED: bool = os.environ.get("FUSION_OVERRIDE_ENABLED", "true").lower() in ("true", "1", "yes")
```

Pattern: `os.environ.get("KEY", "default").lower() in ("true", "1", "yes")`

---

## Testing Requirements

### Test File Location

- Shared module tests: `02-共享模块-shared/tests/test_*.py`
- Skill-specific tests: `01-功能包-packages/<skill>/tests/test_*.py`

### Running Tests

```bash
# All shared module tests (485+ cases)
python3 -m pytest 02-共享模块-shared/tests/

# All skill tests
python3 -m pytest 01-功能包-packages/*/tests/

# Single file
python3 -m pytest 02-共享模块-shared/tests/test_decision_core.py -v

# With keyword filter
python3 -m pytest 02-共享模块-shared/tests/ -k "signal_tracker or calibrator"
```

### Test Conventions

```python
"""decision_core.py decision core tests."""

from __future__ import annotations

import pytest

from trader_shared.decision_core import status_layers, score_for


def _make_ma_values(ma5=10.0, ma10=10.0, ma20=10.0) -> dict:
    """Helper: create MA values dict with defaults."""
    return {"ma5": ma5, "ma10": ma10, "ma20": ma20}


class TestStatusLayers:
    """Group related tests in a class."""

    def test_current_zero_returns_insufficient(self):
        """current=0 → insufficient data (descriptive test name)."""
        result = status_layers(
            current=0, support=10.0, low_zone_upper=10.1, confirm=10.5,
            hard_stop=9.5, position_ratio=0.0, change_pct=0.0,
            ma_values=_make_ma_values(), pressure_space_pct=0.0,
        )
        assert result["base_status"] == "数据不足"
```

**Rules:**
- Test file docstring: which module it tests
- Test class: groups related tests (e.g., `TestStatusLayers`)
- Test method: descriptive name explaining the scenario and expected outcome
- Helper functions: `_make_*` prefixed, provide sensible defaults
- Use `pytest.raises` for expected exceptions, not try/except in tests

### Test Coverage Expectations

| Module Type | Coverage Expectation |
|-------------|---------------------|
| Core computation (decision_core, structure_core, chan_core, etc.) | High — all branches |
| Data fetch (light_data, data_provider) | Medium — main paths + fallbacks |
| CLI entry points (final_report, final_t0) | Low — smoke test only |
| Optional modules (hmm_regime, bayesian_fusion) | Medium — core algorithm |

---

## Code Review Checklist

Before submitting changes:

- [ ] All existing tests pass (`python3 -m pytest 02-共享模块-shared/tests/`)
- [ ] New code has `from __future__ import annotations`
- [ ] Public functions have type hints and docstrings
- [ ] No bare `except:` clauses
- [ ] Numeric data access uses `safe_float()` / `safe_dict()`
- [ ] Optional module imports have fallback functions
- [ ] File writes use atomic pattern (temp + fsync + replace)
- [ ] Constants are in `config.py`, not hardcoded
- [ ] Output follows WeChat format rules (no `#`, no `**`, no tables)
- [ ] No `import logging` — use `print(..., file=sys.stderr)` instead

---

## Common Mistakes

1. **Adding `import logging`**: This project doesn't use the logging module. Use `print()` to stderr.

2. **Hardcoding parameters**: Check `config.py` first. If the constant doesn't exist, add it there.

3. **Not testing edge cases**: Financial calculations must handle `None`, `0`, negative values, and empty lists.

4. **Breaking output format**: Any Markdown rendering (`#`, `**`, `|`) will break WeChat display.

5. **Introducing new dependencies**: Core modules have zero heavy dependencies (numpy is the only exception). Optional deps (akshare, mootdx) must be lazy-loaded.

6. **Not deduplicating cache data**: When merging cached + real-time data, always deduplicate by date.

---

## Exit Strategy Output Format (v2.4)

### Trader Output Sections

```
分析报告 — {name}

现价 / MA / ATR / EXPMA

🌍 大盘
📊 {stage}期 + {momentum} → {action}

🎯 今日行动
  动作：{action}
  理由：{reason}

📍 买卖点
  {price} → 止损
  {price} ← 试探买 {pct}%（{condition}）
  {price} 当前
  {price} → 卖 {pct}%（{reason}）

💡 为什么这么操作
  阶段：{stage}期，{reason}
  动能：{momentum}，{reason}
  结论：{label}，{action}

📌 如果你有持仓（成本 {cost}）
  现在：{action}（{pnl}）
  反弹到 {price}：{action}
  跌破 {price}：{action}

🔍 主力筹码
  {price}（{pct}%）{support_level}
  ...

📊 五层打分
  结构 {x} ｜ 量价 {x} ｜ 筹码 {x} ｜ 动能 {x}

🎯 信号判断
  偏多：✓ {signal}
  警惕：! {signal}

❗ 关键价位
✅ 亮点：{text}
⚠️ 风险：{text}
👉 一句话
```

### Key Conventions

1. **Stage summary**: Single line `📊 {stage}期 + {momentum} → {action}`
2. **Price flow**: `📍 买卖点` sorted by price (stop → buy → current → sell → resistance)
3. **Reasoning**: `💡 为什么这么操作` shows stage/momentum/conclusion
4. **Position advice**: `📌 如果你有持仓（成本 {cost}）` with specific actions
5. **Chip peaks**: `🔍 主力筹码` with percentages and support levels
6. **Scores**: `📊 五层打分` structure/volume/chip/momentum
7. **Signals**: `🎯 信号判断` bullish/cautious signals
8. **Highlights**: Single line `✅ 亮点：xxx` / `⚠️ 风险：xxx`
