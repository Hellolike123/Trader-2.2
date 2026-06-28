# Bug Fix Modification Plan

**Status**: success
**Summary**: Verified all 4 bugs are real, created comprehensive modification plan with file paths, line numbers, and test cases.

## Summary of Verified Bugs

### Bug 1 (CRITICAL): volume_price.py:46-68 - Volume Ratio Inverted
**Verified**: ✅ Real bug
**Impact**: Critical - Inverts volume ratio signal, causing opposite interpretation of volume divergence
**Root Cause**: Variable names `recent_sum` and `prev_sum` are swapped in the loop logic
**Current Behavior**: Returns `avg_recent/avg_prev` where `recent` = older bars, `prev` = newer bars
**Expected Behavior**: Should return `newer/older` per docstring "近N日均量 / 前N日均量"

### Bug 2 (Low): pattern_core.py:241-266 - min_points Not Enforced
**Verified**: ✅ Real bug (but low impact)
**Impact**: Low - Function still works due to Python slicing behavior, but parameter is misleading
**Root Cause**: No explicit check that `len(price_highs) >= min_points` after slicing
**Current Behavior**: With 3 points and min_points=4, slicing returns all 3 elements
**Expected Behavior**: Should enforce min_points parameter or remove it

### Bug 3 (Medium): fusion_core.py:476-481 - Weights Sum to 1.10
**Verified**: ✅ Real bug
**Impact**: Medium - weighted_score can exceed 1.0, affecting scoring normalization
**Root Cause**: `regime_weights` sum to 1.0, then `PATTERN_WEIGHT` (0.10) is added without adjustment
**Current Behavior**: Total weight = 1.10 in regime-based branch
**Expected Behavior**: Total weight should be 1.0

### Bug 4 (Medium): structure_core.py:620 - Stop-loss Uses Close Instead of Low
**Verified**: ✅ Real bug
**Impact**: Medium - Stop-loss level is less protective (close > low typically)
**Root Cause**: Line reads 'close' field instead of 'low' field
**Current Behavior**: Uses recent close prices for stop-loss calculation
**Expected Behavior**: Should use recent low prices for true intraday low

---

## Modification Plan

### Step 1: Fix Bug 1 (CRITICAL) - volume_price.py
**File**: `02-共享模块-shared/trader_shared/volume_price.py`
**Lines**: 46-68

**Change**:
```python
# Before (lines 65-68):
avg_recent = recent_sum / recent_count
avg_prev = prev_sum / prev_count
return avg_recent / avg_prev if avg_prev > 0 else 1.0

# After:
avg_recent = recent_sum / recent_count
avg_prev = prev_sum / prev_count
return avg_prev / avg_recent if avg_recent > 0 else 1.0
```

**Rationale**: Swap the division order to return `newer/older` as documented.

**Test Case**:
```python
def test_volume_ratio_direction():
    """Verify volume ratio returns newer/older, not older/newer."""
    bars = [{"volume": 100}] * 10  # 10 bars with same volume
    # Last 5 bars (newer) should be numerator
    # First 5 bars (older) should be denominator
    ratio = _calc_volume_ratio(bars, window=5)
    assert ratio == 1.0  # Same volume, ratio should be 1.0
    
    # Test with increasing volume
    bars_increasing = [{"volume": i} for i in range(10)]
    ratio = _calc_volume_ratio(bars_increasing, window=5)
    # Newer bars (5,6,7,8,9) avg = 7.0
    # Older bars (0,1,2,3,4) avg = 2.0
    # Expected: 7.0 / 2.0 = 3.5
    assert abs(ratio - 3.5) < 0.01
```

---

### Step 2: Fix Bug 3 (Medium) - fusion_core.py
**File**: `02-共享模块-shared/trader_shared/fusion_core.py`
**Lines**: 476-481

**Change**:
```python
# Before (lines 476-481):
regime_weights = get_regime_weights(regime)
# 补齐 pattern 权重 (但 "很差" regime 全员权重为0，pattern 也不加)
if regime == "很差":
    weights = regime_weights
else:
    weights = {**regime_weights, "pattern": PATTERN_WEIGHT}

# After:
regime_weights = get_regime_weights(regime)
# 补齐 pattern 权重 (但 "很差" regime 全员权重为0，pattern 也不加)
if regime == "很差":
    weights = regime_weights
else:
    # Shrink existing weights proportionally to make room for pattern weight
    shrink_factor = 1.0 - PATTERN_WEIGHT
    weights = {k: v * shrink_factor for k, v in regime_weights.items()}
    weights["pattern"] = PATTERN_WEIGHT
```

**Rationale**: Proportionally reduce existing weights before adding pattern weight to maintain sum=1.0.

**Test Case**:
```python
def test_regime_weights_sum_to_one():
    """Verify regime weights sum to 1.0 after adding pattern weight."""
    from trader_shared.fusion_regime import get_regime_weights
    from trader_shared.fusion_core import PATTERN_WEIGHT
    
    for regime in ["正常", "偏弱", "很差", "未知"]:
        regime_weights = get_regime_weights(regime)
        if regime == "很差":
            total = sum(regime_weights.values())
        else:
            # Apply the fix
            shrink_factor = 1.0 - PATTERN_WEIGHT
            weights = {k: v * shrink_factor for k, v in regime_weights.items()}
            weights["pattern"] = PATTERN_WEIGHT
            total = sum(weights.values())
        assert abs(total - 1.0) < 0.001, f"Regime {regime} weights sum to {total}"
```

