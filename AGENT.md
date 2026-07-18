# AGENT.md — Trader3.0 AI Agent 开发宪法

> **读者**：所有进入本项目的 AI Agent。
> **目的**：仅通过阅读本文档，Agent 即可理解项目全貌、掌握开发规范、独立继续开发。
> **优先级**：本文档是项目最高规范。任何 Agent 必须先读本文档再动手。

---

## 0. Agent 的双重身份

本项目 Agent 有**两个角色**，进入项目后按场景切换：

### A. 分析师（回答用户"这只票怎么样"）

用户问股票分析 → 调脚本拿报告，不手写。**标准三步流水线**：

```
Step 1: 调 markdown（优先）
  python scripts/final_report.py --target <NAME> --output markdown
  成功 → 直接输出报告，结束。
  失败 → 进入 Step 2。

Step 2: 调 JSON（fallback，仅 markdown 失败时）
  python scripts/final_report.py --target <NAME> --output json
  读返回的 dict，参考 §0.1 核心字段解读。

Step 3: 输出
  使用脚本已渲染的 markdown。不手写 Markdown。
```

#### 渲染优先原则
- **优先用 `--output markdown`**（脚本渲染好的完整报告）
- **禁止手写 Markdown**（脚本能输出 markdown 时，绝不从 JSON 手动拼）
- 仅当 markdown 渲染失败 + JSON 可用时，才从 JSON 字段构建

#### 三道 Inversion Gate（分析师输出前必须通过）

**GATE 1 — 数据完备度**：
- `data_status=full` → 正常分析
- `data_status=partial` → 输出开头标注 `⚠️ 数据不完整，分析可能不准`
- `data_status=degraded` → 仅输出基础行情，不做深度分析

**GATE 2 — 信号矛盾检测**（以下矛盾必须说明，不得隐藏）：
- `major_stage=主升` + `theory_status=暂不碰` → 说明矛盾
- `weighted_score > 0.3` + `theory_status=暂不碰` → 说明矛盾
- `major_stage=衰退` + `weighted_score > 0.3` → 以衰退为准
- `major_stage=派发` + `weighted_score > 0.25` → 以派发为准
- `data_status=partial` + 所有信号一致 → 加前缀警告

**GATE 3 — 方向判断铁律**：
- `weighted_score` 正 = 多方，负 = 空方。**唯一方向依据**
- 禁止用 `fusion.action` 字符串字面意思推断方向
- `confidence < 0.3` → 降级：`信号弱，建议轻仓`
- `disagreement > 1` → 提示：`信号有分歧，建议谨慎`
- `regime=很差` → 权重全 0；若 |score|≈0 则 **强制偏空** `weighted_score=-0.5` → 动作多为「空仓/止损」（**不是**字面「暂不碰」一票否决；见 `fusion_core` 4b + `score_to_action` 注释）
- `regime=偏弱` → 正阈值右移 +0.10，买入建议更难触发；展示层宜降一档

#### 绝对优先级（冲突时逐级裁决）
1. `regime="很差"` → 融合偏空（权重 0 + 默认 score=-0.5 → 空仓侧动作；最高）
2. `major_stage=衰退` → 不参与
3. `major_stage=派发` → 不加仓
4. `weighted_score` > `major_stage` > `theory_status`（默认）

#### §0.1 核心字段速查（JSON fallback 时用）

| 字段 | 类型 | 含义 |
|------|------|------|
| `current` / `change_pct` | float | 现价 / 涨跌幅 |
| `major_stage` | str | 四阶段（蓄势/主升/派发/衰退） |
| `short_term_momentum` | str | 短期动能 |
| `fusion.weighted_score` | float | **方向唯一依据** (-1~+1) |
| `fusion.action` / `confidence` / `regime` | — | 融合动作/置信/大盘 |
| `fusion.signals_detail` | dict | 三评委原始信号（chan/momentum/vpf） |
| `conclusion` | dict | 中线/短线看法、出手、原因 |
| `key_prices` / `mid_key_prices` | dict | 短/中线关键价 |
| `discipline` | dict | 纪律：entry_line、caps、invalidation、allow_new_entry |
| `support` / `confirm` / `stop` | float | 结构位 |
| `suggested_pct` | int | 建议仓位%（已被纪律 cap） |
| `data_status` | str | full / partial / degraded |
| `chanlun_midline` / `wyckoff_midline` | any | 周线理论（禁止回退日线） |
| `WyckoffStateView`（可选） | TypedDict | 威科夫统一出口；`to_wyckoff_state_view(wyckoff_midline)`，见 `wyckoff_view.py` |
| `market_env` | dict | 大盘环境（level + change_pct + freshness） |

