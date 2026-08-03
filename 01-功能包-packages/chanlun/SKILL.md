---
name: chanlun
description: Use for A-share Chanlun B-slim structure reports (daily wave + weekly secondary read). Run the script and paste markdown unchanged; do not hand-write signals or issue orders.
---

# Chanlun — 执行包装器

缠论 B·中剪结构报告（默认）+ 旧薄卡（`--brief`）。硬规则见 `references/agent-rules.md`。
产品定位：核对日线/周线的笔、段、中枢和引擎买卖点；不改写周线威科夫中线阶段。

## 做且只做

1. 读 `references/agent-quickstart.md`（若未读）
2. 跑命令
3. 成功后把 stdout 整段放进 code fence 原样贴出，然后停止
4. 失败只报错误，禁止手写或补全结构

```bash
python3 scripts/final_chanlun.py --target <NAME>
```

旧薄卡：

```bash
python3 scripts/final_chanlun.py --target <NAME> --brief
```

仓库根 cwd 时使用：

```bash
python3 01-功能包-packages/chanlun/scripts/final_chanlun.py --target <NAME>
```

## 硬停

- 未跑脚本，不报缠论结构结论
- 禁止手补一买、二买、三买或卖点
- 禁止使用“宜买、可执行、可低吸、该买了、三重共振买”等指令词
- 禁止把中线缠论副读写成中线阶段定论
- 禁止默认 `--output json`，禁止预读全部 references

## 先问用户

标的未指明时先澄清；否则直接执行。
