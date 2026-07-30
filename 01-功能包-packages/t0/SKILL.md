---
name: t0
description: Use for intraday A-share T0 structure reference cards and monitoring. Run the script and paste markdown; do not hand-write panels or issue executable order language.
---

# T0 — AI 盘中结构参考

盘中结构参考卡（策略 v2.4 行动卡）。顺序：基调 → 点位仓位 → 盈亏测算 → 风控。  
**不做**机械下单指令；禁止「可执行/可低吸/三重共振买」叙事。  
法源：`docs/t0-strategy-v2.md`。共用硬规则：`references/agent-rules.md`。

## 快路径（先做这个）

只读 `references/agent-quickstart.md`（若尚未读过）。然后：

```bash
python3 scripts/final_t0.py --target <NAME>
```

成功 → 原样贴出 stdout → 停。  
禁止预读全部 references；禁止默认 `--output json`；禁止手写面板。

## 今天可不做（使用纪律，不是信号）

- 无底仓：只看结构卡，不讨论做 T，不补「可低吸」
- 振幅/费后空间不够 / 单边日 / 临近涨跌停：结论带「宜不做」，清单折叠 → 人宜不做
- 数据不足：结论为「数据不足，仅现价」→ 勿凭记忆补结构
- 有仓动手时：T仓建议底仓20%-30%（最多一半）；约14:50前平当日T仓
- 禁止 AI 手写补「可低吸 / 可执行 / 去买 / 三重共振买」

## 首次使用引导

用户第一次调用 T0 时，若 `~/.trader/position.json` 不存在，主动询问标的/成本/底仓股数/是否有倒 T 现金，并写入该文件。文件已存在则直接读，不再问。

## 命令入口

| 需求 | 命令 |
|------|------|
| 结构卡 | `python3 scripts/final_t0.py --target <NAME>` |
| 盯盘单次 | `python3 scripts/final_t0.py --target <NAME> --monitor --once` |
| 持续监控 | `python3 scripts/final_t0.py --target <NAME> --monitor` |
| 带持仓 / 纪律 | 加 `--cost` `--position`；`--t-mode` 仅为持仓纪律参考 |
| 台账 | `--ledger` / `--ledger-add ...` |

JSON 仅当渲染失败或需额外字段时使用。

## 工作流

1. 跑命令拿 stdout  
2. markdown 成功 → 输出并 Exit  
3. 仅失败时用 `--output json`，再按需读 `ai-guide.md`  
4. 门控见 quickstart

## 什么时候先问用户

直接执行：「南网科技盘中」→ 结构卡；「帮我盯…」→ `--monitor`。  
先澄清：未指明标的；首次且无 position.json → 引导填持仓。

## 按需 references（勿预读）

| 文件 | 何时读 |
|------|--------|
| `agent-quickstart.md` / `agent-rules.md` | 首次使用 |
| `output-template.md` / `output-style-guide.md` | 校验格式 |
| `ai-guide.md` | JSON 回退 |
| `commands.md` | 完整命令表 |

## Exit

输出完成后即停止。不重跑、不补脚本未写的下单指令。
