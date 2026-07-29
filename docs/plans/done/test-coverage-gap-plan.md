> **已归档（2026-07-29）**：历史计划/摘要，勿按本文施工。现行法源见 `AGENTS.md` + `docs/designs/resonance-and-orchestration.md`。

# Test Coverage Gap Modification Plan

Generated: 2026-06-25 | Source: Agent 49 + Agent 50 reports | All gaps verified against source code.

---

## Verification Summary

All 28 reported gaps confirmed genuine. Zero false positives.

---

## Phase 1 — P0 (6 items, ~3.5h)

Core decision paths where bugs produce wrong buy/sell signals.

### 1. sell_points 一类卖/二类卖/三类卖
- **Source**: `fusion_core.py:99-113` inside `_chan_to_signal`
- **Test file**: `test_fusion_core.py` → `TestChanToSignal`
- **What to test**: Three sell types override buy_points priority. 一类卖 confidence=0.8, 二类卖=0.5, 三类卖=0.5. Sell points checked before buy_points in the loop.
- **Cases**: `test_一类卖`, `test_二类卖`, `test_三类卖`, `test_sell_overrides_buy_when_both_present`
- **Effort**: 20m

### 2. data_status 降级
- **Source**: `fusion_core.py:524-526` (score clamp ≤0) + `fusion_core.py:628-631` (confidence cap ≤0.3)
- **Test file**: `test_fusion_core.py` → new `TestDataStatusDegradation`
- **What to test**: Pass `data_status="partial"` to `merge_decisions`. Assert action forced non-positive and confidence capped at 0.3. Also test "degraded" and "failed".
- **Effort**: 25m

### 3. FUSION_OVERRIDE_ENABLED complete path
- **Source**: `decision_core.py:266-280` config check → `_FUSION_STATUS_MAP` lookup → special "暂不碰" de-escalation at lines 272-277
- **Test file**: `test_decision_core.py` → `TestStatusLayers`
- **What to test**: monkeypatch `FUSION_OVERRIDE_ENABLED=True`, `FUSION_CONFIDENCE_THRESHOLD=0.6`. Feed `fusion_result` with high confidence + mapped action. Verify `fusion_override_used=True`. Test "暂不碰" path: when `current <= hard_stop` stays "暂不碰", when `current > hard_stop` de-escalates to "防守观察".
- **Cases**: `test_fusion_override_maps_action`, `test_fusion_override_zanbupeng_with_stop`, `test_fusion_override_zanbupeng_deescalate`
- **Effort**: 30m

### 4. _check_theory_breakout
- **Source**: `decision_core.py:148-217`
- **Test file**: `test_decision_core.py` → new `TestCheckTheoryBreakout`
- **What to test**: Direct function import. Parametrize branches: chan-only (三类买/拉升段/上攻笔), wyk-only (Spring/看多+背离), combined chan+wyk, VP below_va veto, price below confirm (early exit), price below support (early exit).
- **Cases**: ~7 parametrized cases
- **Effort**: 35m

### 5. _score_slope
- **Source**: `expma_status.py:135-166`
- **Test file**: `test_expma_status.py` → new `TestScoreSlope`
- **What to test**: Two paths — bars available (historical recompute at line 145) vs proxy heuristic (EXPMA20 vs EXPMA30 at line 160). Return 0 (steep down), 1 (neutral), 2 (steep up).
- **Cases**: `test_strong_up_with_bars`, `test_neutral`, `test_steep_down`, `test_proxy_above`, `test_proxy_below`, `test_insufficient_data_fallback`
- **Effort**: 15m

### 6. _score_crossover
- **Source**: `expma_status.py:171-216`
- **Test file**: `test_expma_status.py` → new `TestScoreCrossover`
- **What to test**: Rolling 5-day window golden/death cross detection. Variable naming inversion: `expma10_prev` is actually the more recent slice. Return 0/1/2.
- **Cases**: `test_golden_cross`, `test_death_cross`, `test_no_cross`, `test_insufficient_closes`
- **Effort**: 20m

