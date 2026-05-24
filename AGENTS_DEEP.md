# Trader 2.3 — 架构文档（深挖参考）

> 最后更新：2026-05-23
> **注意**: AGENTS.md 是 Agent 快速参考，本文档用于开发调试/架构深挖。

---

## 变更日志

### 2026-05-23 — Trader 2.3：四大高级统计模块上线

新增四个纯 numpy 轻量级统计学模块，零重量级框架依赖：
- `hmm_regime.py` — 隐马尔可夫大势检测（Baum-Welch + Viterbi，3 隐状态）
- `bayesian_fusion.py` — 贝叶斯乘积规则多专家融合（默认关闭，BAYESIAN_FUSION=true 激活）
- `volume_profile.py` — 日内成交量分布，POC 控制节点与 70% Value Area
- `scripts/self_calibration.py` — 离线随机搜索参数校准，写入 ~/.trader/calibrated_params.json

测试体系扩展至 485 个用例（新增 3 个测试文件），全部通过零 Regression。

### 2026-05-23 — Trader 2.2：信号生命周期 V2 + 行情 HA + 融合优先级

- Signal Contract v2：SHA256 deterministic UUID，原子落盘，历史数据迁移工具
- MarketDataSourceController：1.5s TCP 超时熔断，30s 冷却隔离，自动 fallback 至腾讯/新浪
- 融合层场景优先级过滤器 + 置信冲突消解 + Regime 自适应参数缩放

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

### 2.2 light_data.py — 唯一数据入口与双源 HA 管道

`02-共享模块-shared/01-行情数据-market-data/light_data.py` 是所有 skill 的唯一数据拉取入口。在 Trader 2.2 中，该模块已全面重构为**双源热备高可用 (HA) 行情管道**。

#### 2.2.1 MarketDataSourceController 行情源控制器
系统使用独立的 `MarketDataSourceController` 来跟踪 mootdx TCP 行情接口的运行健康度：
* **秒级超时控制**：所有 mootdx 接口调用（如 bars / quotes）强制注入 `socket.setdefaulttimeout(1.5)` 限制，确保因网络阻塞引起的卡死在 1.5s 内强制熔断，防止导致盯盘/选股池任务发生静默离线挂起。
* **隔离冷却机制**：追踪连续失败次数。当 `consecutive_failures >= 3` 时，行情源判定为 `UNHEALTHY`，强制将其隔离并冷却冷却 `cooldown_seconds = 30` 秒。期间所有数据请求直接避开 mootdx 以节约查询开销。
* **静默秒切容灾**：当 mootdx 处于隔离冷却期或单次请求超时失败时，管道进行静默秒切降级：
  * **行情快照 (fetch_quote)**：自动 fallback 至腾讯 HTTP 行情 API。
  * **前复权日线 (fetch_qfq_daily)**：自动 fallback 至腾讯前复权日线接口。
  * **分钟线 (fetch_5m/15m/30m/kline)**：自动 fallback 至 `akshare` (EastMoney API)。

#### 2.2.2 数据完备度标识 (`data_status`)
为保证下游策略对行情数据质量的知情权，`MarketSnapshot` 数据模型原生打上完备度标签：
* `"full"`：所有主行情源均正常返回完整数据（包含五档盘口）。
* `"partial"`：触发了 HTTP 行情源降级（例如 mootdx 挂掉，使用腾讯/akshare 行情），或者缺失了次要数据源（如 5m 分时缺失）。
* `"degraded"`：仅剩下快照或日线单方数据，策略精度降低。
* `"failed"`：完全无法获取数据。
* `missing_sources` 和 `source_errors` 用以记录具体失败源及其 Traceback，消除静默故障。

**核心函数：**

