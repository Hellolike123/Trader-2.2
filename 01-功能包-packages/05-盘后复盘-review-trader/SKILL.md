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
📌 {name}｜{date}盘后复盘
收盘 {price}（{change_pct}）
成本 {cost}｜浮盈亏 {pnl}

结论
{conclusion_text}
{model_summary}

📊 关键价位
支撑：{support} 元 ｜ 压力：{pressure} 元 ｜ 止损：{stop} 元 ｜ 止盈：{take} 元
站上 {pressure} = 转强    跌破{support} = 修复失效

⚠️ 最大风险
放量跌破 {support}
含义：关键支撑失败，短线修复假设失效。

🔎 分时走势
{intraday_summary}

📈 五层打分
结构{s}/量价{v}｜筹码{c}｜动能{m}
缠论：{text}
威科夫：{text}
筹码：{text}
资金行为：{text}

🎯 信号判断
偏多：
  ✓ {bullet}
  ! 警惕：{bullet}

👉 一句话
{one_liner}
明天只有放量站稳 {pressure} 才算确认；否则继续按短线修复看。
如果放量跌破 {support}，这次修复判断失效。
```

Additional optional sections (present if data available):
- `ATR数据不足` or `💡 参考信息  日均波动约 ±{atr}元（占总价{pct}%）`
- `MACD（判断大方向）：目前{偏多/偏空/中性}...`
- `💰 筹码分布（近60日量价粗算）` with price/percentage/level
- `📋 今日信号回溯` with historical signals from signals.jsonl

Midday review output is the same format with `午间复盘` in the title instead of `盘后复盘`.

Compare output:
```text
📌 多股复盘比较｜{date}
结论：
明天主盯{name}，副盯{name}。
排序依据是结构、量价、筹码压力、动能和持仓适配。
排序：
1）{name}|{state}|总分 {score}|压力 {price}
...
主盯：
{name}|{state}
理由：...
副盯：
...
只观察 / 先防守：...
明日动作：
筹码密集区（近60日量价粗算）：...
```

### Old Output Detection
If output contains markdown tables, T0 execution cards, `执行价`, or the two-table `trader` action report format, rerun the script and return stdout verbatim.

## Rules
- Single review uses five-layer theory: 缠论结构, 威科夫量价, 筹码峰/成本结构, 资金行为, 动能确认.
- Main-force wording must be probabilistic: `嫌疑`, `可能`, `证据不足`. Do not state 主力吸筹/锁仓 as fact.
- Cost is optional. If provided, use for floating P/L; do not require it.
- Cache is written to `~/.review-trader/state.json` for `--compare-recent`.
