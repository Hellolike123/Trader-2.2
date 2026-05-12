# 追踪面板融合覆盖维度 Implementation Plan

**Goal:** Propagate `fusion_override` from signal to result, display it in tracking panel breakdown.

## Changes

| File | Change |
|------|--------|
| `signal_tracker.py:_compute_results_for_sig()` | Copy `fusion_override` from signal dict to result dict |
| `signal_tracker.py:_make_panel()` | Add fusion_override breakdown section |
| `final_tracker.py` | (No change — just calls `show_all()` which calls `_make_panel()`) |

## Task 1: Propagate fusion_override in _compute_results_for_sig

In `_compute_results_for_sig()`, find where `res["signal_price"]` is set. After that:

```python
    res: dict[str, Any] = {
        "signal_id": make_signal_id(...),
        "symbol": symbol, "name": name,
        "signal_date": sig_date, "signal_type": sig_type,
        "fusion_override": sig.get("fusion_override", False),
        ...
    }
```

Add `fusion_override` to the result dict, defaulting to `False` if not present.

## Task 2: Add fusion_override breakdown in _make_panel

In `_make_panel()`, after the "按信号类型:" section, add:

```python
    # 按融合覆盖分类
    overridden = [r for r in valid if r.get("fusion_override")]
    not_overridden = [r for r in valid if not r.get("fusion_override")]
    if overridden:
        L.append("按融合覆盖:")
        for label, recs in [("融合覆盖", overridden), ("纯 scene", not_overridden)]:
            ups_r = sum(1 for r in recs if r.get("outcome") == "up")
            total_r = len(recs)
            wr_r = round(ups_r / total_r * 100, 1) if total_r else 0
            avg_r = round(sum(r["r_5d"] for r in recs) / total_r, 1) if total_r else 0
            L.append(f"  {label}: {total_r}次 → 胜率 {wr_r}%（平均{avg_r:+.1f}%）")
        L.append("")
```

## Tests

- mock signal with `fusion_override=True` → result has `fusion_override: true`
- mock signal without `fusion_override` → result has `fusion_override: false`
- panel with mixed records displays fusion override breakdown
