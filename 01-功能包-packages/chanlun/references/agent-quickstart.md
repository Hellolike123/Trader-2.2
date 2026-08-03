# Chanlun Agent 快路径

目标：一条命令产出缠论 B·中剪报告，随后用 code fence 原样贴出并停止。  
硬规则：同目录 `agent-rules.md`。

## 默认（cwd = 本 skill 根）

```bash
python3 scripts/final_chanlun.py --target <NAME>
```

仓库根 cwd：

```bash
python3 01-功能包-packages/chanlun/scripts/final_chanlun.py --target <NAME>
```

旧薄卡（兼容）：

```bash
python3 scripts/final_chanlun.py --target <NAME> --brief
```

- 成功：stdout 整段放进 code fence 原样贴出，然后停止
- 禁止改写、手写面板或补一买／二买／三买
- 禁止把「中线副读」改写成威科夫中线阶段
- 禁止默认 `--output json`
- 失败：只报失败原因，禁止凭记忆补结构

## 硬门控

1. 未跑脚本，不报缠论结论
2. 卡片只核对结构，不给交易指令
3. 买卖点、笔方向和笔数必须保持脚本原文
4. 遵守 `agent-rules.md` 微信红线

## JSON 回退

仅在 Markdown 渲染失败且确需核对字段时使用 `--output json`。

## Exit

输出完成后立即停止。
