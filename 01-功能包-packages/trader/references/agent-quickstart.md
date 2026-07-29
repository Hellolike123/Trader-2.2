# Trader Agent 快路径

目标：1 条命令 → 原样贴出 → 停。禁止先批量读 references。  
硬规则详见同目录 `agent-rules.md`。

## 单票分析（默认 · cwd = 本 skill 根目录）

```bash
python3 scripts/final_report.py --target <NAME> --output markdown
```

- 成功：stdout 即最终报告，禁止改写、禁止手拼 Markdown
- 失败：再考虑 `--output json`，并只读下方「按需文档」
- 禁止默认使用 `--output json`（整包可达数百 KB）

脚本入口会自动清掉 HTTP 代理并走已配置的 Tushare（`tushare_config.py`）。  
Agent **不必**再 export token，也**不必**手写 `env -u http_proxy ...`。  
单票默认开启区间套（30m×800）。批量/只要更快时再设 `TRADER_CHAN_NESTING=0`。

若降级到腾讯：报告仍可出，可能更慢；不要改策略代码、不要删 token。Cursor 沙箱开发时外网被拦属环境限制，验票请在正式 Agent / 本机终端跑。

## 选股池常用

| 需求 | 命令 |
|------|------|
| 入池 | `python3 scripts/final_pool.py add --target <NAME>` |
| 作战表 | `python3 scripts/final_pool.py plan` |
| 概览 / 排序 | `list` / `rank` |
| 刷新全池 | `python3 scripts/final_pool.py refresh` |

## 硬门控（markdown 成功时）

1. 未跑脚本 → 不回答行情/出手结论
2. 能出 markdown → 原样输出，停
3. 不补充脚本未写的买卖建议；不出现 mi姐/Mistery 人设
4. 遵守 `agent-rules.md` 微信红线

## JSON 失败回退时（才读）

1. 查 `data_status`：`partial` 加警告前缀；`degraded` 只出基础行情
2. 出手以 `decision_view`（共振∧策略∧纪律）为准；`fusion.weighted_score` 仅仪表；`conclusion` / `discipline` 只收紧
3. 再读：`anti-hallucination.md`、`fusion-guide.md`

## 按需文档（勿预读）

| 何时 | 读什么 |
|------|--------|
| 校验/改输出格式 | `output-template.md`、`output-style-guide.md` |
| 池子命令细节 | `pool-commands.md`、`pool-output-contract.md` |
| JSON 回退 | `anti-hallucination.md`、`fusion-guide.md` |
| 命令全集 | `commands.md` |

## Exit

输出完成后即停止。不重跑分析、不延伸讨论。
