## Why

代码库有 111 处 `sys.path.insert/append`，分布在每个入口脚本、测试文件和 Provider 方法中。根因是 `01-行情数据-market-data/`、`02-候选逻辑-candidate/`、`03-输出校验-contracts/` 三个目录不是 Python 包，无法直接 import。每次新增功能都要复制"路径发现仪式"（5-10 行样板代码），测试文件的路径拼接比测试代码还多，`_fix_paths.py` 本身就是一个 166 行的自动修补脚本在给债上加债。

通过 pyproject.toml + 渐进式模块迁移，最终消灭所有 sys.path 魔法，统一为 `from trader_shared.xxx import ...`。

## What Changes

- 新增 `pyproject.toml`，声明 `trader_shared` 为唯一 Python 包
- 新增 `trader_shared/__init__.py` 的自动路径配置（过渡期兼容）
- 逐个将 `light_data.py`、`chan_core.py`、`wyckoff_core.py`、`momentum_core.py`、`signal_contract.py` 等模块移入 `trader_shared/`
- 每移一个模块，同步更新所有 import 语句
- 更新 `pack_all.py` 打包脚本适配新结构
- 删除 `_fix_paths.py` 和所有"双模式路径发现"样板代码
- 最终删除空的旧目录

## Capabilities

### New Capabilities
- `pyproject-packaging`: pyproject.toml 包管理配置，支持 `pip install -e .` 开发安装和 `pytest` 直接运行

### Modified Capabilities
（无现有 spec 需要修改）

## Impact

- 修改文件：几乎所有 .py 文件（import 路径变更）
- 新增文件：`pyproject.toml`
- 删除文件：`_fix_paths.py`，旧目录下的 `__init__.py`（迁移完成后）
- 依赖：无新依赖
- 向后兼容：过渡期内 `trader_shared/__init__.py` 自动配置 sys.path，现有 import 仍然可用
