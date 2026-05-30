# Commands — Quick Reference

> **This file is the absolute truth for all commands.** Do not generate commands from memory.

## Single Stock Review

```bash
python3 scripts/final_review.py --target 南网科技 --cost 57.60
python3 scripts/final_review.py --target 南网科技 --session midday
```

## Multi-Stock Compare

```bash
python3 scripts/final_review.py --compare 南网科技 中国铝业
python3 scripts/final_review.py --compare-recent
```

## Validate

```bash
python3 scripts/validate_output.py /path/to/review.md
python3 scripts/self_check.py
```
