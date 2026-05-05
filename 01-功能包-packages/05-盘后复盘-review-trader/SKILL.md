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

## When to use
- User asks for 单票复盘, 盘后复盘, 今日复盘, 明日怎么应对, or wants a WeChat-readable stock review.
- User asks to compare recently reviewed stocks, 明天先看谁, 多股复盘比较, or 谁更值得盯.
- Do not use this for T0 intraday execution prices; that belongs to `t0-trader`.
- Do not use this for the short single-stock action report; that belongs to `trader`.

## Commands
Single stock after-close review:

```bash
python3 scripts/final_review.py --target 南网科技 --cost 57.60
python3 scripts/final_review.py --target 南网科技 --output json
```

Single stock midday review:

```bash
python3 scripts/final_review.py --target 南网科技 --cost 57.60 --session midday
```

Compare stocks directly:

```bash
python3 scripts/final_review.py --compare 南网科技 中国铝业 三安光电
```

Compare recently reviewed stocks from cache:

```bash
python3 scripts/final_review.py --compare-recent
```

Validate and self-check:

```bash
python3 scripts/validate_output.py /path/to/review.md
python3 scripts/self_check.py
```

## Output Contract
Single after-close review output must use this order and no markdown tables:

```text
📌 股票｜日期盘后复盘
📊 今日状态
📈 走势结构
🔎 信号判断
🎯 明日关键价位
🧭 明日应对
👉 一句话
```

Single midday review uses the same format but with midday labels:

```text
📌 股票｜日期午间复盘
📊 上午状态
📈 上午走势
🔎 信号判断
🎯 午后关键价位
🧭 午后应对
👉 一句话
```

Compare output must start with:

```text
📌 多股复盘比较｜日期
```

and include:

```text
结论：
排序：
主盯：
副盯：
只观察 / 先防守：
明日动作：
```

## Rules
- Single review uses the five-layer theory model: 缠论结构, 威科夫量价, 筹码峰/成本结构, 资金行为, 动能确认.
- `--session close` is the default after-close review; `--session midday` is a noon review focused on the afternoon plan.
- This first version uses engineering approximations, not a full canonical Chanlun center algorithm or exact chip distribution.
- Main-force wording must be probabilistic: `嫌疑`, `可能`, or `证据不足`. Do not state 主力吸筹/锁仓 as fact.
- Cost is optional. If provided, use it for floating P/L and cost pressure in the output; do not require it.
- Outside/inside volume is optional. If unavailable, hide it.
- Cache is written to `~/.review-trader/state.json` for `--compare-recent`.
- Do not output markdown tables, T0 execution cards, `执行价`, or the two-table `trader` action report.