| 函数 | 作用 | 完备度标签影响 |
|------ | ------ | ------ |
| `fetch_quote()` | 腾讯实时行情快照 → `QuoteData` | 失败则降级 / 触发重试 |
| `fetch_qfq_daily()` | 腾讯前复权日线，追加 ATR 字段 | 失败则降级 / 触发重试 |
| `fetch_5m()` / `fetch_15m()` / `fetch_30m()` | 新浪分钟线 | 失败 fallback 至 akshare |
| `fetch_kline()` | 通用多周期 K 线拉取 + 归一化 | 失败 fallback 至 akshare |
| `load_market_snapshot()` | 聚合并拉取多源行情返回 `MarketSnapshot` | 自动标注 `data_status` |
| `resolve_security()` | 股票名/代码 → `Security(dataclass)` | 解析归一化证券代码 |
| `is_trading_time()` | 判断当前是否为交易日 9:30-15:00 | 过滤非交易时段 |

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
**缓存**：bars 不含当日日期时缓存 1 小时，实时数据不缓存，行情快照进行 30s TTL 缓存。
**NAME_MAP**：9 个常用股票名到代码的映射（南网科技→688248、中国铝业→601600 等）。

### 2.3 状态机（`candidate_core.STATUS_SCORE`）

> 说明：这里描述的是旧的单层候选状态机，它仍然存在于兼容链里，但不是单票分析的主契约。单票分析现在以 `base_status` + `theory_status` 为主，`state_label` 只是展示/兼容层。

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
🧭 简要分析 → 基础状态/体系结论 + 结构/量价/筹码/动能
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

### 5.6 智能决策融合层 (`fusion_core.py` / `fusion_regime.py`)

决策融合层是贯穿结构、缠论、动量与威科夫等多维分析体系的“终极裁判”。在传统多指标决策中，多头信号与空头冲突往往会导致系统输出“数据冲突”或者“中性旁观”等平庸判定。Trader 2.2 通过智能决策融合层彻底打破了这一桎梏。

#### 5.6.1 信号标准化抽象
融合层首先将底层各个策略子系统的原始计算结果抽象为带有方向与置信度的统一信号包（`CandidateSignal`）：
* **缠论转换**：根据（一/二/三类买点 > 底背驰 > 顶背驰 > 趋势段）优先级映射。一类买点（底背驰极值点）置信度 0.8，趋势拉升段置信度 0.4。
* **动量转换**：使用独特的 **U 型置信度映射函数**。动量指标分值接近两端（极度超买/超卖，$\le 25$ 或 $\ge 75$）时置信度激增为 0.8，处于 41-59 震荡灰区时置信度跌至 0.2。
* **威科夫转换**：Spring 弹簧信号置信度 0.70（叠加看多背离达 0.75），上冲回落（Upthrust）置信度 0.6，看多/看空量价背离置信度 0.5。

#### 5.6.2 场景优先级过滤器 (Scenario Priority Filter)
融合层摒弃了静态等权（Equal Weighting）模式，通过计算股价在 20 日高低区间的相对价格位置（$pos\_pct$），实行动态权重倾斜：
* **筑底/突破区间（$pos\_pct \le 0.3$ 或强结构买点）**：将 **80% 的决策权重分配给结构化理论（缠论 45% + 威科夫 35%）**，动量权重压缩至 20%。以此消除低位筑底时动量指标金叉/死叉频繁交织产生的磨损，强力捕捉“Spring 弹簧低吸位”或“缠论三买突破位”。
* **冲顶/超买区间（$pos\_pct \ge 0.7$ 或强结构卖点/高动量）**：将 **80% 的决策权重分配给动量与威科夫量价（动量 55% + 威科夫 25%）**，缠论权重压缩至 20%。用来在情绪高潮期通过动量极值和威科夫上冲回落拦截假突破，预防高位套牢。
* **震荡区间**：退化为基于宏观大势的标准权重。

```mermaid
graph TD
    Price["相对价格区间 (pos_pct)"] -->|<= 0.3 低位/突破| Breakout["低位/突破场景偏斜"]
    Price -->|>= 0.7 高位/超买| Climax["高位/超买场景偏斜"]
    Price -->|其他 震荡区| Standard["大势标准权重"]

    Breakout -->|缠论 45% + 威科夫 35%| Output1["结构占 80% 权重"]
    Climax -->|动量 55% + 威科夫 25%| Output2["动量占 80% 权重"]
    Standard -->|大盘牛熊自适应权重| Output3["Regime 权重"]
```

