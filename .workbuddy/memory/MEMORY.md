# Trader3.0 项目长期记忆

## 代码位置与提交约定

- **规范源码**：`02-共享模块-shared/trader_shared/` + `01-功能包-packages/trader/scripts/run_analysis.py`
- **⚠️ skill 双安装位**：`~/.workbuddy/skills/trader/`（本会话）+ `~/.hermes/skills/trader/`（pack_all 目标）。修复两边都打。digest 一致 `02c554c66579b09d`。
- **回灌仓库**：纯新增→整文件复制；已分叉→精合保留 repo 更新。禁止整文件覆盖分叉文件。
- 验证：仓库上下文实跑 `final_report.py` + `test_fusion_integration.py` 防回归。
- 提交落 Trader3.0 仓库，**默认不 push**。

## ⚠️ 数据源问题（2026-07-15 发现）

- **tushare HTTP 模式卡死**：SDK 缺失时降级到 HTTP（`fastapic.stockai888.top`），但该 API 不可达→进程 hang 死（SIGKILL/timeout）。`get_provider()` 优先选 tushare（token 存在+HTTP 可用→`available=True`），`TRADER_DATA_PROVIDER=tencent` 环境变量被跳过。
- **临时绕过**：在 Python 中 `from trader_shared.data_provider import UnifiedProvider, set_provider; set_provider(UnifiedProvider(backend="tencent"))` 强制切 tencent。
- **✅ 已修（2026-07-16，commit 93ff9c0）**：`tushare_client.py` 加 `_probe_reachable()`（独立线程 socket.connect + join 硬超时），`TushareClient.__init__` 初始化前先探测 `api_url`，不可达则整条通道标不可用→`get_provider()` 干净回退腾讯。沙箱可达时行为不变，Mac 不可达不再挂死。

## 决策框架（勿破坏）

- 融合层三评委：chan / momentum / vpf + HMM regime 动态权重。短线第三评委是 vpf，非 wyckoff。新增指标不当第 4 评委。
- 展示型指标走 `plugins/` + `display_only=True`，不污染 `weighted_score`。
- 止损：structure_core ATR trailing + stage_positioning 取高（只紧不松）。
- **combo / 箱体已暂停接入报告**（2026-07-14）：渲染接线已摘除，模块+单测保留。等价性基线 42 行无 combo 段，门禁 87 passed。

## 测试

- venv：`/Users/like/.workbuddy/binaries/python/envs/default/bin/python -m pytest`
- `PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts`（shared 在前）
- `test_contract.py` 有 3 项既有失败，非改动引入。
- CI 门禁：`scripts/run-gate-tests.sh` 锁 7 个离线测试（68 passed/~63s），`git config core.hooksPath scripts/git-hooks` 启用。
- **mock_seam 全链路 patch**：`get_env_for_skill` 经 re-export 到包命名空间，须同时打 3 处（源 market_env + 包级 trader_shared + 消费者 report_builder/report_presentation）。

## 模块命名冲突陷阱

- `trader_shared/report_renderer/` 是已追踪包（另一套渲染实验）。**切勿新建同名 `report_renderer.py`**。展示层已命名为 `report_presentation.py`。

## 大文件拆分方法论

- 用 AST 精确提取（`ast.get_source_segment`），不用 sed/行号切片。
- 等价性闸门：分裂前后跑全离线 mock 桩，日期掩码后 diff/md5，证明零回归。
- 测试桩全局改写必须走 `monkeypatch.setattr`。

## 已知技术债（2026-07-14 审计，大部分已修 commit aba3d51）

