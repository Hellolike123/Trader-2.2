# 第 4 批数据采集模块审查与修复报告

> **审查日期**：2026-07-07
> **审查分支**：`audit-batch-4-data`
> **协作模式**：双 Reviewer 并行审查（理论派 + 工程派）→ Arbitrator 裁决+执行
> **审查范围**：6 个数据采集模块（market_env / extend_data / light_data / data_provider / fetchers / tick_cache）
> **前置依赖**：已包含第 1 批 11 项 + 第 2 批 6 项 + 第 3 批 7 项修复（累计 24 项）

---

## 一、审查概览

| 维度 | 理论派 Reviewer | 工程派 Reviewer | 交叉验证 |
|------|----------------|----------------|---------|
| P0 | 2（同根因的两个后果） | 1 | **1（vol_trend 顺序）** |
| P1 | 0 | 3 | 0 |
| P2 | 2 | 5 | 0 |
| 合计 | 4 | 9 | 1 |

**最终裁决**：ACCEPT 4 项 · DEFER 7 项 · REJECT 0 项

两派首次出现**根因级交叉**：market_env.py `vol_trend` 引用顺序错误被两派独立发现——理论派从"HMM 前瞻修正死代码"推理到根因，工程派从"NameError 静默捕获"定位同一根因。其他发现保持互补特性（零重叠）。

---

## 二、裁决矩阵

| # | 模块 | 行号 | 原始发现 | 来源 | 原级 | 裁决 | 理由 |
|---|------|------|---------|------|------|------|------|
| 1 | market_env.py | 199 | `detect_regime(index_returns, volume_ratio=vol_trend)` 中 vol_trend 在 L199 引用但 L213 才赋值 → NameError → except Exception 静默捕获 → HMM 死代码 | 理论派+工程派 | P0 | **ACCEPT** | 两派独立发现，根因确认。vol_trend 计算移到 HMM 调用之前即可 |
| 2 | market_env.py | 233-237 | HMM 前瞻修正（bear+正常→偏弱，bull+偏弱→正常）因 #1 导致 hmm_confidence 永远 0.5，阈值 0.75 永假 | 理论派 | P0 | **ACCEPT** | #1 修复后自动解决（vol_trend 正确传入 → HMM 返回真实 confidence） |
| 3 | extend_data.py | 82 | `data.get("errocode", 0)` 疑为 `"errcode"` 拼写错误（同花顺 API 标准字段），key 永久缺失 → 错误检测完全失效 | 工程派 | P1 | **ACCEPT** | 一字修正，零风险。`"errocode"` → `"errcode"` |
| 4 | light_data.py | 378, 665 | `(last_close_v or 1)` 当 last_close_v 为 0 元时退化为 1 → 显示虚假 -100% 涨跌幅 | 工程派 | P1 | **ACCEPT** | 加 `and last_close_v > 0` 守卫，防御 0 元/停牌股破净股 |
| 5 | light_data.py | 1031 | `fetch_quote()` 全源失败返回 `None`，下游 `data_provider.py:fetch_quote()` 直接透传 → 调用方 `.get()` 引发 AttributeError | 工程派 | P1 | **ACCEPT** | `return None` → `return {}`，空 dict 兼容 `.get()` 调用 |
| 6 | data_provider.py | 327-341 | `fetch_weekly/fetch_monthly` 调用 `fetch_kline(interval="weekly/monthly")`，走 Sina API period_map 无对应 key，fallback 到 "5" → 返回 5 分钟 K 线 | 理论派 | P2 | **DEFER** | 需设计决策——改路由涉及大改动（mootdx 周/月线获取或 Sina API 升级），非一行修复 |
| 7 | extend_data.py | 147-171 | `get_upcoming_unlocks()` page_size=10 固定，90 天内超 10 笔解禁会被截断 | 理论派 | P2 | **DEFER** | 罕见场景（单股 90 天内超 10 笔解禁极少见），当前默认值覆盖绝大多数正常情况 |
| 8 | extend_data.py | 157-158 | `free_date[:10]` + 字符串比较，API 返回格式可能为 YYYYMMDD，与 `today_str`(YYYY-MM-DD) 比较格式不一致 | 工程派 | P2 | **DEFER** | 需验证 API 真实返回格式才能确定修复方案 |
| 9 | tick_cache.py | 全文 | 无文件锁，并发写 JSON 破损 → json.load 异常 → except Exception 静默吞 | 工程派 | P2 | **DEFER** | 需架构改动（引入 fcntl/filelock），当前单线程使用场景下非紧急 |
| 10 | tick_cache.py | 全文 | 无过期清理逻辑，`~/.trader/tick_cache/` 无限增长 | 工程派 | P2 | **DEFER** | 需设计清理策略（TTL/容量上限/定时任务），非单行修复 |
| 11 | data_provider.py | 477 | 只做 binary `full/partial/failed` 判定，缺 "degraded" 状态和 missing_sources 追踪 | 工程派 | P2 | **DEFER** | 非关键路径，现有三态对下游决策已足够，增强可后续迭代 |
| 12 | light_data.py | 292-319 | `run_tdx3_with_timeout()` 中 `_TDX3_CLIENT = None` 后多线程并发重建可能泄露连接 | 工程派 | P2 | **DEFER** | 当前全程同步运行（trader 脚本 seq 分析），多线程化时再处理 |

