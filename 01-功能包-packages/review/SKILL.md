---
name: review
description: Use for after-hours A-share review, portfolio rotation, and signal tracking. Run the script and paste markdown; do not hand-write panels.
---

# Review — 执行包装器

盘后复盘 + 仓位轮动 + 信号追踪。硬规则：`references/agent-rules.md`。

## 做且只做

1. 读 `references/agent-quickstart.md`（若未读）
2. 跑下表命令
3. 成功 → stdout 整段放进 code fence 原样贴出 → Exit
4. 失败 → 只报错误；禁止手写/编造评分或价位

```bash
python3 scripts/final_review.py --target <NAME>
```

| 需求 | 命令 |
|------|------|
| 单票复盘 | `python3 scripts/final_review.py --target <NAME>` |
| 盘中复盘 | `... --session midday` |
| 多票对比 | `python3 scripts/final_review.py --compare A B C` |
| 仓位轮动 | `python3 scripts/final_portfolio.py --targets A B` |
| 信号追踪 | `python3 scripts/final_tracker.py` |
| 决策体检 | `python3 scripts/final_tracker.py checkup --days 90` |

仓库根 cwd 时前缀改为 `python3 01-功能包-packages/review/scripts/...`。

## 硬停

- 未跑脚本 → 不回答复盘结论
- 禁止默认 `--output json`；禁止手写面板
- 禁止预读全部 references；禁止编造评分/价位

## 先问用户

标的未指明 / 对比名单不清 → 先澄清。否则直接执行。
