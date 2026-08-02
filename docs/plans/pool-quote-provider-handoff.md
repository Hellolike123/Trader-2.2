# 池价刷新统一走 Provider（并行）— Agent Handoff

> **状态**: mother_law（实现中）· 2026-08-02  
> **基线**: `main` @ #49 后（与 #50 signal-fusion 独立；本 PR 不依赖 #50）  
> **分支**: `cursor/pool-quote-provider-1c6b`  
> **双 Agent**: 写落地 / 查对照；查完修完再 PR。

---

## 0. 法源

1. [`ARCHITECTURE.md`](../../ARCHITECTURE.md) §5.1：数据 SSOT = `market_types` + `data_provider` / `get_provider`；新写勿绕过 provider 直调 `light_data`。  
2. [`docs/designs/resonance-and-orchestration.md`](../designs/resonance-and-orchestration.md) §2.2 数据层：行情/缓存/HA；上层只吃 snapshot/quote。  
3. [`AGENTS.md`](../../AGENTS.md)「改代码去哪」：选股池逻辑在 `pool_cmds/*`；引擎/数据在 `trader_shared/`。  
4. 现状问题：`pool_cmds/plan_view._refresh_pool_prices` 与 `watch.py` **串行** `light_data.fetch_quote` + 自建 `HttpClient`，绕过 `get_provider()`。

---

## 1. 必须

| ID | 项 |
|----|-----|
| M1 | `_refresh_pool_prices` **禁止**直接 `from trader_shared.light_data import fetch_quote`；改经 `get_provider().fetch_quote(sec)`（或薄封装 `data_access.get_quote` / 新建批量 API） |
| M2 | 多票刷新须**并行**（`ThreadPoolExecutor`，`max_workers` 有上限，建议 4～8；单票失败不影响其余） |
| M3 | `watch.py` 单票现价同样走 provider（可复用同一薄封装），禁止自建 `HttpClient`+`light_data.fetch_quote` |
| M4 | 行为契约：成功时仍写 `current` / `change_pct` / `price_fetched_at`；`refreshed>0` 才 `save_pool`；失败票跳过（与现语义一致） |
| M5 | 可测：支持注入 `quote_fn` / monkeypatch provider，**无网**单测锁 M1/M2/M4 字段写入 |
| M6 | （复用）若加批量 API，落在 `trader_shared/data_access.py`（或 provider），签名稳定：`targets → {key: quote_dict}`；池/watch 只调它 |

---

## 2. 禁止

1. 不改池分道 / `sort_items_unified` / 共振档 / 出手 / fusion。  
2. 不重跑 `build_report` 做 list/rank/plan 刷价。  
3. 不引入新外部依赖；不强制要求 aiohttp（同步线程池即可；已有 aiohttp 可选用但不作硬依赖）。  
4. 不改微信面板骨架 / golden。  
5. 不把 enrich 扫板（`TRADER_ENRICH_BOARDS`）默认打开。

---

## 3. 可改白名单

- `01-功能包-packages/trader/scripts/pool_cmds/plan_view.py`（`_refresh_pool_prices`）  
- `01-功能包-packages/trader/scripts/pool_cmds/watch.py`（现价拉取段）  
- `02-共享模块-shared/trader_shared/data_access.py`（可选：`get_quotes` 批量）  
- 相关 pytest（`01-功能包-packages/trader/tests/` 或 `02-共享模块-shared/tests/`）  
- 本文手递  

---

## 4. 验收表

| ID | 验收 |
|----|------|
| A1 | 源码：`plan_view._refresh_pool_prices` / `watch` 刷新路径 **无** `light_data.fetch_quote` / `HttpClient()` 直调 |
| A2 | 无网测：注入假 quote → items 更新 `current`/`change_pct`/`price_fetched_at`；失败项保留旧价 |
| A3 | 多票注入：证明走并行路径（如 executor 被调用，或批量 API 被调用一次拿到多码）——允许用 mock 计数，禁止真网 |
| A4 | 相关 pytest 绿；门禁不红（若触碰 gate 文件） |
| A5 | 查 Agent 对照本文全部 ✅ |

---

## 5. 双 Agent

| 角色 | 职责 |
|------|------|
| **写** | 只读本文 + 法源 → 实现 + 无网测 → commit/push 本分支 |
| **查** | 对照 M*/禁止；grep 确认无 light_data 直调；跑测；列必须再改 |

父 Agent：查完修完再开/更新 PR。
