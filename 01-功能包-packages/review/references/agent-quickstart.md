# Review Agent 快路径

目标：跑脚本 → 原样贴出复盘/轮动/追踪面板 → 停。禁止先批量读 references。  
硬规则详见同目录 `agent-rules.md`。

## 默认命令（cwd = 本 skill 根目录）

```bash
python3 scripts/final_review.py --target <NAME>
```

仓位轮动：`python3 scripts/final_portfolio.py --targets A B`  
信号追踪：`python3 scripts/final_tracker.py`

成功 → stdout 原样输出 → 停。  
优先渲染输出；仅需要时再 `--output json`。

## 硬门控（markdown 成功时）

1. 未跑脚本 → 不回答复盘结论
2. 评分/价位必须来自脚本输出，禁止编造
3. 遵守 `agent-rules.md` 微信红线

## JSON 失败回退时（才读）

再读 `ai-guide.md`；结论必须能指到具体字段。

## 按需文档（勿预读）

| 何时 | 读什么 |
|------|--------|
| 复盘格式 | `review_output-contract.md` |
| 轮动 / 追踪 | `portfolio_output-contract.md` / `tracking_output-contract.md` |
| JSON 字段 | `ai-guide.md` |
| 命令 | `commands.md`、`portfolio_commands.md`、`tracking_commands.md` |

## Exit

输出完成后即停止。
