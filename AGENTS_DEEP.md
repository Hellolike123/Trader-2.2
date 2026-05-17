# Trader 2.0 — 架构文档（深挖参考）

> 最后更新：2026-05-17
> **注意**: AGENTS.md 是 Agent 快速参考，本文档用于开发调试/架构深挖。

---

## 变更日志

### 2026-05-09 — Skill 结构优化：Commands/Output Contract 移至 references/

**目的：** 降低 SKILL.md 上下文占用，防止 LLM 幻觉生成错误命令或格式。

**变更内容：**
- 6 个 skill（trader, t0-trader, trader-pool, trader-portfolio, review-trader, trader-tracking）
- SKILL.md 从 ~2100 词精简至 ~1200 词（↓43%）
- 每个 skill 新增 `references/` 目录，包含：
  - `commands.md` — 所有脚本命令（声明为"绝对真理"）
  - `output-contract.md` — 输出格式模板和旧输出检测清单（声明为"绝对真理"）
- 打包：`pack_all.py` 会自动将 `references/` 包含进 zip 包

### 2026-05-06 — 算法准确性审计

对核心算法指标模块逐行审计，修复 MACD 金叉/RSI 死代码/缠论分型检测/_calc_macd 副作用/DEA 初始化/中枢步长/一类买点/二类买点等 9 个问题。覆盖 momentum_core、chan_core、wyckoff_core、structure_core、decision_core、indicators.py、ict_execution.py。

---

## 二、数据架构（详细）

### 2.1 数据源

