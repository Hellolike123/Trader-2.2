## 1. ATR 字段修复

- [x] 1.1 在 `cache_utils.py` 的 `merge_daily_bars_with_quote()` 中，创建 today_bar 后，从 bars[-1] 复制 atr14、atr_ratio、atr7、tr 字段到 today_bar
- [x] 1.2 验证：运行 `trader.py analyze --target <任意股票>` 后 atr14 不为 0.0

## 2. fund_flow 编码修复

- [x] 2.1 在 `fund_flow_data.py` 中将 `import urllib.request` 改为 `import requests`
- [x] 2.2 将 `fetch_fund_flow()` 中的 `urllib.request.Request` + `urlopen` 替换为 `requests.get()`，与 `extend_data.py` 的 `_http_get_json` 模式一致
- [x] 2.3 保持异常处理逻辑：失败时返回空列表，warnings.warn 提示

## 3. 并行化优化

- [x] 3.1 在 `run_analysis.py` 中将 fund_flow 检测和 market_env 评估的调用移到 ThreadPoolExecutor 内部
- [x] 3.2 将 executor 的 max_workers 从 3 改为 5
- [x] 3.3 fund_flow future 的结果传入 merge_decisions() 的 main_force_env 参数
- [x] 3.4 market_env future 的结果替代原来串行调用的 market_env_data
- [x] 3.5 保持异常处理：每个 future.result() 用 try/except 包裹，失败时使用降级默认值
