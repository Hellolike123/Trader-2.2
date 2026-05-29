## Why

单票分析在 Hermes 环境下需要 5-15 秒，其中 80% 的时间花在网络请求上。一次分析包含 11 次网络调用，其中至少 6 次的数据在盘中不会变化（日线K线、股东户数、机构EPS、解禁信息、题材归因、大盘环境）。通过分层缓存策略，盘中分析可从 5-15 秒降至 1-3 秒，盘后批量操作可缩短 90%。

## What Changes

- 新增日线K线文件缓存：盘后写入 `~/.trader/cache/daily/{code}.json`，盘中读取缓存 + 追加当日实时 bar 合并计算
- 新增扩展数据（股东/机构EPS/解禁/题材）文件缓存：TTL 12小时，盘中直接读缓存
- 新增大盘环境（指数行情 + HMM regime）文件缓存：收盘后写入，盘中读取 + 追加当日实时指数
- 新增盘后预缓存机制：每日 15:00 自动为选股池所有股票预抓取全量数据写入缓存
- 新增缓存写入校验：bar 数量 >= 200、价格 > 0、日期连续，脏数据不写入
- 新增手动清缓存命令：`trader.py cache clear`
- 日线缓存盘中合并策略：缓存历史日线 + 当日实时 quote 拼接为完整 K 线序列

## Capabilities

### New Capabilities
- `data-cache`: 分层数据缓存系统，区分盘中/盘后策略，支持文件持久化、TTL 过期、写入校验、原子写入
- `pool-precache`: 选股盘后预缓存机制，收盘后自动为池内股票预抓取全量数据

### Modified Capabilities
（无现有 spec 需要修改）

## Impact

- 修改文件：`data_provider.py`（缓存层接入）、`market_env.py`（大盘缓存）、`extend_data.py`（扩展数据缓存）、`cache_utils.py`（增强校验）、`light_data.py`（日线缓存写入）
- 新增文件：预缓存脚本（可集成到 `t0_cron.py` 或独立）
- 依赖：无新依赖，复用现有 `cache_utils.py` 的文件缓存机制
- 向后兼容：缓存不存在时自动 fallback 到实时抓取，行为与当前完全一致
