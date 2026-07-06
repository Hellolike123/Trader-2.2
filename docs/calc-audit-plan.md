# Trader3.0 计算模块与分析逻辑正确性审查总计划

> **版本**：v1.0 · 2026-07-06
> **目的**：把分散在「单点检查提示词」里的方法论整合成一份**项目级、可执行、可复用**的审查方案，覆盖从纯算法正确性到输出契约对齐的全链路。
> **使用方式**：作为后续每次「帮我检查 X 模块逻辑」对话的入口文档，先指明本次审查的【模块组 / 优先级 / 提示词模板】，再发起对话。

---

## 一、审查目标（4 件事）

| # | 目标 | 衡量标准 |
|---|------|---------|
| G1 | **纯算法正确性** —— 实现 vs 理论依据 | 关键函数 100% 覆盖理论步骤，边界用例齐全 |
| G2 | **跨模块数据契约一致性** —— 字段名 / 类型 / 缺失值 | 无字段名映射反转、无 None 透传、单位统一 |
| G3 | **输出契约对齐** —— 模板 vs 实际渲染 | 五层打分齐全、买卖点来源正确、信号 ID 强一致 |
| G4 | **历史回归** —— 已修 P0 bug 不复发 | 历史 P0 用例全绿、关键阈值有单测 |

---

## 二、审查范围（按层分组）

> 模块路径基于实际目录：核心计算在 `02-共享模块-shared/trader_shared/`，技能入口在 `01-功能包-packages/<skill>/scripts/`。

### A. 纯算法层（高风险 · 理论性强）

| 模块 | 理论依据 | 关键检查点 |
|------|---------|-----------|
| `chan_core.py` | 缠论笔/段/走势 | 笔段构建条件、`build_segments()`、`classify_structure()`、背离方向 |
| `wyckoff_core.py` | 威科夫 Spring/SOS/UTAD | `_detect_spring()` 的 ATR 刺穿深度 fallback、Spring 类型判定 |
| `chip_distribution.py` | 动态筹码 + 空间去重 | 时序 `turnover_rate` 折旧、局部极大值提取、空间过滤（间距 ≥4% & ≥4 bins） |
| `hmm_regime.py` | Baum-Welch + Viterbi | 2D 特征 `(returns, vol_ratio)` fallback 到 1D、前向/后向收敛 |
| `bayesian_fusion.py` | 乘积规则融合后验 | 数值溢出保护、三路后验乘积归一化、`BAYESIAN_FUSION=true` 开关 |
| `volume_profile.py` | POC / Value Area 70% | POC 计算窗口、VA 边界插值、与 `_check_theory_breakout` 对接 |
| `structure_core.py` | 多周期支撑压力 | `find_key_levels()` 三级阶梯、`_theory_multipliers` 按 HMM regime 消费 |
| `main_force.py` | 主力五阶段（吸筹/试盘/拉升/派发/砸盘） | 资金流特征权重、与 `main_force_scoring.py` 协同、五阶段优先级 |
| `momentum_core.py` | 动能评估 | 动能取值区间、与 stage 的输入输出契约 |
| `pattern_core.py` | 形态识别 | 形态命名一致性、识别阈值 |
| `indicator_math.py` | 数学指标库 | ATR / RSI / MACD 公式与 TALib 对齐 |

### B. 融合决策层（最高风险 · 一票否决逻辑集中地）

| 模块 | 关键检查点 |
|------|-----------|
| `fusion_core.py` | Scenario Priority Filter 权重偏斜（极值区 80%）、Belief Priority 冲突消解、近 3 日 fund_flow 净流出 >500 万一票否决、`FUSION_STATUS_MAP` 覆盖链路 |
| `decision_core.py` | `status_layers()` 双层状态、假跌破硬性熔断（单日跌幅 >7%）、`HARD_STOP_SINGLE_DAY_DROP` 符号、`ma250_warning` 标记 |
| `stage_positioning.py` | `evaluate_position_state()` T+1 隔离锁、`calc_portfolio_correlation()` R>0.7 合并暴露 |
| `rule_engine.py` / `modifier_rule_engine.py` | YAML 规则解析、布尔表达式求值、评分修饰顺序 |