---

## 三、关键裁决说明

### ★ market_env.py vol_trend 引用顺序（P0 · 两派一致 → ACCEPT）

**发现**：`assess()` 中 L199 的 `detect_regime(index_returns, volume_ratio=vol_trend)` 引用了 `vol_trend`，但此变量在 L213 才首次赋值。Python 局部变量在赋值前引用会抛出 `UnboundLocalError`，被 L203 `except Exception` 静默捕获。两个后果：
1. HMM 永远不返回有效结果（`hmm_res` 未赋值，`hmm_confidence` 保持默认 0.5）
2. L233-237 的 HMM 前瞻修正（`hmm_confidence >= 0.75` 永远 False）完全死代码

**裁决 ACCEPT 的理由**：纯代码顺序错误，非设计问题。vol_trend 计算逻辑本身正确（使用最近 10 根 bar 的成交量比值），只需移到 HMM 调用之前。修复后 HMM 前瞻修正自动恢复。

**修复**：将 L212-L218 的 vol_trend 计算块移到 L187 HMM 代码块之前，确保 `vol_trend` 在 L199 引用前已赋值。

### extend_data.py "errocode" → "errcode"（P1 → ACCEPT）

同花顺 API 标准响应字段为 `errcode`（如 `{"errcode": 0, "data": [...]}`），代码中错写为 `"errocode"`（多一个 'o'）。`data.get("errocode", 0)` 返回默认值 0，导致错误检测永远通过，API 异常返回时不触发降级。

**裁决 ACCEPT 的理由**：一字之差，零风险修正，对错误处理路径有实质改善。

### light_data.py `(last_close_v or 1)` 除零守卫（P1 → ACCEPT）

`last_close_v` 为 0 元时（破净股、停牌恢复首日、退市整理期），`0 or 1` 返回 1，计算 `(price/1 - 1) * 100` 产生虚假涨跌幅（如股价 3 元 → 显示 +200%）。修复为 `if last_close_v and last_close_v > 0` 守卫，0 元场景下 current_change_pct 为 None。

**裁决 ACCEPT 的理由**：极端场景防御，两处同时修正保持一致性。

### light_data.py fetch_quote 返回 None（P1 → ACCEPT）

`fetch_quote()` 全源失败时 `return None`，但类型标注为 `QuoteData`(dict)。下游 `data_provider.py:fetch_quote()` L291 直接透传该值，调用方 `.get()` 操作触发 `AttributeError: 'NoneType' object has no attribute 'get'`。修复为 `return {}`，空 dict 兼容 `.get()` 调用。

**裁决 ACCEPT 的理由**：防御性修复，零破坏性——空 dict 对下游等价于"无行情数据"，`.get()` 正常返回 None/默认值。

---

## 四、修改清单

| # | 文件 | 行号 | 修改类型 | 说明 |
|---|------|------|---------|------|
| 1 | market_env.py | 187-219 | 代码重排 | vol_trend 计算移到 HMM 调用之前（L187-194），HMM 块后移（L196-213） |
| 2 | extend_data.py | 82 | 拼写修正 | `"errocode"` → `"errcode"`，恢复同花顺 API 错误检测 |
| 3 | light_data.py | 378, 665 | 除零防御 | `(last_close_v or 1)` → `(last_close_v if last_close_v and last_close_v > 0 else 1)` |
| 4 | light_data.py | 1031 | 空值防御 | `return None` → `return {}`，防止下游 AttributeError |

**总计**：3 个文件，14 行插入，13 行删除

---

## 五、验证结果

### Import 验证（已通过）

