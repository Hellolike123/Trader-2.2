# 修复 trader_shared 裸 import 路径

## 问题

`trader_shared/` 内部及周边 scripts 目录中，大量使用裸 import 引用同包模块（如 `from light_data import to_float`），导致打包到 Hermes skill 后 sys.path 指向 `scripts/` 而非 `trader_shared/`，运行时报 `ModuleNotFoundError`。

## 修复方案

所有 `trader_shared/` 内部的裸 import 统一加 `trader_shared.` 前缀：
- `from light_data import` → `from trader_shared.light_data import`
- `from safe_cast import` → `from trader_shared.safe_cast import`
- `from models import` → `from trader_shared.models import`
- `from decision_core import` → `from trader_shared.decision_core import`
- 其他同理

## 已修复范围

- `trader_shared/` 内部：36 处
- `t0/scripts/`：3 处（price_point_engine、monitor、t0_core）
- `trader/scripts/`：1 处（run_analysis）
- `02-共享模块-shared/scripts/`：4 处（self_calibration、market_env、signal_tracker）
- 顶层 `scripts/`：2 处（run_trader、t0_cron）

## 保留裸 import

- `structure_core.py` 中 `from self_calibration import` — self_calibration 在 scripts/ 目录而非 trader_shared/ 包内

## 验证

- `rg` 扫描确认无遗漏
- Python 脚本二次校验通过
