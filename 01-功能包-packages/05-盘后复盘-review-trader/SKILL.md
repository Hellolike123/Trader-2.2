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

## Big-Order Extension
- 盘后按交易日时间轴回看大单在什么时候出现
- 逐段解释每次大单意味着什么
- 统计单笔手数、累计手数、成交金额和连续性
- 判断大单之后的走势是否验证
- 最终给出 有效 / 无效 / 背离 的复盘结论

## Commands
Load `references/commands.md` for full command list (absolute truth — never generate commands from memory).

Single: `python3 scripts/final_review.py --target <股票名>`
Compare: `python3 scripts/final_review.py --compare <股票1> <股票2>`

## Output Contract
Load `references/output-contract.md` (absolute truth — never generate output format from memory).

Must pass old output detection — if banned markers are present, rerun the script.

## Rules
- Single review uses five-layer theory: 缠论结构, 威科夫量价, 筹码峰/成本结构, 资金行为, 动能确认.
- Main-force wording must be probabilistic: `嫌疑`, `可能`, `证据不足`. Do not state 主力吸筹/锁仓 as fact.
- Cost is optional. If provided, use for floating P/L; do not require it.
- Cache is written to `~/.review-trader/state.json` for `--compare-recent`.
