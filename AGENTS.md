# Trader 2.0 — 架构文档

> 最后更新：2026-05-06
> 代码版本：trader v0.6.0 / t0-trader v0.7.0 / trader-pool v0.1.0 / trader-portfolio v1.0 / trader-shared v0.6.0 / review-trader v0.1.0
> 变更：缠论3类买卖点 + 威科夫Spring/Upthrust + Phase1解耦(3策略run_all) + MACD集成 + T0增强(ATR止损/布林/RSI背离/ADX方向过滤)

---

## 一、业务全景

### 1.1 系统定位

A 股交易决策辅助系统。通过免费行情 API（腾讯 + 新浪）获取日线/分钟线数据，用缠论/威科夫/筹码/ATR/利弗莫尔等分析方法生成交易信号和操作计划，输出标准化 Markdown 面板供交易员手机端阅读，同时通过  协议输出机器可读信号供下游 Agent 消费。

### 1.2 六大 Skill 定位


| Skill                 | 一句话定位                                    | 使用场景                    |
| --------------------- | ---------------------------------------- | ----------------------- |
| `trader`              | 单票手机端分析报告：状态、行动方向、观察区、仓位管理、理论依据、风险和一句话建议 | 新票验票、日常跟踪票分析            |
| `trader` (alert-text) | 价格监控：关键位触发时输出一行简短提醒，适合定时任务               | Hermes 定时盯盘任务           |
| `t0-trader`           | 盘中 T0 精细执行卡 + 持续盯盘告警                     | 盘中高抛低吸执行、条件触发提醒         |
| `trader-pool`         | 选股池全生命周期管理：入池建议、排序、作战表、执行复盘              | 候选池日常维护、多股横向对比          |
| `trader-portfolio`    | 2-3 只股票轮动仓位计划                            | 持有组合的仓位分配、加仓降仓规则、金字塔级计算 |
| `review-trader`       | 盘后/午间五层理论复盘 + 多股对比                       | 单日或多股深度复盘、信号历史回溯        |
| `trader-compare`      | 已废弃，能力迁入 `trader-pool compare`           | 暂保留兼容入口                 |


## Agent 接入指南

本系统是面向 A 股交易员的决策辅助系统，所有技能包均通过 Agent 平台加载并执行。不依赖第三方数据接口，不自动下单。

### 支持的 Agent 平台


| 平台                | 加载方式                                   | Skill 入口                    | 说明                        |
| ----------------- | -------------------------------------- | --------------------------- | ------------------------- |
| Hermes            | 自动发现 `~/.agents/skills/` + `HERMES.md` | 自动挂载                        | 通过 `HERMES.md` 中定义的命令路由   |
| OpenClaw          | 手动挂载或 symlink 到 `~/.agents/skills/`    | `SKILL.md` YAML frontmatter | 通过 CLI 参数触发               |
| WorkBuddy / Codex | 手动挂载 `SKILL.md`                        | 命令行直接调用                     | 直接执行 `scripts/final_*.py` |
| ChatGPT (GPTs)    | 手动集成                                   | API 调用或终端命令                 | 作为自定义 GPT 的 tools         |


### 使用方式

1. **自然语言触发**
  对 Agent 说"分析一下南网科技" → 自动识别为 `trader` skill → 执行 `final_report.py --target 南网科技` → 返回 stdout 原文。
2. **脚本直接调用**
  ```bash
   python3 scripts/final_report.py --target 南网科技
   python3 scripts/final_report.py --target 南网科技 --output alert-text
   python3 scripts/final_t0.py --target 南网科技 --monitor --once
   python3 scripts/final_pool.py add --target 中国铝业
   python3 scripts/final_portfolio.py --targets 南网科技 中国铝业
   python3 scripts/final_review.py --target 南网科技
  ```
3. **自动化流水线**
  通过 cron 或调度器调用 `scripts/final_report.py --target 南网科技 --output alert-text`（定时价格监控）或 `scripts/final_t0.py --monitor --once`（单次检查）或 `scripts/final_portfolio.py --targets A B`（盘后轮动计划），无需用户在场。

### 信号消费示例

Agent 消费 `signals.jsonl` 的示例方式：

```bash
# Review 自动回溯最近信号
python3 scripts/final_review.py --target 南网科技 --session close
# 输出中自动包含"本月信号追踪"和"历史信号回溯"板块
```

### 各平台命令映射


| 需求        | Hermes / OpenClaw    | 直接执行                                                |
| --------- | -------------------- | --------------------------------------------------- |
| 分析一只票     | `分析南网科技`             | `final_report.py --target 南网科技`                     |
| 价格监控      | `盯盘南网科技`             | `final_report.py --target 南网科技 --output alert-text` |
| T0 盯盘单次检查 | `N/A`（需 `--monitor`） | `final_t0.py --target 南网科技 --monitor --once`        |
| 入池        | `加入选股池南网科技`          | `final_pool.py add --target 南网科技`                   |
| 池内排序      | `池内排序`               | `final_pool.py rank`                                |
| 仓位轮动      | `仓位分配南网科技+中国铝业`      | `final_portfolio.py --targets 南网科技 中国铝业`            |
| 盘后复盘      | `复盘南网科技`             | `final_review.py --target 南网科技`                     |


---

### 1.3 推荐工作流

```
新票验票 ──→ trader
确认跟踪 ──→ trader-pool add
池内优先级 ──→ trader-pool rank
明日作战表 ──→ trader-pool plan
盘中执行 ──→ t0-trader (monitor)
盘后复盘 ──→ review-trader / trader-pool review
仓位轮动 ──→ trader-portfolio
信号回溯 ──→ review-trader (读 signals.jsonl)
```

### 1.4 分析方法论映射


