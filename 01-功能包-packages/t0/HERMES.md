# t0

盘中盯盘 + T0 结构参考卡。

## ⚠️ 输出规则（最高优先级）

1. **默认**：跑脚本渲染输出，stdout **原样输出**，不要改写
2. **禁止默认 `--output json`**；仅需要额外字段时才用 JSON
3. 产品定位为人读结构仪表盘，禁止「可执行/可低吸/三重共振买」指令叙事
4. 微信格式红线：无 `#`、无 `**`、无 `|` 表格、无 `---`、无 `*/-` 列表

## 入口脚本

- `scripts/final_t0.py --target <股票名>` — 单次结构卡（默认）
- `scripts/final_t0.py --target <股票名> --monitor --once` — 盯盘单次
- `scripts/final_t0.py --target <股票名> --monitor` — 持续监控

Agent 编排见 `references/agent-quickstart.md`。
