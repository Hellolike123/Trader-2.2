# 插件机制 PRD

## 目标

新指标（技术分析公式、策略规则）做成独立文件，往插槽里一插就能用，不用改核心代码。

## 现状问题

现在加新指标要改核心代码：
1. 在 `chan_core.py` 或 `wyckoff_core.py` 里加函数
2. 在 `decision_core.py` 里调用
3. 在 `structure_core.py` 里整合
4. 改输出格式

问题：
- 改核心代码容易引入 bug
- 指标之间耦合，改一个影响别的
- 新指标要改3-4个文件，容易漏

## 目标架构

```
trader_shared/
├── plugins/
│   ├── __init__.py          # 插件加载器
│   ├── base.py              # 插件基类
│   ├── chan_plugin.py        # 缠论插件
│   ├── wyckoff_plugin.py    # 威科夫插件
│   ├── momentum_plugin.py   # 动量插件
│   └── my_custom_plugin.py  # 你的自定义插件
├── plugin_registry.py       # 插件注册表
└── ...
```

插件基类：
```python
class IndicatorPlugin(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def analyze(self, data: dict) -> dict:
        """输入K线数据，输出分析结果"""
        ...

    def weight(self) -> float:
        """在融合时的权重，默认1.0"""
        return 1.0
```

使用方式：
```python
# 注册插件
registry = PluginRegistry()
registry.register(ChanPlugin())
registry.register(WyckoffPlugin())
registry.register(MyCustomPlugin())  # 你的插件

# 运行分析
results = registry.analyze_all(data)
```

## 实施步骤

### Phase 1: 设计接口（30分钟）

1. 创建 `plugins/base.py` — 插件基类
2. 创建 `plugin_registry.py` — 注册表

### Phase 2: 迁移现有指标（2-3小时）

1. `chan_core.py` → `plugins/chan_plugin.py`
2. `wyckoff_core.py` → `plugins/wyckoff_plugin.py`
3. `momentum_core.py` → `plugins/momentum_plugin.py`
4. `chip_distribution.py` → `plugins/chip_plugin.py`

每个插件实现 `analyze()` 方法，返回标准格式结果。

### Phase 3: 改造融合层（1小时）

1. `fusion_core.py` — 从 registry 获取所有插件结果
2. `decision_core.py` — 使用插件结果做决策
3. 保持原有逻辑作为 fallback

### Phase 4: 自动发现（30分钟）

1. 插件加载器自动扫描 `plugins/` 目录
2. 新增 `.py` 文件自动注册
3. 支持启用/禁用插件配置

## 向后兼容

1. 保留原有函数入口：
```python
# 旧代码继续工作
from chan_core import chanlun_analysis
result = chanlun_analysis(data)

# 新代码用插件
result = registry.get_plugin("chan").analyze(data)
```

2. 迁移期间两种方式并存

## 验证

1. 所有现有测试通过
2. 新增测试：用 MockPlugin 测试插件机制
3. 手动验证：`python3 scripts/final_report.py --target 南网科技`
4. 验证自定义插件可以正常加载和运行

## 关键文件

- `02-共享模块-shared/trader_shared/plugins/` — 新建目录
- `02-共享模块-shared/trader_shared/plugins/base.py` — 新建
- `02-共享模块-shared/trader_shared/plugin_registry.py` — 新建
- `02-共享模块-shared/trader_shared/chan_core.py` — 迁移
- `02-共享模块-shared/trader_shared/wyckoff_core.py` — 迁移
- `02-共享模块-shared/trader_shared/momentum_core.py` — 迁移
- `02-共享模块-shared/trader_shared/fusion_core.py` — 改造

## 扩展性

未来服务器做好后，可以：
1. 服务器上运行插件，AI 只调接口
2. 插件可以远程加载，不用本地部署
3. 新指标在服务器上开发，AI 自动识别