| 方法论                            | 用哪些 Skill                                     | 对应代码函数                                                                            |
| ------------------------------ | --------------------------------------------- | --------------------------------------------------------------------------------- |
| 缠论                             | trader、review-trader                          | `chan_core.py:chanlun_analysis()` → 分型/笔/中枢/买卖点                               |
| 威科夫量价                          | trader、trader-pool、review-trader              | `wyckoff_core.py:wyckoff_analysis()` → Spring/Upthrust/量价背离                    |
| 筹码峰/成本结构                       | trader、review-trader                          | `review_model.py:build_levels()` → `dense_price_zone()` + `chip_zone`             |
| ATR 动能                         | trader、t0-trader、trader-pool、trader-portfolio | `candidate_core.py:average_amplitude_pct()` + `build_candidate_levels()`          |
| 利弗莫尔金字塔 + ATR 仓位               | trader-portfolio                              | `candidate_core.py:livermore_scale()` + `base_weight()`                           |
| 价格点位引擎 (Price Point Engine)    | t0-trader                                     | `price_point_engine.py:build_price_point_model()` → buy/sell 触发区间                 |
| RSI / MACD / ICT-Lite / 布林带/ADX | t0-trader                                     | `indicators.py` + `ict_execution.py` 的 5m 分析引擎                                    |


---

## 二、数据架构

### 2.1 数据源


| 来源     | 接口                                                 | 返回数据                                  | 用途               |
| ------ | -------------------------------------------------- | ------------------------------------- | ---------------- |
| 腾讯行情   | `qt.gtimg.cn/q=`                                   | 实时快照（现价/昨收/今开/涨跌/成交量/换手率）             | 所有 skill 的现价/涨跌幅 |
| 腾讯日线   | `web.ifzq.gtimg.cn/appstock/app/fqkline/get`       | 前复权日线，附加 `atr14/atr7/atr_ratio/tr` 字段 | 支撑阻力计算、状态判定      |
| 新浪 K 线 | `money.finance.sina.com.cn/quotes_service/api/...` | 5m / 15m / 30m 分钟线                    | t0-trader 盘中分析   |


### 2.2 light_data.py — 唯一数据入口

`02-共享模块-shared/01-行情数据-market-data/light_data.py` (403 行) 是所有 skill 的唯一数据拉取模块。**全局唯一文件，无重复。**

**核心函数：**


| 函数                                           | 作用                                                 |
| -------------------------------------------- | -------------------------------------------------- |
| `fetch_quote()`                              | 腾讯实时行情快照 → `QuoteData`                             |
| `fetch_qfq_daily()`                          | 腾讯前复权日线，追加 ATR 字段（`_compute_atr_fields()`）         |
| `fetch_5m()` / `fetch_15m()` / `fetch_30m()` | 新浪分钟线                                              |
| `fetch_kline()`                              | 通用多周期 K 线拉取 + 归一化                                  |
| `load_market_snapshot()`                     | 聚合 quote + daily + 5m，返回 `MarketSnapshot`（含数据质量分级） |
| `resolve_security()`                         | 股票名/代码 → `Security(dataclass)`, 推断 SH/SZ 市场        |
| `pct_change()` / `to_float()`                | 安全数值工具                                             |
| `is_trading_time()`                          | 判断当前是否为交易日 9:30-15:00                              |


**数据模型层** `models.py` 定义统一 TypedDict：


| TypedDict         | 用途                                               |
| ----------------- | ------------------------------------------------ |
| `BarData`         | 统一 K 线数据行（跨周期）                                   |
| `QuoteData`       | 实时行情快照                                           |
| `MAValues`        | 多周期均线集合                                          |
| `CandidateLevels` | 候选交易区间（支撑/阻力/止损/止盈/确认价）                          |
| `CandidateSignal` | 候选信号核心结构（levels + structure + momentum + volume） |
| `TheoryVerdict`   | 复盘五层理论打分                                         |
| `SignalRecord`    | Signal Contract v1 记录                            |
| `ChanlunSignal`   | 缠论分析结果（trend_label/buy_points/divergence）       |
| `WyckoffSignal`   | 威科夫信号（spring/upthrust/量价背离）                      |


**HTTP 客户端** `HttpClient`：GET with User-Agent、gzip、SSL-unverified。 `retry()` 指数退避 3 次。
**缓存**：bars 不含当日日期时缓存 1 小时，实时数据不缓存。
**NAME_MAP**：9 个常用股票名到代码的映射（南网科技→688248、中国铝业→601600 等）。

### 2.3 状态机完整映射

`candidate_core.STATUS_SCORE` — 状态判定结果集：


| 状态       | score 值 | 触发条件（`status_for()`） | 典型场景       |
| -------- | ------- | -------------------- | ---------- |
| **暂不碰**  | 20      | 现价跌破硬止损              | 破位下行，防守优先  |
| **低吸观察** | 80      | 现价在低吸区附近，未破止损        | 缩量回调用至支撑区  |
| **冲高减仓** | 55      | 现价靠近确认价/压力区，上涨乏力     | 反弹触压，减仓信号  |
| **等转强**  | 70      | 现价在支撑之上但距确认价有空间      | 止跌后等待确认突破  |
| **防守观察** | 60      | 现价靠近支撑但未确认止跌         | 支撑附近观望     |
| **空间不足** | 45      | 距确认价空间过小，盈亏比不够       | 高位震荡，无明确方向 |
| **数据失败** | 0       | K 线数据不足 60 根         | 新股/停牌复牌    |


> 优先级: `status_for()` 判定顺序: 暂不碰 > 低吸观察 > 冲高减仓/等转强 > 空间不足 > 防守观察

### 2.4 持久化文件


| 文件                            | 用途                     | 写入者                                                    | 读取者                                  |
| ----------------------------- | ---------------------- | ------------------------------------------------------ | ------------------------------------ |
| `~/.trader/signals.jsonl`     | Signal Contract v1 事件流 | t0-trader (monitor mode)、trader (--output signal-json) | review-trader、Pool Compare、Portfolio |
| `~/.trader/pool.json`         | 选股池状态                  | trader-pool                                            | trader-pool                          |
| `~/.trader/pending.json`      | 待确认池状态                 | trader-pool                                            | trader-pool                          |
| `~/.trader/last_plan.json`    | 上次作战计划                 | trader-pool                                            | trader-pool                          |
| `~/.t0-trader/state.json`     | T0 盯盘缓存（含冷却计时）         | t0-trader (monitor mode)                               | t0-trader                            |
| `~/.review-trader/state.json` | 复盘缓存                   | review-trader                                          | review-trader                        |


