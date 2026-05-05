# Trader 计算引擎解耦计划

> 最后更新：2025-05-06
> 状态：草稿，待评审

---

## 一、现状诊断

### 1.1 当前架构的三层职责

当前系统中，`02-候选逻辑-candidate/` 目录下的文件同时承担了三件事，但没有层级边界：

| 文件 | 做的三件事 | 问题 |
|------|-----------|------|
| structure_core.py | ① 算 MA/振幅（通用指标）<br>② 构建支撑阻力/低吸区/止损/止盈（缠论结构理论）<br>③ 内部调用 status_for() 下结论（决策层） | 三件事写在一起 |
| decision_core.py | ① status_for() 用 if/else + YAML 规则判断状态<br>② score_for() 打分<br>③ livermore_scale() / base_weight() / atr_* 仓位算法 | 决策层和仓位算法耦合 |
| candidate_core.py | 把上面两个文件的符号全部 star-import 出来，当出口 | 聚合层，不产生新逻辑 |

一个函数调用链：

```
skill run_analysis.py
  → build_structure_context()      ← structure_core:149 缠论结构理论
    → moving_averages()            ← structure_core:95  算 MA（通用指标）
    → average_amplitude_pct()      ← structure_core:99  计算振幅（通用指标）
    → min_price() / max_price()    ← structure_core:75  辅助函数
    → choose_level()               ← structure_core:130 选支撑阻力
    → status_for()                 ← structure_core:186 调用决策层
      → RuleEngine.from_yaml()     ← rule_engine.py:36
      → if/else 硬编码回退逻辑     ← decision_core:70
```

**问题**：MA 计算、振幅计算属于"指标层"，却包在"缠论结构理论"函数里。如果加另一个理论（比如威科夫 RSI 背离），新理论也得重复写一套 MA 逻辑。

### 1.2 指标重复计算清单

同一个指标被多处各自实现，逻辑可能漂移：

| 指标 | 位置清单 |
|------|---------|
| MA | `structure_core.py:87` · `indicators.py:16(T0)` · `review_core.py:94(复盘)` |
| ATR | `decision_core.py:178` · `t0_candidate_core.py` 内联阈值 |
| RSI | `indicators.py:58(T0)` · `price_point_engine.py` 内联检测 |
| MACD | `indicators.py:41(T0)` · `price_point_engine.py` 内联检测 · `review_core.py:586(复盘)` |
| VWAP | `indicators.py:88(T0)` |
| 成交量比 | `indicators.py:104(T0)` · `review_core.py:69` |
| 布林带 | `indicators.py:154(T0)` · `price_point_engine.py` 内联 |
| ADX | `indicators.py:234(T0)` |
| 背离检测 | `indicators.py:196(T0)` · `indicators.py:215(T0)` |

### 1.3 策略链现状

`strategy_protocol.py` 的 `run_all()` 已写好了框架，但实际只注册了一个策略：

```python
# trader_shared/strategy_protocol.py:17
def run_all(current, bars, change_pct, quote, *strategies) -> dict:
    result = {}
    for fn in strategies:
        chunk = fn(current, bars, change_pct, quote)
        result.update(chunk)  # 后注册的理论覆盖先注册的
    return result

# run_analysis.py:107 - 只进了缠论一个策略
strategies = [build_structure_context]
levels = run_all(current, bars, change_pct, quote, *strategies)
```

`wyckoff_core.py`（威科夫检测）已经写好了，但它**没有被接入** `run_all()`。

### 1.4 决策层现状

`status_rules.yml` 已经写好了 YAML 规则引擎，但规则只消费价格字段：

```yaml
# 可用变量只有价格类
context: {current, support, confirm, stop, change, position_ratio, pressure_space_pct, above_ma5_ma10, below_ma_count}
# status_for() 不收任何"理论输出"— 没有 structure_levels、wyckoff_signal、rsi_divergence 等
```

---

## 二、目标架构

### 2.1 三层层分离