---

## Phase 2 — P1 (9 items, ~4.5h)

Fusion extensions, structure calcs, and volume features.

### 7. pattern_result 第4路
- **Source**: `fusion_core.py:393-406` pattern_signal construction → `line 518` weighted_score contribution
- **Test file**: `test_fusion_core.py` → `TestMergeDecisions`
- **What to test**: Pass `pattern_result={"signal": 1, "confidence": 0.6, "reason": "W底"}` to `merge_decisions`. Verify pattern appears in `signals_detail` and affects `weighted_score`.
- **Effort**: 15m

### 8. volume_warning 天量天价
- **Source**: `fusion_core.py:571-578`
- **Test file**: `test_fusion_core.py` → `TestMergeDecisions`
- **What to test**: Pass `volume_warning={"signal": -1, "type": "climactic"}`. When action is positive, should override to "天量天价，减仓观望" and cap confidence at 0.4.
- **Effort**: 15m

### 9. volume_warning 放量滞涨
- **Source**: `fusion_core.py:579-583`
- **Test file**: `test_fusion_core.py` → `TestMergeDecisions`
- **What to test**: Pass `volume_warning={"signal": -1, "type": "stagnation"}`. When `weighted_score > 0`, confidence multiplied by `(1 - vw_conf * 0.3)`, floor 0.2.
- **Effort**: 15m

### 10. extend_fundamental 筹码集中
- **Source**: `fusion_core.py:585-594`
- **Test file**: `test_fusion_core.py` → `TestMergeDecisions`
- **What to test**: Pass `extend_fundamental={"shareholder": {"status": "筹码集中"}}` with `weighted_score > 0.2`. Confidence ×1.15, capped at 1.0. Also test when score ≤0.2 (no boost).
- **Effort**: 15m

### 11. extend_sentiment 限售解禁
- **Source**: `fusion_core.py:596-626`
- **Test file**: `test_fusion_core.py` → `TestMergeDecisions`
- **What to test**: Pass `extend_sentiment={"unlocks": [{"date": "2026-07-10", "ratio": 8.0}]}` with bullish action. Should veto to "空仓 (限售解禁风险)", confidence=0.3, weighted_score=-0.5. Also test ratio<5 (no veto) and date>15 days out (no veto).
- **Effort**: 20m

### 12. take_profit by major_stage
- **Source**: `structure_core.py:638-652` six branches
- **Test file**: `test_structure_core.py` → new `TestTakeProfitByStage`
- **What to test**: Call `build_structure_context` with different `major_stage` values. Assert: 蓄势→resistance, 主升→1.10x fallback, 派发→current, 蓄势偏弱→0.98×resistance, 衰退→current×1.03.
- **Cases**: 6 stage variants + safety floor (`take >= current`)
- **Effort**: 20m

### 13. _theory_multipliers + HMM
- **Source**: `structure_core.py:221-345` 4-layer architecture
- **Test file**: `test_structure_core.py` → extend `TestPhase3Features` in fusion_core test or new class
- **What to test**: Layer 1 (MA regime at lines 272-278) partially covered. Gap: HMM blending at line 292 (`base*0.5 + hmm*0.5`) and Layer 3 theory micro-adjustments (lines 299-344). Need monkeypatch for `_HMM_AVAILABLE`.
- **Cases**: `test_hmm_blend_range`, `test_hmm_blend_bull`, `test_theory_micro_chan_bullish`, `test_theory_micro_wyckoff_bullish`
- **Effort**: 30m

### 14. near_stop ATR lower bound
- **Source**: `decision_core.py:321-327`
- **Test file**: `test_decision_core.py` → `TestFakeBreakAndPhasedExit`
- **What to test**: When `hard_stop ≈ support`, `atr_est` falls back to `current * 0.015`. Assert `_near_stop` triggers correctly when `current - hard_stop < atr_est * 2`.
- **Cases**: `test_near_stop_atr_floor_fires`, `test_near_stop_atr_floor_wide_stop`
- **Effort**: 15m