注意： `candidate_core.py` 内也有一份历史信号缓存池（ `_history_buffer` ），但仅用于 `t0-trader` 自身的 cooldown 管理，与 `~/.trader/signals.jsonl` 的持久化流是独立的两套。

---

## 三、Skill 职责矩阵



**入口**: `01-功能包-packages/01-单票分析-trader/scripts/final_report.py`
**分析模型**: `run_analysis.py::build_report()` → `final_report.py::render_markdown()` → `build_signal()`
**策略链**: `strategies = [build_structure_context, chanlun_strategy, wyckoff_strategy]` 经 `run_all()` 合并
**输入数据**: 腾讯日线（前复权 + ATR）+ 实时快照
**依赖共享模块**: `candidate_core`、`light_data`、`signal_contract`、`chan_core`、`wyckoff_core`

**Output Contract（固定顺序）**:

```
分析报告 — {name}（{code}）
现价 + MA5/MA10/MA20/MA30 + ATR 行
🌍 中证1000 大盘环境（趋势/涨跌/建议）
📍 决策（状态 + 空仓/有底仓/加仓指引）
T0 参考（低吸/高抛/止损价位，止跌确认）
❗ 关键价位（止损 | 减仓 | 止跌 | 支撑）
🧭 简要分析（结构/量价/筹码/动能）
```

**禁止项**: 无 `#` / `---` / `*`* / 表格 / 列表符号。禁止词: 必涨、做T、主力入场第一枪、ATR14=、极端波动 等 30+ 项。
**JSON 输出**: `--output signal-json` → `trader_signal_v1`
**Alert 输出**: `--output alert-text` → 价格触及关键位时输出一行简短提醒，未触发时静默不输出。



**入口**: `01-功能包-packages/02-盘中T0-t0-trader/scripts/final_t0.py`
**子模块**: `t0_run.py`（计划生成）、 `price_point_engine.py`（价格点位）、 `monitor.py`（盯盘循环）、`indicators.py`（技术指标）、 `ict_execution.py`（ICT执行辅助）
**输入数据**: 腾讯实时快照 + 新浪 5m/15m/30m K线
**增强指标**: ATR动态止损(P0-1) · RSI底/顶背离(P0-2) · 布林带20,2σ(P0-3) · ADX方向过滤(P1-4)
**依赖共享模块**: `light_data`、`signal_contract`、`signal_store`

**Output Contract（无表格卡）**:

```
T0 — {name}  现价 {pct}
买入 {observation} → {execution} → {acceptable}
卖出 {观察} → {触发} → {不可接受}
仓位  底仓的 {10%-20%}（别超）
      🌍 大盘level | note
atr_text
止损  price 跌破不接
```

**Monitor Mode**: 3 分钟轮询 → `detect_state_change()` → 15 分钟 cooldown → 输出告警文本 + 追加 `signals.jsonl`。单次 `--once` 适合 cron 调度。



**入口**: `01-功能包-packages/03-选股池-trader-pool/scripts/final_pool.py`
**子模块**: `run_analysis.py`（复用 trader 分析管线）
**输入数据**: 腾讯日线 + 实时快照
**依赖共享模块**: `candidate_core`

**命令集**:


| 命令                      | 作用                          |
| ----------------------- | --------------------------- |
| `analyze`               | 单票分析输出                      |
| `add`                   | 确认入池（上限 POOL_LIMIT=10 票）    |
| `add-pending`           | 加入待确认池                      |
| `confirm-to-pool`       | 从 Pending → 主池              |
| `show` / `show-pending` | 查看池                         |
| `rank` / `compare`      | 多股横排（附 signal tags）         |
| `plan`                  | 生成明日作战表（存 `last_plan.json`） |
| `review`                | 复盘昨日计划执行                    |
| `remove`                | 移出池                         |
| `archive-exited`        | 归档 7+ 天未动票                  |


**入池打分（ `_score_report()` ）**:

- 缠论子分（max 45）: 24 基础 + 阶段/场景/价格距离加分
- 威科夫子分（max 30）: 15 基础 + 量能/动能加分
- 筹码子分（max 25）: 15 基础 + 止损/支撑/止盈加分
- 综合 ≥ 70 + 动能通过 → 执行; ≥ 55 → 观察；触及防守线 → 拒绝/淘汰



**入口**: `01-功能包-packages/04-仓位轮动-trader-portfolio/scripts/final_portfolio.py`
**子模块**: `candidate_model.py`（单票分析 + 排序）、`portfolio_run.py`（仓位构建 + 渲染）
**输入数据**: 2-3 只股票日线 + ATR（或 JSON 快照含持仓/候选/账户）
**依赖共享模块**: `candidate_core`、`light_data`、`signal_contract`

**Output Contract**:

```
轮动仓位 — {名1} + {名2} + ...
📌 组合（主仓/副仓/观察/现金 分配表）
🎯 操作（加仓/降仓/止损规则）
📊 仓位与信号（ATR + 金字塔级/首仓上限）
🎯 关键价位（买入区间/防守/止损/减仓）
```

**Signal 消费**: 每张仓位卡显示最新 signal tags（🟢T0低吸 / 🔴T0高抛 / 🔽减仓）。

**Snapshots 输入**: `{targets: [...], holdings: [...], candidates: [...], account: {max_move_pct: ..., total_position_pct: ..., cash_pct: ...}}`