```
┌────────────────────────────────────────────────────────┐
│                    技能层 (skills/)                      │
│  trader · t0-trader · trader-pool · portfolio · review  │
│  调用 run_all(structure_strategy, wyckoff_strategy...)  │
│  消费多理论的合并结果                                    │
└──────────────┬─────────────────────────────────────────┘
               │ 合并 dict: {levels, wyckoff, rsi_div, ...}
               ▼
┌────────────────────────────────────────────────────────┐
│                 理论层 (theories/)                        │
│                                                         │
│  structure_strategy.py     缠论: 支撑/阻力/低吸区/止损/止盈 │
│  wyckoff_strategy.py       威科夫: spring/upthrust/背离    │
│  momentum_strategy.py      RSI 背离/动量检测               │
│  bollinger_strategy.py     布林带突破                      │
│                                                         │
│  每个理论:                                                │
│    - 消费指标库                                           │
│    - 产出自有 dict 结果                                   │
│    - 互不依赖，可加可删                                    │
└──────────────┬─────────────────────────────────────────┘
               │ {levels, wyckoff_signal, rsi_divergence, ...}
               ▼
┌────────────────────────────────────────────────────────┐
│                    决策层 (decision/)                     │
│                                                         │
│  status_for() 接收多理论结果 + 价格数据                    │
│  规则从 YAML 加载:                                        │
│    - when: 结构突破 AND 威科夫 = spring                   │
│    → then: "低吸观察"                                    │
│  新增: weight 字段，多冲突结果时加权决策                     │
│                                                         │
│  scorer_engine.py  基于同一套规则打分                       │
│  livermore.py       金字塔加仓级                           │
│                                                         │
│  不变：ATR / 仓位 / score_for 算法                        │
└──────────────┬─────────────────────────────────────────┘
               │ "低吸观察"/"冲高减仓"/... + score
               ▼
┌────────────────────────────────────────────────────────┐
│                  指标层 (indicators/)                     │
│                                                         │
│  通用计算函数，各理论自由调用                              │
│  ma.py      SMA / EMA                                   │
│  atr.py     ATR / 振幅 / 波动档位                          │
│  rsi.py     RSI (Wilder)                                │
│  macd.py    MACD DIF/DEA/柱                              │
│  adx.py     ADX                                         │
│  volume.py  VWAP / 成交量比                               │
│  bollinger.py  布林带                                    │
│  divergence.py RSI 背离 / 量价背离                         │
│  utils.py   clamp() / _num() 通用工具                      │
└────────────────────────────────────────────────────────┘
```

### 2.2 策略协议不变

```python
# 输入输出契约
def strategy(current: float, bars: list[dict], change_pct: Any, quote: dict) -> dict:
    """每个理论函数的统一签名。返回 dict 供 run_all() 合并。"""
    pass

# run_all() 不需要改
def run_all(current, bars, change_pct, quote, *strategies) -> dict:
    result = {}
    for fn in strategies:
        try:
            result.update(fn(current, bars, change_pct, quote))
        except Exception:
            continue
    return result
```

---

## 三、风险清单

### 风险 1：破坏面最大 — 5 个 skill 都在调 candidate_core

当前所有 skill 通过 `candidate_core` 导入函数：

| Skill | 导入路径 | 使用的函数 |
|-------|---------|-----------|
| 单票分析 (trader) | `from candidate_core import build_structure_context, atr_volatility_level` | 缠论结构、ATR |
| 选股池 (trader-pool) | `import candidate_core as core` | build_structure_context, STATUS_SCORE, atr_volatility_level |
| 仓位轮动 (portfolio) | `from candidate_core import score_for` | 打分、livermore、base_weight |
| 盘后复盘 (review) | `from candidate_core import atr_volatility_level` | ATR |
| 回测校准 (calibrator) | `from candidate_core import build_candidate_levels` | 兼容性包装函数 |

一旦移动函数位置，5 个调用方都要改 import。

### 风险 2：star-import 的隐蔽性

