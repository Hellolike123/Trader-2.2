# golden 门禁 seam 缺口修复 handoff

> 状态：active（2026-08-06）
> 触发：门禁每次 golden 漂移红（600000），怀疑 seam 未堵全
> 法源：`mock_seam.apply_seam` · `chip_stage` · `chip_core` · `chip_migration_monitor` · `main_force_scoring`

## 一、根因（实证）

`apply_seam` 已 mock：sector / env / `fetch_fund_flow_cached` / `chip_data.get_cyq_perf`（非 cached）/ tushare client。但 golden 仍漂移——**三个真实文件缓存/状态穿透**：

1. `chip_stage.get_cyq_perf_cached` / `get_cyq_chips_cached`（`chip_data`，函数内 import）→ 读真实 `~/.trader/cache/cyq_*` → chip_peaks=真实（8.61/8.81）
2. `chip_core.check_chip_migration`（模块级 pattern-2 import）→ 读真实 `~/.trader/chip_history.json` → chip_migration.has_history=true
3. `chip_core.save_chip_snapshot` → **每次跑 golden 都写真实 chip_history.json（污染生产状态）**

连锁：`score_main_force` 条件 `mf_features or big_order or chip_has_history` → 真实 history 触发评分 → 「主力6/15 · 大单…」文案渗入 → 新开「另2项→另1项」。

## 二、必须（验收表）

| # | 必须项 | 验收 |
|---|--------|------|
| 1 | seam 下 chip_peaks 从 mock bars 算（cyq 空） | seam 跑 600000 chip_peaks 确定性 |
| 2 | chip_migration 无历史（check 返回空、无文件读取） | seam 跑 600000 chip_migration.has_history=False |
| 3 | save_chip_snapshot 被 no-op（不污染真实 chip_history.json） | 跑 golden 前后 chip_history.json diff 空 |
| 4 | golden 门禁**稳定绿**（修复后刷新基线） | `golden_diff_gate.py check` exit 0 |
| 5 | 不改变生产行为（seam 仅测试用） | 生产路径 diff 为空 |

## 三、禁止

- 禁止改 `chip_core` / `chip_stage` / `chip_migration_monitor` 生产逻辑（seam 是测试缝，不是生产修复）
- 禁止把 mock 逻辑混入生产模块
- 禁止删真实 `chip_history.json` / `~/.trader/cache/cyq_*`（生产状态，仅 seam 屏蔽读取）

## 四、可改文件白名单

- `02-共享模块-shared/trader_shared/testing/mock_seam.py`（apply_seam 补 4 个 mock）
- `tests/golden/`（刷新基线）
- 本 handoff

## 五、执行顺序

1. mock_seam 补：`chip_data.get_cyq_perf_cached`→None、`get_cyq_chips_cached`→[]、`chip_core.check_chip_migration`→确定性空、`save_chip_snapshot`→no-op
2. 验证 #3（chip_history.json 前后 diff 空）
3. 刷新 golden 基线（反映修复后确定性行为）
4. 门禁跑绿（#4）
5. 本 handoff 归档

## 六、执行结果（2026-08-06）

- **mock_seam 补 4 个 mock**：`get_cyq_perf_cached`→None、`get_cyq_chips_cached`→[]、`chip_core.check_chip_migration`→确定性空、`save_chip_snapshot`→no-op（防污染）
- **验证**：#1 chip_peaks 从 mock bars 算（确定性）✅ · #2 chip_migration 无历史 ✅ · #3 chip_history.json 全程 MD5 不变 ✅ · #4 两次 diff 逐字一致 → 刷新基线 → **CHECK PASSED** ✅
- **连锁刷新**：`tests/golden/600000.*` + `tests/fixtures/report_render_baseline.txt`（差异=确定性新行为：筹码 8.81 来自 mock bars、主力6/15 为 main_force_scoring 既有接入，旧基线未随代码演进刷新）
- **门禁**：**742 passed / 0 failed**（历史首次全绿，此前 2 failed 均为 golden 漂移）

## 七、b 排查结论（wyckoff rank / 其他批量路径）

- **`wyckoff rank` 实测 0.56s**：`build_wyckoff_rank_rows` 读 pool.json 缓存（`attach_wyckoff_chain_fields`），**不跑 build_report / load_market_snapshot** → 无死锁、无慢，**无需修复**
- 单票 `wyckoff --target` 走 `load_market_snapshot(5m=False)`（无外层池占用 → 无死锁风险）
- refresh 链路 4 层池（trader-prewarm / trader-pool-refresh / trader-build / trader-enrich）互不嵌套，实测无死锁
- **结论：批量路径排查完成，除已修的 refresh 死锁外无其它问题**
