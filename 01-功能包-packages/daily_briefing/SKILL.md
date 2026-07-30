---
name: daily-briefing
description: Use when producing the daily A-share briefing from pool/candidates. Run briefing.py and paste stdout; do not hand-write layered panels.
---

# daily-briefing — 执行包装器

候选池分析、排序、分层简报。硬规则：`references/agent-rules.md`。

## 做且只做

1. 读 `references/agent-quickstart.md`（若未读）
2. 跑下表命令
3. 成功 → stdout 整段放进 code fence 原样贴出 → Exit
4. 失败 → 只报错误；禁止手写/编造分层面板

```bash
python3 scripts/briefing.py
```

| 需求 | 命令 |
|------|------|
| 默认简报 | `python3 scripts/briefing.py` |
| 指定票 | `python3 scripts/briefing.py --watch A B C` |
| 候选文件 | `python3 scripts/briefing.py --candidates candidates.json` |
| 刷新全池 | `python3 scripts/briefing.py --refresh` |
| 分析并入池 | `python3 scripts/briefing.py --candidate A --add` |

仓库根 cwd 时前缀改为 `python3 01-功能包-packages/daily_briefing/scripts/...`。

## 硬停

- 未跑脚本 → 不回答分层/次日操作结论
- 禁止默认 `--json` / `--output json`；禁止手写面板
- 禁止预读策略说明；禁止补脚本未写的买卖建议

## 先问用户

名单范围不清（无池、无 watch、无 candidates）→ 先澄清。否则直接执行。
