# ADR-001: 消除 `trader_shared` 对 `scripts/` 的向上依赖（收编为真库）

- **Status**: Accepted（已合入 `main`，commit `2bc3493`）
- **Branch**: `refactor/trader-architecture`（历史工作分支；基于 `0b48fdc`，ADR-004 已落地）
- **前置**: ADR-004 已完成（stub 层、双 config、死集成已清；ADR-004 文档已归档，走 git 历史）

---

## Context（问题动机）

架构评审指出 `trader_shared` 反向依赖 `scripts/`，无法独立导入/测试/组合，破坏"模块化"根基。
我实测了仓库，确认向上依赖**真实存在且比文档描述更复杂**：

### 向上依赖的三个真代码来源

| # | 位置 | 写法 | 性质 |
|---|------|------|------|
| 1 | `trader_shared/__init__.py:79-205` | `_load_script()` + `get_pipeline/signal_tracker/market_env/calibrator` + `__getattr__` 懒加载 4 个模块 | 过渡期兼容层 |
| 2 | `trader_shared/structure_core.py:41` | `from self_calibration import load_calibrated_params` | **直接裸 import，真实运行依赖** |
| 3 | `trader_shared/cache_utils.py:434-435` | `sys.path.append(str(root/"scripts")); from market_env import assess` | **裸 import + 路径 hack，真实运行依赖** |

> ⚠️ **文档偏差**：原 ADR-001 只点了 `__init__.py` 的懒加载（来源 1），**漏了来源 2、3**。
> 这两处是 `trader_shared` 内部模块直接 `from X import`，**选 B（改懒加载为 DI）管不到它们**。

### 待收编模块清单（`scripts/` → `trader_shared/`）

`scripts/` 共 9 个 `.py`，其中 **5 个**需收编（文档说 4 个，漏了 `self_calibration`）：

| 模块 | 被谁依赖 | 收编后内部引用需改 |
|------|----------|-------------------|
| `pipeline.py` | `__init__` getter | — |
| `signal_tracker.py` | `__init__` getter、`signal_migration_tool`、`review/final_tracker` | — |
| `market_env.py` | `__init__` getter、`cache_utils`、`structure_core`(间接) | `market_env.py:6 from pipeline import write_market` → 包内相对导入 |
| `calibrator.py` | `__init__` getter (`run`/`generate_suggestions`) | — |
| `self_calibration.py` | `structure_core.py:41` | — |

> `backtest_chanlun.py` / `backtest_patterns.py` / `pack_all.py` / `signal_migration_tool.py` 不在收编核心集；
> `signal_migration_tool.py` 仅引用 `signal_tracker`，收编后改 import 即可。

### 其余受影响的引用点（真实代码）

| 文件 | 行 | 当前 | 收编后 |
|------|----|------|--------|
| `trader_shared/structure_core.py` | 41 | `from self_calibration import ...` | `from trader_shared.self_calibration import ...` |
| `trader_shared/cache_utils.py` | 434-435 | `sys.path.append(scripts)` + `from market_env import assess` | 删 path hack；`from trader_shared.market_env import assess` |
| `scripts/signal_migration_tool.py` | 15 | `from signal_tracker import ...` | `from trader_shared.signal_tracker import ...` |
| `01-功能包-packages/review/scripts/final_tracker.py` | 32/44/49 | `from signal_tracker import ...` | `from trader_shared.signal_tracker import ...` |
| `scripts/market_env.py` | 6 | `from pipeline import write_market` | `from trader_shared.pipeline import write_market`（或 `.pipeline`） |

---

## Decision（决策）

**选 A：收编为真库**（实测下几乎是唯一干净解，见下方权衡）。

### 迁移步骤

1. `git mv` 5 个模块 `scripts/{pipeline,signal_tracker,market_env,calibrator,self_calibration}.py` → `trader_shared/`（保留历史）。
2. 改 5 模块内部互相引用为包内相对导入（`from .X import`），已知 `market_env → pipeline`。
3. 改 `structure_core.py:41` 与 `cache_utils.py:434-435` 的 import（删 path hack）。
4. 改 `__init__.py`：删除 `_load_script` / `get_*` / `_find_scripts_dir` / `__getattr__` 中对应分支；改为顶层 `from trader_shared.pipeline import write_stock, ...` **re-export**，保持 `from trader_shared import write_stock` 等公开 API 不变。
5. 改 `scripts/signal_migration_tool.py` 与 `review/final_tracker.py` 的 import。
6. **暂不破坏测试**：`__init__.py:13-19` 的 `scripts/` 注入保留，使 `02-共享模块-shared/tests/*.py`（~15 个裸 import）短期不断；统一改测试留到"补测试基建"步。
7. `py_compile` + 全量导入冒烟 + 重打包 + 同步 hermes/workbuddy（同 ADR-004 流程）。
8. 提交（每 ADR 一 commit，本分支不 push）。

### 选 A vs 选 B（实测修正）

| | 选 A（收编） | 选 B（显式 DI，改懒加载） |
|---|---|---|
| 能否消除来源 1（懒加载） | ✅ | ✅ |
| 能否消除来源 2/3（structure_core/cache_utils 直接 import） | ✅ 一并解决 | ❌ **管不到**，仍向上依赖 |
| 是否成真库 | ✅ | ❌ |
| 改动量 | 移动 5 大文件 + 改 ~7 处 import | 看似小，但来源 2/3 仍需改，且非真库 |

> **架构师判断**：原文档把 B 列为"改动小"的可选，是低估了真实依赖网（只看了 `__init__.py`）。
> 实测下 **选 A 是必选项**；选 B 在这套代码里不彻底。

---

## Consequences（后果）

**变容易**
- `trader_shared` 可独立 `import` / 单测 / 被别的 agent 组合复用 —— 这是 ADR-002/003 的地基。
- 依赖方向单一：`scripts/` 与 `trader` 包依赖 `trader_shared`，不再反向。
- 消除 `cache_utils` 的 `sys.path` 运行时 hack（隐性脆弱点）。

**变困难 / 成本**
- 移动 5 个大文件（pipeline ~1900 行、signal_tracker ~1900 行），`git mv` 安全但内部引用需逐查。
- `__init__.py` 公开 API 面（~30 个 re-export 属性）改动，需用顶层 re-export 保兼容，不能简单删。
- **零测试基建下操作有回归风险** —— 强烈建议**先补最小测试基建（conftest + 关键模块导入冒烟）再执行本 ADR**，否则只能靠打包后导入冒烟兜底。

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 公开 API 断裂（`trader_shared.write_stock` 等被外部用） | 第 4 步用顶层 re-export 保兼容 |
| 移动后内部引用漏改 | 移动后用 `grep -rn "from (pipeline\|signal_tracker\|market_env\|calibrator\|self_calibration) import"` 在 `trader_shared/` 内复扫 |
| 回归无单测守护 | 先补最小测试基建；否则靠打包后 19 模块导入冒烟 + git 可回退 |
| 测试 ~15 个裸 import 短期依赖 scripts path | 第 6 步保留 `__init__.py` path 注入，后续统一迁移测试 |

---

## 后续

- ADR-002（走 PluginRegistry 组合点）、ADR-003（拆 monolith）依赖本 ADR 完成。
- 测试基建（conftest/pytest/CI + `render_single` 单测）建议**插在本 ADR 之后、ADR-002 之前**。
