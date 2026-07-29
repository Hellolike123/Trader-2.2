# review

盘后复盘 + 仓位轮动 + 信号追踪。

## ⚠️ 输出规则（最高优先级）

1. **默认**：跑脚本渲染输出，stdout **原样输出**，不要改写
2. **禁止默认 `--output json`**；仅需要额外字段时才用 JSON
3. JSON 回退时：结论必须能指到具体字段；禁止编造评分/价位
4. 微信格式红线：无 `#`、无 `**`、无 `|` 表格、无 `---`、无 `*/-` 列表

## 入口脚本

- `scripts/final_review.py --target <股票名>` — 单票复盘（默认）
- `scripts/final_review.py --target <股票名> --output json` — 仅需要时
- `scripts/final_portfolio.py --targets A B` — 仓位轮动
- `scripts/final_tracker.py` — 信号追踪

Agent 编排见 `references/agent-quickstart.md`。
