# Hermes Contract

This package is a script-output skill for Trader Pool candidate management.

Hermes must map the user-facing triggers to these commands:

```bash
python3 scripts/final_pool.py add --target <股票名或代码>
python3 scripts/final_pool.py plan
python3 scripts/final_pool.py review
python3 scripts/final_pool.py show
```

Return stdout exactly. Do not summarize, restyle, translate, shorten, add analysis, or add follow-up text. If the script fails, return only the command error.