### B. 开发者（改代码/加功能）

见 §4 标准开发流程 + §5 速查表。

---

## 1. 项目是什么

Trader3.0 是一个 **A 股量化分析系统**。输入一只 A 股代码 → 输出一份多维度分析报告（中线 + 短线双轨）。

**核心能力**：
- 缠论（Chanlun）买卖点 + 背驰检测
- 威科夫（Wyckoff）阶段定位 + 事件检测
- 价量资金（VPF）分析
- 动量 + MACD/RSI/OBV 综合评分
- 筹码分布 + 搬家监测
- 四阶段模型（蓄势/主升/派发/衰退）
- 三评委融合决策（chan/momentum/vpf）
- 纪律门控（出手/仓位/失效）
- 短中线双轨 Markdown 报告

**技术栈**：Python 3.11+ | 无外部 Web 框架 | 数据源：腾讯/新浪/mootdx/akshare/Tushare

---

## 2. 项目目录结构

```
Trader3.0/
├── AGENT.md                          ← 你正在读的文件（最高规范）
├── README.md / ARCHITECTURE.md / BUSINESS.md
│
├── 02-共享模块-shared/               ← ★ 核心共享库（所有代码的真实来源）
│   └── trader_shared/               ← Python 包（83 个 .py 文件）
│       ├── __init__.py              ← 公开 API
│       ├── report_builder.py        ← ★ build_report() 总编排器（1694 行）
│       ├── report_core.py           ← 报告渲染核心（1306 行）
│       ├── report_presentation.py   ← 展示层（1304 行，纯展示/无业务逻辑）
│       ├── fusion_core.py           ← ★ merge_decisions() 融合层（1033 行）
│       ├── fusion_regime.py         ← 大盘环境权重
│       ├── data_provider.py         ← 统一数据入口
│       ├── plugin_registry.py       ← 插件注册表（自动发现）
│       ├── signal_schema.py         ← SignalTier 枚举
│       ├── cache_utils.py           ← 文件缓存（fcntl 锁 + 原子写）
│       ├── config.py                ← 全局可调参数（374 行 / 100+ 常量）
│       ├── interfaces.py            ← DataFetcher / IndicatorPlugin 抽象接口
│       ├── models.py                ← TypedDict 数据模型
│       │
│       ├── plugins/                 ← 分析插件（自动发现，无需手动注册）
│       │   ├── chan_plugin.py       ← 缠论（决策；正常 0.30 / 偏弱 0.50）
│       │   ├── momentum_plugin.py   ← 动量（决策；正常 0.45 / 偏弱 0.15）
│       │   ├── wyckoff_plugin.py    ← 威科夫（日线已退出 fusion；中线周线展示）
│       │   ├── supertrend_plugin.py ← 展示型（display_only=True，不进融合）
│       │   └── vwap_plugin.py       ← 展示型（display_only=True，不进融合）
│       │
│       ├── schema/v1.py             ← 输出校验（禁用语 + 格式）
│       ├── testing/mock_seam.py     ← ★ 确定性 mock 接缝
│       └── config/fusion_regime_weights.yaml  ← Regime 权重矩阵
│
├── 01-功能包-packages/trader/scripts/  ← CLI 入口
│   ├── final_report.py              ← 单票分析
│   ├── final_pool.py               ← 选股池管理（2000 行）
│   ├── run_analysis.py             ← 分析执行器（207 行壳层）
│   └── pool_briefing.py            ← 日报分类
│
├── scripts/                         ← 项目级脚本
│   ├── run-gate-tests.sh            ← ★ CI 门禁（131 passed）
│   ├── golden_diff_gate.py          ← Golden 基线闸门
│   ├── git-hooks/pre-push           ← pre-push hook（版本化）
│   └── pack_all.py                  ← 打包发布
│
├── docs/                            ← 设计文档
│   ├── ADR-001/002/003-*.md         ← 架构决策记录
│   ├── README.md                    ← 文档总入口
│   ├── designs/                     ← 现行设计（含策略分层）
│   ├── architecture/                ← ADR + ci-gate
│   ├── plans/{active,done}/         ← 实施计划
│   ├── reviews/                     ← 审查归档
│   └── guide/                       ← 用户手册等
│
└── 02-共享模块-shared/tests/        ← 测试（70 个文件）
    ├── golden/                      ← Golden 基线
    └── fixtures/                    ← 测试 fixture
```

