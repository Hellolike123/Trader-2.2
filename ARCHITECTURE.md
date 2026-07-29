# ARCHITECTURE.md — Trader3.0 系统架构

> **最后更新**：2026-07-29 | **基于**：`trader_shared/` 代码 + 目标架构法源  
> **产品方向法源**：`docs/designs/resonance-and-orchestration.md`  
> **改代码地图**：[`AGENTS.md`](AGENTS.md)「改代码去哪」（优先于本文行数表）

---

## 1. 架构概览

Trader3.0 采用**分层 + 编排总管 + 插件化**设计。  
**目标主路径**：数据 → 分析（意见卡）→ 岗位共振 / 原典策略 / 纪律 → 多场景展示（单票、T0、池、仓位）。  
厚 fusion 加权为过渡能力，不作长期总司令（详见法源文档）。

```
┌──────────────────────────────────────────────────────────┐
│ 入口层      │ final_report / final_pool(薄) / t0 / review
├──────────────────────────────────────────────────────────┤
│ 编排层      │ report_builder · report_pipeline/*_stage
│             │ pool_cmds · t0_run/monitor（引擎在 shared）
├──────────────────────────────────────────────────────────┤
│ 分析层      │ cores/plugins → analysis_cards
│ 共振/策略   │ resonance · strategy packs · 六闸 match
│ 决策/纪律   │ mistery_gate / chan_discipline（只收紧）
│ Fusion      │ 生产 = cards；classic 仅对照（deprecated）
├──────────────────────────────────────────────────────────┤
│ 数据层      │ market_types SSOT → data_provider / light_data
├──────────────────────────────────────────────────────────┤
│ 展示层      │ report_renderer/short_midline · T0 结构卡 · 池面板
└──────────────────────────────────────────────────────────┘
```

**核心设计决策**（ADR 文档）：
- ADR-001: trader_shared 收编为真 Python 库（消除向上依赖）
- ADR-002: build_report 统一经 PluginRegistry 路由
- ADR-003: 分析逻辑与 CLI 分离（run_analysis.py → report_builder.py）
- ADR-003b: 领域层与展示层分离（report_builder vs report_renderer）
- 2026-07: `report_pipeline/` 分包；t0/review 引擎下沉；`pool_cmds/` 拆分

---

## 2. trader_shared 模块清单

### 2.1 核心基础设施（9 文件）

| 模块 | 行数 | 角色 |
|------|------|------|
| `__init__.py` | 93 | 公开 API（re-export 27 个符号） |
| `interfaces.py` | 110 | 抽象接口：`DataFetcher`(ABC)、`IndicatorPlugin`(ABC) |
| `models.py` | 224 | TypedDict：BarData、QuoteData、SignalRecord 等 15 类型 |
| `config.py` | ~450 | 全局常量池：`LOOKBACK_DAYS=370`、`WEEKLY_LOOKBACK_BARS=260`、缠论 conf 门槛等 |
| `light_data.py` | 1676 | 底层数据引擎：腾讯/新浪/mootdx/akshare 四源 fallback |
| `data_provider.py` | ~800 | 统一 DataProvider；周线默认 `WEEKLY_LOOKBACK_BARS` |
| `cache_utils.py` | 623 | 文件缓存（fcntl 锁 + 原子写 + 共享线程池） |
| `async_utils.py` | 276 | 并发控制 |
| `_logging.py` | - | 日志工厂 |

### 2.2 策略专家层（已拆分）

#### 缠论模块（6 文件，合计 ~4000 行）
| 模块 | 行数 | 角色 |
|------|------|------|
| `chan_core.py` | 617 | 主引擎：chanlun_strategy() / chanlun_strategy_midline() |
| `chan_geometry.py` | 821 | 几何计算：笔识别、中枢构建、背驰 |
| `chan_structure.py` | 872 | 结构分析：类型判定、买卖点 |
| `chan_discipline.py` | 936 | 纪律门控：回踩区/mid_view/资金新开否决 |
| `realtime_chan.py` | - | T0 实时增量 diff |
| `expma_status.py` | 327 | EXPMA 状态打分（10 分制） |

