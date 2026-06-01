# 同步→异步 I/O 重构 PRD

## 目标

把数据抓取从同步阻塞改为异步并发。现在抓5只票的数据要串行等，改完后可以同时抓，速度提升明显。

## 现状问题

现在用 ThreadPoolExecutor 并行，但每个线程内部还是同步等待：
```python
def fetch_quote(code):
    response = requests.get(url)  # 阻塞等待，线程干等着
    return response.json()
```

5只票 = 5个线程，每个线程等1秒 = 总共1秒（理论）
但实际上线程有开销，且 API 可能限流，实际效果不理想。

## 目标架构

用 asyncio 改为异步：
```python
async def fetch_quote(code):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

async def fetch_all(codes):
    tasks = [fetch_quote(code) for code in codes]
    return await asyncio.gather(*tasks)  # 同时抓所有票
```

5只票 = 1个线程，同时发5个请求 = 总共约1秒

## 实施步骤

### Phase 1: 引入 aiohttp（15分钟）

1. `pyproject.toml` 添加 `aiohttp` 依赖
2. 创建 `async_utils.py` 工具函数

### Phase 2: 改造数据层（2-3小时）

1. `light_data.py` 的 `fetch_quote`、`fetch_kline` 改为 async
2. `data_provider.py` 的方法改为 async
3. 保留同步版本作为 wrapper（向后兼容）：
```python
def fetch_quote_sync(code):
    """同步包装器"""
    return asyncio.run(fetch_quote(code))
```

### Phase 3: 改造入口（1小时）

1. `run_analysis.py` 的主循环改为 async
2. `final_report.py`、`final_t0.py`、`final_review.py` 适配

### Phase 4: 改造分析模块（可选，1-2小时）

如果分析模块也需要异步：
- `decision_core.py`、`structure_core.py` 等改为 async
- 或者保持同步，只在数据层异步

## 向后兼容

保留同步包装器，不改调用方代码也能工作：
```python
# 旧代码继续工作
data = fetch_quote(code)

# 新代码可以用异步
data = await fetch_quote_async(code)
```

## 验证

1. 所有现有测试通过
2. 性能测试：抓10只票的数据，对比耗时
3. 手动验证：`python3 scripts/final_report.py --target 南网科技`

## 关键文件

- `02-共享模块-shared/trader_shared/async_utils.py` — 新建
- `02-共享模块-shared/trader_shared/light_data.py` — 改造
- `02-共享模块-shared/trader_shared/data_provider.py` — 改造
- `01-功能包-packages/trader/scripts/run_analysis.py` — 入口改造
- `pyproject.toml` — 添加依赖

## 风险

- aiohttp 是新依赖，需要安装
- 如果分析模块也改 async，改动面大
- 建议先只改数据层，分析模块保持同步