### 15. VP 日内量价分布集成
- **Source**: `decision_core.py:206-217` inside `_check_theory_breakout`
- **Test file**: `test_decision_core.py` → `TestCheckTheoryBreakout`
- **What to test**: Mock `_VP_AVAILABLE=True` and `_vp_assess` to return `{"vp_signal": "below_va"}`. Should cause `is_theory_breakout=False`. Also test `above_poc` / `va_support` paths that pass through.
- **Effort**: 20m

### 16. _trend_label
- **Source**: `expma_status.py:257-280`
- **Test file**: `test_expma_status.py` → new `TestTrendLabel`
- **What to test**: Decision tree mapping alignment+slope→Chinese labels. Sub-branches: price vs EXPMA5 for "pullback in uptrend" vs "uptrend breaking down". Default `current_price=0` skips price sub-branches.
- **Cases**: `test_full_bullish`, `test_slight_bullish`, `test_bearish_weak`, `test_choppy`, `test_pullback_uptrend`, `test_breaking_down`
- **Effort**: 15m

---

## Phase 3 — P2 (7 items, ~3h)

Secondary coverage for edge cases and less-frequent paths.

### 17. low_zone 约束
- **Source**: `structure_core.py:621-625`
- **Test file**: `test_structure_core.py` → new `TestZoneConstraints`
- **What to test**: When support is very low (deep below current), `low_zone_lower` clamped to `current * 0.95` and `low_zone_upper` to `current * 0.985`. Need bars where support << current.
- **Effort**: 15m

### 18. high_zone_lower 约束
- **Source**: `structure_core.py:711-717`
- **Test file**: `test_structure_core.py` → `TestZoneConstraints`
- **What to test**: When resistance is very high, `high_zone_lower` capped at `current * 1.08`. When resistance is near current, `high_zone_lower` floored at `current * 1.005`.
- **Effort**: 15m

### 19. fib_ext_1382/1618
- **Source**: `structure_core.py:719-725`
- **Test file**: `test_structure_core.py` → new `TestFibExtensions`
- **What to test**: Provide chan_result with valid swing_high/swing_low. Assert `fib_ext_1382 = swing_low + diff * 1.382`, `fib_ext_1618 = swing_low + diff * 1.618`. Also test None when swing data missing.
- **Effort**: 15m

### 20. confirm_buffer clamp
- **Source**: `structure_core.py:610`
- **Test file**: `test_structure_core.py` → `TestZoneConstraints`
- **What to test**: After multiplier stacking, `confirm_buffer` must be in [0.5, 2.0]. Monkeypatch extreme multiplier values and verify clamp.
- **Effort**: 10m

### 21. 理论冲突 + 等转强
- **Source**: `decision_core.py:407-415`
- **Test file**: `test_decision_core.py` → `TestTheoryFusionConflict`
- **What to test**: `fusion_result` with action="减仓", confidence below threshold, and `theory_status` in the neutral set. Verify `theory_fusion_conflict=True`. Already partially covered — extend with "等转强" in the neutral set.
- **Effort**: 10m

### 22. 承接存在 + not trend_ok
- **Source**: `decision_core.py:366-375`
- **Test file**: `test_decision_core.py` → `TestStatusLayers`
- **What to test**: `below_ma_count >= 3`, `current > support`, `trend_ok=False`. Should still get "承接存在" (not downgraded by weak market). Existing test covers `trend_ok=True`; add inverse case.
- **Effort**: 10m

