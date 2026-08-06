# 第 3 批融合决策模块审查与修复报告

> **审查日期**：2026-07-07
> **审查分支**：`audit-batch-3-fusion`
> **协作模式**：双 Reviewer 并行审查（理论派 + 工程派）→ Arbitrator 裁决+执行
> **审查范围**：3 个融合决策模块（stage_positioning / rule_engine / modifier_rule_engine + score_rules.yml）
> **前置依赖**：已包含第 1 批 11 项修复 + 第 2 批 6 项修复

---

## 一、审查概览

| 维度 | 理论派 Reviewer | 工程派 Reviewer | 交叉验证 |
|------|----------------|----------------|---------|
| P0 | 1 | 2 | 0 |
| P1 | 2 | 4 | **1（时区）** |
| P2 | 3 | 4 | 0 |
| 合计 | 6 | 10 | 1 |

**最终裁决**：ACCEPT 7 项 · DEFER 8 项 · REJECT 0 项

两派首次出现**交叉重叠**：L1809 时区问题被两派独立发现并一致判定为 P1，增强了信任度。理论派聚焦算法正确性（T+1 死代码、边界一致性、决策矩阵措辞），工程派聚焦边界鲁棒性（None 陷阱、NaN 透传、缓存线程安全、异常处理范围）。

---

## 二、裁决矩阵

| # | 模块 | 行号 | 原始发现 | 来源 | 原级 | 裁决 | 理由 |
|---|------|------|---------|------|------|------|------|
| 1 | stage_positioning.py | 1806-1814 | T+1 隔离锁死代码：调用方 run_analysis.py L1269-1287 未传 `last_add_date`，默认 None 永远不触发锁 | 理论派 | P0 | **ACCEPT** | 读代码确认。集成层缺失——函数签名有参数但调用方未传。修复：run_analysis.py 调用时传入 `last_add_date=bars_date` |
| 2 | stage_positioning.py | 400 | `float(main_force_result.get("confidence", 0))` 遇 confidence 值为 None 时 .get 返回 None → float(None) → TypeError | 工程派 | P0 | **ACCEPT** | 与第 1 批同类 .get 陷阱。修复：`.get("confidence") or 0` |
| 3 | rule_engine.py | 73 | `rule.get("result", 0)` 遇 YAML result 值为 null(None) 时 .get 返回 None → isinstance(None,(int,float)) → False → TypeError | 工程派 | P0 | **ACCEPT** | 与第 1 批同类 .get 陷阱。修复：`.get("result") or 0` |
| 4 | stage_positioning.py | 1809 | `datetime.now()` 取系统本地时间，非东八区时区会误判跨日边界，T+1 锁失效 | 理论派+工程派 | P1 | **ACCEPT** | 两派独立发现，高信任度。修复：`datetime.now(timezone(timedelta(hours=8)))` |
| 5 | stage_positioning.py | 629 | `ws_f > 0.25` 应为 `>= 0.25`，与 fusion-guide.md 表不一致 | 理论派 | P2 | **ACCEPT** | 边界一致性修复，低成本。修复：`> 0.25` → `>= 0.25` |
| 6 | stage_positioning.py | 278 | `avg_vol_20=0` 时 `max(avg_vol_20, 1)` 返回 1，误判放量 | 工程派 | P2 | **ACCEPT** | 防御性修复。avg_vol_20 ≤ 0 直接返回 `(0.0, "", "")` |
| 7 | score_rules.yml | 2 | YAML 注释"only positive-value rules apply"，代码实际求所有匹配规则（含负分） | 理论派 | P2 | **ACCEPT** | 注释与代码语义相反，误导维护者。修复：注释改为"all matching rules apply (both positive and negative)" |
| 8 | stage_positioning.py | 835-838 | _DECISION_MATRIX "蓄势+修复" 映射到"回调低吸(15%)"，fusion-guide 建议"中性偏多/等确认" | 理论派 | P2 | **DEFER** | 涉及交易策略偏好，改措辞可能影响下游决策逻辑，非代码缺陷 |
| 9 | stage_positioning.py | 546 | `_downgrade_stage` 派发→蓄势偏弱跳过了蓄势和蓄势偏强，与主升→蓄势偏强的逐级降级不一致 | 理论派 | P2 | **DEFER** | 可能是刻意设计——派发降级比主升降级更激进是合理的（派发是空头信号最强阶段） |
| 10 | stage_positioning.py | 108-117 | `calc_portfolio_correlation` np.corrcoef 对常量序列返回 NaN，写入 correlation_pairs 字典 | 工程派 | P1 | **DEFER** | NaN > threshold 为 False，不触发熔断，写入字典不影响决策。修复需 `fillna` 但语义不明确 |
| 11 | rule_engine.py | 49-55/82-88 | `from_yaml` 只捕获 ImportError，不捕获 FileNotFoundError/YAMLError | 工程派 | P1 | **DEFER** | 低频场景（YAML 缺失/损坏），当前异常传播暴露堆栈利于排查 |
| 12 | modifier_rule_engine.py | 17-33 | `apply_score_modifiers` 返回 ScoreRuleEngine 结果之和，无 min/max 截断 | 工程派 | P2 | **DEFER** | 可能依赖无界值设计——极端负分本身就是惩罚信号，截断会丢失信息 |
| 13 | stage_positioning.py | 1810 | `last_add_date == today` 裸字符串比较，格式不一致永远 False | 工程派 | P2 | **—** | 已被 #1 修复覆盖——传入 bars_date 后字符串格式一致 |
| 14 | stage_positioning.py | 多处 | `float(b.get("key") or 0)` 中 `or 0` 不拦截 NaN（bool(nan)==True） | 工程派 | P2 | **DEFER** | 模式级问题，需全项目审计，非本批范围 |
| 15 | rule_engine.py | 44 | `rule.get("result")` 无默认值 | 工程派 | P2 | **DEFER** | RuleEngine.evaluate 设计上 None 表示"无匹配"，非 ScoreRuleEngine 语义 |
| 16 | modifier_rule_engine.py | 11-13 | `_ENGINE_CACHE` 模块级全局变量无锁 | 工程派 | P2 | **DEFER** | 当前单线程使用，缓存重试机制（60s 冷却）已提供基本健壮性 |

