# Fix Hermes Zip Issues

## Issues Found by Hermes

### Issue 1: sys.path.insert causes config override (ALL packages)

**Problem**: 
- `__init__.py` line 19: `sys.path.insert(0, str(_scripts))` causes `trader_shared/config.py` to override `scripts/config.py`
- `cache_utils.py` line 272,300: `sys.path.insert(0, str(p))` and `sys.path.insert(0, str(root / "scripts"))` have same issue

**Impact**: `from config import ...` imports wrong config file

**Fix**: 
- Change `sys.path.insert(0, ...)` to `sys.path.append(...)` or remove duplicate path manipulation
- Ensure `scripts/config.py` takes precedence over `trader_shared/config.py`

### Issue 2: review_render.py conclusion format (review.zip only)

**Problem**: 
- Line 35-38: Conclusion is split into multiple lines
```python
lines.append("结论 ")
lines.append(conclusion)
lines.append(model_summary_text)
```

**Expected**: Single line format `"结论 " + conclusion + model_summary`

**Fix**: Merge into single `lines.append()` call

## Files to Modify

1. `02-共享模块-shared/trader_shared/__init__.py` — Fix sys.path.insert
2. `02-共享模块-shared/trader_shared/cache_utils.py` — Fix sys.path.insert
3. `01-功能包-packages/review/scripts/review_render.py` — Fix conclusion format

## Verification

```bash
python3 -m pytest 02-共享模块-shared/tests/
python3 02-共享模块-shared/scripts/pack_all.py --no-install
# Then manually check zip contents
```
