# 分析 / 策略 / 决策 架构边界（给开发 Agent）

> **状态**：架构加固 A+B（进行中）  
> **版本**：v0.1 · 2026-07-18  
> **读者**：所有改 Trader 代码的 Agent / 人类  
> **必读顺序**：本文 → `analysis-opinion-cards.md` → `strategy-gates.md` → `strategy-pack.md` → `strategy-roadmap-and-tests.md`

---

## 0. 一句话架构（不得违背）

```text
分析层 只产「意见卡 analysis_cards」+ 原始大 dict（兼容）
    ↓
策略层 只读 意见卡 + 公共上下文 → 六闸口匹配 strategy_match
    ↓
决策层 fusion / discipline 消费信号（加固目标：逐步只读卡；当前 fusion 仍可读原路径）
    ↓
展示层 report_core 展示状态灯 + 动作 + 📐 闸口
```

**禁止**：策略包或 `strategy_match` 内重跑缠论笔、威科夫 Spring 检测、筹码直方图。  
**禁止**：为加一个包去改 `weighted_score` 公式。  
**禁止**：报告里手写第二套开仓逻辑绕过闸口。

---

## 1. 分层与代码落点

| 层 | 职责 | 代码位置（现行） | 对外 API |
|----|------|------------------|----------|
| **分析 Analysis** | 算结构/事件/动量/筹码等 | `chan_core` / `wyckoff_*` / `momentum_core` / `chip_*` / `plugins/*` | **`analysis_cards.build_*_card`** |
| **策略 Strategy** | 闸口匹配、填止损剧本 | `strategy_match.py` + `config/strategy_packs/*.yaml` | **`match_strategies` / `format_gates_brief`** |
| **决策 Decision** | 融合打分、纪律收紧 | `fusion_core` / `mistery_gate` / `chan_discipline` | `merge_decisions` / gate 结果 |
| **编排 Orchestration** | 串起来写 report | `report_builder.build_report` | report dict |
| **展示 Presentation** | Markdown | `report_core.render_short_midline` | 纯展示 |

### 1.1 依赖方向（箭头只能向下或同层工具）

```text
presentation  →  report dict 字段
strategy      →  analysis_cards + context（禁止 → wyckoff_events / detect_buy_points）
analysis_cards→  analysis cores（适配层，允许）
decision      →  当前可 cores；目标 → cards（阶段 C）
report_builder→  全部层
```

```
❌ strategy_match  import  wyckoff_events / chan_structure 检测实现
❌ strategy_packs  内嵌 Python 重算 K 线
❌ report_core     里 if Spring: 建议买入 30%（应走 match）
✅ analysis_cards  import  resolve_* / format_*（薄适配）
✅ strategy_match  import  analysis_cards 仅类型/文档；运行时读 report["analysis_cards"]
```

---

## 2. report 上的标准字段（Agent 写功能时认这些）

`build_report` **必须**尽量填充（失败时也要有占位或空卡）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `analysis_cards` | dict | 键：`chan` `wyckoff` `wyckoff_midline` `momentum` `chip` `vpf` |
| `strategy_match` | dict | `schema_version=strategy_match_v1`，含 `gates` |
| `discipline` | dict | 纪律合并结果 |
| `conclusion` | dict | 中短线结论 |
| 原有 `chanlun` / `wyckoff` / … | dict | **兼容保留**；新逻辑优先 cards |

构建入口：`analysis_cards.ensure_report_analysis_cards(report)`  
匹配入口：`strategy_match.match_strategies(report)`（内含 `build_match_context`，**优先读 cards**）

---

## 3. 如何加「分析模块」（给 Agent 的菜谱）

1. 在 core/plugin 实现计算（可放 `trader_shared/` 现有位置）。  
2. 在 `analysis_cards.py` 增加 `build_xxx_card`，**冻结字段**写入 `analysis-opinion-cards.md`。  
3. 在 `ensure_report_analysis_cards` 挂上。  
4. 单测：卡字段 + 无 NaN。  
5. **不要**直接改 `strategy_match` 去 import 你的检测函数。  
6. 若策略要用：在 YAML `match` 增加对 context 字段的映射（由 `build_match_context` 从 card 抽取）。

---

## 4. 如何加「策略包」（给 Agent 的菜谱）

1. 新建 `config/strategy_packs/{gate}.{name}.yaml`。  
2. 填 `id/gate/priority/match/summary`（见 `strategy-pack.md`）。  
3. `match` 只使用 **context 已有字段**（`chan_type_short`、`wyckoff_event`、`regime`…）。  
4. 缺字段 → 先扩展 `build_match_context` 从 **card** 抽取，禁止策略里重算。  
5. 单测加在 `tests/test_strategy_match.py`。  
6. 报告 📐 自动出现（P3 已接 `format_gates_brief`）。

闸口：`select | entry | manage | scale | take | stop`（见 `strategy-gates.md`）。

---

## 5. 架构加固阶段（本文范围）

| 阶段 | 内容 | 状态 |
|------|------|------|
| **A** | 边界文档 + import 红线单测 | ✅ 本文 + `test_arch_boundaries.py` |
| **B** | report 必出完整 cards + context 优先读卡 | ✅ `ensure_report_analysis_cards` |
| **C** | fusion 读卡（可回退 classic / compare） | ✅ 默认 `FUSION_FROM_CARDS=cards`；`fusion_card_signals.py` |
| **D** | 物理目录 `analysis/` `strategy/` | **未做** |

### 阶段 C 环境变量

| 变量 | 值 | 行为 |
|------|-----|------|
| `FUSION_FROM_CARDS` | `cards` / `true` / 缺省 | 三席优先意见卡，不足回退 classic |
| | `classic` / `false` | 仅原 `_chan_to_signal` 等路径 |
| | `compare` | 两路都算；主结果用 cards；写入 `fusion_compare` |

结果字段：`fusion_input_path` = `cards` \| `classic`；可选 `fusion_compare`。

---

## 6. 红线清单（Agent 自检）

- [ ] 我改的是分析还是策略？有没有跨层？  
- [ ] 新策略是否只加了 YAML + context 字段？  
- [ ] 是否动了 `weighted_score`？策略需求通常 **不该** 动。  
- [ ] 是否更新了 `docs/designs/` 对应契约？  
- [ ] 是否跑了 `test_arch_boundaries` + `test_strategy_match` + `test_analysis_opinion_cards_p0`？  

---

## 7. 相关文件速查

| 用途 | 路径 |
|------|------|
| 意见卡实现 | `trader_shared/analysis_cards.py` |
| 策略匹配 | `trader_shared/strategy_match.py` |
| 策略包 YAML | `trader_shared/config/strategy_packs/` |
| 报告编排 | `trader_shared/report_builder.py` |
| 报告渲染 | `trader_shared/report_core.py` |
| 架构单测 | `tests/test_arch_boundaries.py` |

---

*架构变更必须先改本文与意见卡/闸口契约，再改代码。其它 Agent 以本文为依赖法源。*
