# T0 Agent 快路径

目标：跑脚本 → 原样贴出结构参考卡 → 停。禁止先批量读 references。

## 默认命令

```bash
python3 01-功能包-packages/t0/scripts/final_t0.py --target <NAME>
```

盯盘单次：`--monitor --once`。持续：`--monitor`。  
有持仓可加 `--cost` / `--position`；降本：`--t-mode cost_cut`。

成功 → stdout 原样输出 → 停。  
禁止手写面板；禁止把评分写成「可执行/可低吸/三重共振买」指令。

## 硬门控

1. 未跑脚本 → 不报盘中结论
2. 产品定位：人读结构仪表盘，不是自动下单指令
3. 微信红线：无 `#`、无 `**`、无 `|` 表格、无 `---`、无 `*/-` 列表

## 按需文档

| 何时 | 读什么 |
|------|--------|
| 格式校验 | `output-template.md`、`output-style-guide.md` |
| JSON/字段 | `ai-guide.md`（仅需要时） |
| 命令全集 | `commands.md` |

## Exit

输出完成后即停止。
