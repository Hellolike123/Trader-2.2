# trader

A股交易决策辅助系统。单票分析 + 选股池管理。

## ⚠️ 输出规则（最高优先级）

双模式输出：
- 给人看时：脚本输出即最终格式，不要修改（保持原样）
- 给 AI 用时：读 JSON 输出，基于数据做解读和建议
- 解读时每个建议必须引用 JSON 中的具体字段
- 禁止从 Markdown 输出解析数据做判断

格式约束（给人看时）：
1. 不要用 ##/### 标题、**粗体**、|表格|、>引用、- 列表
2. 输出后必须跑 validate_output.py 校验
3. 校验不通过 → 重新跑脚本，不要自己修格式

## 入口脚本

- `scripts/final_report.py --target <股票名> --output json` — 单票分析（AI 消费）
- `scripts/final_report.py --target <股票名>` — 单票分析（给人看）
- `scripts/final_pool.py <子命令>` — 选股池管理

## 验证命令

```bash
python3 scripts/validate_output.py
→ 返回 VALID_TRADER_OUTPUT=OK 才算通过
→ 返回错误信息 → 重新跑脚本
```
