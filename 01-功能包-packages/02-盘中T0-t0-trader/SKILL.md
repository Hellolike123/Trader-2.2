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
inputs:
  - name: target
    type: string
    description: A-share stock name or code, for example 南网科技 or 688248.
    required: true
outputs:
  - name: card_or_alert
    type: markdown
    description: Complete validated T0 card, or monitor alert when --monitor is used. Manual card must start with T0 —.
dependencies: [python3]
repository: local
documentation: SKILL.md
---

# T0 Trader

## Critical Rule
This is a script-output skill, not a writing template.

Always run `scripts/final_t0.py` and return stdout exactly. Do not compose from memory, summarize, shorten, translate, restyle, add tables, add disclaimers, or add follow-up lines.

If the script cannot run, return the command error. Do not handwrite a partial card or reuse old examples.

## When to use
- User asks for `T0`, `做T`, `盘中T`, `高抛低吸`, `什么价买`, `什么价卖`, `跌到哪接`, `冲到哪卖`, `盯盘`, or `提醒`.
- Use this for A-share intraday T0 execution support and monitor alerts.
- Do not use this as a full single-stock report; that belongs to `trader`.

## Manual Card Workflow
Run:

```bash
python3 scripts/final_t0.py --target <股票名或代码>
```

Return stdout verbatim.

Manual mode answers:
- 现在买入能不能做。
- 现在卖出能不能做。
- 刚才是否错过买点或卖点。
- 今日发生过哪些关键触发、过期、阻断、失效事件。
- 下一步只需要盯什么。

Manual mode reads the monitor cache for `📜 今日回顾`, but does not write cache.

## Monitor Workflow
Hermes/OpenClaw scheduled monitoring should run one check per scheduled call:

```bash
python3 scripts/final_t0.py --target 中国铝业 --monitor --once --cost 11.50 --position 10000
```

If this command prints nothing, there is no new alert. Return nothing and do not invent a message.

Monitor mode writes cache to `~/.t0-trader/state.json`. Use `--reset-cache` to restart alerts for a target.
When monitor mode emits a real state-change alert, it also appends a `trader_signal_v1` event to `~/.trader/signals.jsonl` for later review. This event is a decision signal only, not an order.
Cron jobs should not pass `--verbose`; verbose mode prints `无新提醒` and is only for manual debugging.
If the cron worker runs remotely, install this skill in that remote worker's skills root. A local `~/.hermes/skills` install does not fix a remote path such as `/home/abc/.agents/skills/...`.

Monitor mode alerts use V2 compact format:

🔔/❌ alerts (trigger/invalidated):
```text
🔔 南网科技 低吸触发
现价 52.73 | 买入 52.65 附近
仓位 底仓10%，最多XXX股
🔥 MACD绿柱缩短 + RSI拐头 | 2个核心信号
⚠️ 大盘偏弱，先做小
止损 49.68 跌破就走
```

- Emoji: 🔔=triggered, ❌=invalidated/expired/blocked
- Must include trigger reason (matched MACD/RSI/VWAP signals)
- Must include 仓位 line and 🌍/⚠️ market warning when available
- Monitor default interval: 3 minutes (--interval 3)
- Only alert on state changes (not every check)

## Commands
Manual T0 assistant:

```bash
python3 scripts/final_t0.py --target 南网科技
python3 scripts/t0_run.py --target 南网科技 --output markdown
python3 scripts/t0_run.py --target 南网科技 --output signal-json
```

Hermes/OpenClaw monitor:

```bash
python3 scripts/final_t0.py --target 中国铝业 --monitor --once --cost 11.50 --position 10000
python3 scripts/final_t0.py --target 中国铝业 --monitor --once --verbose
python3 scripts/final_t0.py --target 中国铝业 --monitor --once --reset-cache
```

Validate:

```bash
python3 scripts/validate_output.py /path/to/t0.md
```

Self-check:

```bash
python3 scripts/self_check.py
```

## Output Contract
Manual card must use this structure and no markdown tables:

```md
T0 — 南网科技  现价 54.91（-2.71%）
xxx（000000.SH）｜现价 xx.xx元（+x.xx%）

📍 当前结论
当前：不动 / 低吸 / 高抛
提醒级别：可执行 / 轻仓做 / 别犯错 / 无
买入：未触发 / 可执行 / 已错过 / 被阻断 / 数据不足 ...
卖出：未触发 / 可执行 / 已错过 / 被阻断 / 数据不足 ...

🎯 今日关键点
低吸观察：xx.xx元以下 / 暂无有效观察价
高抛观察：xx.xx元附近 / 暂无有效观察价
低吸失效：xx.xx元，跌破不接。
高抛取消：xx.xx元，放量站上不卖。

📜 今日回顾
暂无关键事件。

📊 盘中走势
开盘段：...
中段：...
最近：...

📦 仓位建议
当前：不动 / 可做
触发后：单次最多动底仓的 10%-20% / 单次最多动底仓的 20%-30%

🔭 下一步只盯
买入：...
卖出：...
停止：...
```