#### 5.6.3 冲突消解与 Veto 噪点消减机制
当各维理论出现强分歧时（$disagreement = max(dir) - min(dir) > 1$，如 1 与 -1 并存），融合层启动置信度优先级覆盖逻辑：
* **低位转强 Veto 覆盖**：若底层触发了缠论结构买点或威科夫 Spring 看多信号，直接将动量指标的看空噪点归零（$direction = 0$）。
* **高位筑顶 Veto 覆盖**：若底层触发了缠论顶背驰或威科夫上冲回落（Upthrust）看空信号，直接将动量指标的冲高看多噪点归零。
* **分歧解耦**：当发生 Veto 噪声消除时，系统将用于诊断的原始分歧度 `disagreement` 与用于映射决策逻辑的 `disagreement_for_action` 进行解耦，并强制令 `disagreement_for_action = 0`，消除传统策略在强底分型转强突破时被冲突误判拦截的隐患。

### 5.7 大势参数自适应调节器 (Regime Multipliers)

在单票分析的价格计算层（`structure_core.py`），系统不再使用静态硬编码的安全缓冲，而是引入了与大盘宏观牛熊环境（`market_env`）及理论融合结果深度挂钩的自适应调节器：

#### 5.7.1 Regime 参数微调公式
系统通过 `_theory_multipliers` 计算 4 个维度的动态调节系数：

1. **大势缩放 (Regime Factor)**：
   * **偏弱/很差大势**：自动收窄止损缓冲距离（`stop_buffer` = 0.8x），防止单票在弱势行情中阴跌扛单；同时加宽突破确认确认门槛（`confirm_buffer` = 1.3x），规避弱势行情中频发的假突破。
   * **正常大势**：积极拓宽低吸区宽度（`zone_width` = 1.2x），避免低吸区过窄导致强势股踏空；同时收紧突破确认价（`confirm_buffer` = 0.8x），提升在健康市场中的突破敏感度。

2. **理论微调 (Theory Finetuning)**：
   * 触发缠论强势上攻段或三买信号时：`zone_width` 额外放大 1.15x（拓宽低吸吸纳容错）。
   * 触发缠论回调或顶背驰时：`zone_width` 额外压缩 0.90x（紧贴防守线）。
   * 触发威科夫 Spring 弹簧或看多量价背离时：`confirm_buffer` 额外收紧 0.70x（大幅提高对低吸确认的可达性）。
   * 动量强势（bullish + $\ge 65$）时：`space_threshold`（空间不足过滤门槛）缩窄 0.80x（激进买入）。
   * 动量弱势（bearish + $\le 35$）时：`space_threshold` 放大 1.30x（保守防守）。

#### 5.7.2 动态价格闭环
以上 4 维系数完美嵌入 `build_structure_context()`，使得算出来的低吸区上/下沿、止损线、确认价及突破过滤阈值均具备全天候数学鲁棒性，彻底打通了大势-多维理论-单票决策的数据闭环。

---

## 六、Signal Contract 协议层与信号生命周期 V2

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

### 6.4 信号生命周期 V2 与 UUID 强一致去重 (Signal Lifecycle V2)

在 Trader 2.2 中，为了杜绝由于跨组件时区偏差、多进程并发写入、以及大盘跳空等各种边缘场景引起的信号重复生成或冗余结算，引入了严密的信号生命周期 V2 去重防重架构。

#### 6.4.1 make_signal_id 统一 UUID 生成算法
UUID 生成规则基于强一致的 deterministic SHA256 算法，针对 4 个核心业务要素进行归一化后计算哈希值：
1. **证券代码归一化 (`_normalize_symbol`)**：支持 `688248.SH`、`SH688248`、`688248` 等各种杂乱输入，统一映射为带点后缀标准格式 `CODE.MARKET` 并大写。
2. **交易日期归一化 (`_norm_date`)**：将 `2025/5/2`、`20250502`、`2025-05-02T14:30:00` 等日期形式统一转换为零填充的 `YYYY-MM-DD` 格式。
3. **信号类型归一化 (`_normalize_signal_type`)**：自动将各类旧版中文状态名（如"低吸观察"）或非标准缩写映射为 v1 英文标准字段（如 `low_buy_watch`）。
4. **触发价格归一化 (`_safe_price` & `f"{price:.2f}"`)**：无论是数值型还是内嵌字典类型中的价格信息，统一提取并格式化为标准双精度字符串。

