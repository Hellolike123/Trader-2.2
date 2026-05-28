

## 接手先看

- **版本升级**：当前版本为 Trader 2.3，在 2.2 基础上新增了隐马尔可夫大势检测、贝叶斯概率融合、日内成交量分布以及离线参数自校准四大高级统计模块。
- **单票分析双层状态模型**：`base_status` 负责结构位置层，`theory_status` 负责理论结论层；`state_label` 仅作兼容/展示摘要。
- **信号唯一性契约 (Signal Contract v2)**：基于 SHA256 deterministic hash 的 16 位 Hex 强一致 UUID (`make_signal_id`)，严格规避任何时区/数据抖动造成的重复结算。
- **双源热备行情 HA**：`MarketDataSourceController` 接管行情数据通道，mootdx 发生 1.5 秒硬超时或连续 3 次失败时，秒级自动 fallback 至 Tencent HTTP / Sina API，以 `data_status="partial"` 标注数据完备度。
- **智能决策融合层 (Decision Fusion Core)**：通过 Scenario Priority Filter 动态分配结构与动量权重（极值区 80% 权重偏斜），且基于 Belief Priority 冲突消解机制过滤动量噪音。
- **大势参数自适应 (Regime Multipliers)**：根据 `market_env` 大盘牛熊环境因子动态缩放 `zone_width` / `confirm_buffer` / `stop_buffer`。
- **[2.3新增] HMM 大势状态检测器**：`hmm_regime.py` 基于纯 numpy Baum-Welch + Viterbi。已深度整合进 `market_env.py` 及下游 `fusion_core.py` / `structure_core.py`。大势判定从纯均线驱动升级为「均线 + HMM 前瞻」双效驱动（高置信度 HMM 状态会自动前瞻修正 `level`，且 `structure_core` 直接复用避免重复抓包）。
- **[2.3新增] 贝叶斯概率决策融合**：`bayesian_fusion.py` 用乘积规则融合三路专家后验概率。已完整集成在 `fusion_core.py` 中。默认关闭（安全过渡），通过设置环境变量 `BAYESIAN_FUSION=true` 激活，激活后将全面接管传统经验权重，实现基于纯概率后验的最优交易动作决策。
- **[2.3新增] 日内成交量分布 (Volume Profile)**：`volume_profile.py` 计算 POC 控制节点与 Value Area 70% 成交量密集区。已嵌入 `decision_core.py` 的突破确认判定 `_check_theory_breakout`，通过微观日内量价验证过滤假突破。
- **[2.3新增] 离线参数自校准器**：`scripts/self_calibration.py` 支持分层搜索，基于 HMM regime 对历史信号分桶搜优（`bull` / `bear` / `range` / `global`），并引入盈亏比加权胜率模型（`WinRate * ProfitFactor`）仿真打分。参数由 `structure_core.py` 的 `_theory_multipliers` 层按当前 HMM 大势动态消费并进行多级回退兼容。
- **[2.3新增] 动态衰减与空间去重筹码分布**：`chip_distribution.py` 摒弃原有静态累加，实现基于时序 `turnover_rate` 换手折旧的动态筹码曲线，并引入基于局部极大值与空间/价格过滤（间距 $\ge 4\%$ 且 $\ge 4$ bins）的独立筹码峰提取算法，供复盘与仓位控制等技能跨模块全局共享。
- **[2.3新增] 信号生命周期与日志合并**：废弃 `signal_log.jsonl` 等多个冗余文件，将所有 T0 事件、单票分析信号、手动结果回填统一收口至单一可信源 `~/.trader/signals.jsonl`，并由继承自 `os.PathLike` 的原生路径代理 `DynamicPathProxy` 提供透明、防 pytest 缓存污染的无缝 Mock 支持。
- **[2.3新增] 斐波那契黄金挂单位 (Golden Bid)**：`structure_core.py` 自动从缠论笔中计算 38.2%/50%/61.8% 黄金分割回调价，并与当前低吸价格区间求交集，计算出高置信度的「黄金挂单位」（显示于 `📍 决策` 列表的空仓低吸参考旁）。
- 真正的输出格式以 `01-功能包-packages/01-单票分析-trader/references/output-contract.md` 为准。
- 需要看实现时，先看 `01-功能包-packages/01-单票分析-trader/scripts/run_analysis.py`。

---

## 业务全景

A 股交易决策辅助系统。免费行情 API（腾讯 + 新浪），缠论 / 威科夫 / 筹码 / ATR / 利弗莫尔分析，输出标准化 Markdown 面板。

当前核心契约是双层状态模型：
- `base_status` 负责结构位置，描述现在站在什么位置
- `theory_status` 负责理论结论，描述按当前体系算不算转强
- `state_label` 现在只是兼容/展示层摘要，偏向理论结论，不再是主契约
- 旧的 `scene` 语义还会出现在部分兼容代码里，但不应再当成主状态理解

接入本仓库的 AI 协同系统优先阅读本页，随后查阅对应技能目录下的 「output-contract.md」 和 「SKILL.md」 以统一输出契约。

---

## Skill 速查表

| Skill | 一句话 | 版本 | 入口脚本 |
|-------|--------|------|---------|
| `trader` | 单票手机端分析报告 | `0.3.0-action-report` | `scripts/final_report.py` |
| `t0-trader` | 盘中 T0 精确执行卡 + 盯盘告警 | `0.5.0-watch-assistant` | `scripts/final_t0.py` |
| `trader-pool` | 选股池全生命周期管理 | `0.1.0-pool` | `scripts/final_pool.py` |
| `trader-portfolio` | 2-3 只股票轮动仓位计划 | `0.1.2-contract` | `scripts/final_portfolio.py` |
| `review-trader` | 盘后五层理论复盘 + 多股对比 | `0.1.0-review-v1` | `scripts/final_review.py` |
| `trader-tracking` | 信号准确率追踪面板 | `0.1.0-track-v1` | `scripts/final_tracker.py` |

