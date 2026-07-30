---
name: wyckoff
description: Use for A-share Wyckoff structure reference cards and pool accumulation-chain ranking. Run the script and paste markdown; do not hand-write panels or issue buy/sell orders.
---

# Wyckoff — 执行包装器

威科夫结构卡 + 池内吸筹链排序。硬规则：`references/agent-rules.md`。  
产品定位：人读结构卡，不是交易总司令；出手仍以 trader 分道与 `decision_view` 为准。

## 做且只做

1. 读 `references/agent-quickstart.md`（若未读）
2. 跑下表命令
3. 成功 → stdout 整段放进 code fence 原样贴出 → Exit
4. 失败 → 只报错误；禁止手写/编造面板

```bash
python3 scripts/final_wyckoff.py --target <NAME>
```

| 需求 | 命令 |
|------|------|
| 单票结构卡 | `python3 scripts/final_wyckoff.py --target <NAME>` |
| 池内链排序 | `python3 scripts/final_wyckoff.py rank` |

仓库根 cwd 时前缀改为 `python3 01-功能包-packages/wyckoff/scripts/...`。

## 硬停

- 未跑脚本 → 不报威科夫结论
- 禁止手补「可执行 / 宜买 / 可低吸 / 该买了 / 三重共振买」
- 禁止把本 Skill 的 rank 当成 trader 分道（可盯/等齐/先别碰）
- 禁止默认 `--output json`；禁止预读全部 references

## 先问用户

标的未指明且不是 `rank` → 先澄清。否则直接执行。
