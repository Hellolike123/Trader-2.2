# 隐式状态地图（D1 阶段一·调研）

> 来源 handoff：`docs/plans/system-observability-optimization-handoff.md` §1
> 状态：阶段一完成（仅调研，未改码）。阶段二防护待排期。
> 扫描范围：`02-共享模块-shared/trader_shared/` + `scripts/` + `01-功能包-packages/*/scripts/`
> 方法：grep `~/.trader` / `expanduser` 落盘点 + 读关键 `_load/_save` 实现，确认版本号/失效条件/跨进程安全。

## 地图表

风险等级：**红**=无版本号且无失效策略（改阈值/改 schema 后旧缓存仍用老结论）/读写假设可能不一致；**黄**=有自愈/隔离但无显式版本号；**绿**=已有自描述标记或健全锁。

| # | 文件 / 目录 | 写谁 (文件:行) | 读谁 (文件:行) | 版本号 | 失效条件 | 跨进程安全 | 风险 |
|---|-------------|----------------|----------------|--------|----------|------------|------|
| 1 | `~/.trader/wyckoff_phase.json` | `wyckoff_phase.py:_save_phase_state:863`（locked_rmw） | `_load_phase_state:850` | ❌ 无 | 无（仅 `first_seen`） | ✅ fcntl 锁 | 🔴 红：改检测器阈值后旧 phase 结论仍黏住；日线/中线按 `symbol::timeframe` 隔离但无 schema 版本 |
| 2 | `~/.trader/wyckoff_phase_a_anchor.json` | `wyckoff_phase_a_store.py:save_phase_a_anchor:98` | `load_phase_a_anchor:57`（含 `ts`） | ❌ 无 | 自愈：`sc_bar_idx` 越界/`status` 失效→删键 | ✅ locked_rmw | 🟡 黄：有自愈+时间戳，但无 schema 版本，旧格式无 `ts` 字段不识别 |
| 3 | `~/.trader/stage_state.json` | `stage_state.py:_save_stage_state:175` | `_load_stage_state:154` | ❌ 无 | 无显式失效；有旧格式迁移（顶无 symbol key→当全局） | ✅ 读写同文件 | 🔴 红：跨日黏住；旧格式兼容分支一旦新写者只写 symbol 维度会丢失全局态 |
| 4 | `~/.trader/buy_point_lifecycle.json` | `buy_point_lifecycle.py:save_failed_record:172` | `load_failed_record:160` | ❌ 无 | 业务逻辑自带跨日失效（失败日+新 id 才解禁） | ✅ locked_rmw | 🟢 绿：失效由语义控制，非缓存时效问题 |
| 5 | `~/.trader/backtest_cache/` | `scripts/backtest_engine.py:主进程写`（tmp+fsync+replace） | 同文件读 | ⚠️ 隐式（文件名含 days 参数） | **写前 `_sanity_check`：收盘价相对中位数 >5× 即判坏点拦截**（:725） | ✅ 落盘确定性数据 | 🟢 绿：**阶段二防护的参考样板** |
| 6 | `~/.trader/intraday_cache/` | `scripts/intraday_backtest_engine.py:90` | 同文件读 | ❌ 无 | 无 | ⚠️ 子进程/天隔离 | 🟡 黄：靠进程隔离避 OOM，但无坏点断言（不如 backtest 严谨） |
| 7 | `~/.trader/cache/{daily,weekly}/*.json` | `light_data.py`（腾讯成功路径 :1724 等 `_stamp_vol_unit`） | `light_data.py:fetch_weekly` 读 :1989 | ✅ **`vol_unit="lot"` 自描述标记** | 旧格式（无 `vol_unit`/`share`）→ 强制回源重写（:1991） | ✅ 读后断言单位 | 🟢 绿：单位自描述+旧缓存作废，是轻量版本化范例 |
| 8 | `~/.trader/cache/fund_flow/` | `fund_flow_data.py:263` 目录 | `fund_flow_data.py` 读 | ❌ 无 | `cached_at` 时间戳但无 TTL 强制 | ⚠️ 未确认锁 | 🟡 黄：有 `cached_at` 但无失效策略（MEMORY 记格式 `{"data":[...],"cached_at":...}`） |
| 9 | `~/.trader/chanlun_state/` | `config.CHANLUN_STATE_DIR:120` | chanlun 引擎读 | ❌ 无 | 无 | ⚠️ 未确认 | 🟡 黄：缠论中枢快照，无版本→改中枢算法后旧快照不失效 |
| 10 | `~/.trader/tick_cache/` | `tick_cache.py:CACHE_DIR:8` | 同文件读 | ❌ 无 | 无 | ⚠️ 未确认 | 🟡 黄 |
| 11 | `~/.trader/signals.jsonl` / `signal_results.jsonl` | `signal_tracker.py` / `signal_migration_tool.py` | 复盘读 | ✅ **signal_id 稳定化（UUID 长 hex）** + 迁移脚本 | 追加写，无缓存时效问题 | ✅ 追加 | 🟢 绿：事件流非缓存，迁移工具已处理旧 MD5 |
| 12 | `~/.trader/pool.json` / `pending.json` / `last_plan.json` | `daily_briefing/pool_cmds/*` + `backtest_t0.py:370` | 池排序/回测读 | ❌ 无 | 无 | ⚠️ 多写者 | 🟡 黄：多入口写（`final_pool`/`backtest_t0`/`briefing`），无锁易互覆盖 |
| 13 | `~/.trader/holdings.json` / `position.json` / `positions.json` | `holdings.py` / `final_review.py:25` | 持仓读 | ❌ 无 | 无 | ✅ SSOT（holdings.py） | 🟡 黄：双写 legacy（`position.json`/`positions.json`），不一致风险 |
| 14 | `~/.trader/calibrated_params.json` | `self_calibration.py:13` | 同文件读 | ❌ 无 | 无（自校准产物） | ⚠️ 单写者 | 🟡 黄：参数校准结果，无版本→改校准空间后旧参数复用 |
| 15 | `~/.trader/api_limits.json` | `light_data.py:limit_file:290` | 同文件读 | ❌ 无 | 限流计数自然过期 | ✅ 简单 | 🟢 绿：时效由计数逻辑保证 |
| 16 | `~/.trader/trailing_stop_watermark.json` | `structure_core` 持仓票写（只紧不松） | 同文件读 | ❌ 无 | 无仓不落（避免无仓误抬） | ✅ 持仓维度 | 🟢 绿：语义隔离 |
| 17 | `~/.trader/last_target.txt` | `run_trader.py:257/302` | 同文件读 | ❌ 无 | 无 | ⚠️ 单写 | 🟢 绿：纯提示 |
| 18 | `~/.trader/t0_ledger.jsonl` / `position.json` | `t0_ledger.py` / `t0_account.py` | T0 读 | ❌ 无 | 追加/覆盖 | ⚠️ 未确认锁 | 🟡 黄 |

