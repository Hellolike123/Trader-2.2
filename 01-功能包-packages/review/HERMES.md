# review

A股盘后复盘 + 仓位轮动 + 信号统计。

## ⚠️ 输出红线（最高优先级）

1. 脚本输出的文本是最终格式，不要修改任何内容
2. 不要添加脚本输出以外的解释、建议或总结
3. 不要用 ##/### 标题、**粗体**、|表格|、>引用、- 列表
4. 输出后必须跑 validate_output.py 校验
5. 校验不通过 → 重新跑脚本，不要自己修格式
6. 如果用户问格式相关问题，直接引用 output-contract.md

## 入口脚本

- `scripts/final_review.py --target <股票名>` — 单票复盘
- `scripts/final_review.py --compare A B` — 多票对比
- `scripts/final_portfolio.py --targets A B` — 仓位轮动
- `scripts/final_tracker.py` — 信号统计

## 验证命令

```bash
python3 scripts/validate_output.py
→ 返回 VALID_REVIEW_OUTPUT=OK 才算通过
→ 返回错误信息 → 重新跑脚本
```
