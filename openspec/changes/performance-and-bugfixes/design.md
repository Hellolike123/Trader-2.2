## Context

通过实际运行 `trader.py analyze --target 南网科技` 发现的三个问题：

1. **ATR 字段丢失**：`fetch_qfq_daily()` 在返回前调用 `_compute_atr_fields(bars)` 计算 ATR，但随后 `load_market_snapshot()` 调用 `merge_daily_bars_with_quote()` 追加了一根没有 ATR 的 today_bar。`run_analysis.py` 取 `last_bar`（即 today_bar）的 ATR，得到 0.0。

2. **fund_flow 编码错误**：`fund_flow_data.py:65` 使用 `urllib.request.Request` + `urlopen`，在 macOS 有系统代理的环境下触发 `'ascii' codec can't encode characters` 错误。同项目的 `extend_data.py` 使用 `requests` 库无此问题。

3. **串行等待**：`run_analysis.py` 中 fund_flow 检测（line 259）和 market_env 评估（line 353）在三策略并行（line 251）之后串行执行，但三者完全独立。

## Goals / Non-Goals

**Goals:**
- 修复 ATR 字段在 merge 后丢失的 bug
- 修复 fund_flow_data.py 的编码错误
- 将 fund_flow + market_env 与策略并行化

**Non-Goals:**
- 不改变任何业务逻辑或输出格式
- 不新增功能
- 不改变缓存策略

## Decisions

### Decision 1: ATR 修复 — merge 后复制前一根 bar 的 ATR

**选择**: 在 `merge_daily_bars_with_quote()` 中，创建 today_bar 后，从 bars[-1]（前一个交易日）复制 atr14、atr_ratio、atr7、tr 字段。

**原因**: today_bar 是实时数据，无法计算完整 ATR（需要前14根bar的TR）。但前一个交易日的 ATR 仍然有效，作为今日 ATR 的近似值。这比返回 0.0 好得多。

**替代方案**: 在 merge 后重新调用 `_compute_atr_fields()` — 可行但代价更高（O(n) 重算所有 bar），且 today_bar 的 TR 计算需要前一日 close，结果与复制相同。

### Decision 2: fund_flow 修复 — 改用 requests 库

**选择**: 将 `urllib.request` 替换为 `requests.get()`，与 `extend_data.py` 保持一致。

**原因**: `requests` 库正确处理系统代理和编码，`extend_data.py` 已验证可用。`urllib.request` 在 macOS 代理环境下有已知的编码问题。

### Decision 3: 并行化 — 扩大 ThreadPoolExecutor 范围

**选择**: 将 fund_flow 检测和 market_env 评估纳入现有的 ThreadPoolExecutor（或新建一个更大的 executor），与三策略同时执行。

**原因**: 三个任务完全独立（都需要 bars 和 quote，但互不依赖），并行可省 0.5-1s。

**具体方案**:
```
现在:
  ThreadPoolExecutor(3): [chan, wyckoff, momentum]
  → fund_flow (sequential)
  → market_env (sequential)

改为:
  ThreadPoolExecutor(5): [chan, wyckoff, momentum, fund_flow, market_env]
  → fusion (需要全部5个结果)
```

fusion_core.merge_decisions() 的调用点不变，只是传入的参数来源从"先串行再传入"变成"从 future.result() 取值"。

## Risks / Trade-offs

**[ATR 近似值]** 今日 ATR 使用前一日的值，不是精确的今日 ATR。但 ATR 是慢变量，一日之差影响极小，远好于返回 0.0。

**[并行异常处理]** 5 个任务并行时，任何一个异常不应影响其他任务。现有的 future.result() 已有 try/except 包裹，需要保持。

**[fund_flow API 失败]** 改用 requests 后，如果 API 仍然不可用（网络问题），应返回空列表，不影响主流程。现有逻辑已满足。