哈希计算公式：
$$\text{UUID} = \text{SHA256}(\text{normalized\_symbol} \parallel \text{normalized\_date} \parallel \text{normalized\_type} \parallel \text{price\_2decimals}) \text{[:16]}$$
返回 16 位确定性 Hex 字符（48 bit 熵），全局唯一，不随环境时区或系统时间改变。

#### 6.4.2 严格 UUID 双向去重与防重结算
* **加载/检索拦截 (Deduplication)**：在 `check_recent()`、`backfill()` 以及 `log_safe()` 等核心信号读写节点，系统在加载和保存信号时会自动根据新 UUID (及旧 `signal_id_md5` 兼容字段) 在已存在缓存中进行双向检测。只要 UUID 重合，直接幂等丢弃，杜绝二次充填。
* **状态机转换卫语句**：信号状态划分为 `active` (活跃)、`completed` (已结算)、`expired` (已过期)。注册 `_FORBIDDEN_TRANSITIONS` 状态转换黑名单，禁止将已完成/已过期的信号逆向激活。

#### 6.4.3 原子临时写与 fsync 落盘安全
为彻底规避系统崩溃或中断造成的 JSONL 写入残缺甚至文件损坏（Corruption），所有信号持久化变更 (`fill`、`fill_by_target`) 均遵循严密的落盘原则：
1. 先向临时文件 `*.jsonl.tmp` 写入完整序列化内容。
2. 调用 `os.fsync(fd)` 强制操作系统硬件将缓冲区数据刷新落盘。
3. 通过操作系统原子指令 `os.replace()` 替代原始文件，保证文件写操作的绝对完整与强事务级安全。

#### 6.4.4 信号平滑迁移工具 (`signal_migration_tool.py`)
为实现平滑升级，Trader 2.2 提供了一键历史老数据迁移脚本。该 CLI 工具能够自动检索用户根目录 `~/.trader/` 下的 `signals.jsonl` 与 `signal_results.jsonl`，将旧有 MD5 短哈希无损升级为新版 UUID 长 Hex 标识并清理重复记录，保证历史准确率数据无缝流转至新系统。

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
│   ├── 02-候选逻辑-candidate/ (candidate_core.py, chan_core.py, wyckoff_core.py,
│   │                           hmm_regime.py, bayesian_fusion.py, volume_profile.py) ← 2.3新增
│   ├── 03-输出校验-contracts/ (signal_contract.py, signal_store.py)
│   ├── scripts/ (calibrator.py, market_env.py, pipeline.py, signal_tracker.py,
│   │            self_calibration.py, signal_migration_tool.py) ← 2.3/2.2新增
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

## 十五、[2.3新增] 高级统计模块深度技术文档

### 15.1 HMM 大势状态检测器 (`hmm_regime.py`)

**算法**：纯 numpy 实现高斯观测分布隐马尔可夫模型（HMM），无任何外部重量级框架依赖。

**流程**：
1. 输入：最近 60~200 个交易日的大盘指数日收益率序列 `List[float]`
2. Baum-Welch EM 迭代（最多 50 次，收敛阈值 1e-4）学习三组高斯参数（μ, σ）和状态转移矩阵 A
3. Viterbi log-domain 解码输出最可能隐状态序列
4. 按 μ 排序确保状态语义稳定：状态 0 = 低波上涨(Bull)，1 = 高波下跌(Bear)，2 = 宽幅震荡(Range)

**关键函数**：

| 函数 | 说明 |
|-----|-----|
| `detect_regime(returns)` | 一站式检测，返回 state_id/label/confidence/mu/sigma |
| `regime_to_multiplier(result)` | 将状态转为 zone_width/confirm_buffer/stop_buffer 调节系数 |
| `HMMRegimeDetector.fit(returns)` | 独立拟合 |
| `HMMRegimeDetector.predict(returns)` | Viterbi 解码 |

**低置信度保护**：confidence < 0.6 时系数自动向中性 1.0 线性收敛，防止模型噪音放大错误。

---

### 15.2 贝叶斯概率决策融合网络 (`bayesian_fusion.py`)

