

## 接手先看

- **版本升级**：当前版本为 Trader 2.4，在 2.3 基础上完成三大技能整合、四阶段定位模型、分析引擎并行化等重大重构。
- **技能整合**：6 个技能合并为 3 个——`trader`（单票分析 + 选股池）、`t0`（盘中盯盘）、`review`（盘后复盘 + 仓位轮动 + 信号追踪）。
- **四阶段定位模型**：蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退 × 走强/修复/震荡/转弱，贯穿选股池入池三关、仓位轮动、盘后复盘全链路。
> 判定逻辑：主力行为驱动（`main_force.py` 五阶段优先 + 量价确认验证 + 结构兜底），不再使用量价+MA+ATR 三维投票。
> 注意：major_stage 和 momentum 是输入维度，不是输出方向。方向判断必须以 fusion.weighted_score 为准，不得直接从阶段/动能推断方向。详见 fusion-guide.md 的 Stage-Momentum Default Direction 表。
- **250日线趋势提醒**：年线下方标记 `ma250_warning=True` 并在输出中显示警告，但继续完整分析，不再一票否决。
- **分析引擎并行化**：多票分析场景下缠论/威科夫/筹码等模块并行执行，显著提升选股池批量分析速度。
- **选股池四阶段挂钩**：入池三关（阶段匹配 + 基本面 + 技术面）自动筛选，回复 `1` 一步完成入池。
- **T0 输出精简**：从原有冗长格式精简为 4 部分（触发价 / 大单异动 / 操作建议 / 风控提醒）。
- **仓位轮动跟着阶段走**：根据四阶段定位动态调整仓位分配策略，不再单纯依赖评分排序。
- **单票分析双层状态模型**：`base_status` 负责结构位置层，`theory_status` 负责理论结论层；`state_label` 仅作兼容/展示摘要。
- **信号唯一性契约 (Signal Contract v2)**：基于 SHA256 deterministic hash 的 16 位 Hex 强一致 UUID (`normalize_signal_id`)，严格规避任何时区/数据抖动造成的重复结算。
- **双源热备行情 HA**：`MarketDataSourceController` 接管行情数据通道，mootdx 发生 1.5 秒硬超时或连续 3 次失败时，秒级自动 fallback 至 Tencent HTTP / Sina API，以 `data_status="partial"` 标注数据完备度。
- **智能决策融合层 (Decision Fusion Core)**：通过 Scenario Priority Filter 动态分配结构与动量权重（极值区 80% 权重偏斜），且基于 Belief Priority 冲突消解机制过滤动量噪音。
- **大势参数自适应 (Regime Multipliers)**：根据 `market_env` 大盘牛熊环境因子动态缩放 `zone_width` / `confirm_buffer` / `stop_buffer`。
- **HMM 大势状态检测器**：`hmm_regime.py` 基于纯 numpy Baum-Welch + Viterbi。已深度整合进 `market_env.py` 及下游 `fusion_core.py` / `structure_core.py`。大势判定从纯均线驱动升级为「均线 + HMM 前瞻」双效驱动（高置信度 HMM 状态会自动前瞻修正 `level`，且 `structure_core` 直接复用避免重复抓包）。
- **贝叶斯概率决策融合**：`bayesian_fusion.py` 用乘积规则融合三路专家后验概率。已完整集成在 `fusion_core.py` 中。默认关闭（安全过渡），通过设置环境变量 `BAYESIAN_FUSION=true` 激活，激活后将全面接管传统经验权重，实现基于纯概率后验的最优交易动作决策。
- **日内成交量分布 (Volume Profile)**：`volume_profile.py` 计算 POC 控制节点与 Value Area 70% 成交量密集区。已嵌入 `decision_core.py` 的突破确认判定 `_check_theory_breakout`，通过微观日内量价验证过滤假突破。
- **离线参数自校准器**：`scripts/self_calibration.py` 支持分层搜索，基于 HMM regime 对历史信号分桶搜优（`bull` / `bear` / `range` / `global`），并引入盈亏比加权胜率模型（`WinRate * ProfitFactor`）仿真打分。参数由 `structure_core.py` 的 `_theory_multipliers` 层按当前 HMM 大势动态消费并进行多级回退兼容。
- **动态衰减与空间去重筹码分布**：`chip_distribution.py` 摒弃原有静态累加，实现基于时序 `turnover_rate` 换手折旧的动态筹码曲线，并引入基于局部极大值与空间/价格过滤（间距 $\ge 4\%$ 且 $\ge 4$ bins）的独立筹码峰提取算法，供复盘与仓位控制等技能跨模块全局共享。
- **信号生命周期与日志合并**：废弃 `signal_log.jsonl` 等多个冗余文件，将所有 T0 事件、单票分析信号、手动结果回填统一收口至单一可信源 `~/.trader/signals.jsonl`，并由继承自 `os.PathLike` 的原生路径代理 `DynamicPathProxy` 提供透明、防 pytest 缓存污染的无缝 Mock 支持。
- **斐波那契黄金挂单位 (Golden Bid)**：`structure_core.py` 自动从缠论笔中计算 38.2%/50%/61.8% 黄金分割回调价，并与当前低吸价格区间求交集，计算出高置信度的「黄金挂单位」（显示于 `📍 决策` 列表的空仓低吸参考旁）。
- **分层数据缓存**：日线K线、扩展数据（股东/机构EPS/解禁/题材）、大盘环境均支持文件缓存。盘中分析读缓存 + 追加当日实时数据，盘后预缓存选股池全量数据。命令：`trader.py cache warm`（预缓存）、`trader.py cache clear`（清缓存）。
- **统一包结构**：所有核心模块已迁移到 `trader_shared/` 包下，支持 `pip install -e .` 开发安装和 `pytest` 直接运行。import 统一为 `from trader_shared.xxx import ...`。
- **性能优化（2026-05-31）**：`light_data.py` 的 fallback 库（mootdx/akshare/pytdx3）改为懒加载，单票分析 `build_report()` 从 20s 优化到 0.48s（42 倍提升）。`market_env.py` 数据源从 `fetch_kline`（返回分钟线）修正为 `fetch_qfq_daily`（返回日线），缓存增加按日期去重，大盘环境评估从 10s 降到 0.09s。
- **性能优化（2026-06-15）**：① T0 `build_plan` 的 5 个数据请求（quote/daily/5m/15m/30m）从串行改并行，单次卡片从 0.92s 降到 0.45s（约 46%），盘中每个 monitor 循环都受益。② 单票 `build_report` 消除重复的 `get_env_for_skill` 调用与 `_load_historical_win_rate` 重复抓 300 天日线，稳态从 0.48s 降到 0.43s。③ `cache_utils.set_cached` 修复多线程 tmp 文件名竞态（原用 `os.getpid()` 导致同进程线程互相覆盖），选股池刷新的 cache warning 从每次 4 次降到 0。④ 新增 `refresh` 命令批量重跑全池 `build_report` 并行刷新（8 只票约 1.8s），解决 `plan`/`rank` 使用入池时旧数据的问题。
- **筹码搬家监控 (Chip Migration Monitor)**：`chip_migration_monitor.py` 对每次单票分析生成的筹码峰快照进行持久化（`~/.trader/chip_history.json`），并对比前后变化。底部筹码峰下降超过 40% 触发警告、超过 50% 触发清仓信号，用于识别主力出货迹象。
- **资金流向数据 (Fund Flow Data)**：`fund_flow_data.py` 通过东方财富 HTTP API 采集个股日线级资金流向（超大单/大单/中单/小单净流入），并计算衍生特征供主力行为识别引擎使用。
- **Spring ATR 动态刺穿深度**：`wyckoff_core.py` 的 `_detect_spring()` / `_detect_st()` 共用 `_spring_breach_level()`，优先 `support - 0.5×ATR`，否则 `support × 0.985`。配置：`WYCKOFF_SPRING_ATR_MULTIPLE=0.5`。
- **威科夫 fusion 与报告一行人话**：`_wyckoff_to_signal` 优先级 Spring → SOS → UT → BC → SOW → AR → ST → LPS → 背离；高量 Spring 降权；BC 须高位（`WYCKOFF_BC_MIN_POS_PCT=0.65`）。报告用 `format_wyckoff_oneline()` 单行白话（结论+方向+括号说明），无信号时为 `威科夫：暂无明确信号 · 中性`。`🎯` 主阶段仍是主力四阶段（major_stage），不是威科夫 A–E phase。
- **假跌破硬性熔断**：`decision_core.py` 的 `status_layers()` 在假跌破确认之前检查单日跌幅，跌幅超 7% 直接返回"风险回避"，跳过假跌破逻辑。配置：`HARD_STOP_SINGLE_DAY_DROP=-0.07`。
- **T+1 隔离锁**：`stage_positioning.py` 的 `evaluate_position_state()` 新增 `last_add_date` 参数，当天已加仓则返回"持仓观察（T+1冷却）"，禁止日内重复加仓。
- **多周期支撑压力阶梯**：`structure_core.py` 新增 `find_key_levels(bars)` 函数，在 300 根数据里找短线（10日）、中线（60日）、长线（120日）三级支撑压力位。报告展示为价格阶梯（🌟当前位置）。
- **长线压力位动态动作**：`run_analysis.py` 根据 `weighted_score` 动态决定长线压力位动作：≥0.25 持有关注，≥0.1 减仓 20%，否则减仓 50%。
- **止损分层展示**：报告「📌 如果你有持仓」区块分短线止损和中线止损，分别显示认亏比例。
- **亮点与风险距离百分比量化**：亮点描述当前价距离最近支撑的百分比，风险描述当前价距离最近压力的百分比。
- **大单阈值动态比例**：`big_order.py` 的 tick 路径新增动态阈值 `max(绝对阈值, 20日最大量×0.9)`，适应不同市值股票。配置：`BIG_ORDER_HANDS_RATIO=0.9`。
- **大单连续流出一票否决**：`fusion_core.py` 的 `merge_decisions()` 检查近 3 日 fund_flow 数据，连续 3 日主力净流出 > 500 万强制覆盖 action 为"资金流出，减仓观望"。
- **HMM 2D 成交额特征**：`hmm_regime.py` 支持 2D 输入 `(returns, volume_ratio)`，`market_env.py` 导出 `vol_trend`。`volume_ratio=None` 时 fallback 到 1D，完全向后兼容。
- **持仓相关性熔断**：`stage_positioning.py` 新增 `calc_portfolio_correlation()` 函数，计算持仓个股 20 日收盘价两两相关系数，R > 0.7 时合并为同一风险暴露，总仓位上限降为单票上限。
- **开盘尾盘噪音过滤**：`volume_price.py` 新增 `calc_weighted_volume(bars_5m)` 函数，排除 9:30-9:45 和 14:45-15:00 的噪音数据，用 VWAP 计算加权均量。
- **缠论走势分层重构**：`chan_core.py` 补全线段构建（`build_segments()`）和走势分类（`classify_structure()`），支持盘整/趋势/单边上涨/单边下跌/线段不足X/Y。报告输出 `缠论:拉升段(盘整)` 格式。
- **主力行为五阶段识别 (Main Force)**：`main_force.py` 基于资金流向特征、价格数据和筹码信息，识别主力行为所处阶段（吸筹/试盘/拉升/派发/砸盘）。`main_force_output.py` 负责复盘输出格式化。
- **规则引擎 (Rule Engine)**：`rule_engine.py` 基于 YAML 配置的决策规则引擎，支持比较运算和布尔表达式。`modifier_rule_engine.py` 基于评分修饰规则对候选人评分进行动态调整。
- 真正的输出格式以 `01-功能包-packages/trader/references/output-template.md` 和 `01-功能包-packages/trader/references/output-style-guide.md` 为准。
- 需要看实现时，先看 `01-功能包-packages/trader/scripts/run_analysis.py`。

