# Hermes Contract

This package is a script-output skill.

Hermes must run one of:

```bash
python3 scripts/final_t0.py --target <股票名或代码>
python3 scripts/final_t0.py --target <股票名或代码> --monitor --once
```

Return stdout exactly. Do not summarize, restyle, translate, shorten, add analysis, or add follow-up text. If monitor mode prints nothing, return nothing. If the script fails, return only the command error.

Scheduled cron jobs must use `--monitor --once` and should not use `--verbose`; no output means no push. The skill must be installed in the same runtime that executes the cron job. A local install does not fix a remote cron worker such as `/home/abc/.agents/skills/...`.
