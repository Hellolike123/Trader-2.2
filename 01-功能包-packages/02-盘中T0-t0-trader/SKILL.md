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

## Commands
Manual T0 card:
```bash
python3 scripts/final_t0.py --target 南网科技
```

Monitor single check:
```bash
python3 scripts/final_t0.py --target 南网科技 --monitor --once
```

Validate:
```bash
python3 scripts/validate_output.py /path/to/t0.md
python3 scripts/self_check.py
```

## Output Contract
Manual card must start with `T0 —` and use this structure with no markdown tables:

```text
T0 — 南网科技  现价 54.91（-2.71%）

📍 当前结论
当前：不动 / 低吸 / 高抛
买入：未触发 / 可执行 / 已错过 / 被阻断 / 数据不足
卖出：未触发 / 可执行 / 已错过 / 被阻断 / 数据不足

🎯 今日关键点
低吸观察：xx.xx元以下
高抛观察：xx.xx元附近
低吸失效：xx.xx元，跌破不接。
高抛取消：xx.xx元，放量站上不卖。

📜 今日回顾
暂无关键事件。

📊 盘中走势
开盘段：...
中段：...
最近：...

📦 仓位建议
触发后：单次最多动底仓的 10%-20%

🔭 下一步只盯
买入：... 卖出：... 停止：...
```

Monitor alert output only appears on state changes:

```text
🔔 南网科技 低吸触发 | 现价 52.73 | 买入 52.65 附近
```

Or with `--verbose`:

```text
【T0可执行｜低吸触发】中国铝业
现价：11.95元 | 执行参考：11.94元 | 失效：11.72元
```

Valid alert titles: `【T0可执行｜低吸触发】`, `【T0可执行｜高抛触发】`, `【T0轻仓做｜...】`, `【T0别犯错｜...】`.

## Old Output Detection
If output contains any of these, rerun the script and return stdout verbatim:

```text
T0 执行卡
⏱️ 盘中 T0
📉 低吸计划
📈 高抛计划
规则版本：
数据状态：
今日做法：
当前动作：
先买后卖
先卖后买
```

Valid manual output has no markdown tables, no bullet lists, no bold markers, no blockquotes, and no `##/###` headings.

## Rules
- Only status `已触发` can generate execution price.
- `未触发`, `被阻断`, `数据不足`, `触发过期` must not output executable buy/sell prices.
- Observation prices are watch levels, not order prices.
- Monitor is alert-only. Never claims an order was placed.
- Monitor writes cache to `~/.t0-trader/state.json`. Use `--reset-cache` to restart alerts.
- If output is empty (no alert), return nothing.
