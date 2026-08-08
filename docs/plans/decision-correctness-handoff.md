# 决策正确性·已登记问题 handoff（核验后真状态）

> 来源：用户在 observability handoff 之外补充的 5 个"当下就在影响决策"的问题。
> 接手方式：先逐条**核验现状**（代码已漂，MEMORY 旧笔记不可信），再决定改不改。
> 关键结论：**#1 / #3 / #5 的旧账大部分已被修过，真实残留比最初描述的要小**；#2 / #4 是诚实性问题，且 #4 的前提已变。

---

## 优先级（用户拍板）

1. **#1 动量席双关** — 项目自登债、直接喂 fusion；但核心已修，残留=重归一化，需 D4 语义快照作安全网。
2. **#2 北向假接入** — 诚实性，低风险。
3. **#4 tushare 兜底诚实性** — 诚实性；前提已变（实际 mootdx）。
4. **#3 test_contract 3 失败** — 卫生；实测已绿、不在门禁。
5. **#5 渲染死代码** — 卫生；行号漂，2 处确认死、1 处已修。

---

## #1 动量席 score=50 双关（核心已修，残留=重归一化）

### 核验后现状
- `momentum_core.py:144-161`：`len(bars) < 30`（两个分支）已返回 `score=None, direction="insufficient"`，注释明写"避免与真中性 score=50 混淆"。**假 50 已被消除。**
- `analysis/fusion_card_signals.py:158-170`：`dir_map = {"bullish":1,"bearish":-1,"neutral":0,"insufficient":0}`，`direction="insufficient"`→`direction=0` + `reason="动量数据不足"`。故 fusion 不再把 insufficient 当 bullish/bearish 50，**也不崩**（direction 是 int，L406 max/min 安全）。
- `fusion_core.py:361-367`：`mom_score = _raw_score if (是数字 且 direction!="insufficient") else None`——climax 判定已对 insufficient 置 None。

### 真实残留（要修的点）
- `fusion_core.py:427-431` 加权段：`weighted_score = chan*conf*w_chan + momentum*conf*w_mom + vpf*conf*w_vpf`。**insufficient 动量 `direction=0` 仍以满权重 `w_mom` 参与**，贡献 0，与真中性数学等价。
- 用户要的"fusion 侧判为缺位，降权或跳过"**没落地**：insufficient 只是贡献 0，没有把权重 redistribut 给 chan/vpf，所以 chan/vpf 没有"主导权上升"。
- 即：下游仍无法区分"数据不足"与"真中性"对**最终加权分**的影响（两者都让 momentum 项=0）。元数据（reason="动量数据不足" / strength="insufficient"）能区分，但加权分不能。

### 修复方案（须配 D4）
- 在加权前判断 `momentum_signal.get("direction") == "insufficient"` 或 `score is None`：
  - 将 `w_mom` 从三席权重中摘除，按 `w_chan/(w_chan+w_vpf)`、`w_vpf/(w_chan+w_vpf)` 重归一化 chan/vpf 权重（即"跳过"动量席）。
  - 或在 `directions` 列表里把 momentum 项排除出分歧计算（避免 insufficient 被当中性 0 拉低 disagreement）。
- **禁止**：改回"insufficient 给 50"（倒退）。

### 风险
- 改变"数据不足"票的加权结果：chan/vpf 权重上升 → 部分票结论可能变（尤其动量本就边缘的票）。
- **必须**：先铺 D4 语义快照（10+ 票 phase+fusion 轨迹），改后再跑 diff，逐票看"变得对不对"。

### 依赖
- D4 语义级回归测（observability 计划项）必须先建好作安全网。

### 验收
- 单测：`test_insufficient_momentum_renormalized` — 构造 momentum insufficient + chan/vpf 非零，断言 weighted_score 与"把 momentum 权重分给 chan/vpf"一致，且 ≠ "momentum 中性 50" 的结果。
- D4 快照：改动前后逐票 diff，附"变了哪些、对不对"说明。

---

## #2 北向假接入（诚实性，低风险）