### C. 数据采集与缓存层（已知有 P0 历史）

| 模块 | 关键检查点 |
|------|-----------|
| `fund_flow_data.py` | ⚠️ **历史 P0：字段映射反转**。复查超大单/大单/中单/小单映射、东方财富 API schema 对齐 |
| `light_data.py` | fallback 库懒加载、mootdx 1.5s 硬超时、Sina/Tencent fallback 路径、`data_status="partial"` 标注 |
| `market_env.py` | HMM 整合、`vol_trend` 导出、缓存按日期去重、`fetch_qfq_daily` 而非 `fetch_kline` |
| `cache_utils.py` | ⚠️ **历史 P0：多线程 tmp 竞态**（原 `os.getpid()`）。复查 `set_cached` 唯一文件名机制 |
| `extend_data.py` | 股东/机构 EPS/解禁/题材扩展数据字段对齐 |
| `tick_cache.py` / `fetchers.py` / `data_provider.py` | tick 路径、抓取重试、双源 HA 切换 |

### D. 信号与输出契约层

| 模块 | 关键检查点 |
|------|-----------|
| `signal_contract.py` | `normalize_signal_id` SHA256 16位 Hex 强一致 UUID、时区无关性 |
| `signal_utils.py` / `signal_store` | 信号生命周期、单一可信源 `~/.trader/signals.jsonl` |
| `chip_migration_monitor.py` | 底部筹码峰下降 40% 警告 / 50% 清仓、`~/.trader/chip_history.json` 持久化 |
| `main_force_output.py` | 复盘输出格式化与 `main_force.py` 字段对齐 |
| `run_analysis.py`（trader skill 入口） | `weighted_score` 阈值动作（≥0.25 持有 / ≥0.1 减 20% / 否则减 50%）、`report` 主字典、`fusion.weighted_score` 取值来源 |
| `final_report.py` / `final_t0.py` / `final_review.py` | 输出对齐 `output-template.md` 与 `output-style-guide.md` |
| `portfolio_run.py` / `portfolio_core.py` | 仓位轮动跟着阶段走、评分排序兜底 |
| `t0_core.py` / `price_point_engine.py` / `ict_execution.py` | T0 4 段精简输出、触发价/大单/操作/风控 |

---

## 三、审查方法（3 类型 × 3 深度）

### 类型

| 类型 | 说明 | 适配层 |
|------|------|--------|
| T1 纯算法正确性 | 对照理论依据逐函数验证步骤、公式、边界 | A 层 |
| T2 跨模块契约一致性 | 字段名 / 类型 / None 透传 / 单位 / 缺失值 | A→B、B→D |
| T3 输出对齐 | 模板字段 vs 实际渲染来源 | D 层 |

### 深度

| 深度 | 做法 | 产出 |
|------|------|------|
| L1 静态审查 | 读代码 + 理论对照，**只报告不修改** | P0/P1/P2 问题清单 |
| L2 单元测试 | `pytest` 补边界用例（NaN / 长度不足 / 全零 / 单日跌幅） | 单测覆盖度报告 |
| L3 端到端回归 | 用历史样本复现 → 对照已知结果 | 输入→输出对照表 |

> **强制规则**：每次审查必须先做 L1 → 出清单 → 用户确认 → 才进 L2/L3，禁止「审查 + 改」一气呵成。

---

## 四、风险分级与审查优先级

### P0（先查 · 历史 bug 类型高复发）

