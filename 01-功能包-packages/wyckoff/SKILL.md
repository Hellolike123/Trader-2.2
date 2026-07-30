---
name: wyckoff
description: Use for A-share Wyckoff structure reference cards and pool accumulation-chain ranking. Run the script and paste markdown; do not hand-write panels or issue buy/sell orders.
---

# Wyckoff — 威科夫结构参考

人读威科夫结构卡：阶段 / 吸筹链 / 事件 / TR / 失效提示。  
引擎复用 `trader_shared` 的 `wyckoff_core` / `wyckoff_view` / 行情模块；**不作**交易总司令。  
禁止「可执行 / 宜买 / 可低吸 / 三重共振买」叙事。出手仍以 trader 分道与 `decision_view` 为准。  
共用硬规则：`references/agent-rules.md`。

## 快路径（先做这个）

只读 `references/agent-quickstart.md`（若尚未读过）。然后：

```bash
python3 scripts/final_wyckoff.py --target <NAME>
```

池内链排序：

```bash
python3 scripts/final_wyckoff.py rank
```

成功 → 原样贴出 stdout → 停。  
禁止预读全部 references；禁止默认 `--output json`；禁止手写面板。

## 今天可不做（使用纪律，不是信号）

- 不把链进度写成「该买了」
- 不把本 Skill 的 rank 当成池分道（可盯/等齐/先别碰）
- 数据不足：结论为「数据不足，仅现价」→ 勿凭记忆补事件
- 禁止 AI 手写补买卖指令

## 命令入口

| 需求 | 命令 |
|------|------|
| 单票结构卡 | `python3 scripts/final_wyckoff.py --target <NAME>` |
| 池内链排序 | `python3 scripts/final_wyckoff.py rank` |

JSON 仅当渲染失败或需额外字段时使用。

## 工作流

1. 跑命令拿 stdout  
2. markdown 成功 → 输出并 Exit  
3. 仅失败时用 `--output json`  
4. 门控见 quickstart

## Exit

输出完成后即停止。不重跑、不补脚本未写的下单指令。