#### 威科夫模块（5 文件）
| 模块 | 行数 | 角色 |
|------|------|------|
| `wyckoff_core.py` | ~750+ | 主引擎：wyckoff_strategy() / midline / score / format_oneline |
| `wyckoff_events.py` | ~1800+ | 事件检测：Spring/UT/BC/SOW/SOS/PS/UTAD 等 |
| `wyckoff_phase.py` | ~440+ | 阶段状态机 + 持久化转移 |
| `wyckoff_view.py` | ~250 | **A 档出口**：`WyckoffStateView` + `to_wyckoff_state_view()` |
| `main_force.py` | 226 | 主力资金阶段检测（另线，非威科夫原典 A–E） |

契约文档：`docs/designs/wyckoff-state-view.md`。分层演进方向：特征→原子事件→原典事件→phase→View（B 档未做）。

#### 阶段判定模块（6 文件，合计 ~2700 行）
| 模块 | 行数 | 角色 |
|------|------|------|
| `stage_positioning.py` | 692 | 四阶段模型入口 |
| `stage_detect.py` | 999 | 阶段检测核心引擎 |
| `stage_position.py` | 692 | 阶段仓位计算 |
| `stage_state.py` | 190 | 阶段状态管理 |
| `stage_stops.py` | 454 | 阶段止损计算 |
| `pattern_core.py` | 417 | 形态识别核心 |

### 2.3 融合决策层（3 文件）

| 模块 | 行数 | 角色 |
|------|------|------|
| `fusion_core.py` | ~1100+ | merge_decisions() — 信号标准化+加权+冲突消解；**默认 cards** |
| `fusion_regime.py` | ~220 | Regime 权重（yaml + 兜底）+ score_to_action()；很差不字面「暂不碰」 |
| `bayesian_fusion.py` | 230 | 贝叶斯融合（可选，BAYESIAN_FUSION=true 激活） |

### 2.4 报告系统层（编排 + pipeline + 渲染）

| 模块 | 角色 |
|------|------|
| `report_builder.py` | `build_report()` 只排队；用 `StageContext` 接阶段结果 |
| `report_pipeline/` | `*_stage.py` + `attach_*.py`（短中线/纪律/决策挂接） |
| `report_core.py` | 渲染入口；默认委托 `report_renderer/short_midline.py` |
| `report_renderer/short_midline.py` | **短中线双轨文案真相**（改输出先改这里） |
| `report_presentation.py` | 兼容/辅助展示（非主改路径） |
| `conclusion_block.py` | 中短线看法/出手；`_build_wave_label` |
| `market_types.py` | `Security` / `MarketSnapshot` SSOT |
| `main_force_output.py` | 主力资金输出格式化 |

### 2.5 其他重要模块

| 模块 | 角色 |
|------|------|
| `signal_schema.py` | SignalTier 枚举（16 个信号层级） |
| `signal_core.py` | build_signal() — 信号构建 |
| `signal_store.py` | 信号持久化（signals.jsonl） |
| `signal_tracker.py` | 信号跟踪/日志 |
| `plugin_registry.py` | 插件注册表（自动发现 + 管理生命周期） |
| `vpf_core.py` | 价量资金专家（融合第三席） |
| `momentum_core.py` | 动量分析引擎 |
| `volume_price.py` | 量价背离检测 |
| `chip_core.py` | 筹码分析入口 |
| `structure_core.py` | 多周期关键价位检测 |
| `key_prices.py` | 短线关键价构建 |
| `mid_key_prices.py` | 中线关键价薄封装 → midline_structure |
| `midline_structure.py` | 周线独立引擎（weekly_v1：笔/段/摆动） |
| `formulas.md` | 缠论/背驰/买卖点公式权威说明（与代码同目录） |
| `mistery_gate.py` | 纪律门控 |
| `combo_strategy.py` | 组合共振（暂未接入报告） |
| `box_detect.py` | 箱体检测（暂未接入报告） |
| `multi_timeframe_resonance.py` | 月/周/日/60m 共振（13 分制） |
| `testing/mock_seam.py` | 确定性测试接缝 |