---

## 3. 核心架构

### 3.1 分层架构

```
┌─────────────────────────────────────────┐
│  Skill Layer           ← Agent ↔ Python 桥接
├─────────────────────────────────────────┤
│  CLI Layer             ← 命令行入口
├─────────────────────────────────────────┤
│  Domain Layer          ← build_report() 总编排器
│  ├─ Strategy Plugins   ← 缠论/动量/威科夫（自动发现）
│  ├─ Fusion Layer       ← 三评委加权 + 风控否决
│  ├─ Structure/Chip/Stage ← 结构/筹码/阶段分析
│  └─ Discipline/Gate    ← 纪律门控
├─────────────────────────────────────────┤
│  Data Layer            ← 统一数据入口
├─────────────────────────────────────────┤
│  Presentation Layer    ← 纯展示，无策略逻辑
└─────────────────────────────────────────┘
```

### 3.2 数据流（一条分析的全路径）

```
用户输入 target="002050"
  │
  ▼ final_report.py::main()
  ▼ report_builder.build_report(target)
  │
  ├─ [1] load_market_snapshot(target) → Security, quote, bars, fund_flow, extend_*
  ├─ [2] PluginRegistry.analyze_all() → chanlun, momentum, wyckoff results
  ├─ [3] merge_decisions(chan, momentum, vpf, regime) → weighted_score, action
  ├─ [4] structure_core + chip_core + stage_positioning → support/stop/stage
  ├─ [5] mistery_gate + chan_discipline → discipline
  ├─ [6] conclusion_block → 中线/短线看法/出手/原因
  └─ [7] 组装 report dict → render_short_midline() → Markdown
```

### 3.3 融合层三评委

```
第一席 chan     → _chan_to_signal()
                  信号层级：chan_buy_1/2/3, chan_sell_1/2/3, chan_top_div, chan_bottom_div
                  权重：正常 0.30 / 偏弱 0.50 / 很差 0
                  （权威源：config/fusion_regime_weights.yaml；内置兜底同值）

第二席 momentum  → _momentum_to_signal()
                  方向：+1(多) / 0(中性) / -1(空)
                  权重：正常 0.45 / 偏弱 0.15 / 很差 0
                  （正常大势动量占优；偏弱则缠论占优）

第三席 vpf       → vpf_core.build_vpf_signal()
                  信号层级：vpf_bearish_warning（主力净流出/天量滞涨）
                  权重：正常 0.25 / 偏弱 0.35 / 很差 0

公式：weighted_score = Σ(direction × confidence × weight)
映射：score_to_action() → 半仓试 / 增持 / 等转强观察 / 持股观望 / 减1/3 / 减仓 / 空仓/止损
很差：权重全 0 后若 |score|<0.01 → 强制 -0.5 → 空仓侧（非字面「暂不碰」）
```

### 3.4 设计原则（不可破坏）