---

## 业务全景

A 股交易决策辅助系统。免费行情 API（腾讯 + 新浪），缠论 / 威科夫 / 筹码 / ATR 分析，输出标准化 Markdown 面板。

当前核心契约是双层状态模型：
- `base_status` 负责结构位置，描述现在站在什么位置
- `theory_status` 负责理论结论，描述按当前体系算不算转强
- `state_label` 现在只是兼容/展示层摘要，偏向理论结论，不再是主契约
- 旧的 `scene` 语义还会出现在部分兼容代码里，但不应再当成主状态理解

接入本仓库的 AI 协同系统优先阅读本页，随后查阅对应技能目录下的 「output-template.md」、「output-style-guide.md」 和 「SKILL.md」 以统一输出契约。

---

## 趋势过滤与退出策略

### 250日线趋势提醒

股价在 250 日均线（年线）下方时，标记 `ma250_warning=True` 并在输出中显示警告，但继续完整分析。不再一票否决。

- 配置：`TREND_FILTER_ENABLED`、`TREND_MA_LONG=250`、`LOOKBACK_DAYS=300`
- 位置：`decision_core.py` → `status_layers()` 入口
- 返回值新增 `ma250_warning`（bool）和 `ma250`（float|None）

### ATR 移动止损

止损价动态跟踪最高收盘价，只紧不松：

