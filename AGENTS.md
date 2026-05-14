# Trader 2.0 — Agent 快速参考

> 最后更新：2026-05-09
> 代码版本：trader v0.6.0 / t0-trader v0.7.0 / trader-pool v0.1.0 / trader-portfolio v1.0 / trader-shared v0.6.0 / review-trader v0.1.0
> 变更：refactor(skill): extract Commands/Output Contract into references/ — SKILL.md 精简 43%，防 LLM 幻觉

---

## 业务全景

A 股交易决策辅助系统。免费行情 API（腾讯 + 新浪），缠论/威科夫/筹码/ATR/利弗莫尔分析，输出标准化 Markdown 面板。

### 六大 Skill

| Skill | 一句话 | 使用场景 |
|-------|--------|---------|
| `trader` | 单票手机端分析报告 | 新票验票、日常跟踪 |
| `t0-trader` | 盘中 T0 精确执行卡 + 盯盘告警 | 盘中高抛低吸执行 |
| `trader-pool` | 选股池全生命周期管理 | 候选池维护、多股排序 |
| `trader-portfolio` | 2-3 只股票轮动仓位计划 | 组合仓位分配 |
| `review-trader` | 盘后五层理论复盘 + 多股对比 | 单日/多股深度复盘 |
| `trader-tracking` | 信号准确率追踪面板 | 看信号历史表现 |

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

### Skill 映射总结

| 需求 | 命令 |
|------|------|
| 分析一只票 | `trader script --target <NAME>` |
| 价格监控 | `trader script --target <NAME> --output alert-text` |
| T0 盯盘单次检查 | `t0-trader script --target <NAME> --monitor --once` |
| 入池 | `trader-pool script add --target <NAME>` |
| 池内排序 | `trader-pool script rank` |
| 仓位轮动 | `trader-portfolio script --targets A B` |
| 盘后复盘 | `review-trader script --target <NAME>` |

详细自然触发词映射见 `AGENTS_DEEP.md` Section 十四。

---

## Skill 职责与 Output Contract

### trader（单票分析）

**Output Contract**:

```
分析报告 — {name}（{code}）
现价 + MA5/MA10/MA20/MA30 + ATR
🌍 中证1000 大盘环境（趋势/涨跌/建议）
📍 决策（状态 + 空仓/有底仓/加仓指引）
T0 参考（低吸/高抛/止损价位，止跌确认）
❗ 关键价位（止损 | 减仓 | 止跌 | 支撑）
🧭 简要分析（结构/量价/筹码/动能）
```

**禁止项**: 无 `#` / 表格 / `*`粗体。禁止词: `必涨`、`做T`、`主力入场第一枪` 等 30+ 项（见 `AGENTS_DEEP.md` Section 七）。

### t0-trader（盘中T0）

**Output Contract**:

```
🎯 T0 盯盘助理
{name}（{symbol}）｜现价 xx.xx（+/-x.xx%）
🔍 扫描 / 🚩 关键价位 / 🕒 今日关键事件 / 💰 仓位管控 / 👀 下一步只盯
Monitor alert alert only. 只有 `已触发` 才能输出执行价。
```

### trader-pool（选股池）

**命令集**: `analyze` `add` `add-pending` `confirm-to-pool` `show` `show-pending` `rank` `compare` `plan` `review` `remove` `archive-exited`

**入池打分**: 缠论 45 + 威科夫 30 + 筹码 25 = 100。≥70 执行；≥55 观察；触及防守线拒绝/淘汰。

### trader-portfolio（仓位轮动）

**Output Contract**:

```
轮动仓位 — {名1} + {名2} + ...
📌 组合（主仓/副仓/观察/现金）
🎯 操作（加仓/降仓/止损规则）
📊 仓位与信号（ATR + 金字塔级）
🎯 关键价位 / 💡 分析
```

### review-trader（盘后复盘）

**五层理论**: 缠论结构 / 威科夫量价 / 筹码峰 / 资金行为 / 动能确认 → 各 0-100 分

**Signal Backtrack**: 自动读 `~/.trader/signals.jsonl` 回溯历史信号。

### trader-tracking（信号追踪）

**Output Contract**: 从 `~/.trader/signal_results.jsonl` 生成信号准确率面板（胜率、涨跌比、盈亏比）。

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
| `~/.t0-trader/state.json` | T0 盯盘缓存 | t0-trader | t0-trader |
| `~/.review-trader/state.json` | 复盘缓存 | review-trader | review-trader |

---

## 常见坑 & 注意事项

| 问题 | 原因 | 修复 |
|------ | ------ | ------ |
| 中证1000数据不足 | INDEX_CODE 未定义 | `config.py` 设置 `INDEX_CODE = "000852.SH"` |
| 数据包加载冲突 | `sys.path` 错误 | 用 `from trader_shared import X`，不用硬编码路径 |
| 输出格式被改写 | Hermes 没找到 `_meta.json` | zip 结构 flat，确保 `_meta.json` 在 root |
| 脚本无法运行 | `pack_all.py` 漏了核心模块 | `copy_shared()` 必须包含 chan/wyckoff/momentum |

详细见 `AGENTS_DEEP.md` Section 十三。

---

## 自检命令

```bash
# 各 skill 自带 output 校验
python3 scripts/self_check.py                       # 应输出 *_OUTPUT_VALIDATOR=OK

# 打包
python3 02-共享模块-shared/scripts/pack_all.py       # 生成 zip → 03-安装包-dist/releases/
```

---

## Skill 结构变更（2026-05-09）

SKILL.md 精简：Commands/Output Contract 移至 `references/` + "绝对真理"声明防止 LLM 幻觉。
详见 `AGENTS_DEEP.md` Section 变更日志。

---

> 完整架构、算法详情、Signal Contract 全字段、测试体系、目录结构、维护指南 → 见 `AGENTS_DEEP.md`

---

## 待实施变更

| 文档 | 用途 | 状态 |
|------|------|------|
| `docs/buy-zone-accessibility-fix-plan.md` | 低位买入位可达性问题修复计划（P0-P3） | 待实施 |
