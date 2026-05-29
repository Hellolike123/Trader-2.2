## 1. 缓存基础设施增强

- [x] 1.1 增强 `cache_utils.py`：新增写入校验函数 `validate_bars(bars)` — 校验 bar 数量 >= 200、close > 0、日期单调递增
- [x] 1.2 增强 `cache_utils.py`：新增 `set_cached_validated(key, target, data, validator)` 函数，写入前自动校验
- [x] 1.3 新增缓存目录常量：`CACHE_DIR = ~/.trader/cache/`，子目录 `daily/`、`enrich/`、`market_env/`

## 2. 日线K线缓存

- [x] 2.1 修改 `light_data.py` 的 `fetch_qfq_daily()`：成功抓取后写入文件缓存 `~/.trader/cache/daily/{code}.json`
- [x] 2.2 修改 `data_provider.py` 的 `load_market_snapshot()`：盘中读取日线缓存，追加当日实时 quote 合并为完整 K 线
- [x] 2.3 合并逻辑实现：以日期为 key 去重，今天日期的 bar 用实时 quote 覆盖，确保 MA/ATR 计算正确

## 3. 扩展数据缓存

- [x] 3.1 修改 `data_provider.py` 的 `_enrich_snapshot()`：成功抓取后写入文件缓存 `~/.trader/cache/enrich/{code}.json`
- [x] 3.2 修改 `_enrich_snapshot()` 的缓存读取逻辑：优先读文件缓存（TTL 12小时），命中则跳过 4 路 API 调用

## 4. 大盘环境缓存

- [x] 4.1 修改 `market_env.py` 的 `assess()`：成功抓取后写入文件缓存 `~/.trader/cache/market_env.json`
- [x] 4.2 修改 `assess()` 的缓存读取逻辑：盘中读取缓存的指数历史数据，追加当日实时指数价格
- [x] 4.3 HMM regime 缓存：将 regime 结果随大盘环境一起缓存，盘中直接使用（不重新拟合）

## 5. 盘后预缓存

- [x] 5.1 新增预缓存函数 `warm_pool_cache()`：读取 `~/.trader/pool.json`，对每只活跃股票执行全量数据抓取并写入缓存
- [x] 5.2 集成到 `t0_cron.py`：在收盘后流程中调用 `warm_pool_cache()`
- [x] 5.3 新增手动命令 `trader.py cache warm`：立即触发预缓存

## 6. 缓存管理命令

- [x] 6.1 新增 `trader.py cache clear` 命令：清空 `~/.trader/cache/` 下所有文件
- [x] 6.2 新增 `trader.py cache clear --type daily` 参数：只清空指定类型缓存

## 7. 测试

- [x] 7.1 单元测试：日线缓存写入/读取/合并逻辑
- [x] 7.2 单元测试：扩展数据缓存 TTL 过期行为
- [x] 7.3 单元测试：缓存写入校验（脏数据拒绝写入）
- [x] 7.4 集成测试：完整分析流程使用缓存的结果与实时抓取一致
- [x] 7.5 集成测试：预缓存后再次分析的性能验证