```
trailing_stop = highest_close × (1 - ATR% × 3.0)
最终止损 = max(trailing_stop, hard_stop)
```

- 配置：`ENABLE_TRAILING_STOP=True`、`TRAILING_STOP_ATR_MULTIPLE=3.0`
- 位置：`structure_core.py` → `build_structure_context()`

### 假跌破确认 + 分阶段退出

| 条件 | 状态 | 策略 |
|------|------|------|
| 价格距止损 < 2×ATR | "冲高减仓" | 逢高减仓 |
| 跌破止损（无假跌破） | "风险回避" | 全面退出 |
| 跌破止损 + 近3日有收盘≥支撑 | "防守观察" | 持有观察 |

- 配置：`PULLBACK_CONFIRM_DAYS=3`、`EXIT_PHASED_ENABLED=True`
- 位置：`decision_core.py` → `status_layers()`

### 融合覆盖机制

当融合层置信度超过阈值时，其 action 通过 `FUSION_STATUS_MAP` 覆盖 `status_layers()` 的判定。

- 配置：`FUSION_OVERRIDE_ENABLED=True`、`FUSION_CONFIDENCE_THRESHOLD=0.6`
- 位置：`decision_core.py` → `_FUSION_STATUS_MAP`

---

## Skill 速查表

| Skill | 一句话 | 版本 | 入口脚本 |
|-------|--------|------|---------|
| `trader` | 单票分析 + 选股池全生命周期管理 | `2.4.0-consolidated` | `01-功能包-packages/trader/scripts/final_report.py` / `01-功能包-packages/trader/scripts/final_pool.py` |
| `t0` | 盘中 T0 精确执行卡 + 盯盘告警 | `2.4.0-consolidated` | `01-功能包-packages/t0/scripts/final_t0.py` |
| `review` | 盘后复盘 + 仓位轮动 + 信号追踪 | `2.4.0-consolidated` | `01-功能包-packages/review/scripts/final_review.py` / `01-功能包-packages/portfolio/scripts/final_portfolio.py` / `01-功能包-packages/review/scripts/final_tracker.py` |

