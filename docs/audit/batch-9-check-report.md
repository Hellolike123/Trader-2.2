# 第 9 批 · 同类隐患复查报告（data_status 通道静默失效）

- **日期**：2026-07-07
- **触发**：batch-8 修复了 `light_data._check_mootdx` 的导入名 bug（`from mootdx.quotes import Q` → `Quotes`），该 bug 让 mootdx 整条备份通道静默失效，导致 `data_status` 总是 `partial`。本次复查：是否还有同类"导入名写错 / 可用性检查错误 → 通道静默失效"的 bug。
- **方法**：静态读所有 `_XXX_AVAILABLE` 标志位 + 对应 `_check_` 函数源码，并在当前 Python 环境**实测各库的导入与 `_check_` 真实返回值**；端到端实跑 688248 / 600519 佐证。
- **结论**：**未发现同款 bug**。所有已接入的数据源与分析增强模块导入名正确、可用性为真；未安装的两个（pytdx3 / aiohttp）是可选备用/异步模块，非唯一源，实测端到端 `full` 证明不影响主数据。

## 检查范围与结果

### 数据源可用性（light_data.py / async_utils.py）

| 标志位 | 检查函数 | 导入写法 | 实测环境 | 结论 |
|--------|----------|----------|----------|------|
| `_MOOTDX_AVAILABLE` | `_check_mootdx` | `from mootdx.quotes import Quotes` | **True**（batch-8 已修） | ✅ 正常 |
| `_AKSHARE_AVAILABLE` | `_check_akshare` | `import akshare as _ak` | **True** | ✅ 正常 |
| `_TDX3_AVAILABLE` | `_check_pytdx3` | `from pytdx3.hq import TdxHq_API` | **False**（库未安装） | ⚠️ 见观察项① |
| `_AIOHTTP_AVAILABLE` | `_check_aiohttp` | `import aiohttp` | **False**（库未安装） | ⚠️ 见观察项② |

### 分析增强可用性

| 标志位 | 模块 | 导入写法 | 实测 |
|--------|------|----------|------|
| `_HMM_AVAILABLE` | structure_core | `from trader_shared.hmm_regime import detect_regime` | **True** |
| `_CALIBRATION_AVAILABLE` | structure_core | `from self_calibration import load_calibrated_params` | **True** |
| `_BAYESIAN_AVAILABLE` | fusion_core | `from trader_shared.bayesian_fusion import is_enabled` | **True** |
| `_VP_AVAILABLE` | decision_core | `from trader_shared.volume_profile import assess_vp_breakout` | **True** |
| `_CHIP_MIGRATION_AVAILABLE` | run_analysis | `from trader_shared.chip_migration_monitor import ...` | **True** |

全部导入名正确，可用性为真 → 无静默降级。

### 重复文件排查（排除"修复被覆盖"风险）

- 发现第二份 `02-共享模块-shared/01-行情数据-market-data/light_data.py`。
- 实际为 **13 行 re-export stub**：`from trader_shared.light_data import *` + 显式转发符号。
- 结论：**非分叉、不覆盖修复**。任何从它 import 的代码实际都拿到 `trader_shared.light_data` 的符号（含已修的 `_check_mootdx`）。
- 佐证：实跑 `trader.py analyze 688248/600519` 均 `data_status=full`，证明活跃的就是已修复版本。

## 观察项（非 bug，不影响数据完整性）

1. **pytdx3 未安装** → 本地通达信（TDX）HA 备用通道 `_fetch_qfq_tdx3` 等始终 `return None`（L323-324 先行 `if not _check_pytdx3(): return None`）。因主源（腾讯/新浪/mootdx）已覆盖全部核心数据，端到端 `full` 不受影响。若将来想启用本地通达信做行情 HA，需 `pip install pytdx3`。
2. **aiohttp 未安装** → `async_utils` 异步预取模块不可用。主流程 `light_data` 走同步 HTTP（腾讯/新浪），端到端 `full` 不受影响。若想启用异步批量预取加速，需 `pip install aiohttp`。

## 端到端佐证

- `688248`：`data_status=full`、`missing_sources=[]`、`source_errors={}`（batch-8 已验证 + 本次复查一致）
- `600519`：同上

## 与既定流程的关系

本次为"复查类似问题"，采用与 batch-7/8 一致的方法论（静态读 + 实测导入 + 端到端佐证），但未发现需修复的缺陷，故**无代码改动**、无新单测。报告仅作审计留痕。
