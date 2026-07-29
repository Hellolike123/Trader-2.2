# review

盘后复盘 + 仓位轮动 + 信号追踪。

## 输出规则

见 `references/agent-rules.md`（原样贴出、禁默认 JSON、微信红线）。  
JSON 回退时结论必须能指到具体字段；禁止编造评分/价位。

## 入口脚本（cwd = skill 根）

- `scripts/final_review.py --target <股票名>` — 单票复盘（默认）
- `scripts/final_portfolio.py --targets A B` — 仓位轮动
- `scripts/final_tracker.py` — 信号追踪

Agent 编排见 `references/agent-quickstart.md`。