### 已修复（aba3d51 + 2026-07-16 复核确认）
- 威科夫 phase 持久化只进不退 → 改为基于 `_PHASE_ORDER` 符号判断反向翻转
- 中线威科夫回退日线 → 删回退分支，周线不足直接 insufficient
- 打分函数隐藏写盘 → 传 `use_persisted_phase=False`
- SOS 魔法数强耦合 → 改用 `[-1]`/`len()`/`WYCKOFF_DIVERGENCE_BARS-1`
- 缠论 D4：一类买卖「离开段」约束失效 → 新增 `_zone_last_end_index` 兼容 members/strokes
- 🔴 缠论行矛盾：`report_core.py:362-364` 已有 `_insufficient_struct` 守卫（wave_label_mid 含"笔数不足/无法判断/无明确结构/数据不足"时 `_chan_dir_mid` 强制为空、仅补"中性"），不再强叠方向词。2026-07-16 读码复核确认已修。
- 🟠 盘中合成 bar：`report_builder.py:146-148` 注释明确"合成 bar volume=0 绝不追加进 bars"，`live_bar` 仅用于价格/涨跌幅展示。2026-07-16 读码复核确认已修。

### 待修
- 🟡 动量不足返回 score=50/neutral 占位语义双关：`momentum_core.py:207` 默认 `score=50`、`:257` `direction="neutral"`；`fusion_core.py:646` 动量不足时亦用 `mom_score=50` 兜底。"真中性市"与"数据不足"在 score/direction 上无法区分，会污染融合层权重判定。

## 回测技术选型（2026-07-23 决策）