### 核验后现状
- `trader_shared` 渲染层**无"北向"字样**（grep "北向" 全仓只在 fusion_core / extend_data / data_provider 内部）→ **不是面板假行**，用户最初担心的"面板看着有实际 no-op"在当前渲染不成立。
- 北向仅在 `fusion_core.py:640-648` 做置信度微调：`if extend_northbound.get("status")=="正常"` 才按 `north_net_flow_wan` / `north_flow_5d_wan` 微调 confidence（±5%/±2%）。
- `extend_data.py:513-595` `get_northbound_flow`：用户 MEMORY 记"akshare 当日成交净买额 2020+ 全 NaN → no-op"。需核 `status` 字段是否被诚实置为"不可用"还是仍"正常"。

### 真实风险
- 若 `status` 被置"正常"而底层净买额全 NaN，则微调基于 NaN→`safe_float`→0，等价 no-op；用户可能误以为"北向在影响置信度"。属内部诚实性问题，非可见误导。

### 修复方案（二选一，低风险）
- A（推荐，零判定影响）：在 `get_northbound_flow` 里对全 NaN 诚实标 `status="不可用"` 并打 warning；fusion 侧 `status!="正常"` 自然跳过微调。
- B：找替代源（港股通每日净买额别的数据）。成本较高，本 handoff 不强制。

### 禁止
- 禁止伪造北向数；禁止在无数据时仍显示"北向正常"。

### 验收
- 单测：注入全 NaN 北向，断言 `status != "正常"`，fusion confidence 不被北向微调。

---

## #3 test_contract 3 失败（已绿，不动作）

### 核验后现状
- `pytest 01-功能包-packages/trader/tests/test_contract.py` → **37 passed, 0 failed**。
- `scripts/run-gate-tests.sh` 的 `TESTS` 数组**不含** test_contract.py（门禁跑的是锁定的离线核心集）。
- 故"门禁里 3 个失败"在当前代码与环境不成立；狼来了效应当前不存在。

### 结论
- 无需处理。若担心回归，可显式把 test_contract.py 加入门禁（它是离线确定性集，加进去即锁绿）。

---

## #4 tushare 兜底诚实性（前提已变，实际 mootdx）

### 核验后现状（本机实测）
- `TUSHARE_TOKEN` 环境变量：未设；`TRADER_DATA_PROVIDER`：未设。
- `dp._tushare_available()` → **True**（token 来自 `tushare_client` 配置文件，非 env）。
- `dp.get_provider()` → `UnifiedProvider(backend="mootdx")`。
- 即本机实际数据源 = **mootdx（通达信直连）**，既不是 tushare 也不是 tencent。选择逻辑：`get_provider()` 在 WorkBuddy host 且 `_check_mootdx()` 为真时优先 mootdx，先于 tushare/tencent。

### 用户原担忧 vs 现实
- 原担忧"以为 tushare 实际 tencent"与当前状态不符：实际是 mootdx。
- 但**透明度问题仍在**：连我自己都要跑代码才知后端是 mootdx；报告里没有 `_meta` 暴露真实源。这正是 observability D5（数据源溯源 `_meta`）要解决的。

### 修复方案
- 落地 D5：`report["_meta"]` 含 `daily_source` / `daily_cached` / `vol_unit` / `5m_source` / `weekly_source` / `tushare_available` / `fetched_at`。
- 验证：本机跑单票，`_meta.daily_source == "mootdx"`（或 fetch 时若 mootdx 失败回退则显 "tencent"）。
- 顺带确认 mootdx 在 fetch 失败时是否回退 tencent（data_provider.py:784 `_fallback = UnifiedProvider(backend="tencent")` 存在，需确认触发路径）。

### 风险
- 低（仅加 _meta，不改面板渲染）。

---

## #5 渲染死代码（行号漂，2 处确死、1 处已修）

