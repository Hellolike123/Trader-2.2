# Review Agent 快路径

目标：跑脚本 → 原样贴出复盘/轮动/追踪面板 → 停。禁止先批量读 references。

## 默认命令

```bash
python3 01-功能包-packages/review/scripts/final_review.py --target <NAME>
```

仓位轮动：`python3 01-功能包-packages/portfolio/scripts/final_portfolio.py --targets A B`  
信号追踪：`python3 01-功能包-packages/review/scripts/final_tracker.py`

成功 → stdout 原样输出 → 停。  
优先渲染输出；仅需要时再 `--output json`。

## 硬门控

1. 未跑脚本 → 不回答复盘结论
2. 评分/价位必须来自脚本输出或 JSON 字段，禁止编造
3. 微信红线：无 `#`、无 `**`、无 `|` 表格、无 `---`、无 `*/-` 列表

## 按需文档

| 何时 | 读什么 |
|------|--------|
| 复盘格式 | `review_output-contract.md` |
| 轮动 / 追踪 | `portfolio_output-contract.md` / `tracking_output-contract.md` |
| JSON 字段 | `ai-guide.md` |
| 命令 | `commands.md`、`portfolio_commands.md`、`tracking_commands.md` |

## Exit

输出完成后即停止。