Monitor alert output is shorter and only appears on executable or risk events:

```md
【T0可执行｜低吸触发】中国铝业
现价：11.95元
状态：观察中 → 已触发
执行参考：11.94元
最高可接受：11.98元，超过不追
失效：11.72元
成本：11.50，当前盈亏：+3.91%
建议T仓：1000-2000股
```

Valid alert titles:
- `【T0可执行｜低吸触发】`
- `【T0可执行｜高抛触发】`
- `【T0轻仓做｜低吸触发】`
- `【T0轻仓做｜高抛触发】`
- `【T0别犯错｜低吸已过期】`
- `【T0别犯错｜高抛已过期】`
- `【T0别犯错｜停止低吸】`
- `【T0别犯错｜停止高抛】`

## Old Output Detection
If output contains any of these, it is invalid and the agent must rerun the script and return stdout verbatim:

```text
T0 执行卡
⏱️ 盘中 T0
📉 低吸计划
📈 高抛计划
🎯 操作提醒
🎯 价格地图
🚦 执行条件
一句话
T0买入价
T0卖出价
T0失效价
低吸价：
高抛价：
买入提醒：
卖出提醒：
规则版本：
数据状态：
今日做法：
当前动作：
先买后卖
先卖后买
📊 今日5分钟线复盘
开盘急杀
止跌尝试
反弹修复
横盘蓄力
```

Valid manual output has no markdown tables, no bullet lists, no bold markers, no blockquotes, and no `##/###` headings.

## Execution Rules
- Only status `已触发` can generate execution price.
- `未触发`, `被阻断`, `数据不足`, and `触发过期` must not output executable buy/sell prices.
- If data is insufficient, non-trading, or T0 net space is too narrow, show `暂无有效观察价`.
- Observation prices are watch levels, not order prices.
- If price has moved beyond the acceptable zone after a trigger, show `已错过`; do not tell the user to chase or dump.
- Low-buy trigger requires completed 5m confirmation; high-sell trigger requires completed 5m failure confirmation.
- RSI uses Wilder smoothing.
- MACD is ignored until at least 35 completed 5m bars exist.
- ICT-Lite is an execution-quality aid only. It cannot independently trigger buy/sell.
- Monitor is alert-only. It never places orders, generates broker orders, or claims an order was submitted.

## Install Rules
Hermes official local skill root is usually `~/.hermes/skills/`. Use `~/.agents/skills/` only if your Hermes config explicitly lists it as an external skill directory.

Prefer the guarded installer from the Trader repository:

```bash
scripts/install_import_zip.sh t0-trader 03-安装包-dist/t0-trader-import.zip --preset hermes
scripts/install_import_zip.sh t0-trader 03-安装包-dist/t0-trader-import.zip --preset openclaw
scripts/install_import_zip.sh t0-trader 03-安装包-dist/t0-trader-import.zip --preset codex
scripts/install_import_zip.sh t0-trader 03-安装包-dist/t0-trader-import.zip --preset codebuddy
scripts/install_import_zip.sh t0-trader 03-安装包-dist/t0-trader-import.zip --preset workbuddy
scripts/install_import_zip.sh t0-trader 03-安装包-dist/t0-trader-import.zip --target-root /path/to/custom/skills
```

When reinstalling the full test bundle, prefer `scripts/reset_install_skills.sh --preset hermes --aggressive-cache` and switch the preset for other agents.

Do not unzip `t0-trader-skill.zip` into `~/.hermes/skills/t0-trader`; that creates double nesting. Correct layouts:

```bash
# import zip
rm -rf ~/.hermes/skills/t0-trader
mkdir -p ~/.hermes/skills/t0-trader
unzip -o t0-trader-import.zip -d ~/.hermes/skills/t0-trader

# skill zip
unzip -o t0-trader-skill.zip -d ~/.hermes/skills
```

After install, verify:

```bash
test -f ~/.hermes/skills/t0-trader/scripts/final_t0.py
cat ~/.hermes/skills/t0-trader/VERSION_STAMP
python3 ~/.hermes/skills/t0-trader/scripts/final_t0.py --target 南网科技 --monitor --once --verbose
```
