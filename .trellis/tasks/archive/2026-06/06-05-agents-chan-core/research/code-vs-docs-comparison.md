# Research: AGENTS_DEEP.md vs Code — Systematic Comparison

- **Query**: Compare every major claim in AGENTS_DEEP.md against actual code
- **Scope**: Mixed (internal code search + cross-referencing)
- **Date**: 2026-06-07

## Findings

---

## Section 2 (Data Architecture) — `light_data.py`

### 2.1 Data Sources Table

| Claim | AGENTS_DEEP.md Lines | Code File:Line | Verdict |
|---|---|---|---|
| Tencent quote URL `qt.gtimg.cn/q=` | L74 | `light_data.py:81` | MATCH |
| Tencent daily `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | L75 | `light_data.py:82` | MATCH |
| Sina K-line `money.finance.sina.com.cn/quotes_service/api/...` | L76-77 | `light_data.py:83` | MATCH |

### 2.2.1 MarketDataSourceController

| Claim | AGENTS_DEEP.md Lines | Code File:Line | Verdict |
|---|---|---|---|
| Class `MarketDataSourceController` exists | L83 | `light_data.py:417` | MATCH |
| 1.5s socket timeout | L84 | `light_data.py:522` | MATCH |
| `consecutive_failures >= 3` triggers UNHEALTHY | L85 | `light_data.py:428,459-460` | MATCH |
| 30s cooldown | L85 | `light_data.py:424,461` | MATCH |
| Fallback quote → Tencent HTTP | L87 | `light_data.py` (numerous fallback paths) | MATCH |
| Fallback daily → Tencent fqkline | L88 | `light_data.py` | MATCH |
| Fallback minutes → Sina → akshare | L89 | `light_data.py` | MATCH |

### 2.2.2 Data Status Labels & Completeness

| Claim | AGENTS_DEEP.md Lines | Code File:Line | Verdict |
|---|---|---|---|
| `DataStatus = Literal["full", "partial", "degraded", "failed"]` | L93-97 | `light_data.py:412` | MATCH |
| `data_status` field in `MarketSnapshot` | L92 | `light_data.py:677` | MATCH |
| `missing_sources` field | L97 | `light_data.py:680` | MATCH |
| `source_errors` field | L97 | `light_data.py:681` | MATCH |
| `load_market_snapshot()` function | L107 | `light_data.py` (exists as function) | MATCH |

**Function table verification (L101-109):**
- `fetch_quote()`: exists → MATCH
- `fetch_qfq_daily()`: exists → MATCH
- `fetch_5m()`/`fetch_15m()`/`fetch_30m()`: exist → MATCH
- `fetch_kline()`: exists → MATCH
- `load_market_snapshot()`: exists → MATCH
- `resolve_security()`: exists → MATCH
- `is_trading_time()`: exists → MATCH

**TypedDict models table (L111-123):**
Most TypedDicts exist in `models.py`:
- `models.py:19` BarData ✓
- `models.py:36` QuoteData ✓
- `models.py:53` MAValues ✓
- `models.py:62` CandidateLevels ✓
- `models.py:121` CandidateSignal ✓
- `models.py:133` TheoryVerdict ✓
- `models.py:158` SignalRecord ✓
- `models.py:203` ChanlunSignal ✓
- `models.py:214` WyckoffSignal ✓

| Additional TypedDicts in `models.py` NOT documented | Code File:Line | Notes |
|---|---|---|
| TradeStage | models.py:87 | Not in doc's table |
| SignalDirection | models.py:93 | Not in doc's table |
| VolumeProfile | models.py:99 | Not in doc's table |
| PriceAction | models.py:106 | Not in doc's table |
| TheoryScore | models.py:113 | Not in doc's table |
| SignalTrigger | models.py:143 | Not in doc's table |
| Position | models.py:151 | Not in doc's table |

### 2.2.3 Lazy Loading (2026-05-31 fix)

| Claim | AGENTS_DEEP.md Lines | Code File:Line | Verdict |
|---|---|---|---|
| `_check_mootdx()` / `_check_akshare()` / `_check_pytdx3()` exist | L133 | `light_data.py:40-78` | MATCH |
| Three-state bool (None=未检测, True/False=已检测) | L134 | `light_data.py:32,34,36` (None initially) | MATCH |
| Import time reduced 0.895s→0.092s | L136 | Already verified in AGENTS.md L27 | MATCH (prior bugfix) |

### 2.2.4 parse_trade_datetime (2026-05-31 fix)

| Claim | AGENTS_DEEP.md Lines | Code File:Line | Verdict |
|---|---|---|---|
| Priority: fields[30] 14-digit timestamp | L140-142 | `light_data.py:859-866` | MATCH |
| Fallback: scan `YYYY-MM-DD` / `HH:MM:SS` | L143 | `light_data.py:869-875` | MATCH |
| Old bug: mis-match volume field "10349555" | L145 | confirms re. `light_data.py:869` now uses `fullmatch` not `search` | MATCH |

---

## Section 2.3 (State Machine) — `config.py` + `decision_core.py`

### STATUS_SCORE entries

| Claim | Doc L154-170 | Code File:Line | Verdict |
|---|---|---|---|
| "暂不碰"=20 | L156 | `config.py:56` | MATCH |
| "低吸观察"=80 | L157 | `config.py:50` | MATCH |
| "冲高减仓"=55 | L158 | `config.py:53` | MATCH |
| "等转强"=70 | L159 | `config.py:51` | MATCH |
| "防守观察"=60 | L160 | `config.py:52` | MATCH |
| "空间不足"=30 | L161 | `config.py:54` | MATCH |
| "数据失败"=0 | L162 | `config.py:56` | **MISMATCH** — Doc says 56, but code says `config.py:56` has "数据失败":0 → actually MATCH |
| "突破确认"=85 | L163 | `config.py:43` and `decision_core.py:80` | PARTIAL — Defined twice (duplicate) |
| "突破观察"=75 | L164 | `config.py:44` and `decision_core.py:81` | PARTIAL — Defined twice (duplicate) |
| "体系转强确认"=88 | L165 | `config.py:45` and `decision_core.py:82` | PARTIAL — Defined twice (duplicate) |
| "未确认转强"=72 | L166 | `config.py:46` and `decision_core.py:83` | PARTIAL — Defined twice (duplicate) |
| "转强不足"=62 | L167 | `config.py:47` and `decision_core.py:84` | PARTIAL — Defined twice (duplicate) |
| "承接存在"=68 | L168 | `config.py:48` and `decision_core.py:85` | PARTIAL — Defined twice (duplicate) |
| "修复观察"=65 | L169 | `config.py:49` and `decision_core.py:86` | PARTIAL — Defined twice (duplicate) |
| "空间偏紧" = — | L170 | NOT in STATUS_SCORE dict | **MISMATCH** — Doc says "不在STATUS_SCORE中" but doesn't exist at all in config.py |
| **Missing from doc: "防守观察，趋势下行谨慎"=50** | — | `decision_core.py:79` | **MISMATCH** — Not documented |

**Key finding**: `STATUS_SCORE` entries are defined twice — once in `config.py` (canonical) and once in `decision_core.py` (redundant override). The `decision_core.py` override (lines 79-86) re-defines the same values without changing them, plus adds the undocumented `"防守观察，趋势下行谨慎"`.

### status_layers() return value

| Claim (Doc L182-192) | Code File:Line | Verdict |
|---|---|---|
| `"base_status": str` | `decision_core.py:410` | MATCH |
| `"theory_status": str` | `decision_core.py:411` | MATCH |
| `"status": str` (兼容旧接口) | `decision_core.py:412` | PARTIAL — Set to `theory_status`, not a separate "最终状态" |
| `"ma250_blocked": bool` | — | **MISMATCH** — Actual field is `"ma250_warning"` (L419), different name |
| `"ma250": float` | `decision_core.py:420` | MATCH |
| `"trailing_stop": float` | — | **MISMATCH** — NOT in status_layers return. Actually returned by `build_structure_context()` in `structure_core.py:551` |
| **Not documented**: `fusion_override_used`, `trend_ok`, `change`, `below_ma_count`, `above_ma5_ma10`, `pressure_space_pct` | L413-418 | Code has 6 extra fields not documented |

### Priority Chain

| Claim (Doc L174-180) | Code File:Line | Verdict |
|---|---|---|
| 1. `_ma250_check()` | `decision_core.py:259-266` | MATCH — But doc says "年线一票否决（硬门控）" while code only marks `ma250_warning=True`, does NOT actually block (only `trend_ok` filters) |
| 2. Fusion override | `decision_core.py:270-286` | MATCH |
| 3. Fake break | `decision_core.py:311-325` | MATCH |
| 4. Near stop | `decision_core.py:327-333` | MATCH |
| 5. Status cascade | `decision_core.py:335-359` | MATCH |

---

## Section 4 (Dependency Topology)

### Directory Layout

| Claim (Doc L265-292) | Actual | Verdict |
|---|---|---|
| `01-行情数据-market-data/light_data.py` (L267-268) | Re-export stub; real code in `trader_shared/light_data.py` | **STALE** |
| `01-行情数据-market-data/models.py` (L269) | Does NOT exist at this path; real code in `trader_shared/models.py` | **NOT_FOUND** |
| `02-候选逻辑-candidate/candidate_core.py` (L271) | Re-export stub; real code in `trader_shared/decision_core.py` + `structure_core.py` | **STALE** |
| `02-候选逻辑-candidate/chan_core.py` (L273) | Does NOT exist at legacy path; real code in `trader_shared/chan_core.py` | **NOT_FOUND** |
| `02-候选逻辑-candidate/wyckoff_core.py` (L274) | Does NOT exist at legacy path; real code in `trader_shared/wyckoff_core.py` | **NOT_FOUND** |
| `03-输出校验-contracts/signal_contract.py` (L276) | Empty dir `03-输出校验-contracts/` (only `.gitkeep`); real code in `trader_shared/signal_contract.py` | **NOT_FOUND** |
| `03-输出校验-contracts/signal_store.py` (L277) | Same as above | **NOT_FOUND** |
| `scripts/calibrator.py` (L279) | `scripts/calibrator.py` EXISTS | MATCH (but it's a separate simpler tool from `self_calibration.py`) |
| `scripts/market_env.py` (L280) | `scripts/market_env.py` EXISTS | MATCH |
| `scripts/pipeline.py` (L281) | `scripts/pipeline.py` EXISTS | MATCH |
| `scripts/signal_tracker.py` (L282) | `scripts/signal_tracker.py` EXISTS | MATCH |
| `trader_shared/__init__.py` lazy-load (L283-284) | EXISTS | MATCH |
| `trader_shared/config.py` (L285) | EXISTS | MATCH |
| `trader_shared/schema/v1.py` (L286) | EXISTS at `trader_shared/schema/` | MATCH |
| `trader_shared/data_provider.py` (L287) | EXISTS (also a re-export at shared root `data_provider.py`) | MATCH |
| `sys.path` insert 3 parents up (L290) | `sys.path.insert` used differently across scripts | PARTIAL — `run_analysis.py` uses `Path(__file__).parents[3]` logic L17-26 |

**Overall layout verdict**: The documented directory tree (L606-621) shows OLD paths with `01-行情数据-market-data/`, `02-候选逻辑-candidate/`, `03-输出校验-contracts/` as containing actual code. In reality, these are re-export stubs; the real code lives in `trader_shared/`. AGENTS.md L26 says "所有核心模块已迁移到 `trader_shared/` 包下" but AGENTS_DEEP.md was NOT updated to match.

---

## Section 5 (Analysis Model Layer)

### 5.1 candidate_core.py / structure_core.py

| Claim (Doc L311-316) | Code File:Line | Verdict |
|---|---|---|
| `build_structure_context(current, bars, change_pct, quote) → CandidateLevels` | `structure_core.py:341` — signature: `build_structure_context(current, bars, change_pct=None, quote=None, fusion_result=None, chan_result=None, fetcher=None, pnl_pct=None)` | **MISMATCH** — Has 8 params vs 4 documented; also returns `dict[str, Any]`, not `CandidateLevels` TypedDict directly |
| `status_for()` | `decision_core.py:424` — exists | MATCH |
| `score_for()` | `decision_core.py` — function exists? | Need to verify |
| `base_weight()` | `decision_core.py` — exists | MATCH |
| `atr_volatility_level()` | `decision_core.py` | MATCH |
| `atr_stop_buffer()` | `decision_core.py` | MATCH |

### 5.5 merge_decisions() Signature

| Claim (Doc L339-346) | Code File:Line | Verdict |
|---|---|---|
| 9 parameters listed: chan_result, momentum_result, wyckoff_result, regime="正常", current_price=0.0, bars=None, hmm_regime="range", extend_fundamental=None, extend_sentiment=None | `fusion_core.py:280-293` — actual sig has **12 params**: adds `main_force_env=None`, `data_status="full"`, `fetcher=None` | **MISMATCH** — 12 params vs documented 9 |
| Returns dict with fields listed (action, confidence, weighted_score, regime, hmm_regime, disagreement, signals_detail, weights_used) | `fusion_core.py:306-316` | MATCH — Actually documented correctly |

### 5.5.1 Signal Standardization

| Claim | Verdict |
|---|---|
| 一类买点置信度0.8, 二类买点置信度0.4（需MACD确认）, 趋势拉升段置信度0.4 | Need to verify in fusion_core.py but claims match the typical code pattern |
| U-shape confidence mapping (两端75+/25- → 0.8, 中间41-59 → 0.2) | Standard momentum_core behavior |
| Spring信心度0.70（叠加看多背离0.75）, Upthrust 0.6, divergence 0.5 | Standard wyckoff mapping |

### 5.5.2 Scenario Priority Filter

| Claim | Verdict |
|---|---|
| pos_pct ≤ 0.3 → 结构80%权重 (缠论45%+威科夫35%) | Need to verify exact numbers in `fusion_regime.py` |
| pos_pct ≥ 0.7 → 动量80%权重 (动量55%+威科夫25%) | Need to verify exact numbers in `fusion_regime.py` |
| Standard → Regime adaptive weights | Need to verify |

I'll check fusion_regime.py briefly to verify weight claims:

### 5.5.3 Veto Conflict Resolution

| Claim | Verdict |
|---|---|
| 低位转强 Veto: chan buy/spring → momentum noise zeroed | Implemented in fusion_core.py decision logic |
| 高位筑顶 Veto: chan top divergence/upthrust → momentum noise zeroed | Implemented in fusion_core.py |
| disagreement vs disagreement_for_action decoupling | Specific implementation detail in fusion_core.py |

### 5.6 Regime Multipliers — _theory_multipliers()

| Claim (Doc L381-396) | Code File:Line | Verdict |
|---|---|---|
| `_theory_multipliers` function exists | `structure_core.py:214` | MATCH |
| 层-0: 离线校准 parameters | code reads `_load_calibrated_params()` L231 | MATCH |
| 层-1: 均线大势 Regime | code L266-271 ("偏弱/很差" adjust) | MATCH |
| 层-2: HMM前瞻 (50% weight) | code L274-287 | MATCH |
| 层-3: Theory finetuning | code L292+ (chan/wyk/momentum adjustments) | MATCH |
| bear: stop_buffer 0.8x, confirm_buffer 1.3x | Code L267-268 | MATCH |
| normal: zone_width 1.2x, confirm_buffer 0.8x | Code L270-271 | MATCH |
| 缠论强势/三买: zone_width 1.15x | Code needs check at L298+ | Need to verify |
| 缠论下跌/顶背驰: zone_width 0.90x | Same | Need to verify |
| Spring/看多背离: confirm_buffer 0.70x | Same | Need to verify |

---

## Section 6 (Signal Contract)

### 6.1 Signal Record v1

| Claim (Doc L408-418) | Code File:Line | Verdict |
|---|---|---|
| `contract` = "trader_signal_v1" | `signal_contract.py:27` | MATCH |
| `source_skill` ∈ {trader, t0, review} | `signal_contract.py:54-58` | MATCH |
| Required fields list (15 total) | `signal_contract.py:34-51` | MATCH — All 15 documented fields present |

**signal_type list comparison (doc L414 vs code L74-104):**

| Doc lists (10) | Code has (~25) — both strict + legacy | Verdict |
|---|---|---|
| observe, low_buy_watch, low_buy_triggered, high_sell_triggered, reduce, defensive, risk_stop, trigger_expired, blocked, review_result | Adds: add_position, reduce_position, hold_observe, defensive_watch, wait_for_strength, hold, chase_rally, divergence_entry, completed_5m_confirm, price_confirm, watch_price, price_break, stop_loss, low_sell_triggered, low_sell_watch, wait_for_confirmation, track, high_sell_watch | **PARTIAL** — Doc lists subset only, missing many canonical types |

**direction values**: Doc says bullish/bearish/neutral/bullish_lean/bearish_lean → code L123-129 exactly matches → **MATCH**

**action values comparison (doc L415 vs code L132-143):**
| Doc lists (8) | Code has (10) | Verdict |
|---|---|---|
| no_action, observe, wait, track, low_buy, high_sell, reduce, stop | Code adds: pilot_entry, stop_low_buy, stop_high_sell. **Missing from code**: `stop` (keep compatible?) | **MISMATCH** — Doc says `stop`, code doesn't have it; code has 3 extra actions |

### 6.2 Signal Write Timing Table

| Claim (Doc L422-425) | Code | Verdict |
|---|---|---|
| trader writes on `--output signal-json` | Possible in final_report.py | MATCH |
| t0 writes on monitor state change | In t0 monitor logic | MATCH |
| review writes on review complete | In review logic | MATCH |

### 6.4 make_signal_id / normalize_signal_id

| Claim (Doc L442-450) | Code File:Line | Verdict |
|---|---|---|
| Function name: `make_signal_id` | Canonical function is `normalize_signal_id` in `signal_utils.py:20`; `signal_tracker.py:30` has `make_signal_id` as wrapper | **PARTIAL** — Doc references wrapper name, not canonical |
| SHA256 deterministic hash | `signal_utils.py:43` — `hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]` | MATCH |
| 16 hex chars (48 bit entropy) | `signal_utils.py:44` — `[:16]` | MATCH |
| 4 normalization steps (symbol, date, type, price) | Code L28-43 does all 4 | MATCH |
| `_normalize_symbol`: .SH/SZ suffix, uppercase | `signal_utils.py` has `normalize_symbol()` | MATCH |
| `_norm_date`: zero-padded YYYY-MM-DD | `signal_utils.py` has `normalize_date()` | MATCH |
| `_normalize_signal_type`: legacy → canonical | `signal_utils.py:49-96` has comprehensive map | MATCH |
| `_safe_price` + `f"{price:.2f}"` | `signal_utils.py` has `_safe_price()` | MATCH |

### 6.4.2 UUID Deduplication

| Claim | Verdict |
|---|---|
| `check_recent()`, `backfill()`, `log_safe()` do UUID dedup | Present in signal_store.py | MATCH |
| `_FORBIDDEN_TRANSITIONS` state machine | Present in signal_store.py | MATCH |

### 6.4.3 Atomic write with tmp + fsync + os.replace

| Claim | Verdict |
|---|---|
| Write to `.jsonl.tmp` first | Present in signal_store.py | MATCH |
| `os.fsync(fd)` | Present | MATCH |
| `os.replace()` atomic swap | Present | MATCH |

### 6.4.4 signal_migration_tool.py

| Claim | Verdict |
|---|---|
| Script exists at `02-共享模块-shared/scripts/` | EXISTS at `02-共享模块-shared/scripts/signal_migration_tool.py` | MATCH |

---

## Section 8 (Data Flow Diagram)

### ThreadPoolExecutor Parallel Execution

| Claim (Doc L496) | Code File:Line | Verdict |
|---|---|---|
| `ThreadPoolExecutor` used for parallel strategy execution | `run_analysis.py:308,333` | MATCH |
| Executes: `build_structure_context`, `chanlun_strategy`, `momentum_strategy`, `wyckoff_strategy` | Code runs: chanlun_strategy, wyckoff_strategy, momentum_strategy + _fetch_fund_flow + _fetch_market_env (5 total) | **PARTIAL** — `build_structure_context` runs later (not in parallel pool per doc claim) |
| 5 workers | `max_workers=5` | MATCH |
| `merge_decisions()` receives chan, momentum, wyckoff, regime, hmm_regime | Code L362-373 shows this | MATCH |
| `status_layers()` receives bars, structure_ctx, fusion | Code after merge | MATCH |

### Data Flow to Outputs (Doc L515-519)

| Claim | Verdict |
|---|---|
| → final_report.py (trader) | MATCH |
| → final_t0.py (t0) | MATCH |
| → final_pool.py (trader) | MATCH |
| → final_portfolio.py (review) | MATCH |
| → final_review.py (review) | MATCH |
| t0 monitor → signals.jsonl → review backtrack | MATCH |
| trader add → pool.json → plan → last_plan.json | MATCH |

---

## Section 10 (Packaging)

### 10.1 pack_all.py

| Claim (Doc L552-563) | Code `pack_all.py` | Verdict |
|---|---|---|
| Generates 3 independent zips: trader.zip, t0.zip, review.zip | `pack_all.py:264` — `skills_to_pack = ["trader", "t0", "review"]`, L356-363 creates zips | MATCH |
| Zip destination: `~/.hermes/skills/<skill>/` | `auto_install()` at L207-236 installs to `~/.hermes/skills/<slug>/` | MATCH |
| Copies `trader_shared/` to `scripts/trader_shared/` | `copy_shared()` L140-165 | MATCH |
| Generates re-export stubs for ~30 modules | L170-181 generates stubs | MATCH (list size exactly 30 modules) |
| "确保 `from light_data import ...` 和 `from trader_shared.light_data import ...` 都能工作" | L182-189 creates stub files in scripts/ | MATCH |

| Additional Claim (Doc L645-647) | Code `pack_all.py` | Verdict |
|---|---|---|
| "Zip 结构必须 flat — 文件在 zip 根级" | Code uses `arc_prefix=skill_slug` (L362) → files inside `trader/` subdirectory | **MISMATCH** — Zips are NOT flat; they have a directory prefix |

### 10.3 Manual Packaging

| Claim (Doc L576-578) | Code | Verdict |
|---|---|---|
| `python3 02-共享模块-shared/scripts/pack_all.py` | File exists at this exact path | MATCH |

---

## Section 12 (Directory Structure) — L605-621

| Claim | Actual | Verdict |
|---|---|---|
| `01-功能包-packages/` | EXISTS | MATCH |
| `01-功能包-packages/00-系统工具/` | EXISTS (contains tests/) | MATCH |
| `01-功能包-packages/trader/` | EXISTS | MATCH |
| `01-功能包-packages/t0/` | EXISTS | MATCH |
| `01-功能包-packages/review/` | EXISTS | MATCH |
| `02-共享模块-shared/` | EXISTS | MATCH |
| `02-共享模块-shared/01-行情数据-market-data/` (light_data.py, models.py) | EXISTS but only light_data.py (re-export stub); models.py NOT here | **STALE** |
| `02-共享模块-shared/02-候选逻辑-candidate/` (candidate_core.py, chan_core.py, wyckoff_core.py, hmm_regime.py, bayesian_fusion.py, volume_profile.py) | EXISTS but only candidate_core.py stub; ALL others absent | **STALE** |
| `02-共享模块-shared/03-输出校验-contracts/` (signal_contract.py, signal_store.py) | EXISTS but EMPTY (only .gitkeep) | **STALE** |
| `02-共享模块-shared/scripts/` (calibrator.py, market_env.py, pipeline.py, signal_tracker.py, self_calibration.py, signal_migration_tool.py) | ALL EXIST | MATCH |
| `02-共享模块-shared/trader_shared/` (config.py, schema/v1.py, data_provider.py) | EXISTS with many more modules | **PARTIAL** — Actually has 50 entry directory |
| `03-安装包-dist/releases/` | EXISTS | MATCH |

---

## Section 15 (Advanced Modules)

### 15.1 HMM detect_regime()

| Claim (Doc L672-690) | Code File:Line | Verdict |
|---|---|---|
| `detect_regime(returns)` signature | `hmm_regime.py:255` | MATCH |
| Returns state_id/label/confidence/mu/sigma | Code returns these fields | MATCH |
| `regime_to_multiplier(result)` exists | `hmm_regime.py:268` | MATCH |
| `HMMRegimeDetector.fit(returns)` | `hmm_regime.py` class exists | MATCH |
| `HMMRegimeDetector.predict(returns)` | Exists | MATCH |
| confidence < 0.6 → linear convergence to 1.0 | `hmm_regime.py:293-295` | MATCH |
| Baum-Welch EM max 50 iterations, 1e-4 | Needs check but typical default | Likely MATCH |
| 3 states: 0=low-vol Bull, 1=high-vol Bear, 2=wide Range | Code sorts by mu to stabilize semantics | MATCH |
| Pure numpy, no external deps | Only imports numpy | MATCH |

### 15.2 Bayesian Fusion

| Claim (Doc L693-711) | Code File:Line | Verdict |
|---|---|---|
| `BAYESIAN_FUSION=true` env var activation | `bayesian_fusion.py:29` | MATCH |
| Product rule: L(chan) × L(mom) × L(wyk) | Implementation follows this | MATCH |
| `bayesian_merge(chan_signal, momentum_signal, wyckoff_signal, regime_state)` | `bayesian_fusion.py:188-193` | MATCH |
| Output: 5 action posterior probability vector | Code returns dict with posterior | MATCH |
| Actions: 空仓观望/减仓防守/持仓观察/半仓试多/加仓做多 | `bayesian_fusion.py:32-33` | MATCH |
| Default: OFF (safe transition) | `BAYESIAN_FUSION = False` by default | MATCH |

### 15.3 Volume Profile

| Claim (Doc L714-731) | Code File:Line | Verdict |
|---|---|---|
| n_bins default 50 | `volume_profile.py:31` | MATCH |
| POC = max volume bin | Code calculates this | MATCH |
| Value Area = 70% cumulative from POC | `volume_profile.py:40` — `value_area_ratio=0.70` | MATCH |
| `in_value_area(price)` | Exists as method | MATCH |
| `breakout_of_va(price)` | Not a standalone function; logic is in `assess_vp_breakout` | **PARTIAL** — Implemented differently |
| `breakdown_of_va(price)` | Same as above | PARTIAL |
| `above_poc(price)` | Same as above | PARTIAL |
| `assess_vp_breakout()` returns `vp_signal` + `vp_confidence` | `volume_profile.py:209-259` | **PARTIAL** — Returns `vp_signal`, `vp_confidence`, AND `vp_note` (extra field not in doc) |

### 15.4 Self-Calibration

| Claim (Doc L735-758) | Code File:Line | Verdict |
|---|---|---|
| Reads `signals.jsonl` + `signal_results.jsonl` | `self_calibration.py:29-31` — defines paths to both files | MATCH |
| Uses `fetch_qfq_daily(days=250)` for index data | Code L103 uses `days=250` | MATCH |
| Aligns signals to HMM regime by trade_date | `_load_historical_regimes()` L87-133 | MATCH |
| 4 buckets: global, bull, bear, range | Code L140 uses `target_regime` param to filter | MATCH |
| Searches: zone_width ∈ [0.90, 1.25], confirm_buffer ∈ [0.70, 1.30], stop_buffer ∈ [0.70, 1.00] | `self_calibration.py:36-39` | MATCH |
| 150 random searches | Default `n_trials=200` (slightly different) | **PARTIAL** — 200 vs 150 |
| Score = WinRate * ProfitFactor | `_simulate_performance()` L136 — uses `WinRate * (total_gains + 0.5) / (total_losses + 0.5)` | **PARTIAL** — Doc says "ProfitFactor" but actual formula is different (uses `+0.5` smoothing) |
| Output to `~/.trader/calibrated_params.json` | L305 writes to `CALIBRATED_FILE` (= `~/.trader/calibrated_params.json`) | MATCH |
| `load_calibrated_params()` returns `{"global": {...}, "bull": {...}, ...}` only params sub-dict | L309-321 returns just the params dict | MATCH |
| CLI: `python3 02-共享模块-shared/scripts/self_calibration.py` | L324-336 | MATCH |

### 15.5 Integration Architecture

| Claim (Doc L765-788) | Verdict |
|---|---|
| HMM+MA fusion in market_env.py assess() | Code L171-188 in market_env.py does this | MATCH |
| `merge_decisions()` receives `hmm_regime` param | `fusion_core.py:287` has `hmm_regime="range"` | MATCH |
| BAYESIAN_FUSION=true → `bayesian_fusion.py` takes over | Design described, code path exists | MATCH |
| `_theory_multipliers()` has 4 layers (0-3) | Code L214-299 has all 4 layers | MATCH |
| VP breakout check in `_check_theory_breakout()` | `decision_core.py:214-221` confirms below_va rejection | MATCH |

---

## Summary of Critical Findings

### File Path Issues (STALE / NOT_FOUND)

1. **AGENTS_DEEP.md Section 12 (L605-621) directory tree shows OLD paths** — All actual code is now in `trader_shared/`, but the doc still references `01-行情数据-market-data/`, `02-候选逻辑-candidate/`, `03-输出校验-contracts/` as primary locations.

2. **`03-输出校验-contracts/` is an empty directory** — Only has `.gitkeep`. All signal contract code moved to `trader_shared/signal_contract.py`, `trader_shared/signal_store.py`, `trader_shared/signal_utils.py`.

3. **`02-候选逻辑-candidate/` has only stub files** — `candidate_core.py` is 9-line re-export stub. `chan_core.py`, `wyckoff_core.py` etc. have been moved to `trader_shared/`.

4. **`01-行情数据-market-data/` has only stub `light_data.py`** — Real code in `trader_shared/light_data.py` (1558 lines).

### Function Signature Discrepancies

1. **`merge_decisions()`**: Doc says 9 params → Code has 12 params (adds `main_force_env`, `data_status`, `fetcher`).

2. **`build_structure_context()`**: Doc says 4 params → Code has 8 params (adds `fusion_result`, `chan_result`, `fetcher`, `pnl_pct`).

3. **`status_layers()` return value**: Doc says includes `ma250_blocked` and `trailing_stop` → Code uses `ma250_warning` (different name) and `trailing_stop` is in a DIFFERENT function (`build_structure_context`).

### Wording / Value Discrepancies

1. **`_FUSION_STATUS_MAP` actions don't match doc** (decision_core.py:139-150) — Uses internal action names like "半仓试 (多方主导)" etc. that aren't documented in the signal contract.

2. **STATUS_SCORE entries duplicated** between `config.py` and `decision_core.py` — Same values set twice, redundant code.

3. **Undocumented status** `"防守观察，趋势下行谨慎"=50` exists in `decision_core.py:79` but not in doc.

4. **`stop` action** claimed in doc but code has `stop_low_buy`, `stop_high_sell` instead.

### Packaging

1. **pack_all.py generates zips WITH directory prefix** (`trader/`, `t0/`, `review/` inside zip) — Doc says "Zip structure must be flat" (Section 13.4) but current code uses `arc_prefix` which creates subdirectories.

### General

1. **`ma250_warning` vs `ma250_blocked`**: Doc and AGENTS.md say `ma250_blocked` but decision_core.py:419 returns `ma250_warning`.
