# Hermes Contract

This package is a script-output skill.

Hermes must run:

```bash
python3 scripts/final_portfolio.py --targets <股票1> <股票2> ...
python3 scripts/final_portfolio.py --snapshot <portfolio_snapshot.json>
```

Return stdout exactly. Do not summarize, restyle, translate, shorten, add analysis, or add follow-up text. If the script fails, return only the command error.

For machine-readable downstream consumption, `python3 scripts/portfolio_run.py --targets <股票1> <股票2> ... --output json` includes validated `trader_signal_v1` objects under `signal_summaries`. Do not show that JSON to users unless explicitly requested.
