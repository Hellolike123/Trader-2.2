---
name: trader
description: Use when analyzing a single A-share, managing the stock pool, or producing the short/mid-line dual-track report. Run the script and paste markdown; do not hand-write panels.
---

# Trader — 执行包装器

单票分析 + 选股池。硬规则：`references/agent-rules.md`。

## 做且只做

1. 读 `references/agent-quickstart.md`（若未读）
2. 跑下表命令
3. 成功 → stdout 整段放进 code fence 原样贴出 → Exit
4. 失败 → 只报错误；禁止手写/编造面板

```bash
python3 scripts/final_report.py --target <NAME> --output markdown
```

| 需求 | 命令 |
|------|------|
| 单票 | `python3 scripts/final_report.py --target <NAME> --output markdown` |
| 入池 | `python3 scripts/final_pool.py add --target <NAME>` |
| 作战表 | `python3 scripts/final_pool.py plan` |
| 概览 / 排序 / 刷新 | `list` / `rank` / `refresh` |

仓库根 cwd 时前缀改为 `python3 01-功能包-packages/trader/scripts/...`。

## 硬停

- 未跑脚本 → 不回答行情/出手
- 禁止默认 `--output json`；禁止手写 Markdown
- 禁止预读全部 references；禁止补脚本未写的建议

## 先问用户

标的未指明 / 「帮我看看」范围不清 → 先澄清。否则直接执行。