---

## 3. 模块依赖关系

### 3.1 核心依赖图

```
trader_shared/__init__.py (公开 API)
  ├── report_builder.py
  │   ├── report_pipeline/ (context/fusion/structure/chip/assemble + attach_*)
  │   ├── data_provider.py → market_types + light_data / cache / tushare
  │   ├── plugin_registry.py → plugins/
  │   ├── fusion_core.py (cards) + analysis/fusion_card_signals.py
  │   ├── structure_core / chip_core / stage_positioning
  │   ├── key_prices / mid_key_prices / midline_structure
  │   └── mistery_gate / chan_discipline / conclusion_block
  │
  ├── report_core.py → report_renderer/short_midline.py
  ├── t0_*.py / review_*.py / portfolio_*.py（skill 包内为 shim）
  └── 选股池实现在 packages/trader/scripts/pool_cmds/
```

### 3.2 接口抽象与实现

```
interfaces.py
  ├── DataFetcher (ABC) ← fetchers.py (TencentFetcher / SinaFetcher / MockFetcher)
  ├── IndicatorPlugin (ABC) ← plugins/ (5 个插件)
  └── DataProvider (Protocol) ← data_provider.py (UnifiedProvider / TushareProvider)
```

### 3.3 融合层三席

```
merge_decisions()
  ├── 第一席: chan_result → _chan_to_signal() (缠论信号标准化)
  ├── 第二席: momentum_result → _momentum_to_signal() (动量信号标准化)
  └── 第三席: vpf_result → vpf_core.build_vpf_signal() (价量资金信号)
```

---

## 4. 插件架构

### 4.1 设计模式

自动发现 + 注册表模式（importlib + pkgutil 扫描）：

```
PluginRegistry (单例)
  ├── _auto_register() → pkgutil.iter_modules → inspect.getmembers
  │   → 发现所有 IndicatorPlugin 的非抽象子类
  │
  ├── analyze_all() → 遍历所有已注册插件调用 analyze()
  │   ├── decision_names: chanlun / momentum / wyckoff (参与融合)
  │   └── display_names: supertrend / vwap (仅展示)
```

### 4.2 插件分类

| 插件 | 类型 | 权重 | 融合 |
|------|------|------|------|
| ChanlunPlugin | 决策 | 0.45 | 第一席 |
| MomentumPlugin | 决策 | 0.30 | 第二席 |
| WyckoffPlugin | 决策 | 0.35 | 日线已退出（VPF 替代） |
| SupertrendPlugin | 展示 | 0.0 | 否 |
| VwapPlugin | 展示 | 0.0 | 否 |

---

## 5. 数据流详情

### 5.1 一条分析的完整数据流

```
target="南网科技"
  │
  ▼
[1] data_provider.load_market_snapshot(target, days=370)
    → Security + quote + daily_bars + weekly_bars + monthly_bars + bars_5m
    → extend_fundamental (股东/EPS) + extend_sentiment (解禁/热度)
    → extend_margin (融资融券) + extend_northbound (北向)
    → extend_sector (板块) + extend_concept (概念)
    → fund_flow (资金流向)
  │
  ▼
[2] PluginRegistry.analyze_all(midline=True)
    → chanlun: buy_points/sell_points/divergence/trend_label
    → momentum: score/direction/signals
    → wyckoff: spring/upthrust/divergence/phase
    → chanlun_midline (周线) + wyckoff_midline (周线)
  │
  ▼
[3] fusion_core.merge_decisions(chan, momentum, vpf, regime)
    处理: 信号标准化 → 场景权重 → 冲突消解 → 加权 → 风控否决
    输出: action / confidence / weighted_score / signals_detail
  │
  ▼
[4] 结构/筹码/阶段分析
    structure_core → support/resistance/confirm/stop/take
    chip_core → 筹码分布/搬家
    stage_positioning → 蓄势/主升/派发/衰退
  │
  ▼
[5] 纪律门控 (mistery_gate + chan_discipline → merge)
    → allow_new_entry / action / suggested_pct_cap / invalidation
  │
  ▼
[6] conclusion_block → 中线看法/短线看法/出手/原因
  │
  ▼
[7] 组装 report dict (100+ 字段) → render_short_midline(report) → Markdown
```