> ⚠️ `trader-compare` 已废弃，能力迁入 `trader-pool compare`

---

## 推荐工作流

```
新票验票 → trader
确认跟踪 → trader-pool add
池内排序 → trader-pool rank
明日作战表 → trader-pool plan
盘中执行 → t0-trader (monitor)
盘后复盘 → review-trader / trader-pool review
仓位轮动 → trader-portfolio
信号回溯 → review-trader (读 signals.jsonl)
```

### Skill 命令映射

| 需求 | 命令 |
|------|------|
|分析一只票 | `trader script --target <NAME>` |
| 价格监控 | `trader script --target <NAME> --output alert-text` |
| T0 盯盘单次检查 | `t0-trader script --target <NAME> --monitor --once` |
| 入池 | `trader-pool script add --target <NAME>` |
| 池内排序 | `trader-pool script rank` |
| 仓位轮动 | `trader-portfolio script --targets A B` |
| 盘后复盘 | `review-trader script --target <NAME>` |
| 移除出池 | `trader-pool script remove --target <NAME>` |
| 归档已退出 | `trader-pool script archive-exited` |

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
* 动作命令：`trader script --target <NAME>`
* 用途：值不值得看，给出当前位置、该买该卖、多少钱动手。
* 满分标准输出示例：

分析报告 — 南网科技（688248）

现价：59.33元（+2.70%）
MA5：59.63 ｜ MA10：60.74 ｜ MA20：60.60 ｜ MA30：59.72

🧭 简要分析
基础状态：防守观察 ｜ 体系结论：防守观察

📍 决策
状态：防守观察
  空仓：在 57.50-58.64元 试探买 5%, 止损 56.11
  有底仓：反弹 59.84 冲不动就减 10-20%

❗ 关键价位
56.11  ← 止损位
57.50  ← 防守位
59.33  ← 当前位置
59.84  ← 确认位

✨ 亮点与风险
当前处于防守位附近，适合轻仓试探。

### 2. 盘中盯盘预警
* 动作命令：`t0-trader script --target <NAME> --monitor`
* 用途：盘中实时大单异动，谁在买谁在卖，价格到没到触发位。
* 满分标准输出示例（非交易时间输出为空）：

🎯 南网科技（688248） 现价 59.33 靠近关注价

09:35 主动买入 1752万 / 3000手
09:40 主动卖出 2777万 / 4774手
14:35 主动买入 4178万 / 6939手（大单异动）

### 3. 盘后单票复盘
* 动作命令：`review-trader script --target <NAME>`
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
* 动作命令：`trader-pool script add --target <NAME>`
* 用途：无特定微信面板输出，执行完毕后将票加入 `~/.trader/pool.json` 即可。

### 5. 池内排序
* 动作命令：`trader-pool script rank`
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
* 动作命令：`trader-pool script plan`
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
* 动作命令：`trader-portfolio script --targets <NAME1> <NAME2>`
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
| `~/.trader/signals.jsonl` | Signal Contract v1 事件流 | t0 / trader | review / pool / portfolio |
| `~/.trader/pool.json` | 选股池状态 | trader-pool | trader-pool |
| `~/.trader/pending.json` | 待确认池 | trader-pool | trader-pool |
| `~/.trader/last_plan.json` | 上次作战计划 | trader-pool | trader-pool |
| `~/.trader/calibrated_params.json` | 自校准参数（zone_width等）| self_calibration | structure_core |
| `~/.t0-trader/state.json` | T0 盯盘缓存 | t0-trader | t0-trader |
| `~/.review-trader/state.json` | 复盘缓存 | review-trader | review-trader |

---

## 自检与验证命令

```bash
# 运行单元与集成测试（包含 485 个核心计算类测试 + 系统集成测试）
python3 -m pytest 02-共享模块-shared/tests/

# 运行各 Skill 格式与逻辑自检
python3 scripts/check_all.py

# 信号历史老数据迁移与去重工具
python3 02-共享模块-shared/scripts/signal_migration_tool.py

# 全局打包并自动安装各 Hermes 技能包
python3 02-共享模块-shared/scripts/pack_all.py

# [2.3新增] 盘后/周末离线参数自校准（输出 ~/.trader/calibrated_params.json）
python3 02-共享模块-shared/scripts/self_calibration.py
```

---

## 深度参考

| 需要了解 | 去哪里找 |
|---------|---------|
| 完整架构、算法详情 | `AGENTS_DEEP.md` |
| 各 Skill 具体实现 | 各 Skill 目录下 `SKILL.md` |
| 命令绝对真理 | 各 Skill 目录下 `references/commands.md` |
| 输出格式绝对真理 | 各 Skill 目录下 `references/output-contract.md` |
| Signal Contract 全字段 | `AGENTS_DEEP.md` Section 六 |
| 测试体系 | `02-共享模块-shared/tests/TESTING.md` |
| 待实施改进计划 | `docs/superpowers/INDEX.md` |
| 已知问题 | `docs/issues-and-fix-plan.md` |

---

## 待实施变更

| 文档 | 用途 | 状态 |
|------|------|------|
| `docs/buy-zone-accessibility-fix-plan.md` | 低位买入位可达性问题修复计划（P0-P3） | 待实施 |
