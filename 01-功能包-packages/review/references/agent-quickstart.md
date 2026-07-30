# Review Agent 快路径

目标：跑脚本 → code fence 原样贴出复盘/轮动/追踪面板 → 停。禁止先批量读 references。  
硬规则：同目录 `agent-rules.md`。

## 默认（cwd = 本 skill 根）

```bash
python3 scripts/final_review.py --target <NAME>
```

仓位轮动：`python3 scripts/final_portfolio.py --targets A B`  
信号追踪：`python3 scripts/final_tracker.py`  
决策体检：`python3 scripts/final_tracker.py checkup --days 90`

- 成功：stdout 整段 code fence 贴出 → Exit
- 禁止改写、手写面板、编造评分/价位
- 优先渲染输出；禁止默认 `--output json`
- 失败：只报失败原因；禁止凭记忆编面板

## 硬门控

1. 未跑脚本 → 不回答复盘结论
2. 评分/价位必须来自脚本输出
3. 遵守 `agent-rules.md` 微信红线（脚本已渲染则勿再排版）

## JSON 回退（仅需要时）

才读 `ai-guide.md`；结论必须能指到具体字段。

## 按需文档（勿预读）

| 何时 | 读什么 |
|------|--------|
| 复盘格式 | `review_output-contract.md` |
| 轮动 / 追踪 | `portfolio_output-contract.md` / `tracking_output-contract.md` |
| JSON 字段 | `ai-guide.md` |
| 命令 | `commands.md`、`portfolio_commands.md`、`tracking_commands.md` |

## Exit

输出完成后即停止。
