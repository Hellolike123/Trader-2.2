# 架构重构实施指南

## 重要：必须改现有代码！

不能只创建新文件，必须把新架构接入现有系统。

---

## 第一步：依赖注入（必须完成）

### 1.1 检查 interfaces.py 是否存在

文件：`02-共享模块-shared/trader_shared/interfaces.py`

如果不存在，创建它，内容如下：

```python
from abc import ABC, abstractmethod
from typing import Any

class DataFetcher(ABC):
    """数据获取接口"""
    
    @abstractmethod
    def fetch_quote(self, code: str) -> dict[str, Any]:
        """获取实时行情"""
        ...
    
    @abstractmethod
    def fetch_kline(self, code: str, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        """获取K线数据"""
        ...
    
    @abstractmethod
    def fetch_big_order(self, code: str) -> dict[str, Any]:
        """获取大单数据"""
        ...
```

### 1.2 检查 fetchers.py 是否存在

文件：`02-共享模块-shared/trader_shared/fetchers.py`

如果不存在，创建它，内容如下：

```python
from typing import Any
from .interfaces import DataFetcher
from .light_data import fetch_quote as _tencent_fetch_quote
from .light_data import fetch_kline as _tencent_fetch_kline
from .light_data import fetch_big_order as _tencent_fetch_big_order

class TencentFetcher(DataFetcher):
    """腾讯数据源"""
    
    def fetch_quote(self, code: str) -> dict[str, Any]:
        return _tencent_fetch_quote(code)
    
    def fetch_kline(self, code: str, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
        return _tencent_fetch_kline(code, scale, datalen)
    
    def fetch_big_order(self, code: str) -> dict[str, Any]:
        return _tencent_fetch_big_order(code)

# 默认 fetcher 实例
_default_fetcher = TencentFetcher()

def get_default_fetcher() -> DataFetcher:
    """获取默认数据源"""
    return _default_fetcher
```

### 1.3 修改 decision_core.py

文件：`02-共享模块-shared/trader_shared/decision_core.py`

**必须修改**：

1. 在文件顶部添加导入：
```python
from .interfaces import DataFetcher
from .fetchers import get_default_fetcher
```

2. 修改 `status_layers` 函数（或类似主函数），添加 fetcher 参数：
```python
def status_layers(
    sec,
    fetcher: DataFetcher = None,  # 新增参数
    # ... 其他参数保持不变
):
    if fetcher is None:
        fetcher = get_default_fetcher()
    
    # 原有代码保持不变
    # 但所有调用 fetch_quote、fetch_kline 的地方，改为：
    # data = fetcher.fetch_quote(code)
    # 而不是：
    # data = fetch_quote(code)
```

3. 搜索文件中所有 `fetch_quote(` 和 `fetch_kline(` 调用，替换为 `fetcher.fetch_quote(` 和 `fetcher.fetch_kline(`

### 1.4 修改 structure_core.py

文件：`02-共享模块-shared/trader_shared/structure_core.py`

**必须修改**：

1. 在文件顶部添加导入：
```python
from .interfaces import DataFetcher
from .fetchers import get_default_fetcher
```

2. 修改 `build_structure_context` 函数（或类似主函数），添加 fetcher 参数：
```python
def build_structure_context(
    sec,
    fetcher: DataFetcher = None,  # 新增参数
    # ... 其他参数保持不变
):
    if fetcher is None:
        fetcher = get_default_fetcher()
    
    # 原有代码保持不变
    # 但所有调用 fetch_quote、fetch_kline 的地方，改为：
    # data = fetcher.fetch_quote(code)
```

3. 搜索文件中所有 `fetch_quote(` 和 `fetch_kline(` 调用，替换为 `fetcher.fetch_quote(` 和 `fetcher.fetch_kline(`

### 1.5 修改 fusion_core.py

文件：`02-共享模块-shared/trader_shared/fusion_core.py`

**必须修改**：

1. 在文件顶部添加导入：
```python
from .interfaces import DataFetcher
from .fetchers import get_default_fetcher
```

