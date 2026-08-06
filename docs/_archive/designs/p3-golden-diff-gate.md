# P3 · Golden-diff 闸门

> 把散在 3 个测试 + 2 个 capture 脚本里的"离线确定性 seam"收编为单一真相源，
> 并升级成一个能独立跑、能比多副本的回归闸门。

## 背景 / 痛点

| 现状（改造前） | 问题 |
|---|---|
| `test_build_report_golden.py` / `test_build_report_adr002_equivalence.py` / `test_report_render_equivalence.py` | 三份**复制**的 mock seam（`_MockProvider` / `_gen_bars` / `_UnavailableClient` / monkeypatch 固件） |
| `scripts/_render_eq_capture.py` / `scripts/_capture_adr002_baseline.py` | 又两份 seam，且用**裸赋值** `_fetchers.TencentFetcher = MockFetcher`（不还原会污染后续测试，记忆里点名的坑） |
| 单票 600000，无 CLI | 改完代码想"跑一下闸门"只能进 pytest；没法给另一个 skill 副本跑同一闸门 |
| 无多副本比对 | **07-08 双副本安装错位**（`~/.workbuddy/skills/trader` 改了、`~/.hermes/skills/trader` 没改 → `data_status=partial`）没人抓 |

## 设计

### 1. 单一真相源 `trader_shared/testing/mock_seam.py`
- `gen_bars` / `MockProvider` / `UnavailableClient`：合成确定性数据。
- `apply_seam(patcher)`：堵**所有**网络泄漏点（`TencentFetcher` / `get_env_for_skill` / `fetch_fund_flow_cached` / `tushare_client.get_client` / `chip_data.get_cyq_perf` / `run_analysis.read_signals_for_report`）。
  - `patcher` 抽象：pytest 传 `monkeypatch` 固件；CLI 传自带的 `_Patcher`（`undo()` 还原）。**一律走 patcher，禁止裸赋值**。
- `mask_dates` / `render_under_seam` / `build_under_seam` / `extract_fields` / `approx_equal`：复用工具。

### 2. 统一 CLI `scripts/golden_diff_gate.py`
- `capture`：按 `tests/golden/golden_config.json` 重抓 golden（`<symbol>.render.md` 掩码渲染 + `<symbol>.fields.json` 精确字段）。
- `check`（默认）：跑 seam 比对 golden，**渲染逐字节 + 字段精确**双比对，exit 1 即失败。
- `--replicas PATH...`：对每个副本子树 subprocess 跑同一 capture 并比对 primary golden → 抓双副本 staleness。

### 3. 配置 `tests/golden/golden_config.json`
```json
{ "tickers": [ { "symbol": "600000", "render": true,
  "fields": ["fusion.weighted_score","fusion.confidence","fusion.action",
             "fusion.disagreement","chanlun_midline","wyckoff_midline"] } ] }
```
后续加票只需往数组里加一项（纯加法）。

### 4. 门禁接入
- 新增 `test_golden_diff_gate.py`（调 `golden_diff_gate.main(["check"])`，断言 rc==0）。
- 加入 `scripts/run-gate-tests.sh` 的 `TESTS` 数组 → 每次 `git push` 强制跑。

## 保真度验证（关键）
新 seam 抓出的 600000 基线，与旧 `report_render_baseline.txt` / `report_baseline.json` **逐字节 + 字段完全一致**（RENDER IDENTICAL / FIELDS IDENTICAL），证明收编零行为漂移。

## 收益
1. **去重**：4 份 seam → 1 份；未来修泄漏点只改一处。
2. **可独立运行**：`python scripts/golden_diff_gate.py check` 任何人都能秒级自测。
3. **多副本守卫**：`--replicas` 直接抓 07-08 类双副本错位——改完 skill 主副本后，对另一份跑同一闸门即可确认没 drift。
4. **门禁强化**：渲染逐字节 + 字段精确双比对，比单一范围断言更能抓"文案一改融合静默漂移"。

## 已知边界（同 ci-gate.md）
- 守"行为不变"不守"行为正确"：基线若本就带 bug，门禁会锁成绿。
- `--replicas` 依赖副本树内能找到 `trader_shared` 包与 `golden_diff_gate.py`；找不到则 `[SKIP]`。
