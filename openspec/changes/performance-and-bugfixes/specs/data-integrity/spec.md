## ADDED Requirements

### Requirement: ATR 字段在 merge 后保留
`merge_daily_bars_with_quote()` 合并今日实时 quote 到历史 bars 后，today_bar 必须包含前一根 bar 的 atr14、atr_ratio、atr7、tr 字段值。

#### Scenario: 正常 merge 后 ATR 不为零
- **WHEN** 缓存中有带 ATR 的历史 bars，且今日 quote 有效
- **THEN** merge 后的最后一根 bar（today_bar）的 atr14 等于倒数第二根 bar 的 atr14

#### Scenario: 历史 bars 不足时 ATR 为零
- **WHEN** 缓存中 bars 少于 15 根（无法计算 ATR14）
- **THEN** today_bar 的 atr14 为 0.0（与历史 bars 一致）

### Requirement: fund_flow 使用 requests 库
`fund_flow_data.py` 的 HTTP 调用 MUST 使用 `requests` 库，不使用 `urllib.request`。

#### Scenario: 有代理环境下正常获取资金流向
- **WHEN** 系统有 HTTP 代理设置（含非 ASCII 字符）
- **THEN** `fetch_fund_flow()` 正常返回数据，不报编码错误

#### Scenario: API 不可用时降级返回空列表
- **WHEN** 东方财富 API 网络不可达
- **THEN** 返回空列表，不抛异常

### Requirement: fund_flow + market_env 与策略并行执行
`run_analysis.py` 中的 fund_flow 检测和 market_env 评估 MUST 与三策略（缠论/威科夫/动量）在同一个 ThreadPoolExecutor 中并行执行。

#### Scenario: 5 个任务并行完成
- **WHEN** 调用 `build_report()`
- **THEN** chan、wyckoff、momentum、fund_flow、market_env 五个任务同时提交到线程池，fusion 层等待全部完成后执行

#### Scenario: 单个任务异常不影响其他任务
- **WHEN** fund_flow API 超时或失败
- **THEN** 其他 4 个任务正常完成，fusion 层使用 fund_flow 的降级结果
