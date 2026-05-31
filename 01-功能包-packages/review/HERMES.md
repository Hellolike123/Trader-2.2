# review

盘后复盘 + 仓位轮动 + 信号追踪。

## ⚠️ 输出规则（最高优先级）

双模式输出：
- 给人看时：脚本输出即最终格式，不要修改（保持原样）
- 给 AI 用时：读 JSON 输出，基于数据做解读和建议
- 解读时每个建议必须引用 JSON 中的具体字段
- 禁止从 Markdown 输出解析数据做判断

## 入口脚本

- `scripts/final_review.py --target <股票名> --output json` — 单票复盘（AI 消费）
- `scripts/final_review.py --target <股票名>` — 单票复盘（给人看）
- `scripts/final_review.py --all` — 全池复盘
- `scripts/final_portfolio.py --targets A B` — 仓位轮动
- `scripts/final_tracker.py --tracking` — 信号追踪
