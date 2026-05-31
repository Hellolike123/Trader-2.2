## Why

当前体系对"主力资金"的处理是散落的间接推断，不是一个独立的、可量化的维度。big_order.py 的大单检测、wyckoff_core.py 的 Spring/Upthrust、chip_distribution.py 的筹码分布都在隐含地捕捉主力行为，但没有一个模块把"主力在干什么"当作连续的生命周期来跟踪和输出。这导致决策层缺乏一个明确的"主力态势"信号，无法判断当前是吸筹期、拉升期还是派发期。

## What Changes

- 新增主力资金流向数据采集模块，通过东方财富API获取日线级个股资金流向（超大单/大单/中单/小单净流入）
- 新增主力行为识别引擎，基于五阶段模型（吸筹/试盘/拉升/派发/砸盘）识别当前所处阶段及置信度
- 新增 `main_force_env` 作为第三个环境修正因子（与 market_env、hmm_regime 并列），在 fusion_core.py 中调节融合权重
- 复盘面板新增「主力行为」段落，展示行为阶段、资金流向数值、价资关系、趋势符号
- 资金流向数据纳入分层缓存体系（fund_flow/ 子目录，TTL 24h），集成到 warm_pool_cache()
- **不做**入池硬门控（推测数据不适合一票否决）
- **不做**T0盘中实时主力异动告警（日线级数据时效性不够）

## Capabilities

### New Capabilities
- `fund-flow-data`: 资金流向数据采集、缓存、特征工程
- `mainforce-behavior`: 主力行为五阶段识别引擎
- `mainforce-fusion`: 主力行为作为环境因子接入融合层
- `mainforce-review-output`: 复盘面板主力行为展示

### Modified Capabilities
（无现有 spec 需要修改）

## Impact

- 新增模块：`trader_shared/main_force.py`（行为引擎）、`trader_shared/fund_flow_data.py`（数据采集+缓存）
- 修改模块：`trader_shared/fusion_core.py`（新增 main_force_env 权重调节）、`trader_shared/cache_utils.py`（新增 fund_flow 缓存子目录+TTL）、复盘输出脚本（新增段落）
- 新增依赖：akshare（已有）或直接调用东方财富HTTP API（推荐，避免代理问题）
- 新增缓存目录：`~/.trader/cache/fund_flow/`