运维工具（非 Skill 入口）：
| 工具 | 用途 | 入口 |
|------|------|------|
| `run_trader.py` | 全局中央指挥官路由器，统一路由盘中/盘后指令 | `scripts/run_trader.py` |
| `t0_cron.py` | T0 盯盘 cron 入口，适合 crontab 每 5 分钟调用 | `scripts/t0_cron.py` |
| `wechat_monitor.py` | 选股池 WeChat 监控，自动轮询活跃票并推送消息 | `scripts/wechat_monitor.py` |

---

## Skill 输出迭代工作流

五步标准流程：观察 → 诊断 → 提案 → 执行 → 验证

```
观察：发现输出问题（性能/数据/功能/显示）
诊断：定位根因（哪个模块、哪行代码）
提案：用 quick_change.py 创建变更（python scripts/quick_change.py --type <类型> --name <名称>）
执行：按 tasks.md 实施
验证：跑测试 + 手动验证输出
```

四类变更模板（原 `openspec/templates/`，现已废弃）：
- `performance.md` — 性能优化（含耗时对比）
- `data-fix.md` — 数据修复（含正确数据来源）
- `feature.md` — 功能增改（含预期输出示例）
- `display.md` — 显示调整（含微信兼容性检查）

---

## 推荐工作流

```
新票验票 → python 01-功能包-packages/trader/scripts/final_report.py --target <NAME>
入池 → python 01-功能包-packages/trader/scripts/final_pool.py add --target <NAME>
排序 → python 01-功能包-packages/trader/scripts/final_pool.py rank
明日作战表 → python 01-功能包-packages/trader/scripts/final_pool.py plan
盘中执行 → python 01-功能包-packages/t0/scripts/final_t0.py --target <NAME> --monitor
盘后复盘 → python 01-功能包-packages/review/scripts/final_review.py --target <NAME>
仓位轮动 → python 01-功能包-packages/portfolio/scripts/final_portfolio.py --targets A B
信号回溯 → python 01-功能包-packages/review/scripts/final_review.py --target <NAME>（读 signals.jsonl）
```