| 来源 | 接口 | 返回数据 | 用途 |
|------ | ------ | ------ | ------ |
| 腾讯行情 | `qt.gtimg.cn/q=` | 实时快照（现价/昨收/今开/涨跌/成交量/换手率） | 所有 skill 的现价/涨跌幅 |
| 腾讯日线 | `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 前复权日线，附加 `atr14/atr7/atr_ratio/tr` 字段 | 支撑阻力计算、状态判定 |
| 新浪 K 线 | `money.finance.sina.com.cn/quotes_service/api/...` | 5m / 15m / 30m 分钟线 | t0-trader 盘中分析 |

### 2.2 light_data.py — 唯一数据入口

`02-共享模块-shared/01-行情数据-market-data/light_data.py` (403 行) 是所有 skill 的唯一数据拉取模块。

**核心函数：**

| 函数 | 作用 |
|------ | ------ |
| `fetch_quote()` | 腾讯实时行情快照 → `QuoteData` |
| `fetch_qfq_daily()` | 腾讯前复权日线，追加 ATR 字段 |
| `fetch_5m()` / `fetch_15m()` / `fetch_30m()` | 新浪分钟线 |
| `fetch_kline()` | 通用多周期 K 线拉取 + 归一化 |
| `load_market_snapshot()` | 聚合 quote + daily + 5m，返回 `MarketSnapshot` |
| `resolve_security()` | 股票名/代码 → `Security(dataclass)` |
| `pct_change()` / `to_float()` | 安全数值工具 |
| `is_trading_time()` | 判断当前是否为交易日 9:30-15:00 |

**数据模型层** `models.py` 定义统一 TypedDict：

| TypedDict | 用途 |
|------ | ------ |
| `BarData` | 统一 K 线数据行（跨周期） |
| `QuoteData` | 实时行情快照 |
| `MAValues` | 多周期均线集合 |
| `CandidateLevels` | 候选交易区间（支撑/阻力/止损/止盈/确认价） |
| `CandidateSignal` | 候选信号核心结构 |
| `TheoryVerdict` | 复盘五层理论打分 |
| `SignalRecord` | Signal Contract v1 记录 |
| `ChanlunSignal` | 缠论分析结果 |
| `WyckoffSignal` | 威科夫信号 |

**HTTP 客户端** `HttpClient`：GET with User-Agent、gzip、SSL-unverified。 `retry()` 指数退避 3 次。
**缓存**：bars 不含当日日期时缓存 1 小时，实时数据不缓存。
**NAME_MAP**：9 个常用股票名到代码的映射（南网科技→688248、中国铝业→601600 等）。

### 2.3 状态机（`candidate_core.STATUS_SCORE`）

| 状态 | score | 触发条件 | 典型场景 |
|------ | ------ | ------ | ------ |
| **暂不碰** | 20 | 现价跌破硬止损 | 破位下行，防守优先 |
| **低吸观察** | 80 | 现价在低吸区附近，未破止损 | 缩量回调用至支撑区 |
| **冲高减仓** | 55 | 现价靠近确认价/压力区，上涨乏力 | 反弹触压，减仓信号 |
| **等转强** | 70 | 现价在支撑之上但距确认价有空间 | 止跌后等待确认突破 |
| **防守观察** | 60 | 现价靠近支撑但未确认止跌 | 支撑附近观望 |
| **空间不足** | 45 | 距确认价空间过小，盈亏比不够 | 高位震荡，无明确方向 |
| **数据失败** | 0 | K 线数据不足 60 根 | 新股/停牌复牌 |

### 2.4 状态判定优先级

`status_for()` 判定顺序: 暂不碰 > 低吸观察 > 冲高减仓/等转强 > 空间不足 > 防守观察

---

## 三、Skill 职责详情

### 3.1 trader（单票分析）

**入口**: `scripts/final_report.py`
**分析模型**: `run_analysis.py::build_report()` → `final_report.py::render_markdown()` → `build_signal()`
**策略链**: `strategies = [build_structure_context, chanlun_strategy, wyckoff_strategy]`
**输入数据**: 腾讯日线（前复权 + ATR）+ 实时快照
**依赖共享模块**: `candidate_core`、`light_data`、`signal_contract`、`chan_core`、`wyckoff_core`

**Output Contract（固定顺序）**:
```
分析报告 — {name}（{code}）
现价 + MA5/MA10/MA20/MA30 + ATR 行
🌍 中证1000 → 趋势/涨跌%/建议
📍 决策 → 状态 + 空仓/有底仓/加仓指引
T0 参考 → 低吸/高抛/止损
❗ 关键价位 → 止损|减仓|止跌|支撑
🧭 简要分析 → 结构/量价/筹码/动能
```

### 3.2 t0-trader（盘中T0）

**入口**: `scripts/final_t0.py`
**子模块**: `t0_run.py` / `price_point_engine.py` / `monitor.py` / `indicators.py` / `ict_execution.py`
**输入数据**: 腾讯实时快照 + 新浪 5m/15m/30m K线

**Monitor Mode**: 3 分钟轮询 → `detect_state_change()` → 15 分钟 cooldown → 输出告警文本 + 追加 `signals.jsonl`。单次 `--once` 适合 cron 调度。

### 3.3 trader-pool（选股池）

**入口**: `scripts/final_pool.py`
**命令集**: `analyze` `add` `add-pending` `confirm-to-pool` `show` `show-pending` `rank` `compare` `plan` `review` `remove` `archive-exited`

**入池打分（ `_score_report()` ）**:
- 缠论子分（max 45）: 24 基础 + 阶段/场景/价格距离加分
- 威科夫子分（max 30）: 15 基础 + 量能/动能加分
- 筹码子分（max 25）: 15 基础 + 止损/支撑/止盈加分
- 综合 ≥ 70 → 执行; ≥ 55 → 观察；触及防守线 → 拒绝/淘汰

### 3.4 trader-portfolio（仓位轮动）

**入口**: `scripts/final_portfolio.py`
**子模块**: `candidate_model.py` / `portfolio_run.py`
**Snapshots 输入**: `{targets: [...], holdings: [...], candidates: [...], account: {max_move_pct, total_position_pct, cash_pct}}`

### 3.5 review-trader（盘后复盘）

**入口**: `scripts/final_review.py`
**子模块**: `review_model.py` / `review_render.py` / `review_single.py` / `review_compare.py` / `review_store.py`

**五层理论分析** (`theory_verdicts()`):

| 层级 | 范围 |
|------ | ------ |
| 缠论结构 | 0-100 |
| 威科夫量价 | 0-100 |
| 筹码峰 | 0-100 |
| 资金行为 | 0-100 |
| 动能确认 | 0-100 |

### 3.6 trader-tracking（信号追踪）

**入口**: `scripts/final_tracker.py`
**功能**: 从 `~/.trader/signal_results.jsonl` 生成信号准确率面板（胜率、涨跌比、盈亏比）
**版本**: v0.1.0

核心逻辑在共享模块 `signal_tracker.py` 中，该 Skill 是薄包装层，负责调用共享模块并渲染输出。

**脚本清单**:
- `final_tracker.py` — 入口，调用 `signal_tracker.py` 并渲染面板
- `self_check.py` — 输出格式自检
- `validate_output.py` — 输出契约校验
- `install_skill.py` — 安装脚本

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
                    |-- trader_shared/         ← P6: 标准 Python 包
                    |    __init__.py (lazy-load 路由)
                    |    config.py (全系统常量集中管理)
                    |    schema/v1.py (P7: 输出契约规则库)
                    |    data_provider.py (P8: 可插拔数据接口)
                    +--------------------------+
                              ^ sys.path.insert(3 parents up)
                    +- 各 skill scripts/*.py
                    +--------------------------+
```