```python
# candidate_core.py
from decision_core import *   # 导出 decision_core 全部 top-level symbol
from structure_core import *   # 导出 structure_core 全部 top-level symbol
```

下游用 `from candidate_core import atr_volatility_level` 导入。移走函数后：
- 如果 `decision_core.py` 里的 `at_*` 函数都移走了，但 `candidate_core.py` 没有加新 import → import 失败
- 如果有 skill 的 import 没更新 → 运行时 `ImportError`，`try/except ImportError` 会静默降级，**不一定立刻暴露**

### 风险 3：本地懒加载耦合

```python
# structure_core.py:186 - 运行时而非编译时导入
from decision_core import status_for  # local import
```

这个模式避免了编译时循环依赖。拆层后：
- 如果 `status_for` 签名变了（加了理论参数），`structure_core` 里的调用点也要改
- 但 `structure_core` 已经变成了"理论模块"，它不应该再直接调"决策模块"— 这也是解耦的目标之一

### 风险 4：测试覆盖不足

```
tests/ 目录共 ~50 个单测，主要覆盖：
  - Signal Contract 校验 (13 tests)
  - Output 格式验证 (10+ tests)
  - signal tags 消费 (5-8 tests)
```

这些测试验证"输出的 Markdown 对不对"、"JSON 合约结构对不对"。**不验证计算逻辑**。

如果移走 MA 函数到新模块后，精度有 0.01 的差异：
- output 测试可能通过（因为文本不依赖精确数值）
- 但决策阈值（如 `position_ratio >= 0.72`）可能因为这个微小差异触发不同条件

### 风险 5：try/except 回退失效

当前有 `try/except ImportError` 回退模式：

```python
try:
    from config import MA_PERIODS
except Exception:
    MA_PERIODS = (5, 10, 20, 30)
```

但一旦把 `moving_average()` 函数本身移到新模块：
- 旧文件里删掉函数 → 如果导入失败，不能"回退到硬编码默认值"
- 因为函数本身不存在了，不像常量可以 fallback

### 风险 6：回退方案退化（最关键）

```python
# structure_core.py:186
from decision_core import status_for  # 运行时 local import
```

`status_for()` 在 `decision_core` 内是决策中枢。一旦解耦为：

```
structure_strategy → indicators.ma.moving_average()  ← 如果新模块有 bug，无法回退到内联实现
decision.status_for()  ← 签名改了影响面更大
```

**结论：解耦把"一个地方出错 → 一个 skill 挂掉"变成了"一层接口变了 → 五个 skill 全部要改"。**

---

## 四、渐进式迁移策略（分 3 阶段）

### Phase 1：最小改动 — 证明策略链可用

**不改任何现有函数和导入**，只加不加删。

#### 改动清单：

| 文件 | 操作 | 影响面 |
|------|------|--------|
| `trader_shared/strategy_protocol.py` | **不改** | 无 |
| `02-候选逻辑-candidate/wyckoff_core.py` | 加一个适配 `run_all()` 签名的包装函数 | **极低** |
| | ```python | |
| | def wyckoff_strategy(current, bars, change_pct, quote) -> dict: | |
| |     result = wyckoff_analysis(bars) | |
| |     return {"wyckoff": result} | |
| | ``` | |
| `trader/scripts/run_analysis.py:107` | 接入威科夫： | **仅单票分析** |
| | ```python | |
| | from wyckoff_core import wyckoff_strategy | |
| | strategies = [build_structure_context, wyckoff_strategy] | |
| | ``` | |
| `trader/scripts/run_analysis.py` | 在 `build_report()` 返回 dict 和 `render_markdown()` 中消费 `wyckoff` 字段 | 不影响其他 4 个 skill |

#### 验证：

```bash
python3 01-功能包-packages/01-单票分析-trader/scripts/final_report.py --target 南网科技
# 输出 Markdown 中应出现威科夫分析段落
```

**预期**：缠论 + 威科夫两个理论串行执行，结果合并（`result.update(chunk)`），后注册的覆盖先注册的键。

#### 如果 Phase 1 成功：