| 原则 | 说明 | 违规示例 |
|------|------|----------|
| **领域-展示分离** | `report_presentation.py` 不含策略逻辑 | ❌ 展示层调 `chanlun_strategy()` |
| **展示型插件隔离** | `display_only=True` 的插件不进融合 | ❌ fusion_core 引用 supertrend |
| **禁止 print 打 stdout** | 生产代码用 `_logger.debug()` | ❌ `print()` 出现在 build_report 路径 |
| **等价性闸门** | 行为变更前必须过 golden diff gate | ❌ 改渲染格式不刷新 baseline |
| **禁止向上依赖** | trader_shared 不 import scripts/ | ❌ `from trader.scripts import ...` |
| **模块边界：箱体独立** | `box_detect.py` 是独立模块，暂不接入 report_builder，保留代码和测试以备后续 | ❌ 把箱体检测结果写进报告渲染 |
| **模块边界：威科夫周线** | 周线威科夫独占中线，数据不足直接 return insufficient（不回退日线） | ❌ 周线不足时 fallback 到日线 |
| **威科夫出口** | Agent/新代码优先 `to_wyckoff_state_view`；不把威科夫当 fusion 总大脑 | ❌ 从 analysis 里手抄 40 个 `*_signal` 拼叙事 |
| **周线根数** | 默认 `WEEKLY_LOOKBACK_BARS=260`，中线缠论/威科夫同用 | ❌ 仍按旧 80 周假设调试「笔数不足」 |
| **波段标签** | 仅 strokes&lt;3 写「笔数不足」；段少写「线段偏少/未成型」 | ❌ segments&lt;2 就报「笔数不足」 |

---

## 4. 标准开发流程

### Step 1: 阅读文档
```
必读：AGENT.md（本文）→ ARCHITECTURE.md → BUSINESS.md
文档导航：docs/README.md
按需：docs/designs/（策略分层见 strategy-roadmap-and-tests.md）
```

### Step 2: 理解需求
- 新增功能？修改 Bug？重构？
- 确认影响的模块和文件
- 如果是架构变更 → 先写设计文档到 `docs/designs/`

### Step 3: 输出开发方案
- 列出受影响的模块、文件
- 说明数据流变化
- 大改动开分支（`refactor/<name>` 或 `feat/<name>`）

### Step 4: 修改代码
- 遵守分层架构
- 展示层不改策略逻辑
- 新增功能走 Plugin 接口
- 不破坏等价性闸门基线

### Step 5: 自检
```bash
export PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts

# 1. Golden 闸门（行为无漂移）
python scripts/golden_diff_gate.py check

# 2. 全门禁
bash scripts/run-gate-tests.sh

# 3. 真票验证（至少跑一只）
python 01-功能包-packages/trader/scripts/final_report.py --target 002050 --output markdown
```

### Step 6: 更新文档
- 架构变更 → ARCHITECTURE.md
- 业务规则变更 → BUSINESS.md
- 新增设计决策 → `docs/designs/`
- 渲染格式变更 → 刷新 golden 基线：`python scripts/golden_diff_gate.py capture`

### Step 7: Commit & Push
```bash
git add <精确文件列表>     # ❌ 不要 git add --all（会带上用户的 .mimocode/.reasonix 等自有文件）
git commit -m "type: 简述" -m "详细说明"
git push                   # 自动触发 pre-push 门禁
```

Commit 类型：
- `fix`：Bug 修复
- `feat`：新功能
- `refactor`：重构（不改行为）
- `docs`：文档
- `test`：测试

---

## 5. 如何新增功能（含代码示例）

### 5.1 新增分析指标（插件）

**IndicatorPlugin 接口**（来自 `trader_shared/interfaces.py`）：
```python
class IndicatorPlugin(ABC):
    def name(self) -> str: ...             # 唯一标识，如 "my_indicator"
    def analyze(self, current, bars, change_pct, quote, weekly_bars=None) -> dict:
        # 返回 {"direction": ±1/0, "confidence": 0~1, "reason": "..."}
        ...
    def weight(self) -> float: ...         # 默认 1.0
```