所有 skill 通过 `ROOT = Path(__file__).resolve().parents[3]` 向上定位共享模块，再用 `sys.path.insert()`。

---

## 五、分析模型层（详细）

### 5.1 candidate_core.py

**常量配置** 全部集中在 `trader_shared/config.py`，per-skill `config.py` 可覆盖。

**核心函数:**
| 函数 | 参数 | 返回值 |
|------ | ------ | ------ |
| `build_structure_context()` | current, bars, change_pct, quote | CandidateLevels |
| `status_for()` | 价格/支撑/确认价/止损等 + MA + 压力空间 | str 状态 |
| `score_for()` | status + 现价+支撑+空间+MA+ATR dict | float 0-100 |
| `livermore_scale()` | status, score | int 0~5 |
| `base_weight()` | atr_level str | int % |
| `atr_volatility_level()` | atr_ratio | (level_str, cap_pct) |
| `atr_stop_buffer()` | atr_ratio, atr14 | (distance, text) |

### 5.2 利弗莫尔金字塔仓位算法

| Tier | 加仓倍率 | 触发条件 |
|------ | ------ | ------ |
| 0 | 0% | 冲高减仓状态 / score 过低 |
| 1 | 15% | 低吸观察/优先候选，score < 65 |
| 2 | 35% | 优先候选，65≤ score < 80 |
| 3 | 60% | 优先候选，80≤ score < 90 |
| 4 | 85% | 强势确认，score ≥ 90 |
| 5 | 100% | 上限封顶 |

### 5.3 缠论分析 (`chan_core.py`)

`handle_inclusion()` / `find_fractions()` / `build_strokes()` / `build_zones()` / `detect_buy_points()` / `detect_divergence()`

### 5.4 威科夫分析 (`wyckoff_core.py`)

`_detect_spring()` / `_detect_upthrust()` / `_detect_volume_divergence()` / `wyckoff_analysis()`

### 5.5 动量策略 (`momentum_core.py`)

`calc_rsi()` / `calc_macd()` / `calc_adx()` / `calc_bollinger()` / `assess_momentum()`

---

## 六、Signal Contract 协议层

### 6.1 Signal Record v1

版本 `trader_signal_v1`，验证器 242 行。

**必须字段摘要：**

| 字段 | 类型 | 允许值 |
|------ | ------ | ------ |
| `contract` | string | `trader_signal_v1` |
| `source_skill` | string | trader / t0-trader / trader-pool / trader-portfolio / review-trader |
| `symbol` | string | `688248.SH` |
| `signal_type` | string | observe / low_buy_watch / low_buy_triggered / high_sell_triggered / reduce / defensive / risk_stop / trigger_expired / blocked / review_result |
| `direction` | string | bullish / bearish / neutral |
| `action` | string | no_action / observe / wait / track / low_buy / high_sell / reduce |
| `confidence` | string | low / medium / high |
| `position` | dict | max_total_pct + max_single_move_pct |

### 6.2 信号写入

| Skill | 写入时机 | signal_type 示例 |
|------ | ------ | ------ |
| `trader` | `--output signal-json` | `observe` / `reduce` |
| `t0-trader` | monitor mode 状态变化 | `low_buy_watch` → `low_buy_triggered` |
| `review-trader` | 盘后复盘完成 | `review_result` |