| # | 模块 | 检查项 | 理由 |
|---|------|--------|------|
| P0-1 | `fund_flow_data.py` | 超大/大/中/小单字段映射 | 已发生过映射反转 P0 |
| P0-2 | `chan_core.py` | 背离方向、`build_segments` 合并条件 | 已发生过背离方向错误 P0 |
| P0-3 | `fusion_core.py` | 大单一票否决：阈值方向、净流出 >500 万的「>」符号 | 一票否决方向错会直接覆盖错误 action |
| P0-4 | `decision_core.py` | `HARD_STOP_SINGLE_DAY_DROP=-0.07` 符号、`status_layers` 假跌破判定 | 跌幅符号错会跳过/误触发熔断 |
| P0-5 | `structure_core.py` | `weighted_score` 阈值边界（≥0.25 / ≥0.1）的「≥」与「>」 | 边界等号错位导致动作错档 |
| P0-6 | `cache_utils.py` | `set_cached` 多线程 tmp 唯一文件名 | 已发生过竞态 P0 |
| P0-7 | `signal_contract.py` | `normalize_signal_id` 时区无关性 | 信号重复结算根因 |

### P1（中风险 · 数值/单位/边界）

- `hmm_regime.py` 2D 特征 fallback 路径完整性
- `bayesian_fusion.py` 数值溢出 + 归一化
- `chip_distribution.py` `turnover_rate` 单位与衰减系数
- `wyckoff_core.py` `WYCKOFF_SPRING_ATR_MULTIPLE=0.5` fallback
- `stage_positioning.py` `last_add_date` 日期比较时区（T+1 隔离锁）
- `main_force.py` 五阶段优先级覆盖顺序
- `volume_profile.py` POC 与 `decision_core._check_theory_breakout` 的对接字段

### P2（输出层 · 影响展示）

- `final_report.py` 五层打分齐全性（结构/量价/筹码/动能/资金）
- `run_analysis.py` 买卖点字段缺失 → 显示「数据不足」
- `main_force_output.py` 与 `main_force.py` 字段名漂移
- T0 4 段精简输出顺序

---

## 五、统一的提示词模板（4 种场景 · 复制即用）

> 每次发起审查对话，**先指明本次用哪个模板 + 填好【】内的占位**。

### 模板 1：单模块纯算法审查（最常用）

```
用 trader skill 检查【02-共享模块-shared/trader_shared/chan_core.py】中【build_segments / classify_structure】的实现。

【期望行为 · 理论依据】缠论笔段构建：[简述笔的合并条件、走势分类规则]
【我的疑点】背离方向是否正确；segment 合并是否漏掉 X 浪起点
【上游依赖】structure_core._theory_multipliers 消费其输出
【边界用例】数据 <30 根 / 全平 / 单边大涨

只输出 P0/P1/P2 清单（含行号 + 期望 vs 实际），不要改代码，我确认后再修。
```

### 模板 2：融合决策链路审查（跨模块串起来）

```
检查 fusion_core.merge_decisions() 完整链路，从输入到 weighted_score 输出。

输入维度（不得直接当方向用）：
- major_stage + momentum → Scenario Priority Filter（极值区 80% 偏斜）
- structure_core.base_status → Belief Priority 冲突消解
- 三路专家 → bayesian_fusion（仅 BAYESIAN_FUSION=true 生效）

重点验证：
- 权重分配是否真的偏斜到 80%
- FUSION_CONFIDENCE_THRESHOLD=0.6 是否正确触发 FUSION_STATUS_MAP
- 近 3 日 fund_flow 主力净流出 >500 万是否真能覆盖 action

给我一份【最小输入 → 输出对照表】，标出哪一步偏离 AGENTS.md 契约。只报告不修改。
```

### 模板 3：输出契约对齐审查

```
检查【01-功能包-packages/trader/scripts/run_analysis.py + final_report.py】
输出是否被报告模板正确渲染，对照 references/output-template.md。

逐项核对：
- 📍 买卖点（短线止损/中线止损/试探买/当前/卖/压力）来源是否都来自 structure_core.find_key_levels
- 📊 五层打分（结构/量价/筹码/动能/资金）齐全，不能出现"数据不足"
- 🎯 信号判断的 weighted_score 是否真取自 fusion 层（不是从 major_stage 推断）
- 📍 决策里"黄金挂单位"是否在空仓低吸参考旁正确展示

找出任何"字段缺失 → 显示成数据不足"或"取错来源 → 阶段直接推断方向"的位置。只出清单。
```

### 模板 4：历史 P0 回归（防复发）

