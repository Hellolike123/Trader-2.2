# Epic B/C/G phase report

## STATUS: NEEDS_PYTEST_EVIDENCE

## FILES
- `docs/plans/wyckoff-sos-epic-bcg-handoff.md`
- `config.py` — `WYCKOFF_TR_FALLBACK_MIN_WIDTH`, `WYCKOFF_CLUSTER_EVENT_FRESH_BARS`
- `wyckoff_events.py` — TR fallback helpers; cluster SC-reset + fresh
- `wyckoff_core.py` — phase_a failed → 簇作废
- `tests/test_wyckoff_core.py` — TestTradingRangeFallbackBugB, TestEventClusterBugCG
- prior A: SOS thrust + round vol

## TESTS（请本机跑）

```bash
cd /Users/like/Documents/Opencode/Trader3.0
python3 -m pytest 02-共享模块-shared/tests/test_wyckoff_core.py::TestDetectSosThrust \
  02-共享模块-shared/tests/test_wyckoff_core.py::TestTradingRangeFallbackBugB \
  02-共享模块-shared/tests/test_wyckoff_core.py::TestEventClusterBugCG -v --tb=short
python3 -m pytest 02-共享模块-shared/tests/test_wyckoff_core.py -q
```

可选实票：
```bash
python3 01-功能包-packages/wyckoff/scripts/final_wyckoff.py --target 南网科技
```

## NEXT
绿 → 独立 review → 问 commit/PR  
仍未做：F（SC 文案）、D（周线）、E（volume 单位）
