# daily-briefing Agent 快路径

目标：1 条命令 → code fence 原样贴出简报 → 停。禁止先批量读 references。  
硬规则：同目录 `agent-rules.md`。

## 默认（cwd = 本 skill 根）

```bash
python3 scripts/briefing.py
```

| 需求 | 命令 |
|------|------|
| 指定票 | `python3 scripts/briefing.py --watch A B C` |
| 候选文件 | `python3 scripts/briefing.py --candidates <path>` |
| 刷新全池 | `python3 scripts/briefing.py --refresh` |
| 分析并入池 | `python3 scripts/briefing.py --candidate A --add` |

- 成功：stdout 整段 code fence 贴出 → Exit
- 禁止改写、摘要、手写分层、补买卖建议
- 禁止默认 `--json` / `--output json`
- 失败：只报失败原因；禁止凭记忆编简报

## 硬门控

1. 未跑脚本 → 不回答执行区/观察区等结论
2. 能出面板 → 原样输出（code fence），停
3. 遵守 `agent-rules.md` 微信红线（脚本已渲染则勿再排版）

## JSON 回退（仅需要时）

才用 `--output json` 或 `--json`；结论必须能指到脚本字段。

## Exit

输出完成后即停止。不重跑、不延伸讨论。