**触发条件**：环境变量 `BAYESIAN_FUSION=true` 时激活，默认关闭（保持 2.2 场景权重行为）。

**算法**：贝叶斯乘积规则（Naïve Bayes Product Rule）融合三路专家似然。

```
P(action | chan, mom, wyk, regime) ∝ L(chan) × L(mom) × L(wyk)
```

- 每个专家的似然 `L` 由 `direction × confidence × regime_prior_matrix` 计算
- 先验矩阵维度：`[regime(3)] × [direction(3)] × [action(5)]`，按领域知识初始化
- 置信度通过 `blended = confidence × base + (1-confidence) × uniform` 调节，高置信度时向极端动作靠拢
- 输出：5 个动作的后验概率向量，取 argmax 作为最优动作

**动作标签**（按 action_score 排序）：空仓观望(-1.0) / 减仓防守(-0.5) / 持仓观察(0.0) / 半仓试多(0.5) / 加仓做多(1.0)

**关键函数**：`bayesian_merge(chan_signal, momentum_signal, wyckoff_signal, regime_state)`

---

### 15.3 日内成交量分布分析器 (`volume_profile.py`)

**算法**：将分钟 K 线（5m/15m）成交量按价格区间均匀分配到 n_bins（默认 50）个价格网格，计算：

- **POC（Point of Control）**：成交量最大的价格档位，即日内主力成本最密集区
- **Value Area（VA）**：从 POC 向两侧双向扩展，直到累计覆盖 70% 总成交量的价格区间

**边界判断函数**：

| 函数 | 说明 |
|-----|-----|
| `in_value_area(price)` | 价格是否在价值区内 |
| `breakout_of_va(price)` | 价格是否突破 VA 上沿（强势信号）|
| `breakdown_of_va(price)` | 价格是否跌破 VA 下沿（偏空信号）|
| `above_poc(price)` | 价格是否高于 POC |

**assess_vp_breakout()**：综合评估返回 `vp_signal`（va_breakout / above_poc / va_support / below_va）和 `vp_confidence`（0~1）。

---

### 15.4 离线参数自校准器 (`scripts/self_calibration.py`)

**设计原则**：完全离线，非交易时段运行，零实盘干扰。

**流程**：
1. 读取 `~/.trader/signals.jsonl` 历史信号和 `~/.trader/signal_results.jsonl` 结算结果。
2. 历史大势对齐：拉取中证 1000 指数最近一年历史日线，调用 HMM 状态检测器动态为每一个历史信号标定当日所处的 HMM 大势状态（`bull` 上涨 / `bear` 下跌 / `range` 震荡）。
3. 分桶搜优：在 `global`（全局）、`bull`、`bear`、`range` 四个大势分组下，并行执行 150 次随机搜索寻优：
   - `zone_width` ∈ [0.90, 1.25]
   - `confirm_buffer` ∈ [0.70, 1.30]
   - `stop_buffer` ∈ [0.70, 1.00]
4. Blended 盈亏比加权：仿真估算不再采用单一胜率。统计模拟交易的总盈利 `total_gains` 与总亏损 `total_losses`，计算综合评分：
   `Score = WinRate * (total_gains + 0.5) / (total_losses + 0.5)`
   确保参数在保障“高胜率”的同时，具备“极佳盈亏比”。
5. 将最优的嵌套参数结构写入 `~/.trader/calibrated_params.json`。

**调用方式**：
```bash
# 盘后或周末手动运行自校准
python3 02-共享模块-shared/scripts/self_calibration.py

# 在代码中读取已校准参数（支持多层降级，消费时由 structure_core.py 根据当前 hmm_regime 动态匹配）
from self_calibration import load_calibrated_params
params = load_calibrated_params()  # 返回 { "version": "2.3", "params": { "global": {...}, "bull": {...}, "bear": {...}, "range": {...} } }
```


---

### 15.5 四大高级模块的生产环境集成架构 (`market_env.py` / `fusion_core.py` / `structure_core.py` / `decision_core.py`)

在 Trader 2.3 中，四大高级统计模块并非孤立运作，而是作为一套闭环网络在交易决策核心流程中无缝拼合与相互赋能：