### Skill 命令映射

| 需求 | 命令 |
|------|------|
| 分析一只票 | `python 01-功能包-packages/trader/scripts/final_report.py --target <NAME>` |
| 价格监控 | `python 01-功能包-packages/trader/scripts/final_report.py --target <NAME> --output alert-text` |
| 写入信号 | `python 01-功能包-packages/trader/scripts/final_report.py --target <NAME> --write-signal` |
| 入池 | `python 01-功能包-packages/trader/scripts/final_pool.py add --target <NAME>` |
| 入池前分析 | `python 01-功能包-packages/trader/scripts/final_pool.py analyze --target <NAME>` |
| 池子概览 | `python 01-功能包-packages/trader/scripts/final_pool.py list` |
| 排序 | `python 01-功能包-packages/trader/scripts/final_pool.py rank` |
| 明日作战表 | `python 01-功能包-packages/trader/scripts/final_pool.py plan` |
| 刷新全池数据 | `python 01-功能包-packages/trader/scripts/final_pool.py refresh` |
| 刷新单只票 | `python 01-功能包-packages/trader/scripts/final_pool.py refresh --target <NAME>` |
| 池中盯盘 | `python 01-功能包-packages/trader/scripts/final_pool.py watch` |
| 待确认池 | `python 01-功能包-packages/trader/scripts/final_pool.py show-pending` |
| 多票对比 | `python 01-功能包-packages/trader/scripts/final_pool.py compare --targets A B C` |
| 移除出池 | `python 01-功能包-packages/trader/scripts/final_pool.py remove --target <NAME>` |
| 归档已退出 | `python 01-功能包-packages/trader/scripts/final_pool.py archive-exited` |
| T0 盯盘单次 | `python 01-功能包-packages/t0/scripts/final_t0.py --target <NAME> --monitor --once` |
| T0 持续监控 | `python 01-功能包-packages/t0/scripts/final_t0.py --target <NAME> --monitor` |
| 盘后复盘 | `python 01-功能包-packages/review/scripts/final_review.py --target <NAME>` |
| 多票复盘对比 | `python 01-功能包-packages/review/scripts/final_review.py --compare A B C` |
| 盘中复盘 | `python 01-功能包-packages/review/scripts/final_review.py --target <NAME> --session midday` |
| 仓位轮动 | `python 01-功能包-packages/portfolio/scripts/final_portfolio.py --targets A B` |

