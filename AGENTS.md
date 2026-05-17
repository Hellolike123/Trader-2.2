# Trader 2.0 — Agent 快速参考

> 最后更新：2026-05-17

---

## 业务全景

A 股交易决策辅助系统。免费行情 API（腾讯 + 新浪），缠论/威科夫/筹码/ATR/利弗莫尔分析，输出标准化 Markdown 面板。

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
| 分析一只票 | `trader script --target <NAME>` |
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
| `~/.t0-trader/state.json` | T0 盯盘缓存 | t0-trader | t0-trader |
| `~/.review-trader/state.json` | 复盘缓存 | review-trader | review-trader |

---

## 自检命令

```bash
# 各 skill 自带 output 校验
python3 scripts/self_check.py                       # 应输出 *_OUTPUT_VALIDATOR=OK

# 打包
python3 02-共享模块-shared/scripts/pack_all.py       # 生成 zip → 03-安装包-dist/releases/
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