1. **HMM 与 MA 大势的“前瞻融合”**：
   - 入口在 `market_env.py` 中。`_fetch_index_data()` 升级为拉取最近 90 个交易日的大盘指数日 K 线。
   - `assess()` 计算最近 90 日指数收益率序列，喂入 `hmm_regime.detect_regime()` 获得高斯隐状态。
   - 传统均线判定 `level` 时，若 HMM 产生高置信度前瞻状态（`confidence >= 0.75`），如 HMM 为 `bear`（熊市）而均线为 `正常`，将直接前瞻性地将 `level` 修正为 `偏弱`。从而让所有传统风控模块自动获得前瞻性风控防守能力！

2. **HMM 与贝叶斯概率融合的“决策升级”**：
   - 融合入口 `fusion_core.py` 中的 `merge_decisions()` 新增 `hmm_regime` 接收参数，并直接在融合结果中向下游广播该字段。
   - 当环境变量 `BAYESIAN_FUSION=true` 时，`bayesian_fusion.py` 一键接管传统基于固定权重的分类映射决策。它消费标准化后的缠论、动能、威科夫专家信号，根据当前 HMM 解码的 `hmm_regime`（`bull`/`bear`/`range`）动态调整先验条件概率矩阵，利用贝叶斯乘积法则计算 5 个动作的后验分布，决策出最优 action 与置信度。

3. **三层叠加的自适应“自校准+前瞻”微调**：
   - `structure_core.py` 的参数微调器 `_theory_multipliers()` 被彻底重构，升级为极其优美的三层叠加结构：
     - **层-0（基准校准）**：读取由盘后自校准器生成的 `~/.trader/calibrated_params.json`，作为低吸/确认/止损参数的寻优基准倍率。
     - **层-1（均线大盘）**：根据均线大势级别 `level` 进行乘法调节。
     - **层-2（HMM前瞻）**：直接从 `fusion_result` 的 `"hmm_regime"` 中消费前瞻隐状态，进行 50% 权重叠加的精细化调制。这不仅规避了重复抓包计算的高耗时，亦实现了极致的低延迟和防空转韧性。
     - **层-3（理论微调）**：根据具体缠论上攻/下跌笔、威科夫吸筹、动能状态等信号进行 10%~30% 的最终浮动。

4. **日内成交量分布与突破确认验证**：
   - 日内量价分布 `volume_profile.py` 提供的突破评估算法 `assess_vp_breakout()` 已经与 `decision_core.py` 的 `_check_theory_breakout` 精准对接。
   - 在缠论/威科夫发出突破买入（突破前高/三买等）动作时，系统自动检查当前个股日内价格是否处于价值区间下沿（`below_va`）。若价格跳空低于 VA 下沿，量价结构说明不支持，则一票否决此次突破确认，有效扼杀频繁的“假突破”。

这套拼图式的集成链路成功实现了从大势前瞻防守，到联合概率最优决策，再到自适应参数校准，以及日内微观量价拦截的全方位立体交易决策辅助。

---

## 十六、规划与路线图

| 规划 | 说明 | 优先级 | 状态 |
|------ | ------ | ------ | ------ |
| ✅ JSON Schema 化 Output Contract | `trader_shared/schema/v1.py` | P0 | 已完成 |
| ✅ 统一数据层 `DataProvider` 接口 | `trader_shared/data_provider.py` | P0 | 已完成 |
| ✅ Signal Contract v2 + HA 行情管线 | 2.2 核心重构 | P0 | 已完成 |
| ✅ HMM 大势检测 + 贝叶斯融合 | `hmm_regime.py` + `bayesian_fusion.py` | P1 | 已完成(2.3) |
| ✅ 日内量价分布 + 离线自校准 | `volume_profile.py` + `self_calibration.py` | P1 | 已完成(2.3) |
| Tick 订单流分析 | 盘口十档主动买卖追踪，提升日内时机精度 | P2 | 未开始 |
| 行业板块共振管理 | 轮动时加入板块强弱因子 | P2 | 未开始 |
| App/小程序前端面板 | Markdown → 可视化 Chart 面板 | P3 | 未开始 |
| `t0-trader` signal type 扩展 | 增加 `pilot_entry` 试仓等 | P3 | 未开始 |