2. 修改主函数，添加 fetcher 参数：
```python
def fusion_analyze(
    sec,
    fetcher: DataFetcher = None,  # 新增参数
    # ... 其他参数保持不变
):
    if fetcher is None:
        fetcher = get_default_fetcher()
    
    # 原有代码保持不变
    # 但所有调用 fetch_quote、fetch_kline 的地方，改为：
    # data = fetcher.fetch_quote(code)
```

3. 搜索文件中所有 `fetch_quote(` 和 `fetch_kline(` 调用，替换为 `fetcher.fetch_quote(` 和 `fetcher.fetch_kline(`

### 1.6 修改 run_analysis.py

文件：`01-功能包-packages/trader/scripts/run_analysis.py`

**必须修改**：

1. 在文件顶部添加导入：
```python
from trader_shared.fetchers import TencentFetcher
```

2. 在主函数开头创建 fetcher 实例：
```python
def main():
    fetcher = TencentFetcher()
    
    # 原有代码保持不变
    # 但调用 decision_core、structure_core、fusion_core 时，传入 fetcher：
    # result = status_layers(sec, fetcher=fetcher, ...)
```

3. 搜索文件中所有调用 `status_layers`、`build_structure_context`、`fusion_analyze` 的地方，添加 `fetcher=fetcher` 参数

### 1.7 修改 final_report.py、final_t0.py、final_review.py

文件：
- `01-功能包-packages/trader/scripts/final_report.py`
- `01-功能包-packages/t0/scripts/final_t0.py`
- `01-功能包-packages/review/scripts/final_review.py`

**必须修改**：

1. 在文件顶部添加导入：
```python
from trader_shared.fetchers import TencentFetcher
```

2. 在主函数开头创建 fetcher 实例：
```python
def main():
    fetcher = TencentFetcher()
    
    # 原有代码保持不变
    # 但调用 run_analysis 或其他函数时，传入 fetcher
```

---

## 第二步：异步 I/O（必须完成）

### 2.1 检查 async_utils.py 是否存在

文件：`02-共享模块-shared/trader_shared/async_utils.py`

如果不存在，创建它，内容如下：

```python
import asyncio
import aiohttp
from typing import Any

async def fetch_quote_async(session: aiohttp.ClientSession, code: str) -> dict[str, Any]:
    """异步获取实时行情"""
    # 使用腾讯 API
    url = f"https://qt.gtimg.cn/q={code}"
    async with session.get(url) as response:
        text = await response.text()
        # 解析返回数据（与 light_data.py 中的解析逻辑一致）
        return parse_quote_response(text)

async def fetch_all_quotes(codes: list[str]) -> list[dict[str, Any]]:
    """批量异步获取行情"""
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_quote_async(session, code) for code in codes]
        return await asyncio.gather(*tasks)

def fetch_quote_sync(code: str) -> dict[str, Any]:
    """同步包装器（向后兼容）"""
    return asyncio.run(fetch_quote_async(None, code))
```

### 2.2 修改 light_data.py

文件：`02-共享模块-shared/trader_shared/light_data.py`

**必须修改**：

1. 在文件顶部添加导入：
```python
import asyncio
import aiohttp
```

2. 添加异步版本函数：
```python
async def fetch_quote_async(code: str) -> dict[str, Any]:
    """异步获取实时行情"""
    # 复用现有解析逻辑
    url = f"https://qt.gtimg.cn/q={code}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            text = await response.text()
            return parse_quote_response(text)

async def fetch_kline_async(code: str, scale: str, datalen: int = 60) -> list[dict[str, Any]]:
    """异步获取K线数据"""
    # 复用现有解析逻辑
    url = build_kline_url(code, scale, datalen)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            text = await response.text()
            return parse_kline_response(text)
```

3. 保留原有同步函数，作为向后兼容：
```python
def fetch_quote(code: str) -> dict[str, Any]:
    """同步获取实时行情（向后兼容）"""
    return asyncio.run(fetch_quote_async(code))
```

### 2.3 修改 run_analysis.py 使用异步

文件：`01-功能包-packages/trader/scripts/run_analysis.py`

**必须修改**：

1. 在文件顶部添加导入：
```python
import asyncio
from trader_shared.light_data import fetch_quote_async, fetch_kline_async
```

