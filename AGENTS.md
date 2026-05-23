# Trader 2.3 — Agent 快速参考

> 最后更新：2026-05-23

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
- **[2.3新增] 离线参数自校准器**：`scripts/self_calibration.py` 盘后/周末运行。参数已在 `structure_core.py` 的 `_theory_multipliers` 层 -0 中作为基准自校准倍率加载。
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

## 通用输出格式约束

- `#` 标题 → 禁用（用 emoji 标题替代）
- `---` / `***` 水平线 → 禁用
- `**` 粗体 → 禁用
- `|...|` 表格 → 禁用
- `>` 块引用 → 禁用
- `*` / `-` 列表符号 → 禁用
- 首行必须以固定 emoji 开头（如 `分析报告 —` / `📌`）

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
