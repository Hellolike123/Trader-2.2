# Commands — Quick Reference

> **This file is the absolute truth for all commands.** Do not generate commands from memory.

## Commands

```bash
python3 scripts/final_report.py --target 南网科技 --output markdown
python3 scripts/final_report.py --target 南网科技 --output signal-json
python3 scripts/validate_output.py /path/to/report.md
python3 scripts/self_check.py
```

Default user-facing output is validated Markdown. `--output signal-json` is for downstream only.  
Tushare token + HTTP proxy bypass are handled inside the scripts; do not require extra env setup.