2. 修改主函数为异步：
```python
async def main_async():
    # 原有代码保持不变
    # 但调用数据获取时使用异步版本：
    # data = await fetch_quote_async(code)
    pass

def main():
    asyncio.run(main_async())
```

3. 搜索文件中所有 `fetch_quote(` 和 `fetch_kline(` 调用，替换为 `await fetch_quote_async(` 和 `await fetch_kline_async(`

---

## 第三步：插件机制（必须完成）

### 3.1 检查 plugins/ 目录是否存在

目录：`02-共享模块-shared/trader_shared/plugins/`

如果不存在，创建它，并创建以下文件：

#### `__init__.py`
```python
from .base import IndicatorPlugin
from .plugin_registry import PluginRegistry
```

#### `base.py`
```python
from abc import ABC, abstractmethod
from typing import Any

class IndicatorPlugin(ABC):
    """指标插件基类"""
    
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        ...
    
    @abstractmethod
    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """分析数据，返回结果"""
        ...
    
    def weight(self) -> float:
        """在融合时的权重，默认1.0"""
        return 1.0
```

#### `plugin_registry.py`
```python
from typing import Any
from .base import IndicatorPlugin

class PluginRegistry:
    """插件注册表"""
    
    def __init__(self):
        self._plugins: dict[str, IndicatorPlugin] = {}
    
    def register(self, plugin: IndicatorPlugin) -> None:
        """注册插件"""
        self._plugins[plugin.name()] = plugin
    
    def get_plugin(self, name: str) -> IndicatorPlugin | None:
        """获取插件"""
        return self._plugins.get(name)
    
    def analyze_all(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """运行所有插件分析"""
        return {name: plugin.analyze(data) for name, plugin in self._plugins.items()}
    
    def list_plugins(self) -> list[str]:
        """列出所有插件名称"""
        return list(self._plugins.keys())
```

### 3.2 创建 chan_plugin.py

文件：`02-共享模块-shared/trader_shared/plugins/chan_plugin.py`

**必须创建**：

```python
from typing import Any
from .base import IndicatorPlugin
from ..chan_core import chanlun_analysis

class ChanPlugin(IndicatorPlugin):
    """缠论插件"""
    
    def name(self) -> str:
        return "chan"
    
    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """运行缠论分析"""
        # 调用现有缠论分析函数
        result = chanlun_analysis(data)
        return result
    
    def weight(self) -> float:
        return 1.0
```

### 3.3 创建 wyckoff_plugin.py

文件：`02-共享模块-shared/trader_shared/plugins/wyckoff_plugin.py`

**必须创建**：

```python
from typing import Any
from .base import IndicatorPlugin
from ..wyckoff_core import wyckoff_analysis

class WyckoffPlugin(IndicatorPlugin):
    """威科夫插件"""
    
    def name(self) -> str:
        return "wyckoff"
    
    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """运行威科夫分析"""
        # 调用现有威科夫分析函数
        result = wyckoff_analysis(data)
        return result
    
    def weight(self) -> float:
        return 1.0
```

### 3.4 创建 momentum_plugin.py

文件：`02-共享模块-shared/trader_shared/plugins/momentum_plugin.py`

**必须创建**：

```python
from typing import Any
from .base import IndicatorPlugin
from ..momentum_core import momentum_analysis

class MomentumPlugin(IndicatorPlugin):
    """动量插件"""
    
    def name(self) -> str:
        return "momentum"
    
    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """运行动量分析"""
        # 调用现 momentum 分析函数
        result = momentum_analysis(data)
        return result
    
    def weight(self) -> float:
        return 1.0
```

### 3.5 修改 fusion_core.py 使用插件

文件：`02-共享模块-shared/trader_shared/fusion_core.py`

**必须修改**：

1. 在文件顶部添加导入：
```python
from .plugins import PluginRegistry
from .plugins.chan_plugin import ChanPlugin
from .plugins.wyckoff_plugin import WyckoffPlugin
from .plugins.momentum_plugin import MomentumPlugin
```

