---
name: review-trader
description: Generate a validated A-share after-close single-stock review panel or multi-stock review comparison by running scripts/final_review.py. Return stdout verbatim; never handwrite, summarize, shorten, or restyle.
version: 0.2.0-v2-signal-tracking
author: Trader Skill
license: MIT
platforms: [macos, linux]
tags: [finance, stocks, a-share, review, terminal, python]
metadata:
  hermes:
    tags: [Finance, AShare, Review, Terminal, Python]
    requires_toolsets: [terminal]
  openclaw:
    requires:
      bins: [python3]
dependencies: [python3]
repository: local
documentation: SKILL.md
---

# Review Trader

## Critical Rule
This is a script-output skill, not a writing template.

Always run `scripts/final_review.py` and return stdout exactly. Do not compose from memory, summarize, shorten, translate, restyle, add tables, add disclaimers, or add follow-up lines.

## Commands
Single stock review:
```bash
python3 scripts/final_review.py --target 南网科技 --cost 57.60
python3 scripts/final_review.py --target 南网科技 --session midday
```

Multi-stock compare:
```bash
python3 scripts/final_review.py --compare 南网科技 中国铝业
python3 scripts/final_review.py --compare-recent
```

Validate:
```bash
python3 scripts/validate_output.py /path/to/review.md
python3 scripts/self_check.py
```

## Output Contract
Single after-close review (no markdown tables):

```text
📌 股票｜日期盘后复盘
📊 今日状态
📈 走势结构
🔎 信号判断
🎯 明日关键价位
🧭 明日应对
👉 一句话
```

Midday review:

```text
📌 股票｜日期午间复盘
📊 上午状态
📈 上午走势
🔎 信号判断
🎯 午后关键价位
🧭 午后应对
👉 一句话
```

Compare output:

```text
📌 多股复盘比较｜日期
结论： 排序： 主盯： 副盯： 明日动作：
```

## Old Output Detection
If output contains markdown tables, T0 execution cards, `执行价`, or the two-table `trader` action report format, rerun the script and return stdout verbatim.

## Rules
- Single review uses five-layer theory: 缠论结构, 威科夫量价, 筹码峰/成本结构, 资金行为, 动能确认.
- Main-force wording must be probabilistic: `嫌疑`, `可能`, `证据不足`. Do not state 主力吸筹/锁仓 as fact.
- Cost is optional. If provided, use for floating P/L; do not require it.
- Cache is written to `~/.review-trader/state.json` for `--compare-recent`.
