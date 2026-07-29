# trader

A股交易决策辅助系统。单票分析 + 选股池管理。

## ⚠️ 输出规则（最高优先级）

1. **默认**：`python3 scripts/final_report.py --target <股票名> --output markdown`，stdout **原样输出**
2. **禁止默认 `--output json`**；仅 markdown 失败时才用 JSON
3. 禁止手拼 Markdown；微信红线：无 `#`、无 `**`、无 `|` 表格、无 `---`、无 `*/-` 列表
4. Tushare 已配置在包内；脚本会自动直连行情。不要让用户再贴 token / 代理命令

## 入口脚本

- `scripts/final_report.py --target <股票名> --output markdown` — 单票（默认）
- `scripts/final_pool.py <子命令>` — 选股池

编排细节：`references/agent-quickstart.md`。

## 验证命令

```bash
python3 scripts/validate_output.py
→ VALID_TRADER_OUTPUT=OK 才算通过；否则重跑脚本，不要手修格式
```