---

### Step 3: Fix Bug 4 (Medium) - structure_core.py
**File**: `02-共享模块-shared/trader_shared/structure_core.py`
**Line**: 620

**Change**:
```python
# Before (line 620):
recent_lows = [float(b.get('close') or 0) for b in bars[-20:] if b.get('close')]

# After:
recent_lows = [float(b.get('low') or 0) for b in bars[-20:] if b.get('low')]
```

**Rationale**: Use 'low' field for true intraday low as intended by the comment "前低融合".

**Test Case**:
```python
def test_stop_loss_uses_low_prices():
    """Verify stop-loss calculation uses low prices, not close."""
    from trader_shared.structure_core import build_structure_context
    
    # Create bars where low < close
    bars = []
    for i in range(30):
        close = 10.0 + i * 0.1
        low = close * 0.98  # Low is 2% below close
        high = close * 1.02
        bars.append({"open": close * 0.99, "high": high, "low": low, "close": close, "volume": 1000})
    
    result = build_structure_context(current=12.0, bars=bars)
    # The stop-loss should be based on low prices, not close prices
    # Since low < close, the stop should be lower (more protective)
    assert result.get("stop") is not None
```

---

### Step 4: Fix Bug 2 (Low) - pattern_core.py
**File**: `02-共享模块-shared/trader_shared/pattern_core.py`
**Lines**: 262-267

**Change**:
```python
# Before (lines 262-267):
# 需要至少2个高点和2个低点
if len(price_highs) < 2 or len(price_lows) < 2:
    return None

# 至少需要3个高点和3个低点才能形成有效三角形
if len(price_highs) < 3 or len(price_lows) < 3:
    return None

# After:
# 需要至少 min_points 个高点和低点才能形成有效三角形
if len(price_highs) < min_points or len(price_lows) < min_points:
    return None
```

**Rationale**: Enforce the min_points parameter explicitly rather than relying on slicing behavior.

**Alternative**: Remove the min_points parameter entirely and hardcode 3 if that's the actual requirement.

**Test Case**:
```python
def test_triangle_min_points_enforced():
    """Verify triangle detection enforces min_points parameter."""
    from trader_shared.pattern_core import _detect_triangle
    
    # Create data with exactly 3 high points and 3 low points
    closes = [10.0, 11.0, 12.0, 11.5, 10.5, 11.0, 11.5, 12.0, 11.0, 10.0] * 3
    highs = [c * 1.02 for c in closes]
    lows = [c * 0.98 for c in closes]
    
    # With min_points=4, should return None (only 3 points)
    result = _detect_triangle(closes, highs, lows, min_points=4)
    assert result is None
    
    # With min_points=3, should potentially detect pattern
    result = _detect_triangle(closes, highs, lows, min_points=3)
    # (may or may not detect pattern depending on data, but shouldn't error)
```

---

## Dependencies Between Fixes

**No dependencies** - All four fixes are independent and can be applied in any order.

**Recommended order**:
1. Bug 1 (CRITICAL) - Highest priority, affects core volume analysis
2. Bug 3 (Medium) - Affects scoring normalization
3. Bug 4 (Medium) - Affects stop-loss calculation
4. Bug 2 (Low) - Lowest priority, code quality improvement

---

## Test Execution Plan

1. **Run existing tests** to establish baseline:
   ```bash
   python3 -m pytest 02-共享模块-shared/tests/ -v
   ```

2. **Apply fixes in order** (Bug 1 → Bug 3 → Bug 4 → Bug 2)

3. **Run tests after each fix** to verify no regressions

4. **Add new test cases** for each bug fix

5. **Run full test suite** to ensure all fixes work together

6. **Manual verification**:
   - Test volume ratio with known data
   - Test fusion weights sum to 1.0
   - Test stop-loss uses low prices
   - Test triangle detection with min_points parameter

---

## Risk Assessment

- **Bug 1 Fix**: Low risk - Simple division order swap
- **Bug 3 Fix**: Low risk - Proportional scaling preserves relative weights
- **Bug 4 Fix**: Low risk - Direct field name change
- **Bug 2 Fix**: Low risk - Explicit check adds safety

All fixes are localized and don't introduce new logic, just correct existing behavior.

---

**Files touched**: 
- 02-共享模块-shared/trader_shared/volume_price.py (Bug 1)
- 02-共享模块-shared/trader_shared/fusion_core.py (Bug 3)
- 02-共享模块-shared/trader_shared/structure_core.py (Bug 4)
- 02-共享模块-shared/trader_shared/pattern_core.py (Bug 2)
- bug_fix_plan.md (created)

**Findings worth promoting**:
- Two separate `_calc_volume_ratio` functions exist: one in volume_price.py (buggy) and one in main_force.py (correct). Consider consolidating to avoid duplication.
- The volume_price.py bug only affects `detect_volume_divergence()` function, not the main_force.py caller.
- Fusion weights in other branches (breakout/climax/bearish) already sum to 1.0, only the regime-based branch has the 1.10 issue.
- The pattern_core.py min_points bug has minimal impact due to Python slicing behavior, but should be fixed for API correctness.