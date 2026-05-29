# Fusion Integration into build_signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `build_signal()` prefer fusion layer decision when confidence > 0.2, adding `fusion_override` flag to signal output.

**Architecture:** One new mapping function + ~20 lines in `build_signal()`. Fusion action → (signal_type, direction, action) mapping. Guard checks for fusion absence, low confidence, no signal, unpaired action.

**Tech Stack:** Python 3, run_analysis.py, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `01-功能包-packages/01-单票分析-trader/scripts/run_analysis.py` | Modify | Add `_map_fusion_to_signal()`, modify `build_signal()` |
| `01-功能包-packages/01-单票分析-trader/tests/test_fusion_integration.py` | Create | Tests for all 7 fusion integration scenarios |

---

### Task 1: Add `_map_fusion_to_signal()` and modify `build_signal()`

**Files:**
- Modify: `01-功能包-packages/01-单票分析-trader/scripts/run_analysis.py`
- Create: `01-功能包-packages/01-单票分析-trader/tests/test_fusion_integration.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fusion_integration.py
import pytest
from run_analysis import build_signal, _map_fusion_to_signal

# ── _map_fusion_to_signal unit tests ──

def test_map_fusion_buy():
    assert _map_fusion_to_signal("半仓试 (多方主导)") == ("track", "bullish", "track")
    assert _map_fusion_to_signal("增持") == ("track", "bullish", "track")

def test_map_fusion_hold():
    assert _map_fusion_to_signal("持股观望") == ("wait_for_confirmation", "bullish_lean", "observe")

def test_map_fusion_sell():
    assert _map_fusion_to_signal("减仓") == ("defensive", "bearish", "wait")
    assert _map_fusion_to_signal("空仓/止损") == ("defensive", "bearish", "wait")

def test_map_fusion_unmapped():
    assert _map_fusion_to_signal("未知动作") is None
    assert _map_fusion_to_signal("") is None

# ── build_signal integration tests ──

def _make_report_with_fusion(fusion_action, confidence=0.5, has_signal=True):
    """Helper: create a minimal report with fusion field."""
    return {
        "name": "测试", "symbol": "688248.SH",
        "analysis_time": "2026-05-12",
        "current": 100,
        "support": 90, "resistance": 110, "confirm": 105,
        "stop": 85, "take": 120, "stage": "震荡",
        "scene": "低吸观察",
        "market_env": {"level": "正常"},
        "fusion": {
            "action": fusion_action,
            "confidence": confidence,
            "weighted_score": 0.6,
            "regime": "正常",
            "disagreement": 0,
            "signals_detail": {
                "chan": {"direction": 1, "confidence": 0.6},
                "momentum": {"direction": 1, "confidence": 0.5},
                "wyckoff": {"direction": 1, "confidence": 0.4},
            },
        },
    }

def test_build_signal_uses_fusion_when_confident():
    """fusion confidence=0.5 > 0.2 → use fusion action."""
    r = _make_report_with_fusion("增持", confidence=0.5)
    sig = build_signal(r)
    assert sig["signal_type"] == "track"
    assert sig["direction"] == "bullish"
    assert sig.get("fusion_override") is True

def test_build_signal_keeps_scene_when_low_confidence():
    """fusion confidence=0.1 ≤ 0.2 → keep scene."""
    r = _make_report_with_fusion("增持", confidence=0.1)
    sig = build_signal(r)
    assert sig["signal_type"] != "track"  # scene-based, not fusion
    assert sig.get("fusion_override") is None

def test_build_signal_keeps_scene_at_threshold():
    """fusion confidence=0.2 exactly → keep scene (boundary)."""
    r = _make_report_with_fusion("增持", confidence=0.2)
    sig = build_signal(r)
    assert sig.get("fusion_override") is None

def test_build_signal_no_fusion_key():
    """report without fusion → keep scene."""
    r = _make_report_with_fusion("增持", confidence=0.5)
    del r["fusion"]
    sig = build_signal(r)
    assert sig.get("fusion_override") is None

def test_build_signal_all_zeros():
    """fusion with signals_detail all 0 → keep scene."""
    r = _make_report_with_fusion("增持", confidence=0.5, has_signal=False)
    r["fusion"]["signals_detail"]["chan"]["direction"] = 0
    r["fusion"]["signals_detail"]["momentum"]["direction"] = 0
    r["fusion"]["signals_detail"]["wyckoff"]["direction"] = 0
    sig = build_signal(r)
    assert sig.get("fusion_override") is None

def test_build_signal_unmapped_action():
    """fusion action not in mapping → keep scene."""
    r = _make_report_with_fusion("UNKNOWN_ACTION", confidence=0.5)
    sig = build_signal(r)
    assert sig.get("fusion_override") is None

def test_build_signal_same_direction():
    """fusion direction same as scene → keep scene (no override)."""
    r = _make_report_with_fusion("增持", confidence=0.5)
    # 场景是突破确认时 scene 决策也是 bullish/track
    r["stage"] = "走强"
    r["scene"] = "突破确认"
    sig = build_signal(r)
    assert sig.get("fusion_override") is None  # 方向一致，不覆盖
```

