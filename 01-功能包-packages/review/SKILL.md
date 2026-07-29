---
name: review
description: Use for after-hours A-share review, portfolio rotation, and signal tracking. Run the script and paste markdown; do not hand-write panels.
---

# Review — AI 复盘分析师

盘后复盘 + 仓位轮动 + 信号追踪。五层打分、大单回溯、明日策略。  
共用硬规则：`references/agent-rules.md`。

## 快路径（先做这个）

只读 `references/agent-quickstart.md`（若尚未读过）。然后：

```bash
python3 scripts/final_review.py --target <NAME>
```

成功 → 原样贴出 stdout → 停。  
禁止预读全部 references；禁止默认 `--output json`；禁止手写面板。

## 命令入口

| 需求 | 命令 |
|------|------|
| 单票复盘 | `python3 scripts/final_review.py --target <NAME>` |
| 盘中复盘 | `python3 scripts/final_review.py --target <NAME> --session midday` |
| 多票对比 | `python3 scripts/final_review.py --compare A B C` |
| 仓位轮动 | `python3 scripts/final_portfolio.py --targets A B` |
| 信号追踪 | `python3 scripts/final_tracker.py` |

JSON 仅当渲染失败或需额外字段时使用。

## 工作流

1. 跑命令拿 stdout  
2. markdown 成功 → 输出并 Exit  
3. 仅失败时用 `--output json`，再按需读 `ai-guide.md`（字段门控在该文档）  
4. 禁止编造评分/价位

## 什么时候先问用户

直接执行：「南网科技复盘」→ 单票；「轮动 A B」→ portfolio；「信号追踪」→ tracker。  
先澄清：未指明标的 / 对比名单不清。

## 按需 references（勿预读）

| 文件 | 何时读 |
|------|--------|
| `agent-quickstart.md` / `agent-rules.md` | 首次使用 |
| `review_output-contract.md` | 校验复盘格式 |
| `portfolio_output-contract.md` / `tracking_output-contract.md` | 轮动/追踪格式 |
| `ai-guide.md` | JSON 回退 |
| `commands.md` / `portfolio_commands.md` / `tracking_commands.md` | 命令细节 |

## Exit

输出完成后即停止。不重跑、不补脚本未写的延伸建议。
