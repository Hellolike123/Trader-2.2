# Trader3.0 项目长期记忆

## 代码位置与提交约定

- **规范源码**：`02-共享模块-shared/trader_shared/` + `01-功能包-packages/trader/scripts/run_analysis.py`；t0 规范包在 `01-功能包-packages/t0/scripts/`。
- **⚠️ skill 双安装位**：`~/.workbuddy/skills/{trader,t0}/`（本会话）+ `~/.hermes/skills/{trader,t0}/`（pack_all 目标）。修复两边都打。
- **回灌仓库**：纯新增→整文件复制；已分叉→精合保留 repo 更新。禁止整文件覆盖分叉文件。
- 验证：仓库上下文实跑 `final_report.py` + `test_fusion_integration.py` 防回归。提交落仓库，**默认不 push**。

## t0 统一为 Al Brooks 版（2026-07-23 用户拍板）

- 三重共振第一席位 = **Al Brooks 价格行为**（`ab_price_action.analyze_ab`，`build_price_point_model` 内部自算），缠论席位删除；含 `today_bars` VWAP 只用今日、各席位 exit_price、「数据异常」守卫（买区≥卖区→跨日污染）。
- 三处已对齐一致：hermes = workbuddy = 仓库 `01-功能包-packages/t0/scripts/`（回灌未 commit）。今后 t0 修复以 hermes 为准同步。

## 数据源

- **tushare HTTP 不可达卡死已修**（93ff9c0）：`_probe_reachable()` 硬超时探测，不可达干净回退腾讯。
- 回测拉数铁则：绕过 `get_provider` 缓存语义，直接 `TencentFetcher().fetch_qfq_daily(code, days)`；必要时 `set_provider(UnifiedProvider(backend="tencent"))`。
- **🔴 TencentFetcher 跨进程偶发 100× 缩放坏点**：进程内确定，跨进程不保证 → 回测统一走落盘缓存（写前读后都跑 >5× 中位数断言）。
- **🔴 日线 volume 单位实测（2026-08-04，推翻 FDE 轮假设）**：**腾讯日线 volume=手**（amount 交叉验证 amount≈vol×100×close + 腾讯实时 qfqday 与 mootdx 缓存同量级：601398/600519/000001），与 sina/mootdx/pytdx3/tushare **全源一致=手**。FDE 轮「腾讯日线=股」假设错误 → 其周线出口 ×100（=股）与日线（=手）存在跨周期绝对值 100× 差异（A-P4 冻结，待裁决，见 `workflows/phase-scan-audit/README.md` §2）。日线新缓存 bar 打 `vol_unit="lot"`（`_stamp_vol_unit`，light_data.py）；fallback **不 ×100**（实测修正 A-M1）。

## 决策框架（勿破坏）

- 融合层三评委：chan / momentum / vpf + HMM regime 动态权重（短线第三席是 vpf 非 wyckoff）。新增指标不当第 4 评委；展示型走 `plugins/` + `display_only=True`。
- 止损：structure_core ATR trailing + stage_positioning 取高（只紧不松）。
- combo/箱体已暂停接入报告（渲染摘除，模块+单测保留）。

## 测试

- venv：`/Users/like/.workbuddy/binaries/python/envs/default/bin/python -m pytest`；`PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts`（shared 在前）。
- 门禁只跑离线子集 `scripts/run-gate-tests.sh`；`test_contract.py` 有 3 项既有失败。
- mock_seam：`get_env_for_skill` 须同时 patch 3 处（market_env + 包级 + report_builder/report_presentation）。
- 陷阱：`trader_shared/report_renderer/` 是已追踪包，勿新建同名 `.py`；展示层叫 `report_presentation.py`。
- 大文件拆分：AST 提取 + 等价性闸门（mock 桩 diff/md5）；桩改写走 `monkeypatch.setattr`。

## 待修技术债

- 🟡 动量不足 score=50/neutral 占位语义双关（momentum_core.py:207/257，fusion_core.py:646）——"真中性"与"数据不足"无法区分。

## 回测体系（2026-07-23 全部落地）

### 选型结论
- 自研轻量框架，不引 backtrader（feeds 不搭/lines 范式冲突/维护差）。极端场景才上 vectorbt（大规模参数扫描）或 nautilus（tick 撮合）。
- **🔴 `build_report` 直接回测 = 前视偏差，不可行**（内部硬调 load_market_snapshot=最近 N 天，无 end_date）。正确接法：本地全量 bars[:t] 切片 + `analyze_all(bars 参数)` + `merge_decisions` 纯函数 + 冻结 regime 到 t 日 + `TRADER_CHAN_NESTING=0` + `quote["_bars_5m"]=[]`。

### 日线引擎 `02-共享模块-shared/scripts/backtest_engine.py`（v2.2，commit d83e16c）
- cards 对齐实盘（三卡喂 merge_decisions）；ATR trailing 止损+涨跌停撮合约束；`--scan` 多进程参数扫描；落盘缓存 `~/.trader/backtest_cache/`（根治跨进程坏点）。
- 实盘风控 point-in-time：fund_flow veto + 解禁 90 天窗口 veto + 股东户数按披露日生效；A/B 验证风控真实改变撮合（平安银行 -5.80% vs -2.07%）。北向接线正确但 akshare `当日成交净买额` 2020+ 全 NaN → real-run no-op（数据源问题，不伪造）。sector/concept/margin 未接（无历史源）。
- 基准：茅台 300d cards +3.98%/夏普 0.56；平安银行 -5.80%/12 笔/44 veto。扫描：ATR×2.5+step1 最优。
- NaN 防御：`nan or 0 == nan`，必须显式 `x != x` coerce。
- 验证案例：南网科技 688248 日线 +84.10% vs 买入持有 +27.84%（alpha +56pp，科创板 ±20% 撮合正确）。

### 日内 T0 引擎 `02-共享模块-shared/scripts/intraday_backtest_engine.py`（2026-07-23，未 commit）
- 复用 t0 真实信号脑 `build_price_point_model`（sys.path 注入 workbuddy t0 skill），T+0 当日限价撮合+收盘强平，`run_one_day` 子进程/天隔离防 OOM（单日 ~85MB）。
- 数据：Sina `getKLineData datalen=2400`（仅最近 ~50 交易日 5m，窗口硬上限）；落盘缓存 `~/.trader/intraday_cache/`。
- **保真性修复**：① Sina 5m 全缺 13:00 棒→`_fix_lunch_gap` 补棒（否则全下午 degraded 零成交）；② 必须注入 `structure_result`（D 前日线 build_structure_context，t0_run "T0-1 fix" 设计，否则 net_space<0 恒被阻断）。
- Al Brooks 版共振不吃 chan → 裁掉引擎缠论计算，单日 9.6s→1.3s，全量 50 天 52s。
- **结果（688248，50 天）：0 笔成交**。卡点=动量席 RSI 12 棒背离（0-3/天且从不与 ab/wyckoff 同帧）。三重硬共振单票日内极稀疏——需多票扫描或讨论放宽动量席（产品问题非 bug）。
