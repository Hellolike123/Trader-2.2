# Commands — Quick Reference

> **This file is the absolute truth for all commands.** Do not generate commands from memory.

```bash
python3 scripts/final_pool.py analyze --target 南网科技
python3 scripts/final_pool.py add --target 南网科技
python3 scripts/final_pool.py add-pending --target 南网科技
python3 scripts/final_pool.py compare --targets 南网科技 中国铝业
python3 scripts/final_pool.py show
python3 scripts/final_pool.py show-pending
python3 scripts/final_pool.py confirm-to-pool --target 南网科技
python3 scripts/final_pool.py rank
python3 scripts/final_pool.py plan
python3 scripts/final_pool.py review
python3 scripts/final_pool.py remove --target 南网科技
python3 scripts/final_pool.py archive-exited
python3 scripts/validate_output.py /path/to/panel.md
python3 scripts/self_check.py
```

## Remove

从选股池中移除指定标的。匹配规则按 `target` / `name` / `symbol` 依次查找，命中即移除。

```bash
python3 scripts/final_pool.py remove --target <NAME>
```

- `--target`：股票名称或代码（必填）
- 若池中存在该标的，移除后输出 `已移除：{NAME}`
- 若池中未找到，输出 `未找到：{NAME}`，返回码 `4`
- 不影响 `pending.json` 中的待确认记录

## Archive Exited

归档已退出的持仓记录。将状态为 `淘汰` 且超过 7 天未更新的标的从 `pool.json` 移出，写入 `pool_archive.json`。

```bash
python3 scripts/final_pool.py archive-exited
```

-  cutoff 为 7 天：`updated_at <= 今天 - 7 天`
-  被归档的条目追加到 `~/.trader/pool_archive.json`
-  输出 `已归档淘汰记录：{N}`（N 为归档数量）
-  不影响非 `淘汰` 状态的条目