### 核验后现状（`report_renderer/short_midline.py`）
- **`_mom_dir2` 漏 `_safe_int`**：已修。L1533 = `_mom_dir2 = _safe_int(_msig.get("direction", 0))`（与 commit 0c58ed6 修的 `_chan_dir2` 同款）。✅ 旧账已清。
- **`_rr_chase_verdict`（L1639）**：定义后**零引用**（其兄弟 `_rr_buy_verdict` L1638 在 L1705 被用）。→ 确认死代码。
- **`key_levels`（L1835）**：`key_levels = r.get("key_levels") or {}` 后**零引用**。→ 确认死代码。

### 修复方案
- 删除 L1639 `_rr_chase_verdict = ...` 整行。
- 删除 L1835 `key_levels = r.get("key_levels") or {}` 整行（若后续无使用）。
- 低风险纯清理。

### 验收
- `tests/test_report_renderer.py` 跑通；`short_midline.render_short_midline` 冒烟无 NameError。

---

## 执行顺序建议

1. **D4 语义回归（安全网）** → 解锁 #1 残留修复。
2. **#1 重归一化**（在 D4 快照上改 + diff）。
3. **#5 死代码清理**（顺手，零风险）。
4. **#2 北向诚实化**（A 方案）。
5. **#4/D5 数据源 _meta**（透明度）。
6. #3 不动作（已绿）。

## 禁止项（全局）
- 禁止把 insufficient 动量改回 50（倒退 #1）。
- 禁止伪造北向/任何数据源数。
- 禁止为"清理"删有引用代码（删前 grep 确认零引用）。
- 禁止在没 D4 快照的情况下改 fusion 加权逻辑（无安全网=盲改）。

---

## 补充项（第四轮审计，非决策正确性但影响数据可信度）

> 以下 5 项来自第四轮深层审计，与上面 #1-#5 互补。前三项是「你以为对了实际可能错」的数据根，后两项是架构/运维债。

### S1. 周线数据口径确认【已核验风险点，待确认影响】

**核验现状**：
- `light_data.py:1901` `fetch_weekly` 从源取周K
- `light_data.py:1907` 注释：「若上游周线接口实际吐出日线间距（mootdx cat=5 曾如此），丢弃并改由日线聚合周线」——**有 fallback 到日线聚合**
- `report_builder.py:241` `weekly_proxy_close = float(bars[-5]["close"])`——**用日线倒数第 5 根 close 当周 proxy**，非真周K
- `wyckoff_rs.py:139` 指数周线走 `get_weekly`

**问题**：中线 phase（midline_stage）依赖周线威科夫。周线三路径（真实周K / 日线聚合 fallback / proxy_close）口径是否一致未确认。聚合 fallback 的窗口对齐、跨节如何切，直接影响周线中枢/威科夫事件。

**修法（先确认）**：取一只票对比三路径 OHLC；确认聚合窗口定义；确认 proxy_close 用于何处（chip_stage.py:257 用了它）。

**风险**：低（确认性）。不一致则另开修复 handoff。

### S2. HMM regime 准确率验证【已核验上游依赖，待验准确率】

**核验现状**：`hmm_regime.py:53` HMMRegimeDetector 完整实现；`market_env.py:333-336` 调用 detect_regime；`bayesian_fusion.py:18` regime_state 来自 detect_regime。regime 是 fusion 动态权重上游。

**问题**：regime 判定本身的准确率/滞后性**未验**。错判 regime → 三评委权重全错 → fusion 分全错，且难发现（分看着合理）。

**修法（验证性，不改码）**：取 2-3 段已知 regime 行情（如 2024-09 底趋势启动、某段震荡），跑 detect_regime 看是否及时/准确识别；测滞后根数。严重滞后则开 handoff。

**风险**：低（验证性）。

### S3. mock_seam 耦合收口【架构债】

**核验现状**：MEMORY 记「mock_seam 须同时 patch 3 处（market_env + 包级 + report_builder/report_presentation）」。

**问题**：同一配置读取散落 3 处无统一入口。改配置语义要同时想到 3 处，漏一处出 bug。

**修法**：配置读取收口到单一 provider，测试只 patch 1 处。