Run: `cd 01-功能包-packages/01-单票分析-trader && python -m pytest tests/test_fusion_integration.py -v`
Expected: FAIL (functions not defined)

- [ ] **Step 2: Implement _map_fusion_to_signal() and modify build_signal()**

Add before `build_signal()`:

```python
_FUSION_ACTION_MAP: dict[str, tuple[str, str, str]] = {
    "半仓试 (多方主导)": ("track", "bullish", "track"),
    "半仓试 (多方主导但有分歧)": ("track", "bullish", "track"),
    "增持": ("track", "bullish", "track"),
    "持股观望": ("wait_for_confirmation", "bullish_lean", "observe"),
    "减仓": ("defensive", "bearish", "wait"),
    "空仓/止损": ("defensive", "bearish", "wait"),
}

def _map_fusion_to_signal(fusion_action: str) -> tuple[str, str, str] | None:
    """映射融合 action → (signal_type, direction, action)。未匹配返回 None。"""
    if not fusion_action:
        return None
    return _FUSION_ACTION_MAP.get(fusion_action.strip())
```

Modify `build_signal()` — after `signal_type, direction, action, confidence = signal_state(r)`, add:

```python
    fusion_override = False
    fusion = r.get("fusion")
    if isinstance(fusion, dict):
        fc = fusion.get("confidence", 0)
        sd = fusion.get("signals_detail", {})
        has_signal = isinstance(sd, dict) and any(
            isinstance(v, dict) and v.get("direction") != 0
            for v in sd.values()
        )
        if fc > 0.2 and has_signal:
            mapped = _map_fusion_to_signal(fusion.get("action", ""))
            if mapped is not None:
                ft, fd, fa = mapped
                # spec: direction 一致时保留 scene（不切换）
                if fd != direction:
                    signal_type, direction, action = ft, fd, fa
                    fusion_override = True
```

In the signal dict construction, add the key only when True:

```python
if fusion_override:
    signal["fusion_override"] = True
```

- [ ] **Step 3: Run tests**

Run: `cd 01-功能包-packages/01-单票分析-trader && python -m pytest tests/test_fusion_integration.py -v`
Expected: All PASS

- [ ] **Step 4: Full regression — trader tests**

Run: `cd 01-功能包-packages/01-单票分析-trader && python -m pytest tests/ -v -q`
Expected: All PASS

- [ ] **Step 5: Full shared regression (check no side effects)**

Run: `cd 02-共享模块-shared && python -m pytest tests/ -q`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add 01-功能包-packages/01-单票分析-trader/scripts/run_analysis.py 01-功能包-packages/01-单票分析-trader/tests/test_fusion_integration.py
git commit -m "feat: fuse fusion layer into build_signal() decision"
```

---

## Summary

| Task | Files | Key Change |
|------|-------|------------|
| 1 | run_analysis.py, test_fusion_integration.py | `_map_fusion_to_signal()` + fusion override in `build_signal()` |
