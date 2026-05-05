# 可插拔架构改造 — 交接文档

> 2026-05-08 | commit: 02ebfce | 状态：✅ 三步全部完成

## 目标

将分析→决策→渲染三层从硬编码单体拆成可独立替换的模块：

```
数据源 ──→ [分析策略] ──→ [决策引擎] ──→ [渲染器] ──→ 输出
           ↑ 可换         ↑ 可配         ↑ 可换
```

## 已完成的改动

### ✅ 第一步：参数集中化

**改了 3 个文件，不改任何逻辑。**

| 文件 | 改动 |
|------|------|
| `02-共享模块-shared/trader_shared/config.py` | 新增所有硬编码常量（MA_PERIODS、MA_WEIGHTS、STATUS_SCORE、ATR 阈值、PYRAMID_SCALES、BASE_WEIGHTS 等），附带英文注释 |
| `02-共享模块-shared/02-候选逻辑-candidate/structure_core.py` | 原来的 7 个模块级常量改为 `try/except ImportError` fallback 模式，与已有 `RECENT_WINDOW` 风格一致。找不到 per-skill config 时自动使用默认值 |
| `02-共享模块-shared/02-候选逻辑-candidate/decision_core.py` | 同上：STATUS_SCORE、CHANGE_THRESHOLD_*、POSITION_RATIO_*、PYRAMID_SCALES、BASE_WEIGHTS、ATRLV_INDEX、ATR 阈值全改为可覆盖 |

**效果**：任何 per-skill `config.py` 现在都可以覆盖这些参数。不想覆盖的就走 fallback 默认值。

### 🔄 第二步：拆渲染（trader 已完成）

**目标**：`render_markdown()` 只做字符串拼接，不做任何业务判断。

| Skill | 文件 | 状态 | 改动内容 |
|-------|------|------|----------|
| **trader** | `01-单票分析-trader/scripts/run_analysis.py` | ✅ 完成 | `state_text`、`structure_view`、`volume_view`、`get_env_for_skill`、`position_cap` 计算全部从 `render_markdown` 移到 `build_report`。render 只读 `r["state_label"]`、`r["structure_note"]` 等预计算字段 |
| **t0-trader** | `t0_core.py` + `t0_run.py` | ❌ 未做 | `render_markdown` 直接调用 `side_status()`、`observation_value()` |
| **trader-pool** | 复用 trader 的 `run_analysis.py` | ✅ 自动完成 | 与 trader 同一份代码 |
| **trader-portfolio** | `portfolio_run.py` | ❌ 未做 | `render_markdown` 内调用 `sort_candidates`、`build_roles`、`build_advice`、内联 `fmt_ops` 决策 |
| **review-trader** | `review_render.py` + `review_compare.py` | ❌ 未做 | `render_single` 调用 `model_summary`，`render_compare` 调用 `classify` |

## 待完成

### 第二步剩余：拆 t0 / portfolio / review 的渲染

每个 skill 改法一致：
1. 在 build 函数末尾调用决策函数，把结果存入返回 dict
2. render 函数改为从 dict 读字段，不再调用任何决策函数
3. 验证：`diff` 新旧输出一字不变

### 第三步：定义策略契约

新建 `02-共享模块-shared/trader_shared/strategy_protocol.py`：

```python
# 最小契约：一个函数签名，不建类
def analyze(bars, quote, config) -> dict:
    """返回 {structure, momentum, volume, levels, verdict}"""
```

然后：
1. 把现有 `build_structure_context()` 包装成第一个策略实现
2. `build_report()` 中用 config 的策略列表驱动调用
3. 验证：`diff` 输出一字不变

## 验证命令

```bash
# 全部测试
python3 -m pytest 01-功能包-packages/*/tests/ -v

# 已知 1 个失败 (test_pack_all_bundle_structure)，是打包模块问题，与改造无关
```

## 不该动的东西

- `candidate_core.py`：兼容包装器，保持不动
- 分析逻辑内部的计算：只改常量的来源，不改计算公式
- 任何输出文本的措辞
