# Commands — Quick Reference

> **This file is the absolute truth for all commands.** Do not generate commands from memory.

```bash
python3 scripts/final_portfolio.py --targets 南网科技 中国铝业 三安光电
python3 scripts/final_portfolio.py --snapshot /path/to/portfolio_snapshot.json
python3 scripts/final_portfolio.py --record buy --name 南网科技 --shares 1000 --cost 54.00
python3 scripts/final_portfolio.py --record sell --name 南网科技 --shares 500
python3 scripts/validate_output.py /path/to/portfolio.md
python3 scripts/self_check.py
```

`--record buy/sell` writes to `~/.trader/positions.json`. `--targets` auto-merges cost/share data.