详细自然触发词映射见 `AGENTS_DEEP.md` Section 十四。

---

## 通用输出格式约束与日常工作流高分示例

> ⚠️ **接入 AI 须知 - 微信端格式红线 (CRITICAL)**:
> 本系统最终会将所有报告与指令推送到微信等移动端进行展示。因此，接入本仓库的任何其他 AI 进程，在生成最终报告、执行说明或回答日常工作流时，**必须 100% 严格遵守以下“去渲染纯文本”规范，绝对禁止发明任何复杂的 Markdown 标记**：
> 1. **禁用 `#` 标题**：一律禁止使用 Markdown 的 `#` 系列标题（如 `#`、`##`、`###` 等）。分节标题一律使用 emoji 符号 + 普通文本（如 `🧭 简要分析`）独立成行表示。
> 2. **禁用 `---` / `***` 水平线**：一律禁止使用 Markdown 水平线。不同小节之间请直接使用一个空行进行物理区隔。
> 3. **禁用 `**` 粗体**：一律禁止使用任何加粗语法。若需突显重点或数值，请通过精心设计的 emoji（如 `📍` `❗` `🔴` `🟢`）或前缀空格实现，切勿包裹 `**`。
> 4. **禁用 `|...|` 表格**：一律禁止使用 Markdown 语法渲染的表格。如果多列数据需要并列显示，请用中文全角竖线 `｜` 或空格在单行内直接隔开（如 `现价：59.33元 ｜ 涨幅：+2.70%`）。
> 5. **禁用 `>` 块引用**：一律禁止使用块引用。
> 6. **禁用 `*` / `-` 列表符与带圈数字（如 `①` `②` `③`）**：一律禁止使用这些 Markdown 列表语法或特殊序号字符。若有子项，请直接分行或用空格缩进，或使用中文点号 `·` 引导。
> 7. **首行强制规范**：每种移动端/微信端输出的前两行，必须且只能以约定的固定 emoji 和标题开头（例如 `分析报告 —` 或 `📌`）。
>
> 违背以上红线将直接导致移动端/微信端渲染破碎。以下是微信端日常循环中 7 大核心步骤的**高分满分输出范例**，请严格对照模仿：

### 1. 盘中快速验票
* 动作命令：`python 01-功能包-packages/trader/scripts/final_report.py --target <NAME>`
* 用途：值不值得看，给出当前位置、该买该卖、多少钱动手。
* 满分标准输出示例：

分析报告 — 南网科技（688248）

现价 59.33（+2.70%）
  MA5：59.63 ｜ MA10：60.74 ｜ MA20：60.60 ｜ MA30：59.72

🎯 蓄势期 → 低吸试盘
  基础状态：防守观察 ｜ 体系结论：防守观察

  缠论:拉升段(盘整)·看涨
  动量:MACD柱为正(偏多)·看涨
  威科夫：暂无明确信号 · 中性
  2方看多 vs 1方看空

📍 决策
  状态：防守观察
  空仓：在 57.50-58.64元 试探买 5%，止损 56.11

  56.11 止损（跌破支撑，趋势破坏）
  57.50 ← 试探买 5%（蓄势期，盈亏比 2.1:1，65% 胜率回本，止损 56.11）
  59.33 当前位置
  59.84 → 减仓 20%（冲不动即减）

筹码：57.20 · 59.80 · 61.50 ｜ 获利55%

📊 股性与历史回测
  买入信号 12次 ｜ 8胜4负 ｜ 胜率 67% ｜ 平均 +3.2%

✅ 亮点：处于蓄势偏强期，买方力量占优
⚠️ 风险：上方 59.84 元有压力位，需放量确认

当前池 5/10，回复 1 入池