**决策型插件**（进融合评分）：
```python
# 1. 在 plugins/ 下创建 my_plugin.py
from trader_shared.interfaces import IndicatorPlugin

class MyPlugin(IndicatorPlugin):
    def name(self) -> str: return "my_indicator"
    def weight(self) -> float: return 0.25

    def analyze(self, current, bars, change_pct, quote, weekly_bars=None) -> dict:
        # 你的分析逻辑
        return {"direction": 1, "confidence": 0.6, "reason": "示例信号"}

# 2. 在 fusion_core.py 新增信号标准化函数
def _my_to_signal(result: dict) -> dict:
    return {"direction": result["direction"], "confidence": result["confidence"], ...}

# 3. 在 merge_decisions() 中调用（参考 _chan_to_signal 的写法）
# 4. 加测试 → 跑门禁
```

**展示型插件**（不进融合，仅报告展示）：
```python
class MyDisplayPlugin(IndicatorPlugin):
    display_only: bool = True

    def name(self) -> str: return "my_display"
    def weight(self) -> float: return 0.0    # 零权重 = 不进融合

    def analyze(self, current, bars, change_pct, quote, weekly_bars=None) -> dict:
        return {"direction": 0, "confidence": 0.0, "value": 42.5, "reason": "展示数据"}
```

**无需手动注册**：PluginRegistry 用 importlib 自动扫描 `plugins/` 目录，新插件放进去即生效。

### 5.2 新增数据源

```python
# 1. 在 fetchers.py 新增 Fetcher 类
class MyFetcher(DataFetcher):
    @property
    def name(self) -> str: return "my_source"

    def fetch_quote(self, code: str) -> dict: ...
    def fetch_qfq_daily(self, code: str, days: int = 300) -> list[dict]: ...
    def fetch_kline(self, code: str, scale: str = "60", datalen: int = 60) -> list[dict]: ...

# 2. 在 data_provider.py 工厂函数中注册
```

### 5.3 新增报告模板

```python
# 1. 在 report_renderer/ 下创建新渲染器
# 2. 在 report_core.py 的 render_single() 中添加分支
# 3. 刷新 golden 基线
python scripts/golden_diff_gate.py capture
```

### 5.4 修改业务规则

```
1. 修改对应策略文件（chan_core / wyckoff_core / fusion_core 等）
2. python scripts/golden_diff_gate.py check  ← 确保无意外漂移
3. 用真票验证
4. 如有渲染变化 → python scripts/golden_diff_gate.py capture ← 刷新基线
5. 更新 BUSINESS.md
```

### 5.5 新增选股池功能

修改 `final_pool.py`，遵守三关筛选门控（阶段→评分→风控）。评分阈值在 `config.py`。

---

## 6. Skill 设计方法论（Google ADK 5 模式）

本项目 Skills 遵循 Google ADK 的 5 种 Skill 设计模式。编写或修改任何 skill 时，应先确定它属于哪种（或哪几种混合）模式。

### 5 种模式速查

| 模式 | 核心问题 | 结构 | 本项目示例 |
|------|----------|------|-----------|
| **Tool Wrapper** | 如何让 Agent 调用特定工具/API？ | SKILL.md 监听关键词 → 加载 `references/` 约定 → 按约定执行 | `coros-data-fetch`（包装 coros_api）、`trader-indicator-enhancement` |
| **Generator** | 如何生成一致的输出？ | `assets/` 存模板 + `references/` 存风格指南 → Agent 填空不改造结构 | `cycling-training-report`（HTML 报告模板） |
| **Reviewer** | 如何自动化审查？ | `references/` 存检查清单 → SKILL.md 存审查协议 → 输出按严重程度分组 | `review`（五层评分）、`google-skill-patterns` |
| **Inversion** | 如何先收集信息再执行？ | 阶段门控：`⛔ DO NOT proceed until all phases complete` | `trader`（GATE 1/2/3）、`review` |
| **Pipeline** | 如何组织多步骤工作流？ | `scripts/` 执行步骤 → SKILL.md 控制流转 → 每个步骤有显式完成条件 | `trader`（Step 1→2→3）、`t0` |

### 模式可以组合

本项目最常用的组合是 **Pipeline + Inversion + Generator**（trader、review、t0 都是这个组合）：
- Pipeline：定义步骤顺序
- Inversion：在每个步骤设门控（不通过不前进）
- Generator：最终输出按模板填充

### 编写 Skill 时的检查清单