---

## 6. 数据模型（关键 TypedDict）

| 类型 | 用途 | 文件 |
|------|------|------|
| `BarData` | 统一 K 线行 | models.py |
| `QuoteData` | 实时行情快照 | models.py |
| `CandidateLevels` | 候选交易区间 | models.py |
| `CandidateSignal` | 候选信号 | models.py |
| `SignalRecord` | 信号协议 v1 | models.py |
| `ChanlunSignal` | 缠论信号 | models.py |
| `SignalTier` | 信号层级枚举（16 值） | signal_schema.py |

---

## 7. 配置系统

`trader_shared/config.py`（~400 行）是**唯一配置来源**。

类别：
- 均线周期：MA_PERIODS / MA_WEIGHTS
- ATR 阈值：ATR_VERY_HIGH / ATR_HIGH / ATR_MODERATE
- 盈亏比门槛：MIN_RISK_REWARD / IDEAL_RISK_REWARD
- 威科夫参数：WYCKOFF_DIVERGENCE_BARS / WYCKOFF_SPRING_THRESHOLD 等 40+ 常量
- 仓位管理：KELLY_MAX_TOTAL_POSITIONS / MAX_SINGLE_POSITION_PCT
- 三关评分：ADMISSION_SCORE_EXECUTE / ADMISSION_SCORE_OBSERVE

外置配置：`trader_shared/config/fusion_regime_weights.yaml`（Regime 权重矩阵）

---

## 8. 测试架构

### 8.1 测试分类

| 类型 | 位置 | 数量 | CI |
|------|------|------|------|
| 单元测试 | `02-共享模块-shared/tests/test_*.py` | ~60 | 门禁 |
| 等价性测试 | `test_*_equivalence.py` / `test_*_split_equivalence.py` | 6 | 门禁 |
| Golden 闸门 | `test_golden_diff_gate.py` | 1 | 门禁 |
| 集成测试（离线 seam） | `test_build_report_golden.py` | 1 | 门禁 |
| 网络依赖测试 | `test_tushare_integration.py` 等 | ~10 | 排除 |
| Benchmark | `tests/benchmark/` | 3 | 手动 |

### 8.2 mock_seam 使用

```python
from trader_shared.testing.mock_seam import apply_seam, render_under_seam

def test_xxx(monkeypatch):
    apply_seam(monkeypatch)  # 堵所有网络泄漏点
    # ... 跑 build_report / render_markdown ...
```

---

## 9. 扩展方式

### 新增分析策略
1. 创建 `trader_shared/X_core.py`（核心算法）
2. 创建 `trader_shared/plugins/X_plugin.py`（Plugin 包装）
3. 在 `fusion_core.py` 新增信号标准化函数
4. Plugin 自动发现无需手动注册

### 新增报告模板
1. 在 `trader_shared/report_renderer/` 下创建渲染器
2. 在 `report_core.py` 的 `render_single()` 中添加分支

### 新增数据源
1. 实现 `DataFetcher` 接口
2. 在 `data_provider.py` 工厂函数中注册

---

*此文档基于 2026-07-14 代码状态。任何架构变更必须同步更新。*