### 2. 盘中盯盘预警
* 动作命令：`python 01-功能包-packages/t0/scripts/final_t0.py --target <NAME> --monitor`
* 用途：盘中实时大单异动，谁在买谁在卖，价格到没到触发位。
* 满分标准输出示例（非交易时间输出为空）：

🎯 南网科技（688248） 现价 59.33 靠近关注价

09:35 主动买入 1752万 / 3000手
09:40 主动卖出 2777万 / 4774手
14:35 主动买入 4178万 / 6939手（大单异动）

### 3. 盘后单票复盘
* 动作命令：`python 01-功能包-packages/review/scripts/final_review.py --target <NAME>`
* 用途：今天走势怎么看，大单资金什么态度，五层理论打分多少，明天关键位在哪。
* 满分标准输出示例：

📌 南网科技 ｜ 2026-05-28盘后复盘

结论：弱修复观察，还不能按反转处理。

📊 关键价位
下方支撑：59.33 / 58.44 / 57.50
上方压力：60.26 / 62.69 / 65.95

🔎 分时走势与大单回溯
09:35 主动买入 1752万 偏试盘
14:35 主动买入 4178万 偏试盘
14:55 主动买入 1872万 偏试盘
回溯总结：买方更强

📈 五层打分
结构 65 ｜ 量价 45 ｜ 筹码 50 ｜ 动能 50

### 4. 确认跟踪入池
* 动作命令：`python 01-功能包-packages/trader/scripts/final_pool.py add --target <NAME>`
* 用途：无特定微信面板输出，执行完毕后将票加入 `~/.trader/pool.json` 即可。分析报告末尾会提示「回复 1 一步入池」。

### 5. 池内排序
* 动作命令：`python 01-功能包-packages/trader/scripts/final_pool.py rank`
* 用途：看选股池里哪只最好、买多少、止损在哪。
* 满分标准输出示例：

选股池 ｜ 大盘偏弱，防守优先

🥇 南网科技 ｜ 评分：76
    防守观察 现价 14.29
    买（观察区）13.93-14.07 ｜ 仓位 10% ｜ 止损 13.50

🥈 中国铝业 ｜ 评分：72
    防守观察 现价 12.85
    买（观察区）12.53-12.66 ｜ 仓位 10% ｜ 止损 12.14

🥉 三安光电
 4. 宁德时代
 5. 紫金矿业

### 6. 明日作战表
* 动作命令：`python 01-功能包-packages/trader/scripts/final_pool.py plan`
* 用途：明天盯哪几只、什么价格触发、仓位纪律。
* 满分标准输出示例：

选股池盘后分析 — 2026-05-29
容量 5/10 ｜ 执行 0 ｜ 观察 5 ｜ 淘汰 0

明日优先级
🥇 南网科技（观察）
  只看 14.79 是否站稳，不买
🥈 中国铝业（观察）
  只看 13.30 是否站稳，不买
🥉 三安光电（观察）

评分总览
  南网科技 总分76 缠33/45 威18/30 筹25/25

仓位纪律：执行首次1成 确认加至3成 单票风险1R 总仓位≤5成。明天只重点盯南网科技和中国铝业，不触发不买。

### 7. 仓位轮动与管理
* 动作命令：`python 01-功能包-packages/portfolio/scripts/final_portfolio.py --targets <NAME1> <NAME2>`
* 用途：两只票怎么分配资金、当前浮盈浮亏、轮动触发条件。
* 满分标准输出示例：

轮动仓位 — 中国铝业 + 南网科技

🔔 决策：不动

📊 持仓速览
  中国铝业：现价 11.30 成本 11.50 浮盈 -1.7%
  南网科技：现价 59.33 成本 35.99 浮盈 +64.9%

📈 仓位建议
  中国铝业 → 19%
  南网科技 → 22%
  现金 → 59%

💡 操作信号
  南网科技
    🟢 站上 59.87 → 看高 63.46（最多赚 6.0%）
    🔴 跌破 56.11 → 清仓（最多亏 5.4%）

---

## 持久化文件

