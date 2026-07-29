# Commands — review (tracking)

> **This file is the absolute truth for all commands.** Do not generate commands from memory.

```bash
python3 scripts/final_tracker.py
python3 scripts/final_tracker.py --check
python3 scripts/final_tracker.py --stock 南网科技
python3 scripts/final_tracker.py --days 30
python3 scripts/final_tracker.py checkup --days 90
python3 scripts/final_tracker.py --checkup --days 90
```

`--check` checks for updates (calculated from `~/.trader/signals.jsonl`), then display panel.
`checkup` / `--checkup`：决策体检，对比「系统允许买」vs「系统不让买」的 5 日胜率（读 `allow_new_recommend` / `decision_view` / `discipline`）。

新信号须带决策字段才会进分组：验票时加 `--write-signal`，例如  
`python3 01-功能包-packages/trader/scripts/final_report.py --target 南网科技 --write-signal`  
历史无字段的信号仍显示「缺决策字段」，不会伪造次数。