- 证明协议可行 → 可以安全卸载旧理论（从 `strategies` 列表移除）
- **不碰** `candidate_core`、`decision_core`、`structure_core` 的任何现有函数
- 不影响其他 4 个 skill

#### 如果 Phase 1 失败：

- 检查 `strategies` 列表中函数签名是否匹配
- 检查 `wyckoff_analysis()` 对 `bars` 的字段要求
- 修改策略函数适配，不引入任何新结构

---

### Phase 2：建指标库 — 新旧并行

**先写新的指标库，但不删旧的**。两个实现共存 1 个 release cycle。

#### 新文件（新建）：

| 文件 | 来源提取 | 统一函数签名 |
|------|---------|------------|
| `trader_shared/indicators/__init__.py` | index | re-export 所有 |
| `trader_shared/indicators/ma.py` | `structure_core.py:87` + `indicators.py:16` + `review_core.py:94` | `moving_average(closes, period) → float \| None` |
| `trader_shared/indicators/atr.py` | `decision_core.py:178` + `t0_candidate_core` | `atr_volatility_level(atr_ratio) → (str, int)` |
| `trader_shared/indicators/rsi.py` | `indicators.py:58` | `calculate_rsi(closes, period=14) → list[float \| None]` |
| `trader_shared/indicators/macd.py` | `indicators.py:41` + `review_core.py:586` | `calculate_macd(closes) → dict` |
| `trader_shared/indicators/volume.py` | `indicators.py:88` + `indicators.py:104` | `calculate_vwap_from_bars()` + `calculate_volume_ratio()` |
| `trader_shared/indicators/bollinger.py` | `indicators.py:154` | `calculate_bollinger_bands(closes)` |
| `trader_shared/indicators/divergence.py` | `indicators.py:196,215` | `detect_bullish_divergence(bars, rsi_series)` |
| `trader_shared/indicators/adx.py` | `indicators.py:234` | `calculate_adx(highs, lows, closes)` |
| `trader_shared/indicators/utils.py` | 通用工具 | `clamp()`, `_num()` |

#### 并行运行方式：

在 `trader_shared/indicators/__init__.py` 中做双实现：

```python
# 双写，默认走新的，加 flag 可切换
_USE_OLD = os.environ.get("TRADER_USE_OLD_INDICATORS") == "1"

def moving_average(closes, period):
    if _USE_OLD:
        from structure_core import moving_average as _old
        return _old(closes, period)
    from .ma import moving_average as _new
    return _new(closes, period)
```

#### 迁移步骤（逐步替换引用）：

1. 先替换 `wyckoff_strategy` 中不需要的依赖（它只读 bars，不依赖 MA）
2. 替换 `structure_core.py` 中的 `moving_averages()` 调用为 `from trader_shared.indicators import moving_averages`
3. 替换 `t0_candidate_core.py` 中的 ATR 逻辑
4. 替换 5 个 skill 中重复的计算
5. 经过 1 个 release cycle 无问题后，去掉 `_USE_OLD` 开关和旧代码

**此阶段不碰 `candidate_core` star-import**，下游 import 路径完全不变。

---

### Phase 3：`status_for()` 接收多理论结果（高风险）

**这是最大的风险点，建议 Phase 1 + Phase 2 稳定后再做。**

#### 改动：

**a) `status_rules.yml` 扩展**

```yaml
# 新增可用上下文变量
context:
  # 原有（价格类）
  current, support, confirm, stop, change, position_ratio, pressure_space_pct
  above_ma5_ma10, below_ma_count
  
  # 新增（理论输出）
  structure_levels       # structure_strategy 返回的支撑/阻力 dict
  wyckoff_spring         # bool: 是否触发 spring
  wyckoff_upthrust       # bool: 是否触发 upthrust
  wyckoff_summary        # str: 威科夫分析摘要
  rsi_divergence         # str: "bullish" | "bearish" | None
  adx_strength           # float: ADX 值
```

**b) `decision_core.status_for()` 签名扩展**