### 23. status_layers with chan_result
- **Source**: `decision_core.py:294-301` → `_check_theory_breakout` lines 170-184
- **Test file**: `test_decision_core.py` → `TestStatusLayers`
- **What to test**: Pass `chan_result` with `buy_point_text="三类买"`, `trend_label="拉升段"`, or `strokes=[{"direction":"up"}]`. Verify `base_status="突破确认"` when price is strong.
- **Effort**: 15m

### 24. _build_signals
- **Source**: `expma_status.py:285-327`
- **Test file**: `test_expma_status.py` → new `TestBuildSignals`
- **What to test**: Pure string aggregation. Tests for alignment patterns, slope/crossover annotations, overbought/oversold messages when deviation > 5%.
- **Cases**: `test_full_bullish_signals`, `test_bearish_signals`, `test_overbought`, `test_oversold`, `test_empty_input`
- **Effort**: 10m

### 25. Triangle test improvement
- **Source**: `pattern_core.py` — `_detect_triangle`
- **Test file**: `test_pattern_core.py` → `TestTriangle`
- **What to test**: Current test at line 92 says "may return None or detect" — asserts nothing. Create a definitive triangle dataset (clearly converging highs/lows with breakout) and assert result is not None + correct signal direction.
- **Effort**: 15m

### 26. Double top additional tests
- **Source**: `pattern_core.py` — `_detect_double_top`
- **Test file**: `test_pattern_core.py` → `TestDoubleTop`
- **What to test**: Only 1 test currently. Add: no-breakout case, volume validation (same pattern as double_bottom), two tops too close together (should reject).
- **Cases**: `test_no_breakout`, `test_volume_validation_pass`, `test_volume_validation_fail`, `test_tops_too_close`
- **Effort**: 20m

### 27. Double bottom volume validation
- **Source**: `pattern_core.py:159-171`
- **Test file**: `test_pattern_core.py` → `TestDoubleBottom`
- **What to test**: Pass `volumes` parameter. Vol2 must be ≤ vol1 * 1.2. Vol_bounce must be ≥ vol2 * 0.8. Test pass and fail paths.
- **Cases**: `test_volume_pass`, `test_volume_fail_second_higher`, `test_volume_fail_bounce_weak`
- **Effort**: 15m

---

## Dependencies

```
Phase 1: No dependencies between items. All independent.
Phase 2: Items 8-11 depend on understanding merge_decisions() signature (item 7 helps).
          Item 15 (VP) depends on item 4 (_check_theory_breakout tests).
          Item 13 (HMM) may need mock for _HMM_AVAILABLE flag.
Phase 3: Items 17-20 share a TestZoneConstraints class. Items 22-23 extend TestStatusLayers.
```

**Recommended execution order within phases**: Items with shared test classes should be batched together.

---

## Effort Summary

| Phase | Items | Estimated Time |
|-------|-------|---------------|
| P0 | 6 | 125 min (~2h) |
| P1 | 9 | 165 min (~2.75h) |
| P2 | 11 | 145 min (~2.4h) |
| **Total** | **26** | **435 min (~7.25h)** |

---

## Files to Modify

| File | New test classes/methods |
|------|-------------------------|
| `tests/test_expma_status.py` | `TestScoreSlope` (6), `TestScoreCrossover` (4), `TestTrendLabel` (6), `TestBuildSignals` (5) |
| `tests/test_pattern_core.py` | `TestTriangle` rewrite (1), `TestDoubleTop` +3, `TestDoubleBottom` +3 |
| `tests/test_fusion_core.py` | `TestChanToSignal` +4, `TestDataStatusDegradation` (3), `TestMergeDecisions` +6 |
| `tests/test_structure_core.py` | `TestTakeProfitByStage` (7), `TestZoneConstraints` (4), `TestFibExtensions` (3), extend `TestRegimeWeights`/`TestPhase3Features` |
| `tests/test_decision_core.py` | `TestCheckTheoryBreakout` (7), extend `TestStatusLayers` (3), extend `TestFakeBreakAndPhasedExit` (2), extend `TestTheoryFusionConflict` (1) |
