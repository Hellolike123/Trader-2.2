# 信号追踪（TRADER TRACKING）

**一句话：** 展示信号准确率面板。看所有信号发出来后，5 天后到底准不准。

**来源：** `~/.trader/signal_results.jsonl`（自动从 `~/.trader/signals.jsonl` 拉取历史价格计算）

## Critical Rule

这是脚本输出型 skill，不是写面板的模板。

必须执行 `scripts/final_tracker.py`，返回 stdout 原文。**不准自己编面板内容。** 无法运行脚本时说 `Trader Tracking skill cannot run in this environment`。

## Commands

Load `references/commands.md` for full command list (absolute truth — never generate commands from memory).

Basic: `python3 scripts/final_tracker.py`
Update: `python3 scripts/final_tracker.py --check`

## Output Contract

Load `references/output-contract.md` (absolute truth — never generate output from memory).

Valid output starts with `📊 信号追踪面板`.
