# T0 Agent 快路径

目标：1 条命令 → code fence 原样贴出结构参考卡 → 停。禁止先批量读 references。  
硬规则：同目录 `agent-rules.md`。

## 默认（cwd = 本 skill 根）

```bash
python3 scripts/final_t0.py --target <NAME>
```

盯盘单次：`--monitor --once`。持续：`--monitor`。  
有持仓可加 `--cost` / `--position`；降本：`--t-mode cost_cut`。

- 成功：stdout 整段 code fence 贴出 → Exit
- 禁止改写、手写面板、补「可执行/可低吸/三重共振买」
- 失败：只报失败原因；禁止凭记忆补结构

## 首次持仓引导

若 `~/.trader/position.json` 不存在：先问标的/成本/底仓股数/倒 T 现金并写入，再跑脚本。文件已存在则直接读。

## 硬门控

1. 未跑脚本 → 不报盘中结论
2. 产品定位：人读结构仪表盘，不是自动下单指令
3. 遵守 `agent-rules.md` 微信红线（脚本已渲染则勿再排版）

## JSON 回退（仅渲染失败时）

才读 `ai-guide.md`。`partial` / `degraded` 须提示数据不足。

## 按需文档（勿预读）

| 何时 | 读什么 |
|------|--------|
| 格式校验 | `output-template.md`、`output-style-guide.md` |
| JSON/字段 | `ai-guide.md` |
| 命令全集 | `commands.md` |

## Exit

输出完成后即停止。