```python
# 从
def status_for(current, support, low_zone_upper, confirm, hard_stop,
               position_ratio, change_pct, ma_values, pressure_space_pct)

# 变为（加可选参数，保持向后兼容）
def status_for(current, support, low_zone_upper, confirm, hard_stop,
               position_ratio, change_pct, ma_values, pressure_space_pct,
               # 新增理论参数（向后兼容，默认 None）
               wyckoff_spring=None, wyckoff_upthrust=None,
               rsi_divergence=None, adx_strength=None):
```

**c) `structure_core.build_structure_context()` 改动**

它内部调用 `status_for()` 的地方需要同时消费 `run_all()` 返回的多理论结果。

但这有个问题：`structure_strategy` 内部已经调了 `status_for()`— 也就是说**理论自己下结论**。

#### 架构抉择：两层决策是否重复？

当前流程：
```
structure_strategy → 内部调 status_for() 下结论 → 返回 {"status": "低吸观察"}
```

如果要让决策层同时消费多理论结果，有两种方案：

**方案 A：理论只产出原始结果，决策层下结论（推荐）**

```python
# theory: structure_strategy() → {levels: {support, resistance, ...}, status: None}
# theory: wyckoff_strategy() → {spring: True, summary: "弹簧信号..."}
# decision: status_for() 接收全部结果 → {"status": "低吸观察", "reason": "structure_breakout + wyckoff_spring"}
```

`build_structure_context()` **不再内部调用 `status_for()`**，只输出 levels。

**方案 B：理论下结论，决策层做加权仲裁**

```python
# theory: structure_strategy() → {status: "等转强", weight: 0.5}
# theory: wyckoff_strategy() → {status: "低吸观察", weight: 0.3}
# decision: 加权投票 → "等转强" wins
```

**推荐方案 A**，因为当前方案 B 中决策层已经被缠论"承包"了（`structure_core:186` 直接调 `status_for()`），解耦后决策层应该从缠论中独立出来。

**d) 下游改造**

`run_analysis.py`、`portfolio_core.py`、`final_pool.py` 都要更新：
- 从 `run_all()` 结果中提取 `status`
- 从合并的 dict 中提取各理论字段传给 `status_for()`

---

## 五、各阶段验收标准

### Phase 1 验收

- [ ] `final_report.py --target 南网科技` 输出中包含威科夫分析段落
- [ ] 输出中同时有缠论和威科夫两部分
- [ ] 只改了 `strategies = [...]` 一行和 `render_markdown()` 一个函数
- [ ] 其他 4 个 skill 的输出**完全不变**
- [ ] `python3 scripts/self_check.py` 通过

### Phase 2 验收

- [ ] `trader_shared/indicators/` 下所有模块可单独 import
- [ ] 5 个 skill 中至少 3 个的重复指标计算已替换
- [ ] 设置 `TRADER_USE_OLD_INDICATORS=1` 时行为与替换前一致
- [ ] `python3 -m pytest 01-功能包-packages/*/tests/` 全部通过
- [ ] 对比替换前后的计算结果，差异 < 0.01

### Phase 3 验收

- [ ] `status_for()` 签名向后兼容（不传新参数行为不变）
- [ ] `status_rules.yml` 中有至少 1 条使用威科夫信号的条件规则
- [ ] `final_report.py --target 南网科技` 输出的状态受多理论影响
- [ ] 移除 `build_structure_context()` 内部的 `status_for()` 调用
- [ ] 全部 50+ 个单测通过
- [ ] 手动验证 3 个以上股票的输出一致性

---

## 六、卸载旧理论的完整流程

当新架构稳定后，卸载旧理论的步骤：