1. 确定模式 → 按模式的标准结构组织目录（`assets/` / `references/` / `scripts/`）
2. Pipeline 模式 → 每个步骤以 `✅ Step N 完成条件：<可验证项>` 结尾
3. Inversion 模式 → 用 `⛔ STOP. DO NOT OUTPUT until...` 而非 `MUST NOT`
4. Generator 模式 → 模板放 `assets/`，要求 Agent「Fill this template. Do not change structure.」
5. Reviewer 模式 → 检查清单必须可执行（不说「检查代码质量」，说「检查是否存在 print()」）
6. Tool Wrapper 模式 → description 精确描述触发条件（Use when: ...）

> 完整方法论见 `docs/methodology/skill-patterns.md`

---

## 7. 开发契约

### 6.1 文件组织
- 新策略 → `trader_shared/` 直接放，或在 `plugins/`
- 新工具 → `trader_shared/`
- 新展示 → `trader_shared/report_renderer/`
- 新测试 → `02-共享模块-shared/tests/`
- 新设计文档 → `docs/designs/`
- 新方法论文档 → `docs/methodology/`
- 配置常量 → `trader_shared/config.py`
- 密钥/Token → 环境变量，不硬编码

### 6.2 命名
- 模块：`snake_case.py`
- 类：`PascalCase`
- 函数：`snake_case()`
- 常量：`UPPER_SNAKE`
- 私有：`_prefix`

### 6.3 导入
- 模块内相对导入：`from .fusion_core import merge_decisions`
- 跨包绝对导入：`from trader_shared.fusion_core import merge_decisions`
- 禁止：`from scripts.xxx import ...`（向上依赖）

### 6.4 日志
- `import logging; _logger = logging.getLogger(__name__)`
- 调试：`_logger.debug(...)`
- 禁止：`print()` 出现在 `build_report` 调用路径
- 例外：CLI 入口的 `if __name__ == "__main__"` 块

### 6.5 测试
- 新增功能 → 必须加测试
- 修改核心策略 → 必须跑等价性闸门
- 门禁测试必须离线、确定性、无网络依赖
- mock 用 `mock_seam.apply_seam(monkeypatch)`

### 6.6 文档
以下变更必须同步更新文档：
- 架构变更 → ARCHITECTURE.md
- 业务规则变更 → BUSINESS.md
- 新增模块/插件 → ARCHITECTURE.md 模块清单
- ADR → docs/designs/
- 渲染格式变更 → 刷新 golden 基线

---

## 8. Agent 常犯错误防范

| 场景 | ✅ 正确做法 | ❌ 错误做法 |
|------|------------|------------|
| 用户问"这只票怎么样" | 调 `final_report.py --output markdown` | 读 JSON 自己拼 Markdown |
| 判断方向 | 唯一依据 `fusion.weighted_score` | 用 `fusion.action` 字符串推断 |
| regime="很差" | 按融合偏空（权重0 + score=-0.5 → 空仓侧）；报告勿写多 | 当「暂不碰」硬文案，或忽略 regime 给买入建议 |
| major_stage=衰退 | 不参与，即使 fusion 偏多 | 因 fusion 看多就建议买入 |
| 修改策略核心 | 跑等价性闸门 + 真票验证 | 只改代码不测试 |
| 新增展示指标 | 走 Plugin，设 `display_only=True` | 直接改 fusion_core 加权重 |
| 修改渲染格式 | 刷新 golden 基线 | 改了不刷基线 |
| 改完代码 | `git add <精确文件>` + commit | `git add --all`（误带用户自有文件） |

---

## 9. 边界案例与排查