```
对【fund_flow_data.py】做历史 P0 回归检查。

历史 bug：字段映射反转（超大单/大单/中单/小单字段错位）
检查方式：
1. 静态：对照东方财富 API 返回 schema，逐字段核对映射
2. 动态：跑现有单测 test_*.py，确认所有用例绿
3. 边界： fund_flow 为空 / 单日全零 / 仅大单非零 三种场景的返回值

输出：通过/未通过 + 失败用例详情。如发现回归，立即标 P0 并暂停。
```

---

## 六、审查工作流（review-then-fix · 强制）

每个模块走完 5 步，不允许跳步：

1. **L1 静态审查** —— 用对应模板，AI 出 P0/P1/P2 清单（含行号 + 期望 vs 实际）
2. **用户确认** —— 用户标记哪些要修、哪些是误报
3. **修复** —— 一次只修确认的问题，不动其他逻辑
4. **L2 单测补全** —— 补边界用例（NaN / 长度不足 / 全零 / 阈值边界）
5. **L3 历史回归** —— 用历史样本跑一遍，对照已知结果

> **硬约束**：第 3 步之前不得修改任何代码。第 5 步未通过视为审查未完成。

---

## 七、交付物

| 交付物 | 格式 | 存放位置 |
|--------|------|---------|
| 问题清单 | Markdown 表格（模块 / 行号 / P级 / 期望 / 实际 / 状态） | `docs/audit/<module>-issues.md` |
| 修复报告 | Markdown（变更表 + diff 摘要） | `docs/audit/<module>-fix.md` |
| 单测覆盖度 | pytest 输出 + 覆盖率 | `02-共享模块-shared/tests/` |
| 端到端对照表 | 输入→输出 CSV | `docs/audit/<module>-regression.csv` |

---

## 八、执行节奏（分批 · 用户驱动）

| 批次 | 模块组 | 预计轮次 | 启动条件 |
|------|--------|---------|---------|
| 第 1 批 | P0-1 ~ P0-7（7 个历史高复发点） | 7 次对话 | 本计划确认后即可启动 |
| 第 2 批 | A 层剩余算法模块 | 4-5 次 | 第 1 批全部修复+回归通过 |
| 第 3 批 | B 层融合决策链路 | 2-3 次 | 第 2 批通过 |
| 第 4 批 | C 层数据采集层 | 2-3 次 | 与第 3 批可并行 |
| 第 5 批 | D 层输出契约层 | 2-3 次 | 第 3 批通过后启动 |

> **每次只审查一个模块组**，用户确认后才进下一批。禁止并行多模块审查（容易丢上下文）。

---

## 九、发起一次审查的标准动作

1. 打开本文档，找到目标模块对应的【层 / P 级】
2. 复制对应【提示词模板】，填好【】占位
3. 在新对话里发起，附上：「按 calc-audit-plan.md 第 X 节，审查 Y 模块」
4. AI 出 P0/P1/P2 清单 → 你确认 → AI 修 → 跑回归 → 写 `docs/audit/<module>-issues.md`
5. 关闭本批次，进下一批

---

## 附录 A · 已知 P0 历史 bug（防复发锚点）

| 时间 | 模块 | bug | 修复要点 |
|------|------|-----|---------|
| 历史 | `fund_flow_data.py` | 超大/大/中/小单字段映射反转 | 字段名与东财 schema 严格对齐 |
| 历史 | `chan_core.py` | 背离方向错误 | 顶/底背离判定符号核对 |
| 历史 | `cache_utils.py` | 多线程 tmp 文件名竞态 | 用唯一名替代 `os.getpid()` |

> 每次新发现 P0 都追加到此表，作为下次回归锚点。

---

## 附录 B · 审查自查清单（AI 用）

发起审查前 AI 自检：
- [ ] 是否声明了「只报告不修改」
- [ ] 是否提供了理论依据
- [ ] 是否指明了上游/下游依赖
- [ ] 是否列出了边界用例
- [ ] 是否按 P0/P1/P2 分级
- [ ] 是否包含行号 + 期望 vs 实际

未全打勾不得输出清单。