### 6.3 Signal Tag 展示约定

| signal_type | Tag |
|------ | ------ |
| `low_buy_triggered` | 🟢T0低吸 |
| `high_sell_triggered` | 🔴T0高抛 |
| `risk_stop` | ⚠️T0止损 |
| `track` / `low_buy_watch` | 👁跟踪 |
| `reduce` | 📉减仓 |

---

## 七、输出契约与校验（详细）

### 7.1 通用输出格式约束

- `#` 标题 → 禁用
- `---` / `***` 水平线 → 禁用
- `**` 粗体 → 禁用
- `|...|` 表格 → 禁用
- 首行必须以固定 emoji 开头

### 7.2 禁止词清单

| 类别 | 禁止词 |
|------ | ------ |
| 确定性预测 | `必涨`、`必跌`、`无脑加仓` |
| 主力叙事 | `主力入场第一枪`、`主力吸筹`、`主力锁仓` |
| 极端词汇 | `行情结束`、`出货日`、`极端波动` |
| 旧模板 | `📱 单票分析报告`、`✅ 先给结论`、`📌 交易指导卡` 等 |
| T0 旧词 | `t0-trader`、`做T`、`执行价`、`T0买入价` 等 |
| 技术栈 | `pandas`、`requests`、`akshare` 等 |

---

## 八、数据流图

```
Tencent API → light_data.py
Sina API → fetch_5m/fetch_15m/fetch_30m
  ↓
strategy_protocol.py:run_all()
  build_structure_context() → chanlun_strategy() → wyckoff_strategy()
  ↓
  └──→ final_report.py (trader)
  └──→ t0_run.py → final_t0.py (t0-trader)
  └──→ final_pool.py (trader-pool)
  └──→ final_portfolio.py (trader-portfolio)
  └──→ final_review.py (review-trader)

数据流转:
t0-trader monitor → signals.jsonl → review-trader backtrack
trader-pool add → pool.json → plan → last_plan.json
```

---

## 九、测试体系

### 9.1 测试文件分布

| Skill | 单测文件 | 数量 |
|------ | ------ | ------ |
| trader | `tests/test_contract.py` | 13 |
| t0-trader | `tests/test_t0_contract.py` | 4 |
| trader-pool | `tests/test_compare_signals.py` | 8 |
| trader-portfolio | `tests/test_portfolio_signals.py` | 5 |
| review-trader | `tests/test_review_backtrack.py` | 5 |
| shared-chan | `tests/test_chan_core.py` | 18 |
| shared-wyckoff | `tests/test_wyckoff_core.py` | 8 |

### 9.2 测试命令

```bash
python3 scripts/self_check.py
python3 -m pytest 01-功能包-packages/*/tests/
```

---

## 十、打包与部署

### 10.1 zip 包

`pack_all.py` 生成：
- **单独 zip** (`trader.zip` 等) → 解压到 `~/.hermes/skills/trader/`
- **合集 zip** (`trader-all-skill.zip`) → 解压到 `~/.hermes/skills/`

### 10.2 PyInstaller（可选）

```bash
# 仅开发机执行
pyinstaller --onefile --name trader scripts/final_report.py
```

### 10.3 手动打包

```bash
python3 02-共享模块-shared/scripts/pack_all.py
```

---

## 十一、维护指南

### 11.1 触发更新 AGENTS.md 的条件

| 变更类型 | 需更新章节 |
|------ | ------ |
| 新增/删除一个 skill | Skill 职责矩阵 + Section 六 |
| 修改 `light_data.py` | Section 二 |
| 修改 `candidate_core.py` 状态/打分 | Section 二 + 三 |
| 修改打分公式/权重 | Section 五 |
| 新增/修改 skill 间信号传递 | Section 六 + 八 |
| 修改 Output Contract 格式 | Section 三 + 七 |

### 11.2 版本管理

```bash
git tag trader-v0.6.0 HEAD
```

---

## 十二、目录结构

