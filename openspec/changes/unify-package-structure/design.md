## Context

Trader 2.3 代码库有 111 处 sys.path 手动注入，原因是三个共享模块目录（`01-行情数据-market-data/`、`02-候选逻辑-candidate/`、`03-输出校验-contracts/`）不是 Python 包。当前通过 `_fix_paths.py`（166 行自动修补脚本）和每个文件开头的"双模式路径发现"（5-10 行样板代码）来维持运转。

现有 import 模式：
```python
# 每个文件都有这样的样板
_SCRIPT_DIR = Path(__file__).resolve().parent
if (_SCRIPT_DIR.parent / "trader_shared").exists():
    _SHARED = _SCRIPT_DIR.parent          # skill 模式
else:
    _SHARED = _SCRIPT_DIR.parents[3] / "02-共享模块-shared"  # 仓库模式
for _p in (SHARED_CANDIDATE, SHARED_MARKET, SHARED_SCRIPTS, SHARED_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from light_data import to_float  # 现在才能 import
```

## Goals / Non-Goals

**Goals:**
- 消灭 111 处 sys.path 手动注入
- 统一 import 为 `from trader_shared.xxx import ...`
- 支持 `pip install -e .` 开发安装
- 支持 `pytest` 直接运行测试（无需路径拼接）
- 渐进式迁移，每步可独立回滚

**Non-Goals:**
- 不改变业务逻辑
- 不改变打包部署流程（pack_all.py 继续工作）
- 不重命名模块文件名（只移动位置）
- 不拆分 light_data.py（那是另一个技术债）

## Decisions

### 1. 渐进式迁移而非一次性重构

**决策**: 分 3 个阶段，每阶段独立可回滚。

**为什么**: 一次性移动所有模块 + 修改所有 import 的改动面太大（60+ 文件），回归风险高。渐进式每步只改 10-15 个文件，容易 review 和回滚。

**阶段划分**:
- Phase 1: pyproject.toml + sys.path 集中化（改 5 个文件，消灭 111 处散落的 sys.path）
- Phase 2: 核心模块迁移（light_data, chan_core, wyckoff_core, momentum_core, signal_contract 等 ~15 个文件）
- Phase 3: 清理旧目录 + 更新打包脚本

### 2. trader_shared 作为唯一包名

**决策**: 所有模块最终都住在 `trader_shared/` 下。

**为什么**:
- `trader_shared` 已经是现有包名，下游代码已经在用
- 不需要改 `__init__.py` 的对外接口
- Python 包名不能以数字开头，`01-xxx` 格式不可用

### 3. 过渡期 __init__.py 自动配置 sys.path

**决策**: Phase 1 完成后，`trader_shared/__init__.py` 自动将旧目录加入 sys.path。

**为什么**: 确保迁移期间新旧 import 共存——已迁移的模块用新路径 import，未迁移的模块仍然通过 sys.path 魔法工作。

### 4. 每个模块迁移后跑全量测试

**决策**: 每移动一个模块，运行 `python3 -m pytest 02-共享模块-shared/tests/` 确认无回归。

**为什么**: import 路径变更是隐式的，编译器不会报错，只有运行时才会暴露问题。

## Risks / Trade-offs

**[打包脚本破坏]** pack_all.py 硬编码了旧目录路径，模块移动后打包失败
→ 缓解: Phase 3 同步更新 pack_all.py，迁移期间不删除旧目录

**[skill 安装失败]** 已安装的 skill 引用旧路径的模块
→ 缓解: Phase 1 的 __init__.py 兼容层确保旧路径仍然可用

**[测试遗漏]** 某个 import 路径改漏了，测试没覆盖到
→ 缓解: 每阶段跑全量测试，Phase 1 完成后运行 `python3 scripts/check_all.py`

**[过渡期混乱]** 新旧 import 共存，开发者不知道该用哪个
→ 缓解: 在 AGENTS.md 中记录规范，新代码一律用 `from trader_shared.xxx import ...`