**入口**: `01-功能包-packages/05-盘后复盘-review-trader/scripts/final_review.py`
**子模块**: `review_model.py`（复盘建模）、`review_render.py`（渲染）、`review_single.py`（单票）、`review_compare.py`（多股）、`review_store.py`（缓存）
**输入数据**: 腾讯实时 + 日线 + 新浪 5m
**依赖共享模块**: `candidate_core`、`light_data`

**五层理论分析（ `theory_verdicts()` ）**:

```
缠论结构    / 威科夫量价    / 筹码峰    / 资金行为    / 动能确认
0-100 分    0-100 分    0-100 分    0-100 分    0-100 分
```

**Output Contract**:

```
📌 {name}｜{date}盘后复盘
结论 | 五层模型总览
📊 今日状态（O/H/L/V）
📈 走势结构（5m 分段）
🔎 信号判断（偏多✓ / 警惕!）
🎯 明日关键价位
🧭 明日应对（强势/震荡/回落）
👉 一句话
📊 本月信号追踪（低吸观察发出N次/对了X次）
📋 历史信号回溯（从 signals.jsonl）
```

**Signal Backtrack**: `enrich_with_signal_backtrack()` 读取 `~/.trader/signals.jsonl`，按 `trade_date` 匹配 review 日期，无精确匹配则回退最近 N 条。

---

## 四、依赖拓扑图

```
                    +- 02-共享模块-shared/
                    |  01-行情数据-market-data/
                    |    light_data.py (数据拉取 + HTTP)
                    |    models.py (TypedDict 统一模型)
                    |-- 02-候选逻辑-candidate/
                    |    candidate_core.py (核心分析)
                    |    t0_candidate_core.py (T0专用)
                    |    chan_core.py (缠论: 分型/笔/中枢/买卖点)
                    |    wyckoff_core.py (威科夫: Spring/Upthrust)
                    |-- 03-输出校验-contracts/
                    |    signal_contract.py (v1 校验)
                    |    signal_store.py (JSONL 持久化)
                    |-- scripts/
                    |    calibrator.py (回测校准)
                    |    market_env.py (大盘环境)
                    |    pipeline.py (状态管道)
                    |    signal_tracker.py (信号追踪)
                    |    pack_all.py (统一打包 → trader-all-skill.zip)
                    |-- contract_utils.py (文本校验工具)
                    |-- trader_shared/         ← P6: 标准 Python 包
                    |    __init__.py (lazy-load 路由)
                    |    config.py (全系统常量集中管理)
                    |    schema/v1.py (P7: 输出契约规则库)
                    |    data_provider.py (P8: 可插拔数据接口)
                    |    strategy_protocol.py (策略函数协议)
                    |    rule_engine.py (决策规则引擎)
                    |    status_rules.yml (status_for 决策规则)
                    |    score_rules.yml (score_for 规则)
                    |    livermore_rules.yml (livermore 规则)
                    |    chip_distribution.py (筹码分布)
                    +--------------------------+
                              ^ sys.path.insert(3 parents up)
                    +- 各 skill scripts/*.py
                    |  final_report.py / final_t0.py
                    |  final_pool.py / final_portfolio.py
                    |  final_review.py
                    |  validate_output.py → trader_shared.schema.v1
                    +--------------------------+
```

所有 skill 通过 `ROOT = Path(__file__).resolve().parents[3]` 向上定位共享模块根目录，再用 `sys.path.insert()` 注入所需子路径。从 P6 起，skill 统一通过 `from trader_shared import xxx` 导入共享功能，不再硬编码 scripts/ 子目录路径。

---

## 五、分析模型层详细

### 5.1 candidate_core.py（共享核心，拆分为 structure_core + decision_core）

**常量配置** — 全部集中到 `trader_shared/config.py`，支持 per-skill 覆盖：


| 常量                      | 值               | 用途               |
| ----------------------- | --------------- | ---------------- |
| `MA_PERIODS`            | (5, 10, 20, 30) | 均线周期（可覆盖）       |
| `MA_WEIGHTS`            | {ma5:0.92, ...} | 均线权重打分（可覆盖）     |
| `MIN_ZONE_WIDTH_PCT`    | 0.005           | 支撑/阻力区间最小宽度（可覆盖） |
| `MAX_ZONE_WIDTH_PCT`    | 0.012           | 最大宽度（可覆盖）        |
| `MIN_STOP_BUFFER_PCT`   | 0.008           | 止损缓冲下限（可覆盖）      |
| `MIN_CONFIRM_SPACE_PCT` | 0.008           | 确认价最小距离（可覆盖）     |
| `RECENT_WINDOW`         | 5               | 近期窗口（可覆盖）        |
| `STRUCTURE_WINDOW`      | 20              | 结构窗口（可覆盖）        |
| `TAKE_PROFIT_BUFFER`    | 1.06            | 止盈缓冲系数（可覆盖）      |

> 所有常量为 `try/except ImportError` 模式，per-skill `config.py` 可选择性覆盖，未覆盖则使用 `trader_shared/config.py` 默认值。


**核心函数**:


| 函数                         | 参数                               | 返回值                  | 说明                                       |
| -------------------------- | -------------------------------- | -------------------- | ---------------------------------------- |
| `build_structure_context()` | current, bars, change_pct, quote | CandidateLevels      | 主函数：支撑/阻力/止损/止盈/低吸区/状态                   |
| `status_for()`             | 价格/支撑/确认价/止损等 + MA + 压力空间        | str 状态               | 优先走 rule_engine + status_rules.yml，回退硬编码逻辑 |
| `score_for()`              | status + 现价+支撑+空间+MA+ATR dict    | float 0-100          | 综合打分                                     |
| `livermore_scale()`        | status, score                    | int 0~5              | 利弗莫尔金字塔加仓级                               |
| `base_weight()`            | atr_level str                    | int %                | ATR 档位 → 基准首仓上限                          |
| `atr_volatility_level()`   | atr_ratio                        | (level_str, cap_pct) | 波动率档位 → 仓位上限                             |
| `atr_stop_buffer()`        | atr_ratio, atr14                 | (distance, text)     | ATRx2 止损距离                               |
| `average_amplitude_pct()`  | bars                             | float%               | 近 20 日平均振幅                               |
| `moving_averages()`        | bars                             | {ma5,ma10,ma20,ma30} | 多周期均线                                    |
| `count_below_ma()`         | current, ma_values               | int                  | 跌破均线数量                                   |