**风险**：中（架构重构牵涉广），建议独立任务 + 语义回归安全网。

### S4. skill 双安装位同步【运维债】

**核验现状**：MEMORY 记「`~/.workbuddy/skills/` + `~/.hermes/skills/` 双安装位，修复两边都打」。

**问题**：双写是 bug 温床。

**修法**：自动化同步脚本或单源化。

**风险**：低。

---

## 补充项优先级（并入全局执行顺序）

| 序 | 项 | 性质 | 前置 |
|----|-----|------|------|
| S1 | 周线口径确认 | 确认 | 无（10 分钟，省中线怀疑） |
| S2 | HMM regime 验证 | 验证 | 无（fusion 权重根） |
| S3 | mock 耦合收口 | 重构 | 语义回归 |
| S4 | skill 双安装位 | 运维 | 无 |

---

## 落地进度（2026-08-08）

### ✅ #1 动量席 insufficient 重归一化（已落地）
- **安全网（D4）先铺**：`tests/fusion_regression_helpers.py`（9 场景合成三卡，零网络）+ `scripts/dev_capture_fusion.py`（抓/diff 基线）+ `tests/fixtures/fusion_semantic_baseline(_pre).json`。
- **修复**（`fusion_core.merge_decisions`）：检测 `momentum_result["momentum"]["direction"]=="insufficient"` → 分歧列表排除该席、加权段剥离动量权重并按原比例重归一化 chan/vpf 到 1.0、`compute_confidence` 仅用活跃席权重、`weights_used` 回写实际权重。禁止改回 insufficient=50。
- **效果（改前→改后）**：`mom_insufficient_chan_vpf_bull` 0.27/增持/conf0.39 → **0.491/半仓试/conf0.90**；`mom_real_neutral_chan_bull` **指纹不变**（0.27，真中性不重归一化）；分歧场景 `chan_bear_vpf_bull` ws≈0 仍保留（不强行偏多）。
- **回归**：`tests/test_semantic_fusion_regression.py`（基线稳定 + 3 条 #1 不变量）通过；门禁 816 passed/4 skipped。
- **真实票影响**：几乎为零——normal 上市票 bars≫30，momentum 不会 insufficient，生产路径不动；仅 <30 根动量数据的边缘票受影响（正是语义正确方向）。
- **未提交/未 push**。

### ✅ #5 渲染死代码（已清理，见上轮）
### ✅ #4/D5 数据源溯源 _meta（已落地）
- **实现**：`light_data.build_source_meta(snapshot, provider)` 纯函数 + `report_builder.build_report` 挂 `report["_meta"]`（私有键，面板不渲染；`--output json` 可见）。
- **daily_cached 真实命中检测**：`_mark_cached(bars)` 辅助，在 `fetch_qfq_daily` 的 3 处缓存命中返回点（熔断/文件缓存/URL 缓存）浅拷贝打 `cached=True`；网络路径不打 → `build_source_meta` 读 `bars[0].get("cached")`。
- **字段**：`daily_source`/`5m_source`/`weekly_source`/`vol_unit` 直接读 bar 自带 `data_source`/`vol_unit`（honest，无 race）；`provider_backend`=provider 名义选源；`tushare_available`；`fetched_at`。
- **实测（600519 贵州茅台）**：`provider_backend="mootdx"` 但 `daily_source="tencent-http"`（且 `daily_cached=true`）——**名义选源与实际抓取源不一致被诚实暴露**，正面回答 #4「你以为走 A 实际 B」的担忧；`weekly_source="daily_aggregate"`（周线由日线聚合，honest）、`vol_unit="lot"`。
- **回归**：`tests/test_source_meta.py`（5 passed，零网络合同锁：`_mark_cached` 不污染入参 + `build_source_meta` 各分支含 daily_cached 命中/未命中/空 bar）；门禁 816 passed/4 skipped。
- **未提交/未 push**。

### ⏸ #2 北向诚实化（待续）
### ⏸ #3 test_contract（核验后无需处理：37 passed，且不在门禁数组）
