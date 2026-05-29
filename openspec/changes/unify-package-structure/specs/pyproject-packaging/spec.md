## ADDED Requirements

### Requirement: pyproject.toml 包管理

系统 SHALL 提供 `pyproject.toml` 配置文件，支持 `pip install -e .` 开发安装，使 `trader_shared` 包可被直接 import 无需手动 sys.path 配置。

#### Scenario: pip install -e . 成功
- **WHEN** 在项目根目录执行 `pip install -e .`
- **THEN** `import trader_shared` 可直接使用，无需任何 sys.path 配置

#### Scenario: pytest 直接运行
- **WHEN** 执行 `python3 -m pytest 02-共享模块-shared/tests/`
- **THEN** 测试文件可直接 `from trader_shared.xxx import ...` 无需路径拼接

### Requirement: sys.path 集中化

系统 SHALL 将散落在 111 处的 sys.path 手动注入集中到 `trader_shared/__init__.py` 的自动配置逻辑中，确保迁移期间新旧 import 共存。

#### Scenario: 现有 import 仍然可用
- **WHEN** 某个文件使用旧的 `from light_data import to_float`
- **THEN** 通过 `trader_shared/__init__.py` 的 sys.path 配置，import 成功

#### Scenario: 新 import 可用
- **WHEN** 某个文件使用新的 `from trader_shared.light_data import to_float`
- **THEN** import 成功

### Requirement: 渐进式模块迁移

系统 SHALL 逐个将 `01-行情数据-market-data/`、`02-候选逻辑-candidate/`、`03-输出校验-contracts/` 下的模块移入 `trader_shared/`，每步同步更新所有 import 语句。

#### Scenario: light_data.py 迁移完成
- **WHEN** `light_data.py` 移入 `trader_shared/`
- **THEN** 所有 `from light_data import ...` 改为 `from trader_shared.light_data import ...`，测试通过

#### Scenario: 候选逻辑模块迁移完成
- **WHEN** `chan_core.py`、`wyckoff_core.py`、`momentum_core.py` 移入 `trader_shared/`
- **THEN** 所有相关 import 更新，测试通过

### Requirement: 清理遗留路径代码

迁移完成后，系统 SHALL 删除 `_fix_paths.py`、所有"双模式路径发现"样板代码和空的旧目录。

#### Scenario: _fix_paths.py 删除
- **WHEN** 所有模块迁移完成
- **THEN** `_fix_paths.py` 被删除，不再需要

#### Scenario: 旧目录清理
- **WHEN** 所有模块移入 `trader_shared/`
- **THEN** `01-行情数据-market-data/`、`02-候选逻辑-candidate/`、`03-输出校验-contracts/` 目录被删除（仅保留 `.gitkeep` 如需要）
