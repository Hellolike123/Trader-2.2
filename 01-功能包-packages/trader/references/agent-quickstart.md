# Trader Agent 快路径

目标：1 条命令 → code fence 原样贴出 → 停。禁止先批量读 references。  
硬规则：同目录 `agent-rules.md`。

## 单票（默认 · cwd = 本 skill 根）

```bash
python3 scripts/final_report.py --target <NAME> --output markdown
```

- 成功：stdout 即最终报告 → 整段 code fence 贴出 → Exit
- 禁止改写、摘要、润色、手拼 Markdown、补买卖建议
- 禁止默认 `--output json`
- 失败：只报失败原因；禁止凭记忆编报告

脚本已处理代理与 Tushare；Agent 不必再 export token。  
单票默认区间套（30m×800）；批量更快时再设 `TRADER_CHAN_NESTING=0`。

## 选股池

| 需求 | 命令 |
|------|------|
| 入池 | `python3 scripts/final_pool.py add --target <NAME>` |
| 作战表 | `python3 scripts/final_pool.py plan` |
| 概览 / 排序 | `list` / `rank` |
| 刷新全池 | `python3 scripts/final_pool.py refresh` |

## 当选股器用（cwd = 本 skill 根）

```text
验票（结构）→ python3 ../wyckoff/scripts/final_wyckoff.py --target <NAME>
入池 → python3 scripts/final_pool.py add --target <NAME>
刷新 → python3 scripts/final_pool.py refresh
排序 → python3 scripts/final_pool.py rank  与/或  python3 ../wyckoff/scripts/final_wyckoff.py rank
明日盯 → python3 scripts/final_pool.py plan
```

仓库根等价：`python3 01-功能包-packages/wyckoff/scripts/final_wyckoff.py ...` / `python3 01-功能包-packages/trader/scripts/final_pool.py ...`。  
wyckoff 入池行为软建议；出手/分道仍听 trader。

## 硬门控

1. 未跑脚本 → 不回答行情/出手结论
2. 能出 markdown → 原样输出（code fence），停
3. 不出现 mi姐/Mistery 人设；不补脚本未写内容
4. 遵守 `agent-rules.md` 微信红线（脚本已渲染则勿再排版）

## JSON 回退（仅 markdown 失败时）

才可读 `anti-hallucination.md`、`fusion-guide.md`。  
出手以 `decision_view` 为准；`fusion.weighted_score` 仅仪表。

## 按需文档（勿预读）

| 何时 | 读什么 |
|------|--------|
| 校验/改输出格式 | `output-template.md`、`output-style-guide.md` |
| 池子命令细节 | `pool-commands.md`、`pool-output-contract.md` |
| JSON 回退 | `anti-hallucination.md`、`fusion-guide.md` |
| 命令全集 | `commands.md` |

## Exit

输出完成后即停止。不重跑、不延伸讨论。