> **`status_for` 决策规则化**：规则定义在 `trader_shared/status_rules.yml`，由 `trader_shared/rule_engine.py` 按优先级求值。修改决策阈值只需编辑 YAML 文件，无需改 Python 代码。


### 5.2 利弗莫尔金字塔仓位算法

**规则**:


| Tier | 加仓倍率 | 触发条件                 |
| ---- | ---- | -------------------- |
| 0    | 0%   | 冲高减仓状态 / score 过低    |
| 1    | 15%  | 低吸观察/优先候选，score < 65 |
| 2    | 35%  | 优先候选，65≤ score < 80  |
| 3    | 60%  | 优先候选，80≤ score < 90  |
| 4    | 85%  | 强势确认，score ≥ 90      |
| 5    | 100% | 上限封顶                 |


```python
# candidate_core.py 实现
PYRAMID_SCALES = {0: 0, 1: 0.15, 2: 0.35, 3: 0.6, 4: 0.85, 5: 1.0}

def livermore_scale(status, score):
    tier = 0
    if status in {优先候选, 低吸观察}:
        tier = 1
        if score >= 90: tier = 4
        elif score >= 80: tier = 3
        elif score >= 65: tier = 2
    elif status in {等转强, 防守观察}:
        tier = 2
    elif status == 冲高减仓:
        tier = 0
    return min(tier, 5)

# ATR 档位 -> 首仓上限
BASE_WEIGHTS = {0: 15, 1: 10, 2: 7, 3: 4}
ATRLV_INDEX = {数据不足: 0, 波幅偏高: 3, 波动偏大: 2, 波动正常: 1, 波动较低: 0}

def base_weight(atr_level):
    idx = ATRLV_INDEX.get(atr_level, 1)
    return BASE_WEIGHTS.get(idx, 10)
```

**计算示例**:

- 南网科技 score=85, ATR 档位波动正常 → tier=3, 首仓上限=10%
- 中国铝业 score=55, ATR 档位波幅偏高 → tier=0, 首仓上限=4%（不加仓）

### 5.3 T0 价格点位引擎 (price_point_engine.py)

T0 独有的分析管线：

- 5m 日线 → 计算 RSI、MACD → 识别超买/超卖区间
- 结合 `candidate_core` 的 `build_candidate_levels()` 输出低吸区/确认价
- 输出: `observation_price`（开始关注）、`execution_price`（确认下单）、`acceptable_price`（可接受的次优价）、 `invalid_price`（失效价/跌破不接单）

### 5.4 盘后复盘 (review_model.py)


| 函数                                                                       | 返回值                                          |
| ------------------------------------------------------------------------ | -------------------------------------------- |
| `theory_verdicts(current, quote, daily, bars_5m, levels, cost, session)` | {structure, volume, chip, money, total} 五层打分 |
| `analyze_intraday(bars_5m, trade_date, session)`                         | 全天按时间分段（开盘/早盘/午盘/尾盘）逐根分析                     |
| `build_levels(current, quote, daily, cost)`                              | 支撑压力 + 浮盈亏                                   |
| `enrich_with_signal_backtrack(review, limit=10)`                         | 附加 `historical_signals` 字段                   |

### 5.5 缠论分析 (chan_core.py)


| 函数                          | 返回值                             | 说明                     |
| --------------------------- | ------------------------------- | ---------------------- |
| `handle_inclusion()`        | 去包含关系的 K 线列表                     | 合并同向包含                |
| `find_fractions()`          | 顶底分型列表                          | 顶分型/底分型检测             |
| `build_strokes()`           | 笔序列                             | 底→顶/顶→底交替            |
| `build_zones()`             | 中枢列表                            | 3 笔非重叠组，zh_top > zh_bottom |
| `detect_buy_points()`       | 一类买/二类买/三类买                      | MACD 辅助确认             |
| `detect_divergence()`       | 顶/底背驰                           | MACD 柱状图极值比较          |
| `chanlun_analysis()`        | 完整分析结果（trend_label, buy_point_text） | 主入口                   |
| `chanlun_strategy()`        | `{"chanlun": {...}}`              | `run_all()` 协议包装        |

### 5.6 威科夫分析 (wyckoff_core.py)


| 函数                       | 返回值                       | 说明              |
| ------------------------ | ------------------------- | --------------- |
| `_detect_spring()`       | Spring 弹簧信号                | 跌破支撑 + 收回      |
| `_detect_upthrust()`     | Upthrust 上冲回落信号            | 突破阻力 + 回踩      |
| `_detect_volume_divergence()` | (bearish, bullish) 量价背离      | 价格创新高/低但量能不配合 |
| `wyckoff_analysis()`     | 完整结果（spring/upthrust/summary） | 主入口             |
| `wyckoff_strategy()`     | `{"wyckoff": {...}}`        | `run_all()` 协议包装  |


---

## 六、Signal Contract 协议层

### 6.1 Signal Record v1（`signal_contract.py`）

统一的机器可读信号协议，版本 `trader_signal_v1`，验证器 242 行代码。

**必须字段**:


| 字段              | 类型       | 允许值                                                                                                                                                                                              |
| --------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `contract`      | string   | `trader_signal_v1`                                                                                                                                                                               |
| `source_skill`  | string   | trader / t0-trader / trader-compare / trader-portfolio / review-trader / trader-pool                                                                                                             |
| `symbol`        | string   | 股票代码，如 `688248.SH`                                                                                                                                                                               |
| `name`          | string   | 股票名                                                                                                                                                                                              |
| `trade_date`    | string   | `YYYY-MM-DD`                                                                                                                                                                                     |
| `analysis_time` | string   | ISO 时间                                                                                                                                                                                           |
| `signal_type`   | string   | observe / wait_for_confirmation / track / low_buy_watch / low_buy_triggered / high_sell_watch / high_sell_triggered / reduce / defensive / risk_stop / trigger_expired / blocked / review_result |
| `direction`     | string   | bullish / bearish / neutral / bullish_lean / bearish_lean                                                                                                                                        |
| `action`        | string   | no_action / observe / wait / track / pilot_entry / low_buy / high_sell / reduce / stop_low_buy / stop_high_sell                                                                                  |
| `confidence`    | string   | low / medium / high                                                                                                                                                                              |
| `data_status`   | string   | full / degraded / partial / insufficient / fresh / stale / non_trading                                                                                                                           |
| `trigger`       | dict     | price? (numeric, > 0) + text? (string)                                                                                                                                                           |
| `invalidation`  | dict     | 同上                                                                                                                                                                                               |
| `position`      | dict     | max_total_pct + max_single_move_pct (0-100, total >= single)                                                                                                                                     |
| `risk_flags`    | string[] | 自定义风险标签                                                                                                                                                                                          |
| `summary`       | string   | 一句话总结                                                                                                                                                                                            |


**验证器**: `assert_valid_signal(signal)` — 全部通过则静默，有 violation 则 `raise ValueError`。

### 6.2 持久化（`signal_store.py`）

- `DEFAULT_SIGNAL_STORE_PATH` = `~/.trader/signals.jsonl`（环境变量 `TRADER_SIGNAL_STORE_PATH` 可覆盖）
- `append_signal(signal)`: 验证后以 JSON 行追加写入
- `load_recent_signals(symbol=None, limit=20)`: 从尾部读最近 N 条

### 6.3 各 Skill 的信号写入


| Skill              | 写入时机                       | signal_type 示例                                                        |
| ------------------ | -------------------------- | --------------------------------------------------------------------- |
| `trader`           | `--output signal-json` 请求时 | `observe` / `reduce` / `defensive`                                    |
| `t0-trader`        | monitor mode 状态变化          | `low_buy_watch` → `low_buy_triggered` → `trigger_expired` / `blocked` |
| `review-trader`    | 盘后复盘完成                     | `review_result`                                                       |
| `pool compare`     | 消费 signals.jsonl 显示 tags   | 不写入，仅读取                                                               |
| `trader-portfolio` | 消费 signals.jsonl 显示 tags   | 不写入，仅读取                                                               |


### 6.4 Signal Tag 展示约定

下游消费时统一用 emoji 前缀:


| signal_type               | Tag    |
| ------------------------- | ------ |
| `low_buy_triggered`       | 🟢T0低吸 |
| `high_sell_triggered`     | 🔴T0高抛 |
| `risk_stop`               | ⚠️T0止损 |
| `track` / `low_buy_watch` | 👁跟踪   |
| `reduce`                  | 📉减仓   |


---

## 七、输出契约与校验

### 7.1 校验流程

每个 skill 都带 `validate_output.py` + `self_check.py`：

```bash
# 校验某文件
python3 scripts/validate_output.py report.md

# 完整自检（含 mock 数据验证）
python3 scripts/self_check.py
```

### 7.2 通用输出格式约束

所有 skill 的新面板格式统一遵守:

- `#` 标题语法：禁用（用 emoji 标题代替）
- `---` / `***` 水平线：禁用
- `**` 粗体：禁用
- `|...|` 表格：trader/t0/review 均禁用
- `>**`  块引用：禁用
- `*`  / `-`  列表符号：禁用
- 首行必须以固定 emoji 标识开头（如 `分析报告 —`  / `T0 —`  / `轮动仓位 —`  / `📌` ）

### 7.3 禁止词清单


| 类别    | 禁止词                                                                         |
| ----- | --------------------------------------------------------------------------- |
| 确定性预测 | `必涨`、`必跌`、`无脑加仓`                                                            |
| 主力叙事  | `主力入场第一枪`、`主力吸筹`、`主力锁仓`                                                     |
| 极端词汇  | `行情结束`、`出货日`、`极端波动`                                                         |
| 旧模板   | `📱 单票分析报告`、`✅ 先给结论`、`🎯 今日交易计划`、`📏 仓位上限`、`🧭 简化分析逻辑`、`⚠️ 风险管理`、`📌 交易指导卡` |
| T0 旧词 | `t0-trader`、`做T`、`做 T`、`执行价`、`T0买入价`、`T0卖出价`、`T0失效价`、`T0卖出观察`               |
| 技术栈   | `pandas`、`requests`、`akshare`、`enhanced_v1`、`daily_basic_v1`                |


---

## 八、数据流图

```
Tencent API (quotes/K-line)          Sina API (5/15/30m kline)
      |                                      |
      v                                      v
  light_data.py:load_market_snapshot() / fetch_qfq_daily() + fetch_5m()
      | (ATR14, atr7, atr_ratio appended in daily bars)
      v
  strategy_protocol.py:run_all():
    build_structure_context()  → 支撑/阻力/状态  <-- shared
    chanlun_strategy()         → 缠论 分型/笔/中枢/买卖点
    wyckoff_strategy()        → 威科夫 Spring/Upthrust/背离
      |
      +---> skill-1: run_analysis.build_report() -> render_markdown() (single stock)
      |
      +---> skill-2: t0_run.build_plan() -> price_point_engine -> render_markdown() (T0 card)
      |     + monitor.detect_state_change() (event loop)
      |
      +---> skill-3: final_pool.record_from_report() -> score/admission -> pool JSON
      |
      +---> skill-4: candidate_model.analyze_target() -> sort_candidates -> build_roles (portfolio)
      |
      +---> skill-5: review_model.build_review() -> theory_verdicts -> render_single (reversal)
```

**Skill 间数据传递**:

