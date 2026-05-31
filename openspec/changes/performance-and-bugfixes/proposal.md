## Why

单票分析（`trader.py analyze`）存在两个数据层 bug 和一个性能瓶颈：

1. `merge_daily_bars_with_quote()` 创建的今日 bar 缺少 ATR 字段，导致 ATR=0，所有依赖 ATR 的输出（仓位上限、止损距离、风险收益比等）全部显示"数据不足"
2. `fund_flow_data.py` 使用 `urllib.request` 在有代理的 macOS 环境下报编码错误，资金流向数据获取失败
3. 主力资金检测和大盘环境评估在策略分析之后串行执行，但它们与策略完全独立，白等 0.5-1s

## What Changes

- 修复 `merge_daily_bars_with_quote()`：merge 后将前一根 bar 的 ATR 字段复制到 today_bar
- 修复 `fund_flow_data.py`：将 `urllib.request` 改为 `requests` 库，与 `extend_data.py` 保持一致
- 优化 `run_analysis.py` 执行顺序：将 fund_flow 检测和 market_env 评估与三策略并行执行

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
（无 spec 级别的行为变更，纯 bug 修复和性能优化）

## Impact

- 修改文件：`trader_shared/cache_utils.py`、`trader_shared/fund_flow_data.py`、`trader/scripts/run_analysis.py`
- 无新增依赖
- 无 API 变更
- 无行为变更（输出内容不变，只是修复缺失字段）
