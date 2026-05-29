## 1. Phase 1: pyproject.toml + sys.path 集中化

- [x] 1.1 新增 `pyproject.toml`：声明 `trader_shared` 包，配置 `[project]` 元数据和 `[tool.pytest]`
- [x] 1.2 修改 `trader_shared/__init__.py`：自动将旧目录（`01-行情数据-market-data`、`02-候选逻辑-candidate`、`03-输出校验-contracts`）加入 sys.path
- [x] 1.3 验证 `pip install -e .` 成功，`import trader_shared` 可用
- [x] 1.4 验证 `python3 -m pytest 02-共享模块-shared/tests/` 直接运行通过

## 2. Phase 1: 消灭散落的 sys.path（入口脚本）

- [x] 2.1 清理 `trader.py` 的 sys.path 配置（依赖 __init__.py）
- [x] 2.2 清理 `scripts/t0_cron.py` 的 sys.path
- [x] 2.3 清理 `scripts/run_trader.py` 的 sys.path
- [x] 2.4 清理 `scripts/check_all.py` 的 sys.path

## 3. Phase 1: 消灭散落的 sys.path（skill 入口脚本）

- [x] 3.1 清理 `01-单票分析-trader/scripts/run_analysis.py` 的路径发现样板
- [x] 3.2 清理 `02-盘中T0-t0-trader/scripts/` 下所有脚本的路径发现
- [x] 3.3 清理 `03-选股池-trader-pool/scripts/` 下所有脚本的路径发现
- [x] 3.4 清理 `04-仓位轮动-trader-portfolio/scripts/` 下所有脚本的路径发现
- [x] 3.5 清理 `05-盘后复盘-review-trader/scripts/` 下所有脚本的路径发现
- [x] 3.6 清理 `06-信号追踪-trader-tracking/scripts/` 下所有脚本的路径发现

## 4. Phase 1: 消灭散落的 sys.path（测试文件）

- [x] 4.1 批量清理 `02-共享模块-shared/tests/` 下所有测试文件的 sys.path 拼接
- [x] 4.2 批量清理 `01-功能包-packages/*/tests/` 下所有测试文件的 sys.path 拼接

## 5. Phase 1: 消灭散落的 sys.path（共享模块内部）

- [x] 5.1 清理 `data_provider.py` 的 `_ensure_paths()` 方法
- [x] 5.2 清理 `market_env.py` 的路径配置
- [x] 5.3 清理 `signal_tracker.py`、`calibrator.py`、`self_calibration.py` 的路径配置
- [x] 5.4 清理其他散落的 sys.path（validate_output.py 等）

## 6. Phase 2: 核心模块迁移

- [x] 6.1 迁移 `light_data.py` → `trader_shared/light_data.py`，更新所有 import
- [x] 6.2 迁移 `models.py` → `trader_shared/models.py`，更新所有 import
- [x] 6.3 迁移 `chan_core.py` → `trader_shared/chan_core.py`，更新所有 import
- [x] 6.4 迁移 `wyckoff_core.py` → `trader_shared/wyckoff_core.py`，更新所有 import
- [x] 6.5 迁移 `momentum_core.py` → `trader_shared/momentum_core.py`，更新所有 import
- [x] 6.6 迁移 `decision_core.py` → `trader_shared/decision_core.py`，更新所有 import
- [x] 6.7 迁移 `structure_core.py` → `trader_shared/structure_core.py`，更新所有 import
- [x] 6.8 迁移 `fusion_core.py` → `trader_shared/fusion_core.py`，更新所有 import
- [x] 6.9 迁移 `fusion_regime.py` → `trader_shared/fusion_regime.py`，更新所有 import
- [x] 6.10 迁移 `hmm_regime.py` → `trader_shared/hmm_regime.py`，更新所有 import
- [x] 6.11 迁移 `bayesian_fusion.py` → `trader_shared/bayesian_fusion.py`，更新所有 import
- [x] 6.12 迁移 `volume_profile.py` → `trader_shared/volume_profile.py`，更新所有 import
- [x] 6.13 迁移 `signal_contract.py` → `trader_shared/signal_contract.py`，更新所有 import
- [x] 6.14 迁移 `signal_store.py`、`signal_utils.py` → `trader_shared/`，更新所有 import
- [x] 6.15 迁移 `order_book.py`、`t0_candidate_core.py`、`time_window_detector.py` → `trader_shared/`

## 7. Phase 3: 清理

- [x] 7.1 更新 `pack_all.py` 适配新目录结构
- [x] 7.2 删除 `_fix_paths.py`
- [x] 7.3 删除旧目录存根文件（保留 contracts 目录存根供 signal_tracker.py 兼容）
- [x] 7.4 清理 `trader_shared/__init__.py` 的过渡期 sys.path 配置
- [x] 7.5 运行全量测试验证