```
t0-trader monitor --append--> signals.jsonl --load_recent()--> review-trader backtrack
trader --output signal-json --> signals.jsonl (optional consumption)
trader-pool add --> pool.json -> plan --> last_plan.json
review-trader --> ~/.review-trader/state.json (cache)
t0-trader --> ~/.t0-trader/state.json (cooldown timer)
```

---

## 九、测试体系

### 9.1 测试文件分布


| Skill            | 单测文件                               | 数量  | 内容                                     |
| ---------------- | ---------------------------------- | --- | -------------------------------------- |
| trader           | `tests/test_contract.py`           | 13  | Signal Contract 校验、output 验证器          |
| t0-trader        | `tests/test_t0_contract.py`        | 4   | T0 output 验证器、 `detect_state_change()` |
| trader-pool      | `tests/test_compare_signals.py`    | 8   | Pool Compare signal tags 渲染            |
| trader-portfolio | `tests/test_portfolio_signals.py`  | 5   | Portfolio signal tags 消费               |
| review-trader    | `tests/test_review_backtrack.py`   | 5   | Review signal backtrack 回溯             |
| review-trader    | `tests/test_review_contract.py`    | ~10 | Review output 验证器 + banned words       |
| portfolio        | `tests/test_portfolio_contract.py` | ~5  | Portfolio output 验证器                   |
| shared-chan      | `tests/test_chan_core.py`          | 18  | 缠论: 包含处理/分型/笔/中枢/买卖点/背驰             |
| shared-wyckoff   | `tests/test_wyckoff_core.py`       | 8   | 威科夫: Spring/Upthrust/量价背离              |


### 9.2 测试运行

```bash
# 各 skill 自带 self_check
python3 scripts/self_check.py

# 完整测试（需安装 pytest）
python3 -m pytest 01-功能包-packages/*/tests/

# 仅单测
python3 -m pytest 01-功能包-packages/01-单票分析-trader/tests/ -v
```

### 9.3 测试数据

所有测试使用 mock 数据，不发起真实网络请求。 `light_data.py` 的 `HttpClient` 无 monkey-patch，测试中用 mock dict 替代。

---

## 十、维护指南

### 10.1 触发更新 AGENTS.md 的条件


| 变更类型                                                   | 需更新章节                                     |
| ------------------------------------------------------ | ----------------------------------------- |
| 新增/删除一个 skill                                          | Skill 职责矩阵 + Section 6 数据流图               |
| 新增/修改 skill 自然触发映射                                     | 对应 skill 职责小节                             |
| 修改 `light_data.py` 的 URL 或字段                           | Section 2.2 数据源                           |
| 修改 `candidate_core.py` 的 `STATUS_SCORE`/`status_for()` | Section 5.1 常量 + Section 2.3 状态机映射        |
| 修改 `status_rules.yml` 决策规则                        | Section 5.1 规则引擎说明                        |
| 修改打分公式/权重                                              | Section 5.1 + Section 5.2 利弗莫尔算法          |
| 修改 `strategy_protocol.py` 或新增策略实现                      | Section 4 依赖拓扑 + Section 5.1 核心函数         |
| 新增/修改 skill 间信号传递                                      | Section 6.3 写入表 / Section 8 数据流图          |
| 修改 Output Contract 格式                                  | Section 3 skill 卡 + Section 7 校验          |
| 新增持久化文件或修改 schema                                      | Section 2.4 持久化表                          |
| 新增分析方法论                                                | Section 1.4 方法论映射                         |
| 支持新的 Agent 平台                                          | Section 3 各 skill `<!-- AGENT_ROUTE: -->` |


### 10.2 自检命令

```bash
# 各 skill 自带 output 校验
python3 scripts/self_check.py                       # 应输出 *_OUTPUT_VALIDATOR=OK

# 验证 AGENTS.md 完整性
grep -c AGENT_ROUTE AGENTS.md                     # 应等于 skill 数量（含 deprecated）
grep -c OUTPUT_CONTRACT AGENTS.md                 # 应等于 skill 数量
grep -c DATA_DEP AGENTS.md                        # 应 >= 3（signals/pool/candidate）
```

### 10.3 版本管理

文档顶部 `> 最后更新` 和 `> 代码版本` 需手动维护。建议通过 git tag 绑定代码版本：

```bash
git tag trader-v0.4.0 HEAD
```

### 10.4 Agent 自动维护指令

嵌入文档头部：

```html
<!-- AGENT_MAINTENANCE:
  修改代码后，检查 Section 10.1 触发条件表。
  命中任一条件时，自动更新 AGENTS.md 对应章节，
  并更新顶部的版本标记（日期和 VERSION_STAMP）。
  不要主动删除任何章节。
  新增 skill 时，在 Section 3 末尾追加 skill 卡，在 Section 6 追加节点。
  修改 shared 模块后，检查依赖拓扑（Section 4）是否仍然准确。
-->
```

---

## 十一、未来演进方向


| 规划                              | 说明                                                                  | 优先级 | 状态   |
| ------------------------------- | ------------------------------------------------------------------- | --- | ---- |
| ✅ JSON Schema 化 Output Contract | `trader_shared/schema/v1.py` 统一规则库，5 个 skill validate_output 全部迁移   | P0  | 已完成  |
| ✅ 统一数据层 `DataProvider` 接口       | `trader_shared/data_provider.py` 可插拔接口 + `TencentSinaProvider` 默认实现 | P0  | 已完成  |
| 回测引擎                            | `calibrator.py` 扩展为正式回测框架                                           | P1  | 探索中  |
| `t0-trader` signal type 扩展      | 增加更多事件类型（如 `pilot_entry` 试仓）                                        | P2  | 未开始  |
| App/小程序前端面板                     | Markdown → 可视化 Chart 面板                                             | P2  | 未开始  |
| ✅ shared 包标准化                   | `trader_shared/` Python 包，lazy-load `__init__.py`，5 个 skill 导入已迁移   | P3  | 已完成  |
| Level 2 / 逐笔数据接入                | 盘中更精细数据                                                             | P3  | 不打算做 |


