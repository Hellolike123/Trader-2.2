# 依赖注入重构 PRD

## 目标

让模块之间不再直接 import 硬耦合，改为"谁用我，谁把依赖传给我"。好处是测试时可以传假数据，未来换数据源不用改分析代码。

## 现状问题

现在模块直接 import 硬耦合：
```python
# decision_core.py
from light_data import fetch_quote  # 直接依赖具体实现
```

问题：
- 测试时没法 mock fetch_quote，必须真的调 API
- 未来数据源换成服务器 API，要改所有 import 语句
- 模块之间形成网状依赖，改一个影响一片

## 目标架构

```python
# 改为注入方式
class DecisionCore:
    def __init__(self, data_fetcher):
        self.fetcher = data_fetcher  # 谁用我，谁传给我

    def analyze(self):
        data = self.fetcher.fetch_quote(...)  # 通过接口调用
```

使用时：
```python
# 正式环境
fetcher = TencentFetcher()
core = DecisionCore(fetcher)

# 测试环境
fetcher = MockFetcher()  # 假数据
core = DecisionCore(fetcher)

# 未来服务器环境
fetcher = ServerAPIFetcher()  # 调你的服务器
core = DecisionCore(fetcher)
```

## 实施步骤

### Phase 1: 定义接口（30分钟）

创建 `interfaces.py`，定义所有数据获取接口：
```python
from abc import ABC, abstractmethod

class DataFetcher(ABC):
    @abstractmethod
    def fetch_quote(self, code): ...

    @abstractmethod
    def fetch_kline(self, code, scale, datalen): ...

    @abstractmethod
    def fetch_big_order(self, code): ...
```

### Phase 2: 改造数据层（1-2小时）

1. `light_data.py` 实现 `TencentFetcher`、`SinaFetcher`
2. `data_provider.py` 实现 `DataProvider` 接口
3. 保持原有函数作为快捷入口（向后兼容）

### Phase 3: 改造消费方（2-3小时）

1. `decision_core.py` — 接收 data_fetcher 参数
2. `structure_core.py` — 接收 data_fetcher 参数
3. `fusion_core.py` — 接收 data_fetcher 参数
4. `chan_core.py`、`wyckoff_core.py` 等分析模块

### Phase 4: 入口注入（30分钟）

1. `run_analysis.py` — 创建 fetcher 实例并传入
2. `final_report.py`、`final_t0.py`、`final_review.py` — 同上

## 向后兼容

保留原有快捷函数：
```python
def fetch_quote(code):
    """快捷入口，内部用默认 fetcher"""
    return _default_fetcher.fetch_quote(code)
```

这样不改调用方代码也能工作。

## 验证

1. 所有现有测试通过
2. 新增测试：用 MockFetcher 测试分析逻辑
3. 手动验证：`python3 scripts/final_report.py --target 南网科技`

## 关键文件

- `02-共享模块-shared/trader_shared/interfaces.py` — 新建
- `02-共享模块-shared/trader_shared/light_data.py` — 改造
- `02-共享模块-shared/trader_shared/data_provider.py` — 改造
- `02-共享模块-shared/trader_shared/decision_core.py` — 改造
- `02-共享模块-shared/trader_shared/structure_core.py` — 改造
- `02-共享模块-shared/trader_shared/fusion_core.py` — 改造
- `01-功能包-packages/trader/scripts/run_analysis.py` — 入口注入