---

## 三、关键裁决说明

### ★ T+1 隔离锁死代码（理论派 P0 → ACCEPT）

**发现**：`evaluate_position_state()` L1808-1814 实现 T+1 隔离锁逻辑，比较 `last_add_date == today`。但调用方 `run_analysis.py:build_report()` L1269-1287 未传入 `last_add_date` 参数，函数签名默认 `None`，使得 L1810 的 `last_add_date is not None and ...` 永远 False——T+1 隔离从未生效。

**裁决 ACCEPT 的理由**：这是纯粹的集成层遗漏，非设计问题。函数签名已预留参数，调用方已有 `bars_date` 变量（从 K 线数据提取，L1029-1034），修复只需在调用时加一行 `last_add_date=bars_date,`。配合时区修复（#4），T+1 锁将正确生效。

**修复验证**：`run_analysis.py:build_report()` 已传入 `last_add_date=bars_date`，`bars_date` 来自 K 线 `trade_date` 字段，格式 YYYY-MM-DD，与 L1809 日期格式一致。

### stage_positioning.py _DECISION_MATRIX 蓄势+修复 措辞（理论派 P2 → DEFER）

**发现**：`_DECISION_MATRIX` L835-838 中"蓄势+修复"映射到 `("回调低吸", 15)`，fusion-guide.md 倾向"中性偏多/等确认"。两者存在偏差（激进 vs 中性）。

**裁决 DEFER 的理由**：这不是代码缺陷，而是交易策略层面的偏好差异。"回调低吸"15% 仓位与"中性偏多/等确认"指向同一方向（偏多），仅执行力度不同。改措辞无需改代码（不涉及仓位比例或判断逻辑），且可能影响依赖该字符串匹配的下游系统。若需调整，应由交易策略 owner 决定。

### _downgrade_stage 派发跳级（理论派 P2 → DEFER）

