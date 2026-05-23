---
name: t0-trader
description: Generate a validated A-share intraday T0 card or monitor alert by running scripts/final_t0.py. Requires terminal + python3. Return stdout verbatim.
version: 0.6.0-v2-compact
author: Trader Skill
license: MIT
platforms: [macos, linux]
tags: [finance, stocks, a-share, t0, monitor, terminal, python]
metadata:
  hermes:
    tags: [Finance, AShare, T0, Monitor, Terminal, Python]
    requires_toolsets: [terminal]
  openclaw:
    requires:
      bins: [python3]
dependencies: [python3]
repository: local
documentation: SKILL.md
---

# T0 Trader

## Critical Rule
This is a script-output skill, not a writing template.

Always run `scripts/final_t0.py` and return stdout exactly. Do not compose from memory, summarize, shorten, translate, restyle, add tables, add disclaimers, or add follow-up lines. If the script cannot run, return the command error.

## Big-Order Extension
- 盘中在价格接近关注区时，识别逐笔成交、分时连续大单和盘口配合
- 输出关注区附近的大单确认提醒
- 提醒等级为 观察 / 注意 / 强提醒，默认偏保守
- 逐笔成交为主，买卖都看，连续同向才升级提醒
- 输出保持简短，适合盘中盯盘

## Commands
Load `references/commands.md` for full command list (absolute truth — never generate commands from memory).

Manual: `python3 scripts/final_t0.py --target <股票名>`
Monitor single: `python3 scripts/final_t0.py --target <股票名> --monitor --once`

## Output Contract
Load `references/output-contract.md` (absolute truth — never generate output format from memory).

Must pass old output detection — if any banned marker is present, rerun the script.

## Rules
- Only status `已触发` can generate execution price.
- `未触发`, `被阻断`, `数据不足`, `触发过期` must not output executable buy/sell prices.
- Observation prices are watch levels, not order prices.
- Monitor is alert-only. Never claims an order was placed.
- Monitor writes cache to `~/.t0-trader/state.json`. Use `--reset-cache` to restart alerts.
- If output is empty (no alert), return nothing.