## 阶段一结论

- **🔴 必须进阶段二防护（标红）**：#1 `wyckoff_phase.json`、#3 `stage_state.json`。两者都是「改代码后旧结论不失效」的高危点，且均无 schema 版本号、无失效策略。#1 已是前序 handoff 反复踩坑点（日线 phase 跨日黏住、改阈值旧缓存不刷新）。
- **🟡 可顺手补版本号（低风险）**：#2/#8/#9/#10/#12/#13/#14/#18 加一个 `"schema_version"` 字段，读时不符即作废重算。#12 pool 还需加锁防多写者互覆盖。
- **🟢 已有防护，仅作样板**：#5 backtest 坏点断言、#7 vol_unit 自描述、#11 signal_id 迁移，是阶段二要复用的写法。

## 阶段二待办（未做，待排期）

对 #1/#3 补 `schema_version` + 失效策略（版本不符即 `locked_rmw` 内删键重算），复用 #5 的 `>5× 中位数` 断言思路（针对数值型缓存）。加测：改 schema 版本号 → 旧缓存被作废 → 重算。

## 验收对照（handoff §1）

- [x] 阶段一：隐式状态地图表（≥8 项，实际 18 项），每项标风险等级 ✅
- [ ] 阶段二：标红项补版本号 + 失效测（待排期，本 turn 未做）