---

## 十二、附录：目录结构

```
Trader 2.0/
+-- 01-功能包-packages/
|   +-- 01-单票分析-trader/
|   |   +-- SKILL.md    HERMES.md
|   |   +-- scripts/
|   |       +-- final_report.py      # 入口
|   |       +-- run_analysis.py      # 数据拉取 + build_report
|   |       +-- validate_output.py   # output 校验
|   |       +-- self_check.py        # 自检
|   |
|   +-- 02-盘中T0-t0-trader/
|   |   +-- SKILL.md    HERMES.md
|   |   +-- scripts/
|   |       +-- final_t0.py           # 入口
|   |       +-- t0_run.py             # build_plan + signal 构建
|   |       +-- monitor.py            # 盯盘循环 + cooldown
|   |       +-- price_point_engine.py # T0 价格点位
|   |       +-- indicators.py         # RSI/MACD
|   |       +-- ict_execution.py      # ICT-Lite
|   |       +-- validate_output.py
|   |       +-- self_check.py
|   |
|   +-- 03-选股池-trader-pool/
|   |   +-- SKILL.md    HERMES.md
|   |   +-- scripts/
|   |       +-- final_pool.py         # 入口（analyze add/show/rank/plan/review）
|   |       +-- run_analysis.py       # 复用 trader 管线
|   |       +-- final_report.py       # 旧版兼容
|   |       +-- validate_output.py
|   |       +-- self_check.py
|   |
|   +-- 04-仓位轮动-trader-portfolio/
|   |   +-- SKILL.md    HERMES.md
|   |   +-- scripts/
|   |       +-- final_portfolio.py    # 入口
|   |       +-- portfolio_run.py      # 仓位构建 + Markdown 渲染
|   |       +-- candidate_model.py    # analyze_target + livermore 仓位计算
|   |       +-- validate_output.py
|   |       +-- self_check.py
|   |
|   +-- 05-盘后复盘-review-trader/
|   |   +-- SKILL.md    HERMES.md
|   |   +-- scripts/
|   |       +-- final_review.py       # 入口（single/compare/compare-recent）
|   |       +-- review_model.py       # theory_verdicts + enrich_with_signal_backtrack
|   |       +-- review_render.py      # Markdown 渲染
|   |       +-- review_single.py      # 单票入口
|   |       +-- review_compare.py     # 多股入口
|   |       +-- review_store.py       # 缓存
|   |       +-- validate_output.py
|   |       +-- self_check.py
|   |
+-- 02-共享模块-shared/
|   +-- 01-行情数据-market-data/
|   |   +-- light_data.py             # HTTP 客户端 + 数据拉取
|   |   +-- models.py                 # TypedDict 统一数据模型
|   |
|   +-- 02-候选逻辑-candidate/
|   |   +-- candidate_core.py         # 状态机 + 打分 + ATR + Livermore
|   |   +-- t0_candidate_core.py      # T0 专用候选逻辑
|   |   +-- chan_core.py              # 缠论: 分型/笔/中枢/买卖点/背驰
|   |   +-- wyckoff_core.py           # 威科夫: Spring/Upthrust/量价背离
|   |
|   +-- 03-输出校验-contracts/
|   |   +-- signal_contract.py        # trader_signal_v1 校验器
|   |   +-- signal_store.py           # JSONL 持久化读写
|   |   +-- test_signal_contract.py   # contract 单元测试
|   |
|   +-- contract_utils.py             # 文本校验工具（validate_banned/headings）
|   +-- tests/
|   |   +-- test_chan_core.py         # 缠论单元测试（18 个）
|   |   +-- test_wyckoff_core.py      # 威科夫单元测试（8 个）
|   +-- scripts/
|       +-- calibrator.py             # 回测校准
|       +-- market_env.py             # 大盘环境判断
|       +-- pipeline.py               # 状态管道
|       +-- signal_tracker.py         # 信号追踪
|   |
|   +-- trader_shared/                # P6: 标准 Python 包
|       +-- __init__.py               # lazy-load 路由
|       +-- calibrator.py             # 回测校准（副本，品加载）
|       +-- market_env.py             # 大盘环境（副本，品加载）
|       +-- pipeline.py               # 状态管道（副本，品加载）
|       +-- signal_tracker.py         # 信号追踪（副本，品加载）
|       +-- schema/
|       |   +-- v1.py                 # P7: 输出契约规则库
|       +-- data_provider.py          # P8: 可插拔数据接口
|
+-- 03-安装包-dist/                   # zip 安装包和构建产物
+-- agent.md                          # Agent 指令文件（Skill 加载入口）
+-- trader-refactor-plan.md           # ATR 集成重构计划
+-- docs/
|   +-- TRADER_REBUILD_SPEC.md
|   +-- superpowers/
|       +-- plans/                    # 实施计划
|       +-- specs/                    # 设计文档
+-- AGENTS.md                        # <-- 你正在读的这份架构文档
```

---

## 十三、附录：Skill 自然触发词映射


| Skill              | 自然触发词（示例）                                   |
| ------------------ | ------------------------------------------- |
| `trader`           | 分析 XX / 看看 XX / XX 怎么样 / 单票分析 / 盯盘 XX       |
| `t0-trader`        | T0 / 做T / 盘中T / 什么价买 / 什么价卖 / 盯盘 / 提醒       |
| `trader-pool`      | 加入选股池 / 入池 / 对比 / 比较 / 池内排序 / 生成作战表 / 复盘选股池 |
| `trader-portfolio` | 仓位分配 / 轮动 / 仓位计划 / 2-3 只比一下                 |
| `review-trader`    | 复盘 XX / 盘后复盘 / 午间复盘 / compare XX YY         |
| `trader-pool` soft | 这个不错 / 可以关注 / 明天看看                          |