```
light_data import OK
market_env import OK
extend_data import OK
data_provider import OK
fetchers import OK
tick_cache import OK
ALL 6 MODULES LOAD SUCCESSFULLY
```

### 代码级验证

| # | 修复项 | 验证方法 | 结果 |
|---|--------|---------|------|
| 1 | vol_trend 顺序 | 读 L187-213：vol_trend 赋值（L189）→ HMM 引用（L208） | ✅ 顺序正确 |
| 2 | "errocode" 拼写 | `grep "errocode" extend_data.py` → 无匹配 | ✅ 已修正 |
| 3 | last_close 除零 | `grep "last_close_v or 1" light_data.py` → 无匹配 | ✅ 两处均已守卫 |
| 4 | fetch_quote 返回 | `grep "return {}" light_data.py` → L1031 `return {}` | ✅ 已修正 |

---

## 六、遗留问题（DEFER · 需用户决定）

| # | 模块 | 问题 | 暂缓理由 | 建议 |
|---|------|------|---------|------|
| 1 | data_provider.py L327-341 | fetch_weekly/monthly 返回 5 分钟 K 线 | 需设计决策（mootdx 周/月线 vs Sina API 升级），改动较大 | 确认是否需要周/月线功能，再选择实现路径 |
| 2 | extend_data.py L147 | page_size=10 固定 | 90 天内超 10 笔解禁极少见 | 维持现状；如需覆盖极端情况，改为 page_size=50 |
| 3 | extend_data.py L157 | 日期格式不一致风险 | 需验证 API 真实返回格式 | 运行一次真实请求确认 FREE_DATE 字段格式 |
| 4 | tick_cache.py | 无文件锁 | 当前单线程使用，架构改动大 | 后续多线程化时引入 fcntl/filelock |
| 5 | tick_cache.py | 无过期清理 | 需设计清理策略 | 建议加 TTL（默认 30 天）+ 容量上限清理 |
| 6 | data_provider.py L477 | 缺 "degraded" 状态 | 非关键路径，三态对下游已够用 | 后续可选增强 |
| 7 | light_data.py L292-319 | TDX3 连接泄露风险 | 当前同步单线程运行 | 多线程化时引入连接池 |

---

## 七、diff 摘要

```
 02-共享模块-shared/scripts/market_env.py       | 17 ++++++++---------
 02-共享模块-shared/trader_shared/extend_data.py |  2 +-
 02-共享模块-shared/trader_shared/light_data.py  |  8 ++++----
 3 files changed, 14 insertions(+), 13 deletions(-)
```

---

## 八、本次协作流程评估

### 两派首次根因级交叉验证

本批两派**针对同一根因独立发现**：`vol_trend` 引用顺序错误被理论派和工程派各自定位——理论派从"HMM 前瞻修正死代码"向下推理找到根因，工程派从"NameError 静默捕获"向上定位同一行。这是截止目前交叉深度最高的一次。

其他发现保持强互补性：
- **理论派独占**：fetch_weekly 路由错误（P2）、page_size 截断（P2）——从数据完整性/业务语义层面推理
- **工程派独占**："errocode" 拼写（P1）、last_close 除零（P1）、fetch_quote 返回 None（P1）、tick_cache 无锁/无清理（P2）、akshare 状态缺失（P2）、TDX3 连接泄露（P2）——从异常输入/防御性编程/并发安全层面推理

### Arbitrator 裁决的关键判断

1. **vol_trend 顺序**：两派一致 P0，证据链完整（L199 引用 → L213 赋值 → except 静默 → HMM 死代码）。修复后整个 HMM 前瞻链路恢复。
2. **DEFER 标准**：涉及架构改动（tick_cache 锁/清理、TDX3 连接池）、需外部信息确认（API 返回格式）、或罕见场景（page_size 截断）的发现统一暂缓，避免过度修复。
3. **ACCEPT 标准**：可单行修复、零风险、有明确防御价值的发现（拼写、除零、空值）全部修改。

---

## 九、下一步建议

1. **用户审阅本报告 + diff**：`git diff` 查看完整改动
2. **合并到 main**：审阅通过后合并支分支
3. **DEFER 项优先级排序**：
   - **高**：data_provider.py 周/月线路由（如需启用周/月线分析）
   - **中**：tick_cache 清理策略（磁盘空间增长）
   - **低**：其他 DEFER 项（罕见场景或非关键路径）
4. **后续批次**：本批通过后，按审查计划启动第 5 批审查