2. 在主函数开头创建插件注册表：
```python
def fusion_analyze(
    sec,
    fetcher: DataFetcher = None,
    # ... 其他参数保持不变
):
    # 创建插件注册表
    registry = PluginRegistry()
    registry.register(ChanPlugin())
    registry.register(WyckoffPlugin())
    registry.register(MomentumPlugin())
    
    # 原有代码保持不变
    # 但调用分析函数时，改为使用插件：
    # results = registry.analyze_all(data)
    # chan_result = results.get("chan", {})
    # wyckoff_result = results.get("wyckoff", {})
    # momentum_result = results.get("momentum", {})
```

3. 搜索文件中所有调用 `chanlun_analysis`、`wyckoff_analysis`、`momentum_analysis` 的地方，替换为从 `registry.analyze_all(data)` 中获取结果

---

## 第四步：打包脚本（必须完成）

### 4.1 修改 pack_all.py

文件：`02-共享模块-shared/scripts/pack_all.py`

**必须修改**：

1. 在文件顶部添加新文件列表：
```python
# 新增的架构文件
_NEW_ARCHITECTURE_FILES = [
    "interfaces.py",
    "fetchers.py",
    "async_utils.py",
    "plugin_registry.py",
]
```

2. 在 `copy_shared` 函数中，添加复制新文件的逻辑：
```python
def copy_shared(bundle: Path, skill_slug: str) -> None:
    # ... 原有代码保持不变 ...
    
    # 复制新架构文件
    for f in _NEW_ARCHITECTURE_FILES:
        src = SHARE_DIR / "trader_shared" / f
        if src.exists():
            dst = scripts_dir / "trader_shared" / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    
    # 复制 plugins 目录
    plugins_src = SHARE_DIR / "trader_shared" / "plugins"
    plugins_dst = scripts_dir / "trader_shared" / "plugins"
    if plugins_src.exists():
        if plugins_dst.exists():
            shutil.rmtree(plugins_dst)
        shutil.copytree(
            plugins_src,
            plugins_dst,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".DS_Store"),
        )
```

3. 在 `cleanup_old_releases` 函数开头，添加创建目录的逻辑：
```python
def cleanup_old_releases(releases_dir: Path, keep: int = MAX_RELEASES) -> int:
    # 确保目录存在
    releases_dir.mkdir(parents=True, exist_ok=True)
    
    # ... 原有代码保持不变 ...
```

---

## 验证清单

完成以上步骤后，必须运行以下验证：

### 1. 运行测试
```bash
python3 -m pytest 02-共享模块-shared/tests/
```

### 2. 验证依赖注入
```bash
python3 -c "from trader_shared.fetchers import TencentFetcher; print('依赖注入 OK')"
```

### 3. 验证异步 I/O
```bash
python3 -c "from trader_shared.async_utils import fetch_quote_sync; print('异步 I/O OK')"
```

### 4. 验证插件机制
```bash
python3 -c "from trader_shared.plugins import PluginRegistry; print('插件机制 OK')"
```

### 5. 验证打包
```bash
python3 02-共享模块-shared/scripts/pack_all.py --no-install
```

### 6. 手动验证分析功能
```bash
python3 01-功能包-packages/trader/scripts/final_report.py --target 南网科技
```

---

## 常见错误

### 错误1：只创建文件不改现有代码
**症状**：新文件存在，但现有代码没有使用
**修复**：必须按照上述步骤修改 decision_core.py、structure_core.py、fusion_core.py、run_analysis.py 等文件

### 错误2：忘记添加 fetcher 参数
**症状**：函数调用时报错 "missing 1 required positional argument: 'fetcher'"
**修复**：在所有调用 status_layers、build_structure_context、fusion_analyze 的地方，添加 fetcher=fetcher 参数

### 错误3：忘记导入新模块
**症状**：ImportError: cannot import name 'DataFetcher' from 'trader_shared.interfaces'
**修复**：确保 interfaces.py 存在，且在文件顶部添加 from .interfaces import DataFetcher

### 错误4：异步函数没有 await
**症状**：RuntimeError: coroutine was never awaited
**修复**：所有调用异步函数的地方，必须使用 await，例如：data = await fetch_quote_async(code)

### 错误5：插件没有实现抽象方法
**症状**：TypeError: Can't instantiate abstract class ChanPlugin with abstract methods analyze, name
**修复**：确保所有插件都实现了 name() 和 analyze() 方法