| 文件 | 用途 | 写入者 | 读取者 |
|------|------|--------|--------|
| `~/.trader/signals.jsonl` | Signal Contract v2 事件流 | t0 / trader | review / trader |
| `~/.trader/pool.json` | 选股池状态 | trader | trader |
| `~/.trader/pending.json` | 待确认池 | trader | trader |
| `~/.trader/last_plan.json` | 上次作战计划 | trader | trader |
| `~/.trader/calibrated_params.json` | 自校准参数（zone_width等）| self_calibration | structure_core |
| `~/.trader/tick_cache/` | Tick 缓存，盘后复盘可读取真实资金异动 | t0 / review | review |
| `~/.t0-trader/state.json` | T0 盯盘缓存 | t0 | t0 |
| `~/.review-trader/state.json` | 复盘缓存 | review | review |
| `~/.trader/signal_results.jsonl` | 信号结算结果（胜率/盈亏比） | signal_tracker / self_calibration | review / self_calibration |
| `~/.trader/chip_history.json` | 筹码搬家历史快照（用于对比底部筹码峰变化） | chip_migration_monitor | chip_migration_monitor / review |
| `~/.trader/last_target.txt` | 上次分析标的 | final_report | final_report |

---

## 自检与验证命令

```bash
# 运行单元与集成测试（包含 718 个核心计算类测试 + 系统集成测试）
python3 -m pytest 02-共享模块-shared/tests/
python3 -m pytest 01-功能包-packages/*/tests/

# 运行各 Skill 格式与逻辑自检
# （check_all.py 已废弃，运行 pytest 即可覆盖格式校验）

# 信号历史老数据迁移与去重工具
python3 02-共享模块-shared/scripts/signal_migration_tool.py

# 全局打包并自动安装各 Hermes 技能包
python3 02-共享模块-shared/scripts/pack_all.py

# T0 盯盘 cron 入口（crontab 每 5 分钟）
# */5 9-14 * * 1-5  cd /path/to/project && python3 scripts/t0_cron.py --pool

# [2.3新增] 盘后/周末离线参数自校准（输出 ~/.trader/calibrated_params.json）
python3 02-共享模块-shared/scripts/self_calibration.py
```

---

## 深度参考

| 需要了解 | 去哪里找 |
|---------|----------|
| 完整架构、算法详情 | `AGENTS_DEEP.md` |
| 各 Skill 具体实现 | 各 Skill 目录下 `SKILL.md` |
| 命令绝对真理 | 各 Skill 目录下 `references/commands.md` |
| 输出格式绝对真理 | 各 Skill 目录下 `references/output-template.md` + `output-style-guide.md`（review 技能用 `review_output-contract.md` 等替代） |
| Signal Contract 全字段 | `AGENTS_DEEP.md` Section 六 |
| 测试体系 | `02-共享模块-shared/tests/TESTING.md` |
| 待实施改进计划 | `docs/_deprecated/superpowers/` |
| 已知问题 | `docs/_deprecated/issues-and-fix-plan.md` |

---

## 待实施变更

| 文档 | 用途 | 状态 |
|------|------|------|
| `docs/_deprecated/buy-zone-accessibility-fix-plan.md` | 低位买入位可达性问题修复计划（P0-P3） | 已归档（待实施） |

---

## 包结构与 import 规范

所有核心计算模块位于 `02-共享模块-shared/trader_shared/` 包下。标准 import 方式：

```python
from trader_shared.light_data import to_float, fetch_quote
from trader_shared.chan_core import chanlun_analysis
from trader_shared.config import LOOKBACK_DAYS
from trader_shared.cache_utils import get_cached, set_cached
from trader_shared.data_provider import get_provider
```

开发环境安装：`pip install -e .`（项目根目录下）
测试运行：`python3 -m pytest 02-共享模块-shared/tests/`

缓存管理命令：
```bash
trader.py cache warm              # 盘后预缓存选股池
trader.py cache clear             # 清空全部缓存
trader.py cache clear --type daily  # 只清日线缓存
```
