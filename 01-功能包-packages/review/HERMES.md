# Hermes Contract

This package is a script-output skill combining review, portfolio, and tracking.

Hermes must run one of:

```bash
# 盘后复盘
python3 scripts/final_review.py --target <股票名或代码> --cost <成本价>
python3 scripts/final_review.py --target <股票名或代码> --cost <成本价> --session midday
python3 scripts/final_review.py --compare <股票1> <股票2> ...
python3 scripts/final_review.py --compare-recent

# 仓位轮动
python3 scripts/final_portfolio.py --targets <股票1> <股票2>

# 信号追踪
python3 scripts/final_tracker.py
```

Return stdout exactly. Do not summarize, restyle, translate, shorten, add analysis, or add follow-up text. If the script fails, return only the command error.
