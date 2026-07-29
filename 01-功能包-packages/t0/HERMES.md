# t0

盘中盯盘 + T0 结构参考卡。

## 输出规则

见 `references/agent-rules.md`（原样贴出、禁默认 JSON、微信红线）。  
产品定位：人读结构仪表盘，禁止「可执行/可低吸/三重共振买」指令叙事。

## 入口脚本（cwd = skill 根）

- `scripts/final_t0.py --target <股票名>` — 单次结构卡（默认）
- `scripts/final_t0.py --target <股票名> --monitor --once` — 盯盘单次
- `scripts/final_t0.py --target <股票名> --monitor` — 持续监控

Agent 编排见 `references/agent-quickstart.md`。
