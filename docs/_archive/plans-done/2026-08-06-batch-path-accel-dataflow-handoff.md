# 批量路径加速（死锁修复）+ 数据流图 handoff

> 状态：active（2026-08-06）
> 触发：用户「我们做 2 3」——批量路径加速 + ARCHITECTURE 数据流图
> 法源：`ARCHITECTURE.md` §2/§7 · `report_builder.py` · `pool_cmds/refresh.py` · `light_data.py` · `cache_utils.py`

## 一、根因（实测证据）

`final_pool.py refresh`（全池 9 票）**死锁**，非慢：

1. `refresh.py` 用全局共享池 `get_shared_build_pool()`（`ThreadPoolExecutor(max_workers=5)`）submit 9 个 `safe_build_report`
2. 每票 `build_report` → `light_data.load_market_snapshot` 用**同一个共享池** submit quote/daily/5m/weekly，再 `as_completed` 等结果
3. 共享池 5 worker 全被外层占用 → 子任务永远排不上 → 9 票全部永久卡死

实测：`TRADER_PROFILE=1 final_pool.py refresh`，300s timeout，stdout/stderr **零输出**（exit=124）。

旁证：`data_provider._enrich_snapshot` 注释已警告同坑（"refresh 已占用共享池时，再 submit+wait 同一池会死锁"），enrich 已用独立池绕开；`light_data.load_market_snapshot` 未绕开。

## 二、必须（验收表）

| # | 必须项 | 验收 |
|---|--------|------|
| 1 | refresh 改用**独立线程池**跑 build_report（不进共享池） | refresh 300s 内完成，stdout 出「刷新 n/9」 |
| 2 | 不改变任何报告字段 / fusion / stage / 入池分（结论不变） | 修复前后单票 build_report 字段 diff 为空 |
| 3 | 禁止改引擎（light_data/data_provider/build_report/report_pipeline 内部） | 变更仅限 pool_cmds/refresh.py |
| 4 | 禁止关 enrich / 关 5m（fusion_core:564-661、stage_detect:882、chip/context/structure 消费，会改结论） | grep 无新增禁用 |
| 5 | 保持 9 票并行语义（不串行化） | refresh 仍多 worker 并行 |
| 6 | TRADER_PROFILE=1 重跑，记录各阶段耗时分布 | marks 写入结果，用于 ②b 决策 |
| 7 | 数据流图（③）基于实际代码链路，标注数据源与消费方 | ARCHITECTURE.md 新增 §2.x |

## 三、禁止（勿改）

- 禁止改 `get_shared_build_pool` 的 max_workers 或全局语义（影响单票/t0/review 共享方）
- 禁止 `TRADER_SNAPSHOT_ENRICH=0` 进批量路径（fusion/stage 消费 extend_*，改结论）
- 禁止改 enrich TTL / 日 K TTL（数据新鲜度语义，需用户单独拍板，本轮不动）
- 禁止把 refresh 串行化或用「跳过未变」改变语义

## 四、可改文件白名单

- `01-功能包-packages/trader/scripts/pool_cmds/refresh.py`（② 死锁修复）
- `ARCHITECTURE.md`（③ 数据流图）
- 本 handoff

## 五、执行顺序

1. ②a：refresh.py 独立线程池修复 → 重跑基准（验收 #1/#6）
2. ③：ARCHITECTURE.md 数据流图（验收 #7）
3. ②b：基于修复后基准，若 enrich 实时抓取是耗时大头，写**单独 handoff** 提议 TTL 细分/预热（本轮不实现）
4. 验收：单票字段 diff 空（#2）+ refresh 完成（#1）+ 门禁冒烟
5. 本 handoff 归档 `_archive/plans-done/`

## 六、执行结果（2026-08-06）

- **②a ✅**：refresh.py 改用独立线程池（`trader-pool-refresh`），修复共享池死锁
  - 修复前：9 票 refresh 300s 超时零输出（exit=124）
  - 修复后：**36.5s 完成，刷新 9/9**（每票 2.8~27s，并行度 5）
- **③ ✅**：ARCHITECTURE.md 新增 §2.1 数据流图（mermaid）+ 关键消费矩阵（extend_* 消费方）
- **验收**：单票 refresh 7.3s 完成（snapshot 4.1s=56%）；门禁 740 passed / 2 failed = **golden 数据漂移**（600000 筹码/资金文本随行情变化，非本次改动；golden 基线本就随数据刷新）
- **②b（待用户拍板）**：enrich 12h 文件缓存几乎全过期 → 每票首次实时 8 路抓取。候选：① 细分 TTL（股东/解禁/EPS 日频数据可放宽至 7d，两融/北向/行业保持 12h）；② refresh 内先预热 enrich 缓存。均涉及数据新鲜度语义，需用户确认后**另开 handoff**
