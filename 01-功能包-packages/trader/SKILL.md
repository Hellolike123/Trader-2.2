---
name: trader
description: Use when analyzing a single A-share, managing the stock pool, or producing the short/mid-line dual-track report. Run the script and paste markdown; do not hand-write panels.
---

# Trader — AI 分析师

单票分析 + 选股池。默认中短线双轨报告（🧭 中线｜⚡ 短线）。纪律只收紧出手/仓位，不改 fusion 分与关键价数字。  
共用硬规则：`references/agent-rules.md`。

## 快路径（先做这个）

只读 `references/agent-quickstart.md`（若尚未读过）。然后：

```bash
python3 scripts/final_report.py --target <NAME> --output markdown
```

成功 → 原样贴出 stdout → 停。  
禁止预读全部 references；禁止默认 `--output json`；禁止手写 Markdown。  
Tushare token 与去代理已由脚本/配置处理，Agent 不要再配环境变量、不要因沙箱里 Tushare 探测失败去改代码。

## 命令入口

| 需求 | 命令 |
|------|------|
| 单票报告 | `python3 scripts/final_report.py --target <NAME> --output markdown` |
| 价格监控 | `python3 scripts/final_report.py --target <NAME> --output alert-text` |
| 入池 | `python3 scripts/final_pool.py add --target <NAME>` |
| 作战表 | `python3 scripts/final_pool.py plan` |
| 概览 / 排序 / 刷新 | `list` / `rank` / `refresh` |

JSON 仅当 markdown 失败或需额外字段判断时使用。

## 工作流

1. 跑命令拿 stdout  
2. markdown 成功 → 输出并 Exit  
3. 仅失败时用 `--output json`，再按需读 `anti-hallucination.md` / `fusion-guide.md`  
4. 门控与字段细则见 quickstart「JSON 失败回退」

## 什么时候先问用户

直接执行：「南网科技怎么样」→ 单票；「入池…」→ add；「明日作战表」→ plan；「池子概览」→ list。  
先澄清：未指明标的 / 「帮我看看」范围不清 / 「要不要买」缺标的与价位。

## 按需 references（勿预读）

| 文件 | 何时读 |
|------|--------|
| `agent-quickstart.md` / `agent-rules.md` | 首次使用本 skill |
| `output-template.md` / `output-style-guide.md` | 校验或怀疑格式不对 |
| `pool-commands.md` / `pool-output-contract.md` | 选股池操作 |
| `anti-hallucination.md` / `fusion-guide.md` | JSON 回退 |
| `commands.md` | 需要完整命令表 |

`references/` 仍是契约真理；**按需 read，禁止开工前批量读完。**

## Exit

输出完成后即停止。不重跑、不补脚本未写的延伸建议。
