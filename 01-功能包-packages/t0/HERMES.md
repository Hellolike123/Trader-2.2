# t0

盘中盯盘 + T0 执行卡。

## ⚠️ 输出规则（最高优先级）

双模式输出：
- 给人看时：脚本输出即最终格式，不要修改（保持原样）
- 给 AI 用时：读 JSON 输出，基于数据做解读和建议
- 解读时每个建议必须引用 JSON 中的具体字段
- 禁止从 Markdown 输出解析数据做判断

## 入口脚本

- `scripts/t0_run.py --target <股票名> --once --output json` — 单次检查（AI 消费）
- `scripts/t0_run.py --target <股票名> --once` — 单次检查（给人看）
- `scripts/t0_run.py --target <股票名> --monitor` — 持续监控
