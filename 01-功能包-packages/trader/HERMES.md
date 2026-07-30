# trader

A股交易决策辅助系统。单票分析 + 选股池管理。

## 输出规则

见 `references/agent-rules.md`（原样贴出、禁默认 JSON、微信红线）。  
取数由脚本按宿主分流：`TRADER_HOST=hermes|workbuddy|local`（也可探测 `~/.workbuddy/connectors`）。  
WorkBuddy：资金流优先 Tdx；有 Tushare 时行情仍走 Tushare，无 token 时 provider 标 mootdx（报价/日线仍可能走腾讯链）。  
打包勿默认 stamp `trader_host=hermes`；WorkBuddy 包请显式 `TRADER_HOST=workbuddy`。  
不要让用户再贴 token；不要让 Agent 自己调 MCP 拼数。

## 入口脚本（cwd = skill 根）

- `scripts/final_report.py --target <股票名> --output markdown` — 单票（默认）
- `scripts/final_pool.py <子命令>` — 选股池

编排细节：`references/agent-quickstart.md`。

## 验证命令

```bash
python3 scripts/validate_output.py
→ VALID_TRADER_OUTPUT=OK 才算通过；否则重跑脚本，不要手修格式
```