```
Trader 2.0/
├── 01-功能包-packages/
│   ├── 00-系统工具/ (系统级工具包，含 tests/test_pack_all.py 打包测试)
│   ├── 01-单票分析-trader/ (SKILL.md, scripts/final_report.py, references/)
│   ├── 02-盘中T0-t0-trader/ (SKILL.md, scripts/final_t0.py, references/)
│   ├── 03-选股池-trader-pool/ (SKILL.md, scripts/final_pool.py, references/)
│   ├── 04-仓位轮动-trader-portfolio/ (SKILL.md, scripts/final_portfolio.py, references/)
│   ├── 05-盘后复盘-review-trader/ (SKILL.md, scripts/final_review.py, references/)
│   └── 06-信号追踪-trader-tracking/ (SKILL.md, scripts/final_tracker.py, references/)
├── 02-共享模块-shared/
│   ├── 01-行情数据-market-data/ (light_data.py, models.py)
│   ├── 02-候选逻辑-candidate/ (candidate_core.py, chan_core.py, wyckoff_core.py)
│   ├── 03-输出校验-contracts/ (signal_contract.py, signal_store.py)
│   ├── scripts/ (calibrator.py, market_env.py, pipeline.py, signal_tracker.py)
│   └── trader_shared/ (config.py, schema/v1.py, data_provider.py)
└── 03-安装包-dist/releases/ (构建产物，不提交)
```

---

## 十三、Hermes 集成要点（详细）

### 13.1 技能文件结构

| 文件 | 用途 | 谁读它 |
|------ | ------ | ------ |
| `_meta.json` | 元数据（name/version） | Hermes 框架 |
| `HERMES.md` | 框架指令：运行什么命令 | Hermes 框架 |
| `SKILL.md` | **LLM prompt** | **LLM**（每次对话注入 context） |

### 13.2 核心问题

**LLM 可以忽略 SKILL.md。** 即使命令很明确，LLM 也可能自己编答案。

### 13.3 解决方案

**Agent 操作者直接调 `terminal()` 跑脚本**，不让 LLM 参与内容生成。

### 13.4 Pack_all.py 注意事项

**Zip 结构必须 flat** — 文件在 zip 根级，不能有多余目录前缀。
每个 skill zip 的 `scripts/` 里必须包含所有共享模块（light_data, candidate_core, chan_core, wyckoff_core, momentum_core 等）。

### 13.5 SKILL.md 写法要点

- 必须简洁、指令明确
- 必须包含 **Critical Rule**: "This is a script-output skill"
- 必须包含 **Output Contract**: 精确标题顺序和格式
- 必须包含 **Old Output Detection**: 禁止词和错误模式
- 现在必须引用 `references/commands.md` 和 `references/output-contract.md` — "绝对真理"声明防止幻觉

---

## 十四、Skill 自然触发词映射

| Skill | 自然触发词 |
|------ | ------ |
| `trader` | 分析 XX / 看看 XX / XX 怎么样 / 单票分析 / 盯盘 XX |
| `t0-trader` | T0 / 做T / 盘中T / 什么价买 / 什么价卖 / 盯盘 |
| `trader-pool` | 加入选股池 / 入池 / 对比 / 比较 / 池内排序 / 生成作战表 |
| `trader-portfolio` | 仓位分配 / 轮动 / 仓位计划 / 2-3 只比一下 |
| `review-trader` | 复盘 XX / 盘后复盘 / 午间复盘 / compare XX YY |
| `trader-pool` soft | 这个不错 / 可以关注 / 明天看看（→ add-pending） |

---

## 十五、规划与路线图

| 规划 | 说明 | 优先级 | 状态 |
|------ | ------ | ------ | ------ |
| ✅ JSON Schema 化 Output Contract | `trader_shared/schema/v1.py` | P0 | 已完成 |
| ✅ 统一数据层 `DataProvider` 接口 | `trader_shared/data_provider.py` | P0 | 已完成 |
| 回测引擎 | `calibrator.py` 扩展为正式回测框架 | P1 | 探索中 |
| `t0-trader` signal type 扩展 | 增加 `pilot_entry` 试仓等 | P2 | 未开始 |
| App/小程序前端面板 | Markdown → 可视化 Chart 面板 | P2 | 未开始 |
| ✅ shared 包标准化 | `trader_shared/` Python 包 | P3 | 已完成 |