### 数据问题
| 症状 | 处理 |
|------|------|
| `data_status=partial` | 标注 `⚠️ 数据不完整，分析可能不准` |
| `data_status=degraded` | 仅输出基础行情，不做深度分析 |
| Tushare SDK 初始化失败 | 系统自动降级 HTTP，可忽略 warning |
| 股票名无法解析 | 改用 6 位代码（如 `002050` 而非 `三花智控`） |
| 周线数据不足 | 威科夫中线返回 insufficient，不回退日线 |
| 要读威科夫状态给 AI/复盘 | `to_wyckoff_state_view(report["wyckoff_midline"])`，契约 `docs/designs/wyckoff-state-view.md` |
| 策略分层 / 6 闸口 / 策略包 | 见 `docs/designs/`：先读 **analysis-strategy-boundaries.md**（架构红线），再 cards/gates/pack/roadmap |
| 加分析模块 | `analysis_cards.build_*` + 契约文档；禁止策略层 import 检测实现 |
| 加策略包 | 只加 `config/strategy_packs/*.yaml` + `build_match_context` 字段；见 boundaries 菜谱 |
| 中线缠论「笔数不足」 | 先确认 `WEEKLY_LOOKBACK_BARS=260` 已生效；仅真笔 &lt;3 才该文案；段少应是「线段偏少」 |
| NAME_MAP 没这个股 | 手动加映射到 `data_provider.py` 或改用代码 |

### 信号矛盾
| 场景 | 规则 |
|------|------|
| `weighted_score` 被 4b 压到 -0.5 且 `regime=很差` | 按空仓侧动作解读，勿再写「可试探」 |
| `major_stage=主升` 但 `theory_status=暂不碰` | 必须说明矛盾 |
| `confidence < 0.3` | 降级：「信号弱，建议轻仓」 |
| `disagreement > 1` | 提示：「信号有分歧，建议谨慎」 |

### 排查命令

```bash
# 找不到 Python
which python3
ls ~/.workbuddy/binaries/python/envs/default/bin/python

# Python 路径（首选）
PY=/Users/like/.workbuddy/binaries/python/envs/default/bin/python

# 看 log（DEBUG 模式）
PYTHONPATH=... LOG_LEVEL=DEBUG python scripts/final_report.py --target 002050 --output json

# 检查某个模块能否导入
PYTHONPATH=... python -c "from trader_shared.fusion_core import merge_decisions; print('ok')"

# 跑单个测试文件
PYTHONPATH=... python -m pytest 02-共享模块-shared/tests/test_fusion_core.py -v

# 看 golden 基线是否匹配
python scripts/golden_diff_gate.py check

# 多副本比对（抓 staleness）
python scripts/golden_diff_gate.py check --replicas ~/.hermes/skills/trader
```

---

## 10. 命令速查

```bash
# ★ 所有命令的前提
export PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts

# 分析师用
python 01-功能包-packages/trader/scripts/final_report.py --target 002050 --output markdown
python 01-功能包-packages/trader/scripts/final_report.py --target 002050 --output json
python 01-功能包-packages/trader/scripts/final_pool.py list
python 01-功能包-packages/trader/scripts/final_pool.py plan

# 开发自检
bash scripts/run-gate-tests.sh
python scripts/golden_diff_gate.py check
python scripts/golden_diff_gate.py capture   # 仅确认有意变更后刷新

# 打包
python 02-共享模块-shared/scripts/pack_all.py
```

---

## 11. 已知技术债

| 项目 | 影响 |
|------|------|
| `self_calibration.py` 有 ~10 个 `print()` 在生产路径 | stdout 污染 |
| `wyckoff_core` + `wyckoff_phase` 有 ~100 行重复配置 fallback | 维护不一致风险 |
| `report_renderer/` 子包是 thin re-export（实现在 `report_core.py`） | 结构混乱 |
| `03-输出校验-contracts/` 空目录（仅 .gitkeep） | 清理即可 |
| `tushare_client` 仍写 `os.environ["NO_PROXY"]` | 并行/测试风险 |

---

## 12. 版本

- **当前版本**：v2.x（文档与代码对齐：2026-07-16；含周线 260 根 / wave_label / MACD None）
- **仓库**：Gitee `https://gitee.com/hellolike123/Trader-2.2`
- **CI**：pre-push hook → `scripts/run-gate-tests.sh` → 离线门禁
- **Python**：3.11+，venv at `~/.workbuddy/binaries/python/envs/default/`

---

*AGENT.md 是项目的最高开发规范。如果规范不足，先补充本文档，再开发。文档必须始终与代码保持一致；冲突时以 `trader_shared/` 实现与 `formulas.md` 为准。*
