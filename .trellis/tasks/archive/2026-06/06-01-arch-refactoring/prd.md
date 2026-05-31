# Architecture Refactoring: DI + Async + Plugins

## Overview

Three major architecture changes to improve testability, performance, and extensibility.

## Task 1: Dependency Injection

### Goal
Modules no longer directly import data fetchers; dependencies are passed via parameters.

### Requirements

#### 1.1 Create `trader_shared/interfaces.py`
Define data fetching interface:
```python
from abc import ABC, abstractmethod

class DataFetcher(ABC):
    @abstractmethod
    def fetch_quote(self, code): ...
    
    @abstractmethod
    def fetch_kline(self, code, scale, datalen): ...
```

#### 1.2 Create `trader_shared/fetchers.py`
Implement concrete fetchers:
```python
class TencentFetcher(DataFetcher):
    def fetch_quote(self, code):
        # Move existing Tencent API logic here

class SinaFetcher(DataFetcher):
    def fetch_quote(self, code):
        # Move existing Sina API logic here
```

#### 1.3 Modify consumers (add fetcher parameter)
- `decision_core.py` — add fetcher parameter to init
- `structure_core.py` — add fetcher parameter to init
- `fusion_core.py` — add fetcher parameter to init

#### 1.4 Modify entry points (inject fetcher)
- `run_analysis.py` — create TencentFetcher() and pass it
- `final_report.py` — same
- `final_t0.py` — same
- `final_review.py` — same

#### 1.5 Backward compatibility
- Keep `from light_data import fetch_quote` working
- Internally forward to default fetcher

---

## Task 2: Sync → Async I/O

### Goal
Data fetching改为异步并发，多票同时抓取。

### Requirements

#### 2.1 Add dependency to `pyproject.toml`
```
aiohttp
```

#### 2.2 Create `trader_shared/async_utils.py`
```python
import asyncio
import aiohttp

async def fetch_quote_async(session, code):
    # Async fetch

async def fetch_all_quotes(codes):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_quote_async(session, c) for c in codes]
        return await asyncio.gather(*tasks)
```

#### 2.3 Modify `light_data.py`
- Add async versions of functions
- Keep sync versions as wrappers:
```python
def fetch_quote_sync(code):
    return asyncio.run(fetch_quote_async(code))
```

#### 2.4 Modify `run_analysis.py`
- Main loop改为async
- Use `asyncio.run()` to start

---

## Task 3: Plugin Mechanism

### Goal
新指标做成独立文件，插进去就能用。

### Requirements

#### 3.1 Create `trader_shared/plugins/` directory

#### 3.2 Create `trader_shared/plugins/base.py`
```python
from abc import ABC, abstractmethod

class IndicatorPlugin(ABC):
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    def analyze(self, data: dict) -> dict: ...
    
    def weight(self) -> float:
        return 1.0
```

#### 3.3 Create `trader_shared/plugin_registry.py`
```python
class PluginRegistry:
    def __init__(self):
        self._plugins = {}
        
    def register(self, plugin):
        self._plugins[plugin.name()] = plugin
        
    def analyze_all(self, data):
        return {name: p.analyze(data) for name, p in self._plugins.items()}
```

#### 3.4 Migrate existing indicators as plugins
- `chan_core.py` → `plugins/chan_plugin.py`
- `wyckoff_core.py` → `plugins/wyckoff_plugin.py`
- `momentum_core.py` → `plugins/momentum_plugin.py`

#### 3.5 Modify `fusion_core.py`
- Get all plugin results from registry
- Fuse by weight

#### 3.6 Backward compatibility
- Keep original imports working

---

## Verification

```bash
python3 -m pytest 02-共享模块-shared/tests/
python3 -m pytest 01-功能包-packages/*/tests/
```

## Success Criteria

- All tests pass
- Original imports still work
- New architecture is testable and extensible