```bash
# 1. 备份
cp -r 02-共享模块-shared/02-候选逻辑-candidate/ ~/backup/candidate_pre_decouple/

# 2. Phase 1: 接入新理论，验证并行可用
#    不改任何现有文件

# 3. Phase 2: 迁移指标，新旧并行
#    验证 1 个 release cycle

# 4. Phase 3: 改造 status_for() 接收多理论结果

# 5. 卸载（所有改动完成后）
#    a. 从 strategies 列表中移除旧理论
#       strategies = [wyckoff_strategy]  # 只留威科夫
#    b. 删除旧指标函数（不再被任何地方引用）
#    c. 更新 candidate_core.py 的 star-import（移除已删除的 symbol）
#    d. 最终状态：
#       02-候选逻辑-candidate/
#       ├── candidate_core.py     # 兼容包装：build_candidate_levels() → build_structure_context()
#       ├── decision_core.py      # status_for() + score_for() + livermore + ATR
#       ├── structure_core.py     # build_structure_context() → 内部不再调 status_for()
#       ├── wyckoff_core.py       # wyckoff_analysis() + wyckoff_strategy()
#       
#       trader_shared/
#       ├── theory_core/
#       │   ├── structure_strategy.py   # 缠论理论
#       │   ├── wyckoff_strategy.py     # 威科夫理论
#       │   └── __init__.py
#       ├── indicators/
#       │   ├── ma.py, atr.py, rsi.py, macd.py, ...
#       │   └── __init__.py
#       ├── strategy_protocol.py
#       ├── status_rules.yml
#       └── decision_engine.py          # 新的决策层
```

---

## 七、各阶段可独立交付

| 阶段 | 交付物 | 能否单独运行 | 影响面 |
|------|--------|------------|--------|
| Phase 1 | 威科夫策略接入 | 是 — 只改一个 skill | 仅 trader |
| Phase 2 | 指标库 + 部分替换 | 是 — 新旧并行 | 渐进式，可随时回退 |
| Phase 3 | 决策层解耦 | 是 — 向后兼容 | 5 个 skill，风险最高 |

**建议**：Phase 1 验证策略链 → 用 1-2 天做，立刻看到效果 → 决定下一步。

---

## 八、决策记录

| 决策 | 方案 A（推荐） | 方案 B（备选） | 理由 |
|------|--------------|--------------|------|
| 理论下结论还是集中决策 | 集中决策（方案 A） | 理论各自下结论 | 避免多理论结论冲突，决策规则可统一配置 |
| 指标库实现策略 | 新建 + 旧并行 | 原地修改 + 回退 flag | 保留旧实现可随时切换 |
| 迁移顺序 | indicator → theory → decision | decision → theory → indicator | 指标层破坏面最小，先移最安全 |
| 新理论接入方式 | 写函数 + 塞进 strategies | 注册表 + 配置 | 简单即战力，注册表后续优化 |

---

## 附录 A：当前 `status_for()` 完整调用链

```
structure_core.build_structure_context() [line 149-225]
  └─ 调用 decision_core.status_for() [line 186-198]  ← 缠论理论内部直接下结论
      └─ RuleEngine.from_yaml("status_rules.yml") [line 70]  ← 先试 YAML
      └─ 回退 if/else 硬编码 [line 80-97]  ← YAML 没匹配时
  
  返回 {"status": "低吸观察", "levels": {...}, ...}  ← 结论混在理论结果里
```

## 附录 B：`strategy_protocol.py` 当前状态

```python
# 已就绪，接收多策略
def run_all(current, bars, change_pct, quote, *strategies) -> dict:
    result = {}
    for fn in strategies:
        try:
            result.update(fn(current, bars, change_pct, quote))
        except Exception:
            continue
    return result

# 但只进一个策略
# run_analysis.py:107
strategies = [build_structure_context]  # ← 缠论
```

## 附录 C：wyckoff_core.py 已就绪但没有接入

```python
# wyckoff_core.py 已实现，但没被 run_all() 调用
wyckoff_analysis(bars) → {spring_signal, upthrust_signal, ...}

# 需要加一个简单的适配函数
def wyckoff_strategy(current, bars, change_pct, quote) -> dict:
    result = wyckoff_analysis(bars)
    return {"wyckoff": result}

# 然后
strategies = [build_structure_context, wyckoff_strategy]
```