- **方向：自研轻量框架为主，不引 backtrader。** 仓库已有 `scripts/backtest_t0.py`（复用 T0 三重共振引擎）、`scripts/backtest_chanlun.py`（滑动窗口 `bars[:i]` 前向验证）、`trader_shared/strategy/match.py`（六闸闸口）。模式正确：信号大脑用现有引擎，撮合外壳自写。
- **backtrader 否决理由**：`bt.feeds` 与 `data_provider` 不搭需 adapter；假设指标在策略内用 `lines` 算，与"先 build_report 再决策"范式冲突；对"每根 K 重跑完整分析"事件逻辑表达别扭；维护差、参数优化单进程慢。
- **缺失待补（升级成框架）**：① 撮合层——次日开/收成交+滑点+费(万2.5+印花)+A股 T+1+涨跌停；② 绩效层——equity curve+夏普/卡玛/最大回撤/胜率/盈亏比；③ 参数扫描——`itertools.product`+`concurrent.futures` 多进程；④ 抽象 `BacktestEngine`，信号层统一 `signal_fn(bars_upto_t)->Signal` 包住 `build_report`/`check_resonance`。
- **🔴 前视偏差验证结论（2026-07-23 查码确认）**：`build_report` 内部硬调 `load_market_snapshot(days=LOOKBACK_DAYS)` 且**不接受数据注入**；`load_market_snapshot`/`fetch_qfq_daily` 只有 `days`、无 `end_date`；tushare 路径虽有 `end_date` 但**硬编码 `datetime.now()`**（data_provider.py:603）；腾讯/新浪底层是"最近 N 天"模式不支持历史截止。**结论：`build_report` 直接用于回测=严重前视偏差，不可行。**
- **回测正确接入（绕开 build_report）**：① 一次 `fetch_qfq_daily(sec, days=1200)` 拉全量历史 + 本地 `bars[:t]` 切片绕过 end_date 缺失；② 直接调 `plugin_registry.analyze_all(current_t, bars[:t], ...)`（吃 bars 参数，传 `bars[:t]` 即无前视，report_builder.py:241）+ `fusion_core.merge_decisions(...)` 纯函数拿 `weighted_score`/`action`；③ **必须冻结 `market_env`(HMM regime) 到 t 日**，否则融合层仍前视；④ `current` 用 `bars[t]['close']` 不能用 snapshot.quote.current_price（今天的）。现有 `backtest_chanlun.py`/`backtest_t0.py` 已走此路（只验证信号级前向收益，未碰融合层+regime 冻结）。
- **铁律**：回测与实盘共用同一套 `data_provider` + `build_report`，杜绝两套数据。
- **仅极端场景才上框架**：几百参数×几百票向量化扫描→vectorbt（比 bt 快几个量级、API 现代，但偏向量化）；tick 级真撮合/订单簿→nautilus_trader（过度）。
- **✅ 已实现 `BacktestEngine` v2（2026-07-23）**：`02-共享模块-shared/scripts/backtest_engine.py`。三项升级全部落地并验证：① **cards 对齐实盘**（默认 `fusion_from_cards="cards"`，`signal_at` 内用 `build_chan_card`/`build_momentum_card`/`build_vpf_card` 三卡喂 `merge_decisions`，与 `build_report` 同源；`--no-cards` 退回 classic 提速）；② **ATR trailing 止损**（Wilder ATR×倍数，只上移、地板=初始硬止损，替代固定 8%）+ **涨停买不进/跌停卖不出**（按代码自动 10%/20%）；③ **参数扫描**（`--scan`：信号只算一遍，`ProcessPoolExecutor` 多进程并行跑撮合层复用同一份 `signals`/`bars`，`atr_mult×stop_pct×step` 网格）。另加**非破坏性数据健全性快检**（收盘价相对中位数 >5× 告警，抓 `TencentFetcher` 偶发 100× 缩放坏点）。验证：茅台 300 天 cards +3.98%/夏普 0.56/盈亏比 2.12；平安银行 -2.07%（弱势亏损合理）。扫描结论：ATR×2.5+step1 最优，step=2 因漏信号明显转差。
- **✅ 已实现 `BacktestEngine` v2.1（2026-07-23）— 实盘风控接入（与实盘彻底一致）**：`make_signal_fn` 内 `_risk_inputs(date_t, cur)` 按 t 切片历史风控数据喂 `merge_decisions`，**全部 point-in-time 无前视**：① `fund_flow_data=calc_fund_flow_features(slice≤date_t, cur)` → 连续主力净流出 veto 触发（茅台 27 根资金流/7 次 veto；平安银行 267 根/44 次）；② `extend_sentiment={"unlocks":[t≤u.date≤t+90]}` → 解禁风险空仓 veto（用 `eastmoney_datacenter(RPT_LIFT_STAGE)` 原始拉全量事件，循环内切 90 天窗口，与实盘「未来 90 天」一致）；③ `extend_fundamental={"shareholder":...}` 仅当 `date_t≥latest_notice_date` 才生效 → 股东户数筹码集中置信加成。**A/B 验证（决定性）**：平安银行风控开 vs 关 → 总收益 -5.80% vs -2.07%、交易 12 vs 13 笔（veto 挡掉 1 次建仓信号），证明风控真正改变撮合、与实盘一致；茅台 veto 日恰为非建仓日故数字不变（合法）。`--no-riskdata` 关闭做对照。报告打印「风控触发」次数对账。
- **🔴 数据层非确定坑（回测必看）**：`TencentFetcher().fetch_qfq_daily` 跨进程偶发返回不一致数据——某根 bar 的 open/close 被缩放 ~100×（A股单日 ≤20%，>5× 几乎必为错误）。**进程内 `run_backtest` 完全确定**（同进程两次调用结果逐位一致），故扫描（主进程抓数一次、传 worker）不受影响；但**不同独立进程各自抓数**可能拿到不同数据集 → 单次报告若撞上坏点会静默污染。引擎已加 >5× 中位数告警兜底；根治需修 `TencentFetcher` 缓存/去重或回测前落盘缓存复用。
- **🔴 实现踩坑（回测拉数必看）**：① `get_provider()` 默认 backend=tushare，Mac 上 `fetch_qfq_daily` 主路径落空/吐陈旧值 → 必须 `set_provider(UnifiedProvider(backend="tencent"))` 强制切腾讯。② 即使切 tencent，`provider.fetch_qfq_daily` 仍被 `get_day_scoped_bars` 的**「当日快照缓存」**污染（曾吐陈旧 2 根）→ 回测须绕过，直接 `from trader_shared.fetchers import TencentFetcher; TencentFetcher().fetch_qfq_daily(code, days)` 拉全量（底层同源，只是不要缓存语义）。③ 冻结 regime 用 `TencentFetcher().fetch_qfq_daily(INDEX_CODE, days)`（INDEX_CODE=000852.SH）。④ 前视防御：`os.environ["TRADER_CHAN_NESTING"]="0"`（防 analyze_all 现场拉未来 30m/5m）+ `quote["_bars_5m"]=[]`（防 VWAP 插件拉未来 5m）+ fund_flow/extend_* 全传 None。
- **🔴 风控接入已知边界（v2.1 out-of-scope，需各自历史源）**：① `extend_sector`/`extend_concept`/`extend_margin`/`extend_northbound` 在 `merge_decisions` 仅软修正（行业强弱/融资/北向），非硬 veto，且需板块指数/融资/北向各自历史序列，暂未接入；② 资金流 API 对部分票仅返回最近 ~27 交易日（茅台），故 veto 只在回测末段最近窗口生效——**与实盘一致**（实盘 `build_report` 同样只取最近资金流）；对平安银行等返回长历史（267 根）则全程生效；③ 股东户数只有「最新披露日」单点，按 `date_t≥notice_date` point-in-time 生效（仅近一季）。核心硬 veto（资金流出 + 解禁）已接、已验证一致。
- **✅ 已实现 `BacktestEngine` v2.2（2026-07-23）— 落盘缓存 + 北向软修正接入**：
  - **① 落盘缓存（根治跨进程坏点）**：`load_data` 增加 `use_cache=True/force_refresh=False`，写到 `~/.trader/backtest_cache/{code}_{days}_{kind}.json`（日线/周线/指数三份）。`_sanity_check` 在**写前和读后**都跑「收盘价 >5× 中位数」断言 → 坏点绝不落盘、也绝不读入。二次运行显示「日线命中 指数命中」，所有 run（含 scan/A-B）读同一份确定数据，彻底消除 `TencentFetcher` 跨进程偶发 100× 缩放污染。CLI：`--no-cache` 关闭、`--refresh-cache` 强制重抓。
  - **② 北向软修正 point-in-time 接入**：`_fetch_extend_history` 用 `ak.stock_hsgt_hist_em(symbol="北向资金")` 拉全量（2714 行）→ 映射 `日期`→date、`当日成交净买额`(亿元)×1e4→万元 `net_wan`，按 date 排序落盘缓存（key `NB/0/nbh`）。`_northbound_inputs(date_t)` 用 bisect 切片 `<=t`，返回 `{status, north_net_flow_wan, north_flow_5d_wan}`（≤t 求和）；喂 `merge_decisions(extend_northbound=...)`。`--no-extend` 关闭。
  - **🔴 关键数据源发现（诚实披露，非 bug）**：`ak.stock_hsgt_hist_em` 的 `当日成交净买额` 列对 **2020+ 的所有行全是 NaN**（仅 2014 早期零星有值）。回测窗口 2025-09+ 内北向恒为 0 → 落入 `merge_decisions` 的 dead-zone（`weighted_score>0.1` 才微调，且需 `north_net_flow_wan>2000`，0 不满足）→ **real-run 恒为 no-op**。已用合成北向数据注入验证接线 100% 正确（33 天 confidence 改变，如 0.094→0.099 = +5%），错在数据源非接线。决定不伪造数据。
  - **NaN 防御**：`net_yi = float(_raw) if _raw is not None else 0.0; if net_yi != net_yi: net_yi = 0.0`（nan 在 Python 里 `nan or 0 == nan`，必须显式 coerce，否则下游算出 nan 静默跳过）。
  - **sector/concept/margin 仍 out-of-scope**：Mac 上 akshare 实时 `get_sector_data`/`get_concept_data` 对个股→板块分类返回「无数据」；margin 无分票历史序列。需可联网沙箱或换 tushare 源才能补。
  - **最终回归验证（无退化）**：茅台 600519（300d, cards）+3.98%/夏普 0.56/5 笔；平安银行 000001 -5.80%/夏普 -0.88/12 笔/44 次 fund_flow veto。与 v2.1 数值一致（缓存+北向不改变已验证结果）。
  - 注：`_print_report` 改用 `%`-format 规避本 Python 版本 f-string 字面 `(` 解析歧义（曾反复 SyntaxError）。