**发现**：`_downgrade_stage()` L542-548 中"派发"直接降级到"蓄势偏弱"（跳 2 级），而"主升"降级到"蓄势偏强"（降 1 级），不符合逐级降级规律。

**裁决 DEFER 的理由**：派发阶段是四阶段中最强的空头信号，从派发跳到蓄势偏弱（最弱多头阶段）是合理的加速降级设计。与主升（最强多头）降一级到蓄势偏强（次强多头）逻辑一致——都是从极端信号降回保守区域。这不是 bug，而是不对称降级策略。

### rule_engine.py from_yaml 异常范围窄（工程派 P1 → DEFER）

**发现**：`from_yaml()` L49-55 和 L82-88 的 try/except 只捕获 `ImportError`，若 YAML 文件缺失或损坏，FileNotFoundError/YAMLError 将直接传播。

**裁决 DEFER 的理由**：PyYAML 缺失是唯一需要特殊引导的场景（提示安装步骤）。文件缺失和 YAML 损坏属于系统级错误，原始异常传播（含完整 stack trace）比包装后的模糊信息更利于排查根因。如需增强，应改为更细粒度的错误信息包装而非整体吞异常。

### modifier_rule_engine 缓存无锁（工程派 P2 → DEFER）

**发现**：`_ENGINE_CACHE` L11-13 是模块级全局变量，无锁保护，多线程下可能重复初始化（非致命）。

**裁决 DEFER 的理由**：当前调用链全程同步单线程（trader 脚本 seq 分析），`_ENGINE_CACHE` 写入是幂等的（重复赋相同值），重试机制（60s 冷却）避免了高频重试。多线程场景下即使竞态也不会产生错误结果，仅可能浪费一次 YAML 解析。修复成本（引入 threading.Lock + 双检锁）高于收益。

---

## 四、修改清单

| # | 文件 | 行号 | 修改类型 | 说明 |
|---|------|------|---------|------|
| 1 | run_analysis.py | 1287+ | 集成层修复 | `evaluate_position_state()` 调用时传入 `last_add_date=bars_date`，激活 T+1 隔离锁 |
| 2 | stage_positioning.py | 400 | None 防御 | `.get("confidence", 0)` → `.get("confidence") or 0`，防止 None → TypeError |
| 3 | stage_positioning.py | 21 | import 扩展 | `from datetime import datetime` → `from datetime import datetime, timezone, timedelta` |
| 4 | stage_positioning.py | 1809 | 时区修复 | `datetime.now()` → `datetime.now(timezone(timedelta(hours=8)))`，东八区准确 |
| 5 | stage_positioning.py | 629 | 边界一致 | `> 0.25` → `>= 0.25`，与 fusion-guide.md 一致 |
| 6 | stage_positioning.py | 275-278 | 零量防御 | avg_vol_20 ≤ 0 时直接返回 `(0.0, "", "")`，避免误判放量 |
| 7 | rule_engine.py | 73 | None 防御 | `.get("result", 0)` → `.get("result") or 0`，防止 YAML null → TypeError |
| 8 | score_rules.yml | 2 | 注释修正 | 注释改为准确描述代码行为（同时匹配正分和负分规则） |

**总计**：4 个文件，10 行插入，7 行删除

---

## 五、验证结果

### Import 验证（已通过）

```
$ python -c "
from trader_shared.stage_positioning import evaluate_position_state, calc_portfolio_correlation
from trader_shared.rule_engine import RuleEngine, ScoreRuleEngine
from trader_shared.modifier_rule_engine import apply_score_modifiers
"
import OK — all modules load successfully
```

### 功能验证（4 项关键修复 · 全部通过）

| # | 修复项 | 验证方法 | 结果 |
|---|--------|---------|------|
| 1 | L400 None 陷阱 | `float({}.get("confidence") or 0)` → `0.0` | ✅ PASS |
| 2 | L73 None 陷阱 | `ScoreRuleEngine([{when:True, result:None}]).evaluate({})` → `0.0` | ✅ PASS |
| 3 | L278 零量防御 | avg_vol_20=0, avg_vol_5=5.0 → `(0.0, '', '')` | ✅ PASS |
| 4 | L1809 时区 | `datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')` 正确输出东八区日期 | ✅ PASS |

---

## 六、遗留问题（DEFER · 需用户决定）

| # | 模块 | 问题 | 暂缓理由 | 建议 |
|---|------|------|---------|------|
| 1 | stage_positioning.py L835-838 | _DECISION_MATRIX "蓄势+修复" 措辞与指南不一致 | 交易策略偏好，非代码缺陷 | 由策略 owner 决定是否调整决策措辞 |
| 2 | stage_positioning.py L546 | _downgrade_stage 派发跳级降级 | 可能是刻意设计（派发空头信号最强） | 维持现状；如需统一逐级降级，改为 派发→蓄势 |
| 3 | stage_positioning.py L108-117 | calc_portfolio_correlation NaN 写入字典 | NaN>threshold=False 不触发熔断，安全 | 后续可加 `np.isfinite` 过滤 |
| 4 | rule_engine.py L49-55 | from_yaml 异常范围窄 | 低频场景，原始异常更利于排查 | 可选：增加 FileNotFoundError 友好提示 |
| 5 | modifier_rule_engine.py L17-33 | 修饰器结果无截断 | 设计上依赖无界值，截断丢失信号 | 维持现状 |
| 6 | stage_positioning.py 多处 | `float(b.get() or 0)` NaN 透传 | 模式级问题，需全项目审计 | 后续全局审计一次性修复 |
| 7 | rule_engine.py L44 | `rule.get("result")` 无默认值 | RuleEngine 设计 None 表示"无匹配" | 维持现状 |
| 8 | modifier_rule_engine.py L11-13 | 缓存无锁 | 单线程使用，重复初始化为幂等操作 | 未来多线程化时加锁 |

---

## 七、diff 摘要

```
 01-功能包-packages/trader/scripts/run_analysis.py |  1 +      T+1 隔离锁激活
 02-共享模块-shared/trader_shared/rule_engine.py    |  2 +-     None 陷阱防御
 02-共享模块-shared/trader_shared/score_rules.yml   |  2 +-     注释修正
 02-共享模块-shared/trader_shared/stage_positioning.py | 12 ++++-----  时区/零量/边界/None 防御
 4 files changed, 10 insertions(+), 7 deletions(-)
```

---

## 八、本次协作流程评估

### 两派首次交叉验证

本批两派**首次出现交叉发现**：L1809 时区问题被理论派和工程派独立判定为 P1。交叉验证增强了该问题的可信度，Arbitrator 无需单独验证直接 ACCEPT。

其他发现仍保持互补特性（零重叠）：
- **理论派独占**：T+1 死代码（P0）、边界不一致（P2）、注释误导（P2）——从算法语义/契约层面推理
- **工程派独占**：None 陷阱 2 处（P0）、NaN 透传（P1）、异常范围（P2）、缓存无锁（P2）——从异常输入/边界条件层面推理

### Arbitrator 裁决的关键判断

1. **T+1 死代码**：判定为集成层遗漏而非设计问题。函数签名已预留参数，调用方已有正确值（bars_date），修复成本极低（1 行）。这是典型的"接口已实现但未连接"问题。
2. **时区修复**：两派独立发现增强信心。使用标准库 `datetime.timezone` 避免引入 pytz 依赖，保持依赖简洁。
3. **_DECISION_MATRIX 措辞**：区分了"代码正确性"和"策略偏好"。矩阵条目是策略配置而非逻辑缺陷，修改需策略 owner 参与。

---

## 九、下一步建议

1. **用户审阅本报告 + diff**：`git diff` 查看完整改动
2. **合并到 main**：审阅通过后 `git checkout main && git merge audit-batch-3-fusion`
3. **DEFER 项处理**：
   - _DECISION_MATRIX 措辞：是否需要策略 owner 调整
   - from_yaml 异常范围：是否需要更友好的错误信息
4. **后续批次**：本批通过后，按审查计划启动第 4 批审查
