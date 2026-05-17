# P0-P4 实施后改进计划

> 状态：待实施（前置依赖：buy-zone-accessibility-fix-plan P0-P4 完成）
> 创建日期：2026-05-14
> 前置：buy-zone-accessibility-fix-plan.md 中 P0-P4 已全部实施并通过验证
> 背景：P0-P4 实施后，从理论和代码两个角度审查，发现 7 项待改进项

---

## 一、理论角度 — 策略逻辑缺陷

### I-1. 费波纳契只用上攻笔算回调，遗漏下跌笔反弹位

**现状**：`_compute_fib_retrace()` 只取最近一个 `direction=up` 的笔计算 38.2%/50%/61.8% 回撤位。

**问题**：
- 下跌笔的反弹位同样重要：从 swing_high → swing_low 的下跌，38.2%/50%/61.8% 是空头的压力参考
- 只算回撤不算反弹 = 只给了"低吸"参考，没给"高抛"参考
- 对 T0 高抛价位的指导性不足

**方案**：同时取最近一个 `direction=down` 的笔算反弹位，输出两个字段：

```python
"fib_retrace_up": {        # 上攻笔回撤（低吸参考）
    "swing_high": 12.50, "swing_low": 10.00,
    "382": 11.55, "500": 11.25, "618": 10.96
},
"fib_retrace_down": {      # 下跌笔反弹（高抛参考）
    "swing_high": 12.50, "swing_low": 10.00,
    "382": 10.96, "500": 11.25, "618": 11.55
}
```

**影响范围**：`structure_core.py` 的 `_compute_fib_retrace()` + `build_structure_context()` 返回值 + 报告渲染

---

### I-2. 费波纳契没考虑笔的"有效性"

**现状**：`_compute_fib_retrace` 不验证笔的长度或振幅，任何笔都参与计算。

**问题**：
- 缠论笔有最小 K 线数要求（`CHANLUN_MIN_BARS_PER_STROKE=5`），但费波纳契计算不检查
- 一根只有 2 根 K 线的毛刺笔也可能被选中，导致回调位失真
- 实战中，振幅太小的笔没有费波纳契参考价值

**方案**：过滤笔时增加两个校验：

```python
# 校验1：笔的 bar 数量 >= CHANLUN_MIN_BARS_PER_STROKE
stroke_bars = stroke.get("end_idx", 0) - stroke.get("start_idx", 0) + 1
if stroke_bars < 5:
    continue

# 校验2：振幅 > 1.5 倍 ATR（避免毛刺笔）
stroke_range = swing_high - swing_low
if atr_pct and stroke_range / current < atr_pct * 1.5:
    continue
```

**影响范围**：`structure_core.py` 的 `_compute_fib_retrace()`

---

### I-3. 理论微调系数是"开关式"而非"渐变式"

**现状**：`_theory_multipliers` 是硬编码阶梯值：

```python
# 当前实现
if signal.confidence >= 0.4:
    zone_width = 1.15   # 无论 confidence 是 0.40 还是 0.95
```

**问题**：
- confidence=0.40 和 confidence=0.95 的缠论上攻笔，zone_width 乘数都是 1.15
- 理论上 confidence 越高，调整幅度应该越大
- 开关式导致"弱信号和强信号获得同样加成"，不够精细

**方案**：改为线性插值：

```python
def _confidence_scale(confidence: float, low: float, high: float,
                      base: float = 1.0, max_adj: float = 0.15) -> float:
    """confidence 在 [low, high] 区间线性映射到 [base, base+max_adj]"""
    if confidence < low:
        return base
    if confidence > high:
        return base + max_adj
    ratio = (confidence - low) / (high - low)
    return base + max_adj * ratio

# 使用示例
zone_width_mult = _confidence_scale(chan_conf, 0.4, 1.0, base=1.0, max_adj=0.15)
# confidence=0.4 → 1.00
# confidence=0.7 → 1.075
# confidence=1.0 → 1.15
```

**影响范围**：`structure_core.py` 的 `_theory_multipliers()`，所有理论信号的 multiplier 计算逻辑

---

### I-4. 三理论信号独立乘，没有交叉验证

**现状**：缠论看多 + 威科夫看多 + 动量看多时，三个 multiplier 各自生效：

```python
# 三信号共振时
zone_width *= 1.15     # 缠论
confirm_buffer *= 0.70 # 威科夫
space_threshold *= 0.80 # 动量
# 综合效果：三个参数同时偏移，没有全局校验
```

**问题**：
- 三个信号方向一致时，不同参数的乘积效应可能导致"过于激进"
- 例如 zone_width 放大 + confirm_buffer 缩小 + space_threshold 收窄 = 三重放宽
- 缺乏"方向一致时的安全边界"

**方案**：加全局安全检查——三信号方向一致时，限制任何 multiplier 偏离 1.0 不超过 ±20%：

```python
def _apply_theory_multipliers(zone_w, confirm_b, space_t, signals):
    # ... 原有计算 ...

    # 全局安全检查：三信号方向一致时限制偏移
    directions = [s.direction for s in signals if s is not None]
    if len(set(directions)) == 1 and len(directions) >= 2:
        # 全部同向，限制 ±20%
        MAX_DEVIATION = 0.20
        zone_w = 1.0 + max(-MAX_DEVIATION, min(MAX_DEVIATION, zone_w - 1.0))
        confirm_b = 1.0 + max(-MAX_DEVIATION, min(MAX_DEVIATION, confirm_b - 1.0))
        space_t = 1.0 + max(-MAX_DEVIATION, min(MAX_DEVIATION, space_t - 1.0))

    return zone_w, confirm_b, space_t
```

**影响范围**：`structure_core.py` 的 `_theory_multipliers()` 返回后

---

### I-5. 时间窗口检测器只找一个 pivot，缺多级转折点

**现状**：`_find_pivot_index()` 只返回最近一个转折点，所有周期从同一个 pivot 计数。

**问题**：
- 费波纳契/江恩时间窗口理论要求从不同级别的转折点分别计数
- 大级别转折看 144/360 bar，小级别看 21/34/55 bar
- 单一 pivot 导致小周期窗口频繁命中（噪声），大周期窗口命中率低

**方案**：识别最近 2-3 个转折点（大/中/小级别），分别匹配对应级别的窗口周期：

```python
def _find_multi_level_pivots(bars, max_pivots=3):
    """找多个级别的转折点"""
    pivots = []
    # 方法：从不同窗口长度找局部极值
    windows = [5, 15, 40]  # 小/中/大级别
    for w in windows:
        for i in range(len(bars) - 1, max(w, len(bars) - 100), -1):
            is_peak = all(bars[i].high >= bars[j].high for j in range(max(0,i-w), min(len(bars),i+w+1)) if j != i)
            if is_peak:
                pivots.append({"index": i, "level": w, "type": "peak"})
                break
    return pivots

# 匹配规则：
# 大级别 pivot → 检测 90/144/360
# 中级别 pivot → 检测 55/89
# 小级别 pivot → 检测 21/34
```

**影响范围**：`time_window_detector.py` 的 `_find_pivot_index()` 和 `check_time_windows()`

---

### I-6. 筹码信号在 P3 中被规划但未实现

**现状**：修复计划中明确提到"筹码峰密集在支撑位附近 → support_level 权重 +0.10"，但 `_theory_multipliers` 中没有筹码相关代码。

**问题**：
- 筹码分布是 A 股最重要的特色理论之一
- 当前 fusion_core 的 `signals_detail` 可能包含筹码信号，但 `structure_core` 没有读取
- 缺失筹码信号 = 缺少一个重要的支撑/阻力强度评估维度

**方案**：

1. 确认 `fusion_core.py` 的 `signals_detail` 中是否已有筹码信号
2. 如果有：在 `_theory_multipliers` 中读取并映射到 `support_weight` 调整
3. 如果没有：需要先在 `fusion_core` 中接入 `chip_core` 的输出

```python
# 筹码信号映射
chip_signal = _extract_signal(fusion_result, "chip")
if chip_signal and chip_signal.direction == "bullish":
    support_weight += 0.10  # 支撑位权重提升
elif chip_signal and chip_signal.direction == "bearish":
    confirm_buffer_mult = 1.10  # 确认缓冲加宽，更保守
```

**前置**：需先检查 `fusion_core.py` 和 `chip_core.py` 的接口

---

## 二、代码角度 — 工程质量与健壮性

### C-1. `build_structure_context` 函数签名膨胀

**现状**：函数签名已有 6 个参数，其中 `fusion_result` 和 `chan_result` 是新增的可选参数：

```python
def build_structure_context(current, bars, change_pct=None, quote=None,
                            fusion_result=None, chan_result=None):
```

**问题**：
- 每次加功能都要加参数，违反开闭原则
- 可选参数越来越多，调用方需要记住参数顺序
- 未来 P4 的时间窗口、筹码信号可能还要加更多参数

**方案**：改为 `options: dict` 模式：

```python
def build_structure_context(current, bars, change_pct=None, quote=None, *,
                            options=None):
    opts = options or {}
    fusion_result = opts.get("fusion_result")
    chan_result = opts.get("chan_result")
    # 未来扩展只需在 opts 中加 key
```

调用方：
```python
ctx = build_structure_context(current, bars, options={
    "fusion_result": fusion,
    "chan_result": chan,
    # 未来: "chip_result": chip, "time_windows": tw
})
```

**影响范围**：`structure_core.py` + 所有调用方（`run_analysis.py`, `t0_candidate_core.py` 等）

---

### C-2. `decision_core.status_for` 和 `t0_candidate_core.status_for` 逻辑分裂

**现状**：两个文件各有一个 `status_for`，判定规则不完全一致：

| 判定 | decision_core | t0_candidate_core |
|------|--------------|-------------------|
| "空间不足" | 有（已降优先级） | 无 |
| MA 过滤 | 有 | 无 |
| 动态 space_threshold | 有（ATR） | 无 |
| "低吸观察" | 有 | 有 |

**问题**：
- P1 让 T0 复用了 trader 的价位，但状态判定逻辑仍然分裂
- 同一只票在 trader 和 T0 中可能给出不同状态
- 后续任何判定逻辑修改需要同步改两处

**方案**：让 `t0_candidate_core.status_for` 直接调用 `decision_core.status_for`：

```python
# t0_candidate_core.py
from decision_core import status_for as _trader_status_for

def status_for(current, support, resistance, ...):
    # 复用 trader 的核心判定逻辑
    result = _trader_status_for(current, support, resistance, ...)
    # T0 特有的覆盖（如有）
    # ...
    return result
```

**影响范围**：`t0_candidate_core.py`，需确认 T0 是否有独有的状态判定需要保留

---

### C-3. `THEORY_ADJUST_LOG_ONLY` import 路径有隐患

**现状**：`structure_core.py` 中：

```python
from config import THEORY_ADJUST_LOG_ONLY
```

**问题**：
- 这依赖当前工作目录下的 `config.py`（可能是 skill 级别的 config），而非 `trader_shared.config`
- 打包后（zip 环境）工作目录不同，可能导致读不到
- `fusion_core.py` 用的是 `from trader_shared.config import FUSION_LOG_ONLY`，风格不一致

**方案**：统一为绝对导入：

```python
from trader_shared.config import THEORY_ADJUST_LOG_ONLY
```

**影响范围**：`structure_core.py` 第 361 行附近

---

### C-4. `_theory_multipliers` 和 `_compute_fib_retrace` 缺少单元测试

**现状**：只有手动终端验证，没有正式的 `test_*.py` 文件。

**问题**：
- 这些是核心决策逻辑，一旦被后续修改打破，很难发现
- 手动验证无法覆盖边界情况
- 回归风险高

**方案**：新增 `test_structure_core_p3_p4.py`，覆盖：

```python
# 测试用例设计
class TestTheoryMultipliers:
    def test_all_signals_bullish(self): ...    # 三信号看多
    def test_partial_signals(self): ...        # 部分信号
    def test_no_signals(self): ...             # 无信号→退化为1.0
    def test_conflicting_signals(self): ...    # 冲突信号
    def test_confidence_interpolation(self): ...  # 线性插值（I-3实施后）

class TestFibRetrace:
    def test_up_stroke(self): ...              # 上攻笔回撤
    def test_down_stroke(self): ...            # 下跌笔反弹（I-1实施后）
    def test_no_strokes(self): ...             # 无笔数据
    def test_invalid_stroke(self): ...         # 异常笔（I-2实施后）

class TestTimeWindow:
    def test_exact_window_hit(self): ...       # 刚好在窗口内
    def test_just_outside_window(self): ...    # 刚好在窗口外
    def test_no_pivot(self): ...               # 无转折点
```

**影响范围**：新建测试文件

---

### C-5. `average_atr_pct` 第一根 bar 的 TR 不够准确

**现状**：第一根 bar 没有 `prev_close`，直接用 `high - low` 作为 TR：

```python
for i, bar in enumerate(bars[-period:]):
    if i == 0:
        tr = bar.high - bar.low  # 精度略低
    else:
        prev_close = bars[-(period) + i - 1].close
        tr = max(bar.high - bar.low,
                 abs(bar.high - prev_close),
                 abs(bar.low - prev_close))
```

**问题**：
- 如果传入的 bars 前面还有数据，可以往前多取一根获取 `prev_close`
- 第一根 bar 的 TR 偏小（跳空高开/低开时误差最大）

**方案**：调用时多传一根 bar，ATR 从第 2 根开始计算：

```python
# run_analysis.py 调用处
bars_for_atr = bars[-21:]  # 多取一根
atr_pct = average_atr_pct(bars_for_atr, period=20)  # 内部跳过第一根

# 或者在 average_atr_pct 内部处理
def average_atr_pct(bars, period=20):
    trs = []
    for i in range(1, len(bars)):  # 从第2根开始
        prev_close = bars[i-1].close
        tr = max(bars[i].high - bars[i].low,
                 abs(bars[i].high - prev_close),
                 abs(bars[i].low - prev_close))
        trs.append(tr)
    avg_tr = sum(trs[-period:]) / min(period, len(trs))
    return avg_tr / bars[-1].close
```

**影响范围**：`structure_core.py` 的 `average_atr_pct()` + 调用方

---

### C-6. `time_window_detector` pivot 检测降级方案太粗糙

**现状**：降级方案只找最近 20 根 K 线内的最高点：

```python
# 降级方案
recent = bars[-20:]
pivot_idx = max(range(len(recent)), key=lambda i: recent[i].high)
```

**问题**：
- 最高点不一定是转折点（可能是连续上涨的末端）
- 真正的转折点应该满足"前后都更低"（局部极值）

**方案**：降级方案改为局部极值检测：

```python
def _find_pivot_fallback(bars, lookback=30):
    """找满足局部极值的转折点"""
    recent = bars[-lookback:]
    for i in range(len(recent)-2, 0, -1):
        if (recent[i].high > recent[i-1].high and
            recent[i].high > recent[i+1].high):
            return len(bars) - lookback + i
    # 没找到局部极值，退回最高点
    return len(bars) - lookback + max(range(len(recent)), key=lambda i: recent[i].high)
```

**影响范围**：`time_window_detector.py` 的 `_find_pivot_index()`

---

### C-7. `run_analysis.py` 调用链未打通 — P3/P4 增强不生效

**现状**：`build_structure_context` 新增了 `fusion_result` 和 `chan_result` 参数，但 `run_analysis.py` 中调用时没有传入：

```python
# run_analysis.py 当前调用
ctx = build_structure_context(current, bars, change_pct, quote)
# fusion_result 和 chan_result 未传入 → P3 理论微调和 P4 费波纳契不生效
```

**问题**：
- P3/P4 的增强在当前 trader skill 的实际运行中**不生效**
- 代码结构上准备好了，但调用链没打通
- 这是**最紧急**的问题——改了等于没改

**方案**：在 `run_analysis.py` 中先调用融合层和缠论，再把结果传给 `build_structure_context`：

```python
# run_analysis.py 修改
from fusion_core import compute_fusion
from chan_core import analyze_chan

# 在调用 build_structure_context 之前
fusion_result = compute_fusion(bars, quote) if bars else None
chan_result = analyze_chan(bars) if bars else None

ctx = build_structure_context(current, bars, change_pct, quote,
                              fusion_result=fusion_result,
                              chan_result=chan_result)
```

**影响范围**：`run_analysis.py`，需确认 fusion_core 和 chan_core 的接口

---

## 三、实施优先级

| # | ID | 内容 | 类别 | 影响 | 难度 | 优先级 |
|---|-----|------|------|------|------|--------|
| 1 | C-7 | 打通 `run_analysis.py` 调用链 | 代码 | P3/P4 当前不生效，最紧急 | 中 | **P0** |
| 2 | C-2 | 合并两个 `status_for` | 代码 | 消除长期逻辑分裂 | 中 | **P1** |
| 3 | C-3 | 修复 `THEORY_ADJUST_LOG_ONLY` import 路径 | 代码 | 打包后可能失效 | 低 | **P1** |
| 4 | I-3 | 理论微调改为渐变式 | 理论 | 提高精度 | 低 | **P2** |
| 5 | I-4 | 三信号交叉验证加安全边界 | 理论 | 防止过于激进 | 低 | **P2** |
| 6 | I-1 | 费波纳契加下跌笔反弹位 | 理论 | 补全理论维度 | 低 | **P2** |
| 7 | I-2 | 费波纳契笔有效性校验 | 理论 | 防止毛刺笔 | 低 | **P2** |
| 8 | C-5 | ATR 前置一根 bar | 代码 | 小幅提升准确度 | 低 | **P3** |
| 9 | C-6 | 时间窗口降级方案改进 | 代码 | 提高鲁棒性 | 低 | **P3** |
| 10 | I-5 | 时间窗口多级转折点 | 理论 | 提高时间窗口准确性 | 中 | **P3** |
| 11 | I-6 | 筹码信号接入 P3 | 理论 | 补全 A 股特色维度 | 中 | **P3** |
| 12 | C-1 | 函数签名改为 options dict | 代码 | 长期可维护性 | 低 | **P4** |
| 13 | C-4 | 新增单元测试 | 代码 | 防回归 | 中 | **P4** |

### 依赖关系

```
C-7 (调用链打通)
  ├── I-3 (渐变式微调) ← 需要 fusion_result 能传入
  ├── I-4 (交叉验证) ← 需要三信号都能获取
  ├── I-1 (下跌笔反弹) ← 需要 chan_result 能传入
  └── I-2 (笔有效性) ← 同上

C-2 (合并 status_for) ← 独立，可并行
C-3 (import 路径) ← 独立，可并行

I-6 (筹码信号) ← 依赖 fusion_core 是否已有筹码输出
C-1 (options dict) ← 建议在 I-1/I-3 实施时一起改
C-4 (单元测试) ← 建议在所有理论改动完成后统一补
```

---

## 四、验收标准

### C-7 调用链打通

- [ ] `run_analysis.py` 传入 `fusion_result` 和 `chan_result`
- [ ] trader 报告中可见费波纳契回调位（fib_retrace）
- [ ] trader 报告中可见理论微调效果（日志中 multiplier ≠ 1.0）
- [ ] 无 fusion/chan 数据时不报错，退化为纯数学计算

### C-2 合并 status_for

- [ ] 同一只票在 trader 和 T0 中状态一致
- [ ] T0 特有逻辑（如有）仍保留

### I-3 渐变式微调

- [ ] confidence=0.4 → multiplier=1.00
- [ ] confidence=0.7 → multiplier≈1.075
- [ ] confidence=1.0 → multiplier=1.15
- [ ] confidence<0.4 → multiplier=1.00

### I-1 下跌笔反弹位

- [ ] 同时输出 `fib_retrace_up` 和 `fib_retrace_down`
- [ ] T0 高抛价位参考下跌笔反弹位
- [ ] 无下跌笔时 `fib_retrace_down` 为空

### I-4 交叉验证

- [ ] 三信号同向时，任何 multiplier 不超过 1.0 ± 20%
- [ ] 非同向时不受限

---

## 五、风险与注意事项

1. **C-7 打通调用链需确认 fusion_core / chan_core 接口**：这两个模块可能在某些 skill 环境中不可用（如 T0 skill 不一定运行缠论分析），需要做好 `try/except` 和降级

2. **I-3 渐变式微调可能改变现有行为**：原来 confidence=0.4 就给 1.15 的加成，改为渐变后只给 1.0。需要确认是否有"弱信号也给加成"的业务需求

3. **C-2 合并 status_for 需确认 T0 独有逻辑**：T0 可能有特有的状态判定（如盘中急跌后的状态），需要先梳理清楚再合并

4. **I-6 筹码信号需要先检查 fusion_core 接口**：如果 fusion_core 尚未接入 chip_core，需要先做那一步

---

## 六、深度审查补充 — 新发现问题

> 以下问题在初次审查中遗漏，经逐行重读全部核心文件后发现

### C-8. `status_rules.yml` 中"空间不足"规则仍用硬编码 0.008，与 Python 代码的 ATR 动态阈值矛盾

**现状**：`decision_core.py` 第 144-159 行，当规则引擎可用时，优先走 `status_rules.yml`：

```yaml
# status_rules.yml 第 43-45 行
- name: 空间不足
  result: 空间不足
  when: pressure_space_pct >= 0 and pressure_space_pct < 0.008
```

但 Python fallback 代码用的是动态阈值：
```python
# decision_core.py 第 177 行
if 0 <= pressure_space_pct < space_threshold:  # space_threshold 由 ATR 动态计算
```

**问题**：
- 当 `RuleEngine.from_yaml()` 成功加载时，**永远走 yml 规则**，Python fallback 的 ATR 动态阈值根本不生效
- yml 中硬编码 `0.008` 与 P2 的动态阈值方案直接矛盾——高波幅票应给更多容忍，但 yml 一刀切 0.8%
- 这意味着 P0+P2 的核心改进在规则引擎可用的环境下**完全失效**

**方案**：在 yml 中也改用动态变量：

```yaml
- name: 空间不足
  result: 空间不足
  when: pressure_space_pct >= 0 and pressure_space_pct < space_threshold
```

同时需要修改 `RuleEngine` 或在 `decision_core` 传入 `space_threshold` 作为 context 变量（当前已传入 `pressure_space_pct`，同理可加）。

**影响范围**：`status_rules.yml` + `decision_core.py` 的 `engine.evaluate(ctx)` 调用

---

### C-9. `run_analysis.py` 中 `run_all()` 的调用顺序导致 `build_structure_context` 拿不到融合层/缠论数据

**现状**：`run_analysis.py` 第 159-160 行：

```python
strategies = [build_structure_context, chanlun_strategy, wyckoff_strategy, momentum_strategy]
levels = run_all(current, bars, quote.get("current_change_pct"), quote, *strategies)
```

`run_all` 按顺序执行策略，`build_structure_context` 排在第一个，此时 `chan_result` 和 `fusion_result` 还没有产出。

**问题**：
- 即使 C-7 修复了"传入参数"的问题，**执行顺序**仍然导致 `build_structure_context` 在缠论/威科夫/动量之前运行
- 融合层 `merge_decisions` 在第 178-188 行单独调用，不在 `run_all` 流程中
- 正确的顺序应该是：缠论 → 威科夫 → 动量 → 融合层 → structure_core

**方案**：调整 `run_all` 的策略顺序，或将 `build_structure_context` 从 `run_all` 中抽出：

```python
# 方案 A：调整顺序
strategies = [chanlun_strategy, wyckoff_strategy, momentum_strategy]
levels = run_all(current, bars, change_pct, quote, *strategies)
# 然后单独调用
from fusion_core import merge_decisions
fusion_result = merge_decisions(levels["chanlun"], levels["momentum"], levels["wyckoff"], ...)
levels["structure"] = build_structure_context(current, bars, change_pct, quote,
                                              fusion_result=fusion_result,
                                              chan_result=levels["chanlun"])
```

**影响范围**：`run_analysis.py` 的 `build_report()` 函数 + `strategy_protocol.run_all()` 的调用方式

---

### I-7. 筹码支撑/阻力位已计算但未传入 `structure_core` 的支撑/阻力候选列表

**现状**：`run_analysis.py` 第 222-256 行已经计算了 `chip_support` 和 `chip_resistance`，但只用于报告渲染（"关键价位"区域）。`build_structure_context` 内部的 `support_levels` / `resistance_levels` 列表不包含筹码数据。

**问题**：
- 筹码峰密集区是最真实的支撑/阻力（代表真实持仓成本），但 `choose_level` 选支撑/阻力时完全不考虑
- 筹码支撑可能比 5 日低点更有意义（大量持仓成本的支撑），但不参与加权选择
- I-6 提到"筹码信号接入 P3"，但更基础的问题是筹码价位没进入候选列表

**方案**：在 `build_structure_context` 内部或外部注入筹码支撑/阻力：

```python
# 方案 A：在 build_structure_context 调用前，把筹码价位加到 quote 中
quote_with_chip = dict(quote)
quote_with_chip["chip_support"] = chip_support
quote_with_chip["chip_resistance"] = chip_resistance

# 方案 B：build_structure_context 接受 options 中传入
ctx = build_structure_context(current, bars, change_pct, quote,
                              options={"chip_support": chip_support,
                                       "chip_resistance": chip_resistance})
```

然后在 `build_structure_context` 内部：
```python
if chip_support := (quote or {}).get("chip_support"):
    add_level(support_levels, "筹码支撑", chip_support, 0.95)
if chip_resistance := (quote or {}).get("chip_resistance"):
    add_level(resistance_levels, "筹码阻力", chip_resistance, 0.95)
```

**影响范围**：`structure_core.py` 的 `build_structure_context()` + `run_analysis.py` 的调用

---

### I-8. 费波纳契回调位未参与 `choose_level` 的支撑/阻力候选

**现状**：`_compute_fib_retrace()` 计算了 38.2%/50%/61.8% 回调位，但结果只作为附加信息输出（`fib_retrace` 字段），不参与 `support_levels` / `resistance_levels` 的加权选择。

**问题**：
- 费波纳契 61.8% 回调位经常与结构支撑重合，是极强的支撑参考
- 但它不在候选列表中，不会被 `choose_level` 选中
- 结果是：费波纳契只作为"展示信息"而非"决策依据"

**方案**：将费波纳契关键回调位注入候选列表：

```python
fib = _compute_fib_retrace(chan_result)
if fib:
    # 61.8% 回调位作为强支撑参考
    add_level(support_levels, "费波纳契61.8%", fib["618"], 0.80)
    # 50% 回调位作为中等支撑参考
    add_level(support_levels, "费波纳契50%", fib["500"], 0.70)
```

**影响范围**：`structure_core.py` 的 `build_structure_context()`

---

### C-10. `t0_candidate_core.py` 的 `score_for` 与 `decision_core.py` 的 `score_for` 各自独立实现

**现状**：两个文件各有一个 `score_for`，计算逻辑不同：

| 评分项 | decision_core | t0_candidate_core |
|--------|--------------|-------------------|
| 基础分来源 | `STATUS_SCORE` (含"空间不足":30) | `STATUS_SCORE` (无"空间不足") |
| 修改器 | `apply_score_modifiers` + 手动加减分 | 纯手动加减分 |
| `gap_pct <= 0` | -4 | -4 |
| 跌破 hard_stop | -40 | -40 |
| 接近 hard_stop | -8 | -8 |
| 低于MA数量 | -2/条 | 不扣分 |

**问题**：
- C-2 提到 `status_for` 分裂，但 `score_for` 也分裂，影响选股池排序
- `decision_core.score_for` 使用 `apply_score_modifiers`（规则引擎），`t0_candidate_core.score_for` 不用
- 选股池 `trader-pool` 的排序用哪个？如果用 t0 版本，会缺少规则引擎的加成

**方案**：与 C-2 一起合并，统一使用 `decision_core.score_for`

**影响范围**：`t0_candidate_core.py` 的 `score_for()`

---

### I-9. `build_candidate_zones` 仍用振幅而非 ATR 计算 T0 的 zone 宽度

**现状**：`price_point_engine.py` 第 257-282 行：

```python
def build_candidate_zones(report_data, key_levels):
    amplitude_pct = intraday_amplitude_pct(report_data["quote"])
    if amplitude_pct is not None:
        width_pct = min(ZONE_MAX_WIDTH_PCT, amplitude_pct * ZONE_AMPLITUDE_FACTOR)
    else:
        width_pct = DEFAULT_ZONE_WIDTH_PCT
```

**问题**：
- P2 让 `structure_core` 用了 ATR，但 T0 的 `price_point_engine` 仍用日内振幅 `amplitude_pct`
- 日内振幅 = `(high - low) / pre_close`，不含跳空，与 trader 的 ATR 体系不一致
- 同一只票，trader 的低吸区宽度基于 ATR（含跳空），T0 的基于日内振幅（不含跳空），两个宽度可能差异很大

**方案**：T0 也引入 ATR 计算：

```python
def build_candidate_zones(report_data, key_levels, atr14=None):
    if atr14 and atr14 > 0:
        current = float(report_data["current_price"])
        atr_pct = atr14 / current
        width_pct = min(ZONE_MAX_WIDTH_PCT, atr_pct * ZONE_AMPLITUDE_FACTOR)
    else:
        # fallback 到日内振幅
        amplitude_pct = intraday_amplitude_pct(report_data["quote"])
        width_pct = min(ZONE_MAX_WIDTH_PCT, amplitude_pct * ZONE_AMPLITUDE_FACTOR) if amplitude_pct else DEFAULT_ZONE_WIDTH_PCT
```

**影响范围**：`price_point_engine.py` 的 `build_candidate_zones()`

---

### C-11. `pack_all.py` 的 T0 技能包不包含 `structure_core.py` 和 `decision_core.py`

**现状**：`pack_all.py` 第 149-161 行：

```python
if "t0" in skill_slug:
    core = candidates_dir / "t0_candidate_core.py"
    if core.exists():
        shutil.copy2(core, scripts_dir / "candidate_core.py")
else:
    for src_name, dst_name in (
        ("candidate_core.py", "candidate_core.py"),
        ("structure_core.py", "structure_core.py"),
        ("decision_core.py", "decision_core.py"),
    ):
```

T0 技能包中：
- `t0_candidate_core.py` 被重命名为 `candidate_core.py`
- `structure_core.py` 和 `decision_core.py` **不打包**

**问题**：
- C-2 如果要让 `t0_candidate_core.status_for` 调用 `decision_core.status_for`，但 T0 包里没有 `decision_core.py`
- `t0_candidate_core.py` 第 89 行调用 `status_for` 用的是自己定义的简化版
- 如果合并两个 `status_for`，T0 包必须也包含 `decision_core.py`

**方案**：修改 `pack_all.py`，让 T0 包也包含 `decision_core.py`：

```python
if "t0" in skill_slug:
    core = candidates_dir / "t0_candidate_core.py"
    if core.exists():
        shutil.copy2(core, scripts_dir / "candidate_core.py")
    # T0 也需要 decision_core（C-2 合并后）
    dec = candidates_dir / "decision_core.py"
    if dec.exists():
        shutil.copy2(dec, scripts_dir / "decision_core.py")
```

**影响范围**：`pack_all.py` + T0 打包结构

---

### I-10. 融合层只融合缠论/威科夫/动量，缺筹码维度

**现状**：`fusion_core.py` 的 `merge_decisions` 只接收三个参数：

```python
def merge_decisions(chan_result, momentum_result, wyckoff_result, regime="正常"):
```

**问题**：
- I-6 提到"筹码信号未接入 P3"，但根源在融合层本身就没有筹码信号入口
- `fusion_core` 不接收 `chip_result`，`signals_detail` 中也没有 `chip` 字段
- 筹码分布（`chip_distribution`）已在 `run_analysis.py` 中计算，但没有标准化为融合层信号

**方案**：在 `fusion_core.py` 中新增筹码信号标准化：

```python
def _chip_to_signal(chip_result: dict) -> dict:
    """将筹码分布映射为统一信号。"""
    peaks = chip_result.get("peaks", [])
    mid_price = chip_result.get("mid_price")
    current_pct = chip_result.get("current_pct")  # 当前价在筹码分布中的百分位
    
    if current_pct is not None:
        if current_pct < 0.3:
            # 低位筹码密集 → 看多支撑
            return {"direction": 1, "confidence": 0.6,
                    "reason": "低位筹码密集支撑", "raw_key": "chip"}
        elif current_pct > 0.7:
            # 高位套牢盘密集 → 看空压力
            return {"direction": -1, "confidence": 0.6,
                    "reason": "高位套牢盘压力", "raw_key": "chip"}
    return {"direction": 0, "confidence": 0.2,
            "reason": "筹码无明显信号", "raw_key": "chip"}

# merge_decisions 签名扩展
def merge_decisions(chan_result, momentum_result, wyckoff_result,
                    chip_result=None, regime="正常"):
```

**影响范围**：`fusion_core.py` + `run_analysis.py` 调用处

---

### 更新后的完整优先级

| # | ID | 内容 | 类别 | 影响 | 难度 | 优先级 |
|---|-----|------|------|------|------|--------|
| 1 | C-8 | `status_rules.yml` 硬编码 0.008 与 ATR 动态阈值矛盾 | 代码 | **P0+P2 在规则引擎环境下完全失效** | 低 | **P0** |
| 2 | C-7 | 打通 `run_analysis.py` 调用链 | 代码 | P3/P4 当前不生效 | 中 | **P0** |
| 3 | C-9 | `run_all` 执行顺序导致 structure_core 先于缠论运行 | 代码 | 即使 C-7 修了也拿不到数据 | 中 | **P0** |
| 4 | C-2 | 合并两个 `status_for` | 代码 | 消除长期逻辑分裂 | 中 | **P1** |
| 5 | C-11 | T0 包不包含 `decision_core.py` | 代码 | C-2 合并后 T0 会报错 | 低 | **P1** |
| 6 | C-3 | 修复 `THEORY_ADJUST_LOG_ONLY` import 路径 | 代码 | 打包后可能失效 | 低 | **P1** |
| 7 | I-7 | 筹码支撑/阻力未进入候选列表 | 理论 | 最真实的支撑/阻力被忽略 | 低 | **P2** |
| 8 | I-3 | 理论微调改为渐变式 | 理论 | 提高精度 | 低 | **P2** |
| 9 | I-4 | 三信号交叉验证加安全边界 | 理论 | 防止过于激进 | 低 | **P2** |
| 10 | I-8 | 费波纳契回调位未参与支撑/阻力候选 | 理论 | 费波纳契只是展示不是决策 | 低 | **P2** |
| 11 | I-1 | 费波纳契加下跌笔反弹位 | 理论 | 补全理论维度 | 低 | **P2** |
| 12 | I-2 | 费波纳契笔有效性校验 | 理论 | 防止毛刺笔 | 低 | **P2** |
| 13 | I-9 | T0 zone 宽度仍用振幅而非 ATR | 理论 | 与 trader 体系不一致 | 低 | **P2** |
| 14 | C-10 | `score_for` 也分裂 | 代码 | 选股池排序不一致 | 低 | **P2** |
| 15 | I-10 | 融合层缺筹码维度 | 理论 | A 股特色理论缺失 | 中 | **P3** |
| 16 | C-5 | ATR 前置一根 bar | 代码 | 小幅提升准确度 | 低 | **P3** |
| 17 | C-6 | 时间窗口降级方案改进 | 代码 | 提高鲁棒性 | 低 | **P3** |
| 18 | I-5 | 时间窗口多级转折点 | 理论 | 提高时间窗口准确性 | 中 | **P3** |
| 19 | I-6 | 筹码信号接入 P3（依赖 I-10） | 理论 | 补全维度 | 中 | **P3** |
| 20 | C-1 | 函数签名改为 options dict | 代码 | 长期可维护性 | 低 | **P4** |
| 21 | C-4 | 新增单元测试 | 代码 | 防回归 | 中 | **P4** |

### 关键发现总结

C-8 是**最严重的遗漏**：`status_rules.yml` 硬编码 `0.008`，意味着只要规则引擎加载成功，P0+P2 的 ATR 动态阈值改进就完全失效。这比 C-7 更紧急，因为 C-7 影响的是 P3/P4（增强），而 C-8 影响的是 P0+P2（核心 bug 修复）。

C-9 是 C-7 的前置依赖：即使修了 C-7 把参数传进去，`run_all` 的执行顺序决定了 `build_structure_context` 跑的时候缠论/威科夫/动量还没执行，数据根本不存在。

---

## 七、第三轮深度审查 — 补充发现

> 逐行重读全部核心文件 + 辅助模块 + 打包脚本 + rule_engine/modifier_rule_engine/chip_distribution/light_data/final_pool/portfolio_run/review_core 后发现

### C-12. `run_analysis.py` 中 `_pool_count()` 有类型错误 — `str` 对象调 `Path.read_text()`

**现状**：`run_analysis.py` 第 570-579 行：

```python
def _pool_count() -> int:
    import json
    import os
    path = os.path.expanduser("~/.trader/pool.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))  # BUG!
        ...
```

**问题**：
- `os.path.expanduser()` 返回 `str`，而 `read_text()` 是 `pathlib.Path` 的方法
- 运行时必定报 `AttributeError: 'str' object has no attribute 'read_text'`
- 这意味着 trader 报告末尾的"当前池 X/10，回复 1 入池"**永远显示不出来**
- 被 `try/except` 吞掉了，不会崩溃但功能完全失效

**方案**：

```python
def _pool_count() -> int:
    import json
    from pathlib import Path
    path = Path.home() / ".trader" / "pool.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("items", [])
        return sum(1 for i in items if i.get("status") not in {"淘汰", "已退出"})
    except Exception:
        return 0
```

**影响范围**：`run_analysis.py` 第 570-579 行

---

### C-13. `TREND_MA_LONG = 900` 使趋势过滤器对大部分股票无效

**现状**：`config.py` 第 65 行：

```python
TREND_MA_LONG: int = 900
```

`decision_core._trend_filter()` 第 114 行：

```python
if len(closes) < TREND_MA_LONG:
    return True  # 默认趋势OK
```

`price_point_engine._trend_filter()` 第 433 行：

```python
if len(closes) < 900:
    return True
```

**问题**：
- 900 个交易日 ≈ 3.5 年，大部分 A 股没有这么长的历史数据
- `data_provider` 默认 `LOOKBACK_DAYS = 30`，只取 30 天日线
- 这意味着 `_trend_filter` 几乎总是 `return True`，趋势过滤器**形同虚设**
- 结果是：即使大盘处于下降趋势，`trend_ok=True` 也不会对"低吸观察"降级为"防守观察，趋势下行谨慎"
- `market_env.get_env_for_skill()` 已经提供了大盘趋势判断（中证1000），但 `_trend_filter` 用的是个股 900 日均线，两者含义不同

**方案**：降低门槛或改用大盘环境替代：

```python
# 方案 A：降低 TREND_MA_LONG 到更现实的值
TREND_MA_LONG: int = 120  # 半年均线，大部分股票都有

# 方案 B：个股数据不足时，改用大盘环境
def _trend_filter(bars):
    closes = _close(bars)
    if len(closes) < TREND_MA_LONG:
        # 数据不足时用大盘环境替代
        try:
            from trader_shared.scripts.market_env import get_env_for_skill
            env = get_env_for_skill("trader")
            return env.get("level") not in ("偏弱", "很差")
        except Exception:
            return True
    # ... 正常逻辑
```

**影响范围**：`config.py` + `decision_core._trend_filter()` + `price_point_engine._trend_filter()`

---

### I-11. 三套 MACD 实现可能产生不一致结果

**现状**：代码库中有三个独立的 MACD 实现：

| 模块 | 用途 | 返回格式 | DEA 初始化 |
|------|------|---------|-----------|
| `chan_core._calc_macd()` | 缠论背驰检测 | 原地修改 bars `macd_histogram` | buffer 累积 9 根后 SMA |
| `momentum_core.calc_macd()` | 动量评分 | `{macd_line, dea, histogram, golden_cross, death_cross}` | 同上 |
| `review_core.calc_macd()` | 复盘五层评分 | `{macd_line, signal_line, histogram, prev_hist, golden, death}` | 同上 |

**问题**：
- 三个实现使用相同的 EMA 公式（12/26/9），理论上结果应该一致
- 但 `chan_core._calc_macd()` 的 DEA 缓冲区管理方式不同（直接累积 buffer），边界条件下可能有微小差异
- 更重要的是：`chan_core._calc_macd()` 修改 bars 的 `macd_histogram` 字段，`momentum_core.calc_macd()` 独立计算不修改 bars。如果两者在同一次分析中被调用，`chan_core` 先修改了 bars，`momentum_core` 读到的 bars 就已经带了 MACD 数据
- 重复计算浪费性能

**方案**：统一 MACD 计算到 `light_data.py` 或新建 `indicators.py`（共享模块），所有模块共用一个实现：

```python
# trader_shared/indicators.py
def calc_macd(closes, fast=12, slow=26, signal=9):
    """统一的 MACD 计算。"""
    # ... 唯一实现

# chan_core.py
from trader_shared.indicators import calc_macd

# momentum_core.py
from trader_shared.indicators import calc_macd

# review_core.py
from trader_shared.indicators import calc_macd
```

**影响范围**：`chan_core.py` + `momentum_core.py` + `review_core.py`

---

### C-14. `status_rules.yml` 不使用 `trend_ok` 变量，Python 后处理与 yml 规则易冲突

**现状**：`decision_core.py` 第 144-159 行：

```python
engine = _get_engine()
if engine:
    ctx = {
        ...
        "trend_ok": trend_ok,
    }
    result = engine.evaluate(ctx)
    if result is not None:
        status = str(result)
        # yml 之后再用 Python 修改
        if not trend_ok and status in {"低吸观察", "冲高减仓"}:
            status = "防守观察，趋势下行谨慎"
        return status
```

`status_rules.yml` 中没有任何规则引用 `trend_ok` 变量。

**问题**：
- `trend_ok` 传入了 context 但 yml 不用，全靠 Python 后处理
- 如果有人在 yml 中添加"趋势下行暂不碰"规则，会与 Python 后处理冲突
- 更严重的：C-13 发现 `trend_ok` 几乎总是 `True`（因为 900 日数据不足），所以 Python 后处理也很少触发
- yml 规则和 Python 后处理各管一段，维护者容易遗漏一边

**方案**：统一趋势过滤的位置——要么全在 yml 中，要么全在 Python 中：

```python
# 方案 A：yml 中增加趋势过滤规则（推荐，因为 yml 可配置）
# status_rules.yml:
- name: 趋势下行降级
  result: 防守观察，趋势下行谨慎
  when: not trend_ok and (result == "低吸观察" or result == "冲高减仓")
# 但 RuleEngine 只支持 first-match，不支持"后处理"，需要改用两阶段评估

# 方案 B：Python 中去掉后处理，改用 TREND_FILTER_ENABLED 开关
# 如果 TREND_MA_LONG 不现实，干脆关掉：
TREND_FILTER_ENABLED: bool = False  # 等改成合理的 MA_LONG 后再开
```

**影响范围**：`decision_core.py` + `status_rules.yml` + `config.py`

---

### I-12. `structure_core.py` 不注入缠论笔端点/中枢边界到支撑/阻力候选列表

**现状**：`build_structure_context` 的 `support_levels` 和 `resistance_levels` 只包含：
- 5 日低点/高点
- 今日低点/高点
- 20 日低点/高点
- MA5/MA10/MA20/MA30

不包含任何缠论衍生的价位（笔端点、中枢上下沿、买点价位等）。

**对比**：`price_point_engine.py` 的 `find_key_levels` 会注入 `"结构支撑(trader)"` / `"结构阻力(trader)"`，weight=1.1。

**问题**：
- 缠论笔端点（如最近下跌笔的终点 = 一类买价格）是最精确的支撑参考
- 中枢下沿是缠论的核心支撑概念，不进入候选列表 = 缠论分析对 `choose_level` 的选位无影响
- `price_point_engine` 注入了结构支撑但 `structure_core` 自己不注入，逻辑不一致
- 缠论分析做了但只影响 `_theory_multipliers`（微调系数），不影响实际选位

**方案**：在 `build_structure_context` 中注入缠论关键价位：

```python
# 在 build_structure_context 的 support_levels 构建中
if chan_result is not None:
    chan = chan_result.get("chanlun", {}) if isinstance(chan_result, dict) else {}
    strokes = chan.get("strokes", [])
    if isinstance(strokes, list) and strokes:
        # 最后一笔下跌笔的终点 = 缠论支撑
        down_strokes = [s for s in strokes if s.get("direction") == "down"]
        if down_strokes:
            end_price = float(down_strokes[-1].get("end_price") or 0)
            if end_price > 0 and end_price <= current:
                add_level(support_levels, "缠论下跌笔终点", end_price, 0.90)

    zones = chan.get("zones", [])
    if isinstance(zones, list) and zones:
        # 最近有效中枢的下沿 = 缠论中枢支撑
        for z in reversed(zones):
            if isinstance(z, dict) and z.get("valid"):
                zh_bottom = float(z.get("zh_bottom") or 0)
                if zh_bottom > 0 and zh_bottom <= current:
                    add_level(support_levels, "缠论中枢下沿", zh_bottom, 0.85)
                break
```

**影响范围**：`structure_core.py` 的 `build_structure_context()`

---

### C-15. `t0_candidate_core.STATUS_SCORE` 缺少"空间不足"键 — 潜在 KeyError

**现状**：

```python
# t0_candidate_core.py 第 50-57 行
STATUS_SCORE = {
    "低吸观察": 80,
    "等转强": 70,
    "防守观察": 60,
    "冲高减仓": 55,
    "暂不碰": 20,
    "数据失败": 0,
}
# 没有 "空间不足"
```

但 `t0_candidate_core.status_for` 不会返回"空间不足"（它的判定逻辑中没有这个状态），所以 `score_for` 不会遇到 KeyError。

**问题**：
- 如果未来 T0 的 `status_for` 被替换为 `decision_core.status_for`（C-2 合并），就可能返回"空间不足"
- 此时 `score_for` 中的 `STATUS_SCORE.get(status, 0)` 会返回 0，导致评分异常低
- `config.py` 中 `"空间不足": 30`，如果 T0 不加这个键，合并后会出问题

**方案**：在 T0 的 `STATUS_SCORE` 中也加上"空间不足"（或在合并时统一用 `config.py` 的版本）：

```python
STATUS_SCORE = {
    "低吸观察": 80,
    "等转强": 70,
    "防守观察": 60,
    "冲高减仓": 55,
    "空间不足": 30,  # 补齐
    "暂不碰": 20,
    "数据失败": 0,
}
```

**影响范围**：`t0_candidate_core.py`

---

### I-13. `fusion_regime.py` "很差" regime 的 confidence=0 误导 — 实际是最确定的决定

**现状**：

```python
# fusion_regime.py
REGIME_WEIGHTS = {
    ...
    "很差": {"chan": 0.0, "momentum": 0.0, "wyckoff": 0.0},
}

def compute_confidence(weighted_score, disagreement, weights):
    base = min(abs(score) * 2, 0.9)  # score=0 → base=0
    disagree_penalty = (disagreement / 2) * 0.3  # 0
    concentration_bonus = concentration * 0.1  # 很小
    confidence = 0 - 0 + 0.009 = 0.009  # 接近 0
```

**问题**：
- "很差" regime 一票否决空仓，这是**最确定**的决策（无论个股信号如何都必须空仓）
- 但 `compute_confidence` 返回 ≈0，表示"毫无信心"
- 下游消费者看到 `confidence=0` 可能误解为"数据不足/不确定"，而不是"非常确定要空仓"
- `run_analysis.py` 第 595 行 `if fc > 0.2 and has_signal:` 会让"很差"的融合层结果被忽略（因为 confidence < 0.2）

**方案**：对"很差" regime 特殊处理 confidence：

```python
def compute_confidence(weighted_score, disagreement, weights, regime="正常"):
    if regime == "很差":
        return 0.9  # 一票否决 = 高置信度
    # ... 正常逻辑
```

或者在 `merge_decisions` 中直接设置：

```python
if regime == "很差":
    confidence = 0.9
    action = "空仓 (大盘很差, 一票否决)"
```

**影响范围**：`fusion_regime.py` 的 `compute_confidence()` + `fusion_core.py` 的 `merge_decisions()`

---

### C-16. `pack_all.py` 不验证 `score_rules.yml` / `livermore_rules.yml` 是否存在于 `trader_shared` 包中

**现状**：`modifier_rule_engine.py` 引用 `score_rules.yml` 和 `livermore_rules.yml`：

```python
_MODIFIER_RULES_PATH = Path(__file__).resolve().parent / "score_rules.yml"
_LIVERMORE_RULES_PATH = Path(__file__).resolve().parent / "livermore_rules.yml"
```

`pack_all.py` 的 `copy_shared()` 会把整个 `trader_shared/` 目录复制到技能包中，所以只要 yml 文件存在于 `trader_shared/` 目录下就没问题。

**问题**：需要确认这两个 yml 文件是否存在。如果不存在，`modifier_rule_engine.py` 的懒加载会失败，`apply_score_modifiers` 返回 `None`，`decision_core.score_for` 的规则引擎加成就不会生效。

**影响范围**：需要确认文件存在性；如果缺失则 `apply_score_modifiers` 退化

---

### C-17. `run_all()` 的 `result.update(chunk)` 会导致策略间 key 冲突覆盖

**现状**：`strategy_protocol.py` 第 23-33 行：

```python
def run_all(current, bars, change_pct, quote, *strategies):
    result: dict[str, Any] = {}
    for fn in strategies:
        try:
            chunk = fn(current, bars, change_pct, quote)
            if isinstance(chunk, dict):
                result.update(chunk)  # 后面的覆盖前面的
        except Exception:
            continue
    return result
```

**问题**：
- `build_structure_context` 返回的 key 包括 `support`, `resistance`, `status` 等
- `chanlun_strategy` 返回 `{"chanlun": {...}}`，不会冲突
- `wyckoff_strategy` 返回 `{"wyckoff": {...}}`，不会冲突
- `momentum_strategy` 返回 `{"momentum": {...}}`，不会冲突
- 但如果未来有策略也返回 `support` 或 `status`，会被覆盖
- 更隐蔽的：`build_structure_context` 已经在 `run_all` 内部调用了 `decision_core.status_for`，产出了 `status`。之后如果其他策略也产出 `status`，就会覆盖

**方案**：为策略约定命名空间前缀，或在 `run_all` 中检测冲突：

```python
def run_all(current, bars, change_pct, quote, *strategies):
    result: dict[str, Any] = {}
    for fn in strategies:
        try:
            chunk = fn(current, bars, change_pct, quote)
            if isinstance(chunk, dict):
                overlap = set(chunk.keys()) & set(result.keys())
                if overlap:
                    print(f"WARN: strategy {fn.__name__} overwrites keys: {overlap}", file=sys.stderr)
                result.update(chunk)
        except Exception:
            continue
    return result
```

**影响范围**：`strategy_protocol.py`

---

### 更新后的完整优先级（v3）

| # | ID | 内容 | 类别 | 影响 | 难度 | 优先级 |
|---|-----|------|------|------|------|--------|
| 1 | C-8 | `status_rules.yml` 硬编码 0.008 与 ATR 动态阈值矛盾 | 代码 | **P0+P2 核心改进完全失效** | 低 | **P0** |
| 2 | C-12 | `_pool_count()` str/Path 类型错误 | 代码 | **运行时必定报错，池计数永远为 0** | 低 | **P0** |
| 3 | C-7+C-9 | 打通调用链 + 修复执行顺序 | 代码 | P3/P4 当前不生效 | 中 | **P0** |
| 4 | C-13 | `TREND_MA_LONG=900` 使趋势过滤无效 | 代码 | 大盘弱时仍给"低吸观察" | 低 | **P1** |
| 5 | C-14 | yml 规则与 Python 后处理冲突风险 | 代码 | 维护困难 | 低 | **P1** |
| 6 | C-2 | 合并两个 `status_for` | 代码 | 消除长期逻辑分裂 | 中 | **P1** |
| 7 | C-11 | T0 包不包含 `decision_core.py` | 代码 | C-2 合并后 T0 会报错 | 低 | **P1** |
| 8 | C-15 | T0 `STATUS_SCORE` 缺"空间不足"键 | 代码 | C-2 合并后 KeyError | 低 | **P1** |
| 9 | C-3 | 修复 `THEORY_ADJUST_LOG_ONLY` import 路径 | 代码 | 打包后可能失效 | 低 | **P1** |
| 10 | I-12 | 缠论笔端点/中枢边界未进支撑候选 | 理论 | 缠论分析不影响实际选位 | 低 | **P2** |
| 11 | I-7 | 筹码支撑/阻力未进入候选列表 | 理论 | 最真实的支撑/阻力被忽略 | 低 | **P2** |
| 12 | I-3 | 理论微调改为渐变式 | 理论 | 提高精度 | 低 | **P2** |
| 13 | I-4 | 三信号交叉验证加安全边界 | 理论 | 防止过于激进 | 低 | **P2** |
| 14 | I-8 | 费波纳契回调位未参与支撑/阻力候选 | 理论 | 费波纳契只是展示不是决策 | 低 | **P2** |
| 15 | I-1 | 费波纳契加下跌笔反弹位 | 理论 | 补全理论维度 | 低 | **P2** |
| 16 | I-2 | 费波纳契笔有效性校验 | 理论 | 防止毛刺笔 | 低 | **P2** |
| 17 | I-9 | T0 zone 宽度仍用振幅而非 ATR | 理论 | 与 trader 体系不一致 | 低 | **P2** |
| 18 | C-10 | `score_for` 也分裂 | 代码 | 选股池排序不一致 | 低 | **P2** |
| 19 | I-13 | "很差" regime confidence=0 误导 | 理论 | 融合层结果被下游忽略 | 低 | **P2** |
| 20 | I-11 | 三套 MACD 实现可能不一致 | 理论 | 边界条件微小差异 | 中 | **P3** |
| 21 | I-10 | 融合层缺筹码维度 | 理论 | A 股特色理论缺失 | 中 | **P3** |
| 22 | C-5 | ATR 前置一根 bar | 代码 | 小幅提升准确度 | 低 | **P3** |
| 23 | C-6 | 时间窗口降级方案改进 | 代码 | 提高鲁棒性 | 低 | **P3** |
| 24 | I-5 | 时间窗口多级转折点 | 理论 | 提高时间窗口准确性 | 中 | **P3** |
| 25 | I-6 | 筹码信号接入 P3（依赖 I-10） | 理论 | 补全维度 | 中 | **P3** |
| 26 | C-16 | 验证 score_rules.yml / livermore_rules.yml 存在 | 代码 | 规则引擎加成不生效 | 低 | **P3** |
| 27 | C-17 | `run_all` 策略间 key 冲突覆盖 | 代码 | 潜在数据丢失 | 低 | **P4** |
| 28 | C-1 | 函数签名改为 options dict | 代码 | 长期可维护性 | 低 | **P4** |
| 29 | C-4 | 新增单元测试 | 代码 | 防回归 | 中 | **P4** |

### 第三轮审查关键发现

1. **C-12 是运行时必定报错的 bug**：`_pool_count()` 中 `str.read_text()` 100% 会抛 `AttributeError`，导致选股池计数永远为 0。虽然被 `try/except` 吞了不崩溃，但功能完全失效。

2. **C-13 让趋势过滤器形同虚设**：`TREND_MA_LONG=900` 意味着需要 3.5 年日线数据，而默认只取 30 天。结果是 `_trend_filter` 几乎总是返回 `True`，即使大盘在暴跌也不会把"低吸观察"降级为"防守观察，趋势下行谨慎"。

3. **I-12 是缠论分析的"最后一公里"问题**：缠论算了笔、中枢、买点，但全部只用于展示和微调系数（15%幅度），实际选支撑/阻力时完全不考虑缠论价位。等于做了缠论分析但决策不用。

4. **I-13 让"很差"环境下的融合层信号被忽略**：`confidence≈0` 导致 `run_analysis.py` 第 595 行的 `fc > 0.2` 判断跳过融合层结果，大盘"很差"时融合层的"空仓"建议无法覆盖个股级的"低吸观察"。

---

## 八、信号传递架构问题（第四轮深度审查）

> 发现日期：2026-05-14
> 审查方法：从行情输入到最终信号输出，全链路追踪信号传递路径
> 严重程度：⚠️ **系统性架构问题**，影响所有 skill 的决策一致性

### 8.1 信号流全景与断点图

```
行情数据
  │
  ├─ chan_core ─→ {chanlun: {buy_points, divergence, strokes, zones, ...}}
  ├─ wyckoff_core ─→ {wyckoff: {spring_signal, ...}}
  ├─ momentum_core ─→ {momentum: {score, direction, signals}}
  │
  ├─ build_structure_context ← ❌ 断点1: fusion_result=None, chan_result=None
  │    ├─ _theory_multipliers(fusion_result=None) → 全 1.0，理论信号对参数无影响
  │    ├─ _compute_fib_retrace(chan_result=None) → None
  │    ├─ status_for(...) → 基于纯数学的状态（不知道缠论/威科夫信号）
  │    └─ 返回 {support, resistance, status, ...}
  │
  ├─ fusion_core.merge_decisions ← 在 run_all 之后单独调用
  │    └─ 返回 {action, confidence, signals_detail, ...}
  │
  └─ build_signal()
       ├─ signal_state() ← 基于 scene(=status) 判断，不用融合层
       ├─ 融合层覆盖：fc > 0.2 and has_signal → 可能覆盖
       └─ ❌ 断点2: "很差" regime confidence≈0 → fc < 0.2 → 融合层信号被跳过

T0 信号链（完全独立）:
  行情数据
  │
  ├─ price_point_engine.find_key_levels ← 只读 structure_result 支撑/阻力
  │    ❌ 断点3: 不读 fusion_result / chan_result / 筹码分布
  │
  ├─ detect_buy_trigger / detect_sell_trigger ← 只基于 5m 量价指标
  │    ❌ 断点4: 完全不知道日线级别的理论信号
  │
  └─ 输出 T0 执行卡
```

### 8.2 问题 S-1：融合层与 decision_core 是两条独立决策路径，信号不互通

**严重程度**：🔴 高（P0 级，影响决策一致性）

**现状**：

`status_for()` 决定 `status`（如"低吸观察"），融合层 `merge_decisions` 决定 `action`（如"半仓试"）。这两条路：

- **输入不同**：`status_for` 用支撑/阻力/ATR 纯数学；融合层用缠论/威科夫/动量理论信号
- **输出不同**：`status_for` 输出状态字符串；融合层输出 action + confidence
- **信号不回传**：融合层的结果不回传给 `status_for`，只在 `build_signal` 中做"后置覆盖"
- **覆盖条件苛刻**：需要 `fc > 0.2 and has_signal and _map_fusion_to_signal` 匹配

**后果**：

- 缠论出三类买点 → 融合层给"半仓试" → 但 `status_for` 不知道，仍输出"防守观察"
- 最终在 `build_signal` 中靠后置覆盖修正，但覆盖率低（尤其 I-13 导致"很差"regime 下完全失效）
- 两条路径可能给出矛盾的信号，用户看到的报告"简要分析"和"决策"部分可能不一致

**方案**：将融合层信号作为 `status_for` 的输入之一，让理论信号直接影响状态判断，而非仅靠后置覆盖修正。

```python
# 方案：status_for 接收 fusion_result
def status_for(self, price, supports, resistances, atr, position,
               fusion_result=None,  # 新增
               chan_result=None):   # 新增
    # ... 原有逻辑 ...
    
    # 融合层信号直接参与状态判断
    if fusion_result:
        action = fusion_result.get("action")
        confidence = fusion_result.get("confidence", 0)
        if confidence > 0.3 and action in ("buy", "strong_buy"):
            # 如果融合层给出买入信号且置信度足够，提升状态
            if status == "防守观察" and self._near_support(price, supports, atr):
                status = "低吸观察"
            elif status == "低吸观察":
                status = "低吸确认"
```

### 8.3 问题 S-2：fusion_result 信号未回传到 status_for，"分析-决策"脱节

**严重程度**：🔴 高（P0 级，是 S-1 的根因之一）

**现状**：

即使 C-7+C-9 修复后 `fusion_result` 能传给 `build_structure_context`，它也只影响 `_theory_multipliers`（参数微调 15%）。真正的状态决策 `status_for` 完全不读融合层信号。

**后果**：

- 理论分析做了（缠论/威科夫/动量），但对最终状态判断的影响微乎其微
- 与 I-12 问题叠加：缠论价位不参与支撑/阻力候选 × 融合层信号不参与状态判断 = 理论分析几乎白做
- 花了大量计算资源做理论分析，但决策路径几乎不用

**方案**：`status_for` 必须显式读取 `fusion_result` 和 `chan_result`，让理论信号有直接的投票权（不是微调 15% 参数，而是直接影响状态级别）。

### 8.4 问题 S-3：T0 信号链与 trader 完全独立，不共享日线级理论信号

**严重程度**：🟡 中（P1 级，影响 T0 执行卡质量）

**现状**：

`price_point_engine.find_key_levels` 从 `structure_result` 读支撑/阻力，但不读：
- 融合层结果（fusion_result）→ 不知道日线级是"买"还是"卖"
- 缠论笔端点（chan_result）→ 不知道三类买点/卖点位置
- 筹码分布（chip_support/chip_resistance）→ 不知道筹码密集区

T0 的 `detect_buy_trigger` / `detect_sell_trigger` 只基于 5m 量价指标（量比、涨幅、MA），完全不知道日线级别的理论信号。

**后果**：

- 日线级"三类买点确认"→ T0 不知道，可能在日线买点附近高抛而非低吸
- 日线级"趋势下行"→ T0 不受约束，可能给出逆趋势的低吸建议
- T0 执行卡与 trader 分析报告可能给出矛盾建议

**方案**：T0 的 `price_point_engine` 和触发检测接收日线级信号上下文。

```python
# 方案：T0 接收日线级信号上下文
def find_key_levels(self, price, structure_result, 
                    fusion_result=None,   # 新增
                    chan_result=None,     # 新增
                    chip_support=None,    # 新增
                    chip_resistance=None):  # 新增
    # 原有支撑/阻力候选
    candidates = []
    
    # 新增：缠论笔端点作为关键价位候选
    if chan_result:
        for bp in chan_result.get("buy_points", []):
            candidates.append({"price": bp["price"], "type": "support", "source": "chanlun", "weight": 0.8})
    
    # 新增：融合层方向影响 T0 策略
    if fusion_result:
        self.daily_bias = fusion_result.get("action", "hold")  # buy/sell/hold
```

### 8.5 问题 S-4：Signal Contract 信号丢失维度

**严重程度**：🟡 中（P1 级，影响复盘回溯质量）

**现状**：

`build_signal` 产出的 Signal Contract v1 不包含：
- `fusion_result`（融合层决策和置信度）→ 复盘不知道"当时融合层怎么判断的"
- `theory_multipliers`（理论信号对参数的调整）→ 复盘不知道"参数被微调了什么"
- `fib_retrace`（费波纳契回调位）→ 复盘不知道"回调位是怎么算的"
- `time_window`（时间窗口状态）→ 复盘不知道"当时时间窗口是否活跃"

**后果**：

- review-trader 读 `signals.jsonl` 回溯信号时，无法回答"为什么最终信号是 X 而不是 Y"
- 信号审计无法回溯融合层决策路径
- 后续优化缺乏数据支撑（不知道融合层信号被跳过了多少次）

**方案**：扩展 Signal Contract v1，增加 `context` 字段保留完整决策上下文。

```python
# 方案：Signal Contract v1.1 扩展
signal["context"] = {
    "fusion_result": fusion_result,          # 融合层完整输出
    "theory_multipliers": multipliers,       # 理论微调参数
    "fib_retrace": fib_levels,              # 费波纳契回调位
    "time_window": time_window_status,      # 时间窗口状态
    "fusion_override_applied": override_used, # 融合层覆盖是否生效
    "fusion_override_skipped_reason": skip_reason  # 覆盖被跳过的原因（如 fc < 0.2）
}
```

### 8.6 四个信号传递问题的依赖关系

```
S-2（fusion_result 不回传 status_for）
  │
  ├─→ S-1（两条独立决策路径）的根因
  │     修复 S-2 后，S-1 自然缓解
  │
  └─→ S-4（Signal Contract 丢失维度）
        如果 fusion_result 不参与决策，记了也没用
        所以 S-2 先修，S-4 才有意义

S-3（T0 不共享日线信号）独立于 S-1/S-2
  但如果 S-2 修好后 fusion_result 更可靠，
  T0 接收它的价值也更大
```

### 8.7 优先级更新（v4）

将信号传递问题纳入总表，更新优先级：

| # | ID | 标题 | 类型 | 影响 | 难度 | 优先级 |
|---|-----|------|------|------|------|--------|
| 1 | S-2 | fusion_result 未回传 status_for | 架构 | 决策脱节根因 | 中 | **P0** |
| 2 | S-1 | 两条独立决策路径 | 架构 | 决策不一致 | 中 | **P0** |
| 3 | C-12 | `_pool_count()` str.read_text() 必崩 | 代码 | 选股池计数失效 | 低 | **P0** |
| 4 | C-13 | TREND_MA_LONG=900 数据不足 | 代码 | 趋势过滤失效 | 低 | **P0** |
| 5 | C-7 | `build_structure_context` 调用链断裂 | 代码 | 融合层未传入 | 中 | **P0** |
| 6 | C-9 | `run_all` 执行顺序错误 | 代码 | 融合结果为 None | 中 | **P0** |
| 7 | C-11 | `fusion_regime` config key 错误 | 代码 | regime 判断失效 | 低 | **P0** |
| 8 | S-3 | T0 不共享日线级理论信号 | 架构 | T0 执行卡质量 | 中 | **P1** |
| 9 | S-4 | Signal Contract 丢失维度 | 架构 | 复盘回溯质量 | 低 | **P1** |
| 10 | C-14 | `_merge_dicts` 静默覆盖 | 代码 | 潜在信号丢失 | 低 | **P1** |
| 11 | I-12 | 缠论价位不参与支撑/阻力候选 | 理论 | 缠论分析白做 | 中 | **P1** |
| 12 | C-15 | 筹码函数 split 未校验 | 代码 | IndexError 崩溃 | 低 | **P1** |
| 13 | C-3 | `status_for` 分裂问题 | 代码 | 状态判断不一致 | 中 | **P1** |
| 14 | C-8 | `signal_state` 不读 fusion_result | 代码 | 信号源不一致 | 中 | **P1** |
| 15 | C-2 | `_theory_multipliers` 返回 int | 代码 | 微调效果打折 | 低 | **P2** |
| 16 | I-7 | ATR 安全距离改为滑点感知 | 理论 | 提高实战精度 | 低 | **P2** |
| 17 | I-3 | 理论微调改为渐变式 | 理论 | 提高精度 | 低 | **P2** |
| 18 | I-4 | 三信号交叉验证加安全边界 | 理论 | 防止过于激进 | 低 | **P2** |
| 19 | I-8 | 费波纳契回调位未参与支撑/阻力候选 | 理论 | 费波纳契只是展示不是决策 | 低 | **P2** |
| 20 | I-1 | 费波纳契加下跌笔反弹位 | 理论 | 补全理论维度 | 低 | **P2** |
| 21 | I-2 | 费波纳契笔有效性校验 | 理论 | 防止毛刺笔 | 低 | **P2** |
| 22 | I-9 | T0 zone 宽度仍用振幅而非 ATR | 理论 | 与 trader 体系不一致 | 低 | **P2** |
| 23 | C-10 | `score_for` 也分裂 | 代码 | 选股池排序不一致 | 低 | **P2** |
| 24 | I-13 | "很差" regime confidence=0 误导 | 理论 | 融合层结果被下游忽略 | 低 | **P2** |
| 25 | I-11 | 三套 MACD 实现可能不一致 | 理论 | 边界条件微小差异 | 中 | **P3** |
| 26 | I-10 | 融合层缺筹码维度 | 理论 | A 股特色理论缺失 | 中 | **P3** |
| 27 | C-5 | ATR 前置一根 bar | 代码 | 小幅提升准确度 | 低 | **P3** |
| 28 | C-6 | 时间窗口降级方案改进 | 代码 | 提高鲁棒性 | 低 | **P3** |
| 29 | I-5 | 时间窗口多级转折点 | 理论 | 提高时间窗口准确性 | 中 | **P3** |
| 30 | I-6 | 筹码信号接入 P3（依赖 I-10） | 理论 | 补全维度 | 中 | **P3** |
| 31 | C-16 | 验证 score_rules.yml / livermore_rules.yml 存在 | 代码 | 规则引擎加成不生效 | 低 | **P3** |
| 32 | C-17 | `run_all` 策略间 key 冲突覆盖 | 代码 | 潜在数据丢失 | 低 | **P4** |
| 33 | C-1 | 函数签名改为 options dict | 代码 | 长期可维护性 | 低 | **P4** |
| 34 | C-4 | 新增单元测试 | 代码 | 防回归 | 中 | **P4** |

### 8.8 第四轮审查关键发现

1. **S-2 是整个信号链的"根断点"**：融合层做了判断但信号不回传给 `status_for`，导致理论分析和实际决策是两条平行线。修复 S-2 可以同时缓解 S-1。

2. **S-1 + I-12 叠加 = 理论分析几乎白做**：缠论价位不参与支撑/阻力候选（I-12）× 融合层信号不参与状态判断（S-1）= 花大量计算做缠论/威科夫/动量分析，但最终决策几乎不看这些结果。

3. **S-3 让 T0 和 trader 给出矛盾建议**：日线级"三类买点确认"时 T0 可能在同一价位给"高抛"建议，因为 T0 完全不知道日线级的理论信号。

4. **S-4 让复盘无法回答"为什么"**：Signal Contract 不记录融合层结果，review-trader 无法回溯"当时融合层判断了什么、为什么被跳过了"。

5. **修复顺序建议**：S-2 → S-1 → I-12 → S-3 → S-4，由内到外，先修根因再修下游。

---

## 九、理论分析实现缺陷（第五轮深度审查）

> 发现日期：2026-05-14
> 审查方法：逐行审查 chan_core / wyckoff_core / momentum_core / fusion_core / fusion_regime 的算法实现
> 严重程度：⚠️ **理论实现不完整**，部分分析"做了但做错了"或"做了一半"

### 9.1 缠论分析缺陷

#### T-1：只有买点检测，没有卖点检测

**严重程度**：🔴 高（P0 级）

**现状**：`chan_core.py` 只有 `detect_buy_points`（一类买/二类买/三类买），完全没有 `detect_sell_points`。

**后果**：
- 缠论只输出看多信号，从不输出看空信号
- 融合层 `_chan_to_signal` 从 `buy_points` 只能得到 direction=1
- 看空信号只能靠"顶背驰"和"回调段"两个弱信号，缺少一类卖/二类卖/三类卖
- 当股价处于顶部时，缠论分析无法给出明确的卖出信号

**方案**：新增 `detect_sell_points`，实现一类卖（顶背驰）/二类卖（高点降低）/三类卖（跌破中枢）。

```python
# 方案：detect_sell_points（对称于 detect_buy_points）
def detect_sell_points(strokes, zones, last_close, macd_hist_current, macd_hist_prev):
    sell_points = []
    
    if not strokes:
        return sell_points
    
    # 一类卖: 向上笔 + MACD 红柱缩短 (顶背驰信号)
    last_stroke = strokes[-1]
    if last_stroke["direction"] == "up":
        if macd_hist_current is not None and macd_hist_prev is not None:
            if macd_hist_current > 0 and macd_hist_prev > 0:
                if macd_hist_current < macd_hist_prev:
                    sell_points.append({
                        "type": "一类卖",
                        "price": round(last_stroke["end_price"], 4),
                        "confidence": 3,
                    })
    
    # 二类卖: up_1(high_a) -> down -> up_2(high_b) 且 high_b < high_a
    if len(strokes) >= 3:
        up_strokes = [s for s in strokes if s["direction"] == "up"]
        down_strokes = [s for s in strokes if s["direction"] == "down"]
        if len(up_strokes) >= 2 and down_strokes:
            high_a = up_strokes[-2]["end_price"]
            high_b = up_strokes[-1]["end_price"]
            if high_b < high_a:
                sell_points.append({
                    "type": "二类卖",
                    "price": round(high_b, 4),
                    "confidence": 2,
                })
    
    # 三类卖: 跌破中枢下沿
    if last_close > 0 and zones:
        last_valid = None
        for z in reversed(zones):
            if z["valid"]:
                last_valid = z
                break
        if last_valid is not None:
            zh_bottom = last_valid["zh_bottom"]
            below_pct = (zh_bottom - last_close) / zh_bottom
            if 0 < below_pct <= 0.02:
                sell_points.append({
                    "type": "三类卖",
                    "price": round(last_close, 4),
                    "confidence": 1,
                })
    
    return sell_points
```

同步修改 `chanlun_analysis` 和 `_chan_to_signal`，让卖点参与融合层决策。

#### T-2：二类买验证逻辑有时序错误

**严重程度**：🟡 中（P1 级）

**现状**：`detect_buy_points` 第 264-276 行的二类买检测：

```python
# chan_core.py:264-276
down_strokes = [s for s in strokes if s["direction"] == "down"]
up_strokes = [s for s in strokes if s["direction"] == "up"]
if len(down_strokes) >= 2 and up_strokes:
    low_a = down_strokes[-2]["end_price"]
    low_b = down_strokes[-1]["end_price"]
    up_high = max(s["end_price"] for s in up_strokes)  # ← 所有上攻笔的最高点
```

**问题**：
1. `up_high = max(s["end_price"] for s in up_strokes)` 取了所有上攻笔的最高价，而非两次下攻笔之间的上攻笔的高点
2. 没有验证上攻笔在时间上确实位于两次下攻笔之间
3. 逻辑应该是：down_1 → up_1 → down_2，验证 up_1 是连接 down_1 和 down_2 的中间笔

**方案**：基于 strokes 列表的时间顺序，找到"下-上-下"三笔模式。

```python
# 方案：基于时间顺序的二类买检测
for i in range(len(strokes) - 2):
    s1, s2, s3 = strokes[i], strokes[i+1], strokes[i+2]
    if s1["direction"] == "down" and s2["direction"] == "up" and s3["direction"] == "down":
        low_a = s1["end_price"]  # 第一笔下端点
        up_high = s2["end_price"]  # 中间上攻笔高点
        low_b = s3["end_price"]  # 第二笔下端点
        if low_b > low_a and low_b < up_high:
            buy_points.append({
                "type": "二类买",
                "price": round(low_b, 4),
                "confidence": 2,
            })
            break  # 只取最近的二类买
```

#### T-3：中枢重叠未处理

**严重程度**：🟡 中（P2 级）

**现状**：`build_zones` 以步长 1 滑动取 3 笔为一组，每 3 笔都生成一个"zone"。这导致：
- 相邻 zone 大量重叠
- 严格缠论中，中枢应由重叠的笔合并而成，不是滑动窗口
- 当前产生过多"有效中枢"，影响买点判断

**方案**：合并重叠中枢，或改为从连续重叠笔中构建单一中枢。

#### T-4：背驰检测过于简化

**严重程度**：🟡 中（P2 级）

**现状**：`detect_divergence` 只比较最近 2 个峰值/谷值的 price 和 MACD 关系，没有：
- 比较两个相关笔之间的 MACD 面积（积分），而非单点值
- 验证两个峰值/谷值属于同一方向的两笔
- 考虑区间套（多级别背驰共振）

严格缠论中，背驰是"两笔同方向运动的力度衰减"，应该比较同方向两笔的 MACD 积分面积，而非任意两个相邻峰值。

### 9.2 威科夫分析缺陷

#### T-5：缺少阶段识别（吸筹/派发/上涨/下跌）

**严重程度**：🔴 高（P1 级）

**现状**：`wyckoff_core.py` 只检测 Spring 和 Upthrust 两个信号，没有阶段识别。威科夫理论的核心是识别市场处于吸筹（Accumulation）→ 上涨（Markup）→ 派发（Distribution）→ 下跌（Markdown）哪个阶段。

**后果**：
- Spring 信号只在吸筹阶段末期有效，但如果不知道当前阶段，Spring 信号可能被误用
- 在派发阶段出现的 Spring 是"假弹簧"（bear trap），应该看空而非看多
- 缺少阶段判断，所有 Spring 信号一视同仁，降低信号质量

**方案**：增加简单阶段识别（基于价格与长期均线的关系 + 成交量趋势）。

```python
# 方案：简化阶段识别
def _detect_phase(bars):
    """基于价格与均线关系 + 量能趋势，粗判威科夫阶段。"""
    closes = [to_float(b.get("close")) for b in bars]
    volumes = [to_float(b.get("volume")) or 0 for b in bars]
    
    if len(closes) < 20:
        return "unknown"
    
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else ma20
    current = closes[-1]
    
    vol_recent = sum(volumes[-10:]) / 10
    vol_prior = sum(volumes[-30:-10]) / 20 if len(volumes) >= 30 else vol_recent
    vol_shrinking = vol_recent < vol_prior * 0.8
    
    if current < ma20 < ma60:
        return "markdown" if not vol_shrinking else "accumulation"
    elif current < ma20 and ma20 > ma60:
        return "accumulation" if vol_shrinking else "markdown"
    elif current > ma20 > ma60:
        return "markup"
    else:
        return "distribution" if vol_shrinking else "markup"
```

#### T-6：缺少 No Demand / No Supply 信号

**严重程度**：🟡 低（P3 级）

**现状**：威科夫短期信号只有 Spring 和 Upthrust，缺少：
- **No Demand**：窄幅 + 量缩 → 上涨无量支撑，偏空
- **No Supply**：窄幅下跌 + 量缩 → 卖压枯竭，偏多

这两个是威科夫理论中常用的日内/短期信号，对 T0 执行卡很有价值。

### 9.3 动量分析缺陷

#### T-7：信号评分存在重复计算

**严重程度**：🟡 中（P1 级）

**现状**：`assess_momentum` 的评分逻辑存在条件重叠：

```python
# momentum_core.py:182-220
if rsi_oversold or bb_below:           # 条件A
    if rsi_rising or macd_golden:      # 条件A+B
        signals.append("RSI超卖+回升(看多)")
        score += 15                     # ← RSI rising 贡献 +15
if macd_golden and rsi_rising:         # 条件B（与A+B完全重叠）
    signals.append("MACD金叉+RSI上升(偏多)")
    score += 12                         # ← RSI rising 再次贡献 +12
```

**问题**：当 RSI 超卖 + RSI 上升 + MACD 金叉同时满足时：
- 第一次 `score += 15`（RSI超卖+回升）
- 第二次 `score += 12`（MACD金叉+RSI上升）
- 还可能第三次 `score += 8`（MACD柱为正）
- 以及 `score += 10`（多指标共振）

同一个"RSI 上升"事实被计入了 4 次，总分可能 +45，远超单条件应有贡献。

**方案**：用互斥条件替代累加，或用权重矩阵避免重复。

```python
# 方案：互斥条件优先级
if rsi_oversold and macd_golden and rsi_rising:
    score += 25  # 最强组合，一次性计入
elif rsi_oversold and (rsi_rising or macd_golden):
    score += 15
elif rsi_oversold:
    score += 5
# ... 后续条件不再重复这些信号
```

#### T-8：MACD 金叉/死叉没有回看窗口

**严重程度**：🟡 中（P1 级）

**现状**：`calc_macd` 只返回最后一次计算的状态（`golden_cross` / `death_cross`），不记录交叉发生的具体 bar 位置。

**问题**：
- 10 根 bar 前发生的金叉仍然 `golden_cross=True`
- 1 根 bar 前发生的金叉也是 `golden_cross=True`
- 两者信号强度完全不同，但代码一视同仁

**方案**：在 `calc_macd` 中返回交叉发生的 bar 距离，近期的交叉权重更高。

```python
# 方案：返回交叉距离
def calc_macd(closes):
    # ... 现有逻辑 ...
    # 记录金叉/死叉发生的位置
    golden_cross_bars_ago = None
    death_cross_bars_ago = None
    for i in range(len(closes)-1, max(len(closes)-10, 25), -1):
        # 检测交叉点
        ...
    return {
        "golden_cross": gc,
        "death_cross": dc,
        "golden_cross_bars_ago": golden_cross_bars_ago,  # 新增
        "death_cross_bars_ago": death_cross_bars_ago,      # 新增
    }
```

#### T-9：BB squeeze 评分为 0，无实际效果

**严重程度**：🟢 低（P3 级）

**现状**：`momentum_core.py` 第 212-214 行：

```python
if bb_squeeze:
    signals.append("布林收口(变盘前兆)")
    score += 0  # ← 等于没加
```

信号被识别了，但对评分完全没有影响。要么给一个非零权重（如 ±5），要么在输出时标注"仅提示，不影响评分"。

#### T-10：ADX 计算使用错误平滑方法

**严重程度**：🟡 低（P2 级）

**现状**：`calc_adx` 使用简单 EMA 式平滑（`tr_s = (tr_s * (period-1) + tr[i]) / period`），但标准 Wilder 平滑应使用 `α = 1/period`（而非 `1/period` 在 EMA 中的不同含义）。

Wilder 平滑公式：`Wilder_value = prev_value * (1 - 1/period) + current_value * (1/period)`

当前代码用的 EMA 式：`EMA_value = prev_value * (period-1)/period + current_value * 1/period`

这两个公式看似相同，但 Wilder 平滑的初始值计算方式不同（应该用 period 天的 SMA 初始化，且后续扩展为递推）。当前代码初始值正确（SMA），后续递推也正确——实际上是一样的。**此条撤回，不是 bug。**

### 9.4 融合层实现缺陷

#### T-11：融合层 Action 映射不完整，部分决策被静默丢弃

**严重程度**：🔴 高（P0 级）

**现状**：`run_analysis.py` 的 `_FUSION_ACTION_MAP` 只映射了 6 种融合层 action：

```python
# run_analysis.py:111-118
_FUSION_ACTION_MAP = {
    "半仓试 (多方主导)": ...,
    "半仓试 (多方主导但有分歧)": ...,
    "增持": ...,
    "持股观望": ...,
    "减仓": ...,
    "空仓/止损": ...,
}
```

但 `fusion_regime.py` 的 `score_to_action` 和 `ACTION_MAP_DISAGREE` 还会输出：

- `"空仓 (大盘很差, 一票否决)"` — regime="很差" 时
- `"观望 (信号冲突)"` — 分歧过大且加权分 < 0.0 时
- `"等转强 (多方主导但有分歧)"` — 分歧过大但加权分 ≥ 0.0 时

这 3 个 action 在 `_FUSION_ACTION_MAP` 中没有映射，`_map_fusion_to_signal` 返回 `None`，融合层决策被**静默丢弃**。

**后果**：
- 大盘"很差"时融合层输出"空仓"→ 映射失败 → 信号仍然是"低吸观察"
- 信号冲突时融合层输出"观望"→ 映射失败 → 决策忽略冲突

**方案**：补全映射表。

```python
_FUSION_ACTION_MAP = {
    # 现有
    "半仓试 (多方主导)": ("track", "bullish", "track"),
    "半仓试 (多方主导但有分歧)": ("track", "bullish", "track"),
    "增持": ("track", "bullish", "track"),
    "持股观望": ("wait_for_confirmation", "bullish_lean", "observe"),
    "减仓": ("defensive", "bearish", "wait"),
    "空仓/止损": ("defensive", "bearish", "wait"),
    # 新增
    "空仓 (大盘很差, 一票否决)": ("risk_stop", "bearish", "stop"),
    "观望 (信号冲突)": ("observe", "neutral", "observe"),
    "等转强 (多方主导但有分歧)": ("wait_for_confirmation", "bullish_lean", "observe"),
}
```

#### T-12：筹码分布计算在结构分析之后，无法参与支撑/阻力候选

**严重程度**：🟡 高（P1 级，与 I-12/S-3 关联）

**现状**：

```
run_analysis.py:
  1. run_all(current, bars, ..., build_structure_context, ...)  ← 结构分析
  2. chip = _calc_chip(bars, lookback=60)                        ← 筹码分布
  3. chip_support/chip_resistance → 只进 report，不回传结构分析
```

`build_structure_context` 在第一步就被调用了，筹码分布在第二步才计算。筹码峰值无法作为支撑/阻力候选进入 `choose_level`。

**后果**：
- 筹码密集区是 A 股最重要的支撑/阻力之一，但完全不影响核心决策
- 筹码数据只用于报告展示（"关键价位"里的"有量支撑"/"套牢压力区"），不影响 status/confirm/stop

**方案**：先算筹码分布，将 peaks 作为参数传入 `build_structure_context`。

```python
# 方案：筹码分布前置
def build_report(target):
    # ... 获取数据 ...
    
    # 1. 先算筹码分布
    chip = _calc_chip(bars, lookback=60)
    chip_peaks = chip.get("peaks", [])
    
    # 2. 结构分析时传入筹码数据
    levels = run_all(current, bars, ..., 
                     chip_peaks=chip_peaks,  # 新增
                     ...)
```

`build_structure_context` 中的 `add_level` 增加 chip 峰值候选：

```python
# structure_core.py 中新增
for peak in (chip_peaks or []):
    if peak["price"] < current:
        add_level(support_levels, "筹码支撑", peak["price"], 0.7)
    elif peak["price"] > current:
        add_level(resistance_levels, "筹码阻力", peak["price"], 0.7)
```

### 9.5 问题依赖关系图

```
T-1（缠论无卖点）
  └─→ 融合层只能从缠论获得看多信号，加重了多空信号不对称

T-11（融合层 Action 映射不完整）
  ├─→ 与 I-13 叠加：regime="很差" → 融合层输出"空仓" → 映射失败 → 信号被丢弃
  └─→ 与 S-1 叠加：融合层的"观望"/"等转强"信号被静默丢弃

T-12（筹码不参与结构分析）
  ├─→ 与 I-12 叠加：缠论价位 × 筹码价位 × 费波纳契都不参与支撑/阻力
  └─→ 与 S-3 叠加：T0 也不知道筹码密集区在哪

T-7（动量评分重复计算）
  └─→ 影响 score → direction → 融合层输入 → 最终决策偏向看多

T-2（二类买时序错误）
  └─→ 二类买信号可能误判（取了不相关的上攻笔高点）

T-5（威科夫缺阶段识别）
  └─→ Spring 在派发阶段是陷阱信号，但当前无法区分
```

### 9.6 优先级更新（v5）

将理论分析问题纳入总表：

| # | ID | 标题 | 类型 | 影响 | 难度 | 优先级 |
|---|-----|------|------|------|------|--------|
| 1 | S-2 | fusion_result 未回传 status_for | 架构 | 决策脱节根因 | 中 | **P0** |
| 2 | S-1 | 两条独立决策路径 | 架构 | 决策不一致 | 中 | **P0** |
| 3 | C-12 | `_pool_count()` str.read_text() 必崩 | 代码 | 选股池计数失效 | 低 | **P0** |
| 4 | C-13 | TREND_MA_LONG=900 数据不足 | 代码 | 趋势过滤失效 | 低 | **P0** |
| 5 | C-7 | `build_structure_context` 调用链断裂 | 代码 | 融合层未传入 | 中 | **P0** |
| 6 | C-9 | `run_all` 执行顺序错误 | 代码 | 融合结果为 None | 中 | **P0** |
| 7 | C-11 | `fusion_regime` config key 错误 | 代码 | regime 判断失效 | 低 | **P0** |
| 8 | T-11 | 融合层 Action 映射不完整 | 代码 | 决策被静默丢弃 | 低 | **P0** |
| 9 | T-1 | 缠论无卖点检测 | 理论 | 多空信号不对称 | 中 | **P1** |
| 10 | S-3 | T0 不共享日线级理论信号 | 架构 | T0 执行卡质量 | 中 | **P1** |
| 11 | S-4 | Signal Contract 丢失维度 | 架构 | 复盘回溯质量 | 低 | **P1** |
| 12 | T-12 | 筹码不参与结构分析 | 代码 | 筹码不影响核心决策 | 中 | **P1** |
| 13 | T-2 | 二类买验证时序错误 | 理论 | 误判二类买 | 低 | **P1** |
| 14 | T-5 | 威科夫缺阶段识别 | 理论 | Spring 信号可能误用 | 中 | **P1** |
| 15 | T-7 | 动量评分重复计算 | 代码 | 评分偏向看多 | 低 | **P1** |
| 16 | T-8 | MACD 金叉/死叉无回看窗口 | 理论 | 陈旧交叉等同新交叉 | 低 | **P1** |
| 17 | C-14 | `_merge_dicts` 静默覆盖 | 代码 | 潜在信号丢失 | 低 | **P1** |
| 18 | I-12 | 缠论价位不参与支撑/阻力候选 | 理论 | 缠论分析白做 | 中 | **P1** |
| 19 | C-15 | 筹码函数 split 未校验 | 代码 | IndexError 崩溃 | 低 | **P1** |
| 20 | C-3 | `status_for` 分裂问题 | 代码 | 状态判断不一致 | 中 | **P1** |
| 21 | C-8 | `signal_state` 不读 fusion_result | 代码 | 信号源不一致 | 中 | **P1** |
| 22 | T-3 | 中枢重叠未处理 | 理论 | 过多无效中枢 | 低 | **P2** |
| 23 | T-4 | 背驰检测过于简化 | 理论 | 背驰信号不准 | 中 | **P2** |
| 24 | C-2 | `_theory_multipliers` 返回 int | 代码 | 微调效果打折 | 低 | **P2** |
| 25 | I-7 | ATR 安全距离改为滑点感知 | 理论 | 提高实战精度 | 低 | **P2** |
| 26 | I-3 | 理论微调改为渐变式 | 理论 | 提高精度 | 低 | **P2** |
| 27 | I-4 | 三信号交叉验证加安全边界 | 理论 | 防止过于激进 | 低 | **P2** |
| 28 | I-8 | 费波纳契回调位未参与支撑/阻力候选 | 理论 | 费波纳契只是展示不是决策 | 低 | **P2** |
| 29 | I-1 | 费波纳契加下跌笔反弹位 | 理论 | 补全理论维度 | 低 | **P2** |
| 30 | I-2 | 费波纳契笔有效性校验 | 理论 | 防止毛刺笔 | 低 | **P2** |
| 31 | I-9 | T0 zone 宽度仍用振幅而非 ATR | 理论 | 与 trader 体系不一致 | 低 | **P2** |
| 32 | C-10 | `score_for` 也分裂 | 代码 | 选股池排序不一致 | 低 | **P2** |
| 33 | I-13 | "很差" regime confidence=0 误导 | 理论 | 融合层结果被下游忽略 | 低 | **P2** |
| 34 | T-6 | 威科夫缺 No Demand/No Supply | 理论 | 缺少短期信号 | 低 | **P3** |
| 35 | T-9 | BB squeeze 评分为 0 | 代码 | 信号无效 | 低 | **P3** |
| 36 | I-11 | 三套 MACD 实现可能不一致 | 理论 | 边界条件微小差异 | 中 | **P3** |
| 37 | I-10 | 融合层缺筹码维度 | 理论 | A 股特色理论缺失 | 中 | **P3** |
| 38 | C-5 | ATR 前置一根 bar | 代码 | 小幅提升准确度 | 低 | **P3** |
| 39 | C-6 | 时间窗口降级方案改进 | 代码 | 提高鲁棒性 | 低 | **P3** |
| 40 | I-5 | 时间窗口多级转折点 | 理论 | 提高时间窗口准确性 | 中 | **P3** |
| 41 | I-6 | 筹码信号接入 P3（依赖 I-10） | 理论 | 补全维度 | 中 | **P3** |
| 42 | C-16 | 验证 score_rules.yml / livermore_rules.yml 存在 | 代码 | 规则引擎加成不生效 | 低 | **P3** |
| 43 | C-17 | `run_all` 策略间 key 冲突覆盖 | 代码 | 潜在数据丢失 | 低 | **P4** |
| 44 | C-1 | 函数签名改为 options dict | 代码 | 长期可维护性 | 低 | **P4** |
| 45 | C-4 | 新增单元测试 | 代码 | 防回归 | 中 | **P4** |

### 9.7 第五轮审查关键发现

1. **T-11 是隐蔽的 P0 bug**：融合层输出了"空仓"或"观望"决策，但因为 Action 映射不完整，这些决策被静默丢弃。与 I-13 叠加后，"大盘很差"时融合层的"空仓"建议完全无效——既因为 confidence 太低被跳过，又因为映射缺失被丢弃，双重失效。

2. **T-1 导致多空信号严重不对称**：缠论只看多不看空，融合层从缠论只能得到 direction=1 的信号。这意味着即使股价处于顶部，缠论分析也永远只输出"无明确信号"或"拉升段"，从不会主动说"该卖了"。

3. **T-12 与 I-12 叠加 = 支撑/阻力体系只剩纯数学**：缠论价位（I-12）、筹码峰值（T-12）、费波纳契回调位（I-8）都不参与支撑/阻力候选，`choose_level` 只在 MA 和近期高低点中选择。A 股最有价值的支撑/阻力信号被系统性地排除在决策之外。

4. **T-7 让动量评分系统性偏向看多**：RSI 上升被计入 4 次（+15+12+8+10=+45），而 RSI 下降的重复计数类似但方向相反。但由于看多条件多于看空条件（布林带下轨 vs 上轨、金叉 vs 死叉 等），总体评分偏多。

5. **修复顺序建议**：T-11 → T-1 → T-12 → T-7 → T-2 → T-5，先修代码 bug（T-11 最简单影响最大），再补理论维度（T-1/T-12），再修算法精度（T-7/T-2/T-5）。

---

## 十、T0 模块独立问题（第六轮深度审查）

> 发现日期：2026-05-14
> 审查方法：逐文件审查 t0-trader 全部代码（config/indicators/ict_execution/price_point_engine/t0_core/t0_run/monitor）
> 严重程度：⚠️ **T0 模块存在严重信号断裂**，与 trader 主链几乎无有效交互

### 10.1 T0 信号链现状

```
t0_run.build_plan()
  │
  ├─ report_data = trader 的 build_report 输出
  │
  ├─ build_price_point_model(report_data)
  │    ├─ find_key_levels(price, structure_result=None)  ← ❌ 未传入！
  │    │    ├─ 候选区构建 → 只靠 VWAP + 近期高低点
  │    │    ├─ choose_level → 从候选中选最佳
  │    │    └─ 完全忽略 trader 的支撑/阻力分析结果
  │    │
  │    ├─ detect_buy_trigger / detect_sell_trigger
  │    │    └─ 只基于 5m 量价指标，不知道日线级理论信号
  │    │
  │    └─ 返回 price_model（低吸/高抛/止损价位）
  │
  └─ t0_core.build_t0_signal(plan) → T0 执行卡
```

### 10.2 T0 模块问题

#### T0-1：T0 完全未传入 structure_result，支撑/阻力分析结果被丢弃

**严重程度**：🔴 高（P0 级）

**现状**：`t0_run.py` 第 77 行调用 `build_price_point_model(report_data)` 时没传 `structure_result` 参数：

```python
# t0_run.py:77
plan = build_price_point_model(report_data)
# 应该是：
# plan = build_price_point_model(report_data, structure_result=report_data.get("structure"))
```

`price_point_engine.py` 的 `find_key_levels` 函数签名接收 `structure_result` 参数（第 157-163 行），内部会用它构建支撑/阻力候选区。但因为从未传入，`structure_result` 始终为 `None`，所有来自 trader 的支撑/阻力数据被完全忽略。

**后果**：
- T0 的关键价位（低吸/高抛/止损）完全脱离 trader 的支撑/阻力体系
- `choose_level` 只能靠 VWAP 和近期高低点选关键价位，质量远低于 trader
- 与 S-3 叠加后，T0 和 trader 是两套完全独立的定价体系，可能给出矛盾建议

**方案**：在 `build_plan` 中传入 `structure_result`。

```python
# 方案：t0_run.py 修改
def build_plan(target, report_data):
    structure_result = report_data.get("structure") or report_data.get("structure_result")
    plan = build_price_point_model(report_data, structure_result=structure_result)
    # ...
```

同步确保 `find_key_levels` 在 `structure_result` 非 None 时，正确读取支撑/阻力候选。

#### T0-2：indicators.py 背离检测逻辑根本不对

**严重程度**：🔴 高（P0 级）

**现状**：`indicators.py` 第 183-217 行的背离检测：

```python
# indicators.py:183-198 detect_bullish_divergence
# 按 RSI 值排序，取 RSI 最小的两个点
sorted_indices = sorted(range(len(rsi_values)), key=lambda i: rsi_values[i])[:2]
idx1, idx2 = sorted_indices[0], sorted_indices[1]
# 比较这两个点的价格关系
if closes[idx1] > closes[idx2]:  # 价格创新低但 RSI 未创新低
    return True, ...
```

**问题**：
- 这不是标准背离检测。标准背离是"价格创新低但 RSI 未创新低"，要求两个比较点分别是**前一个低点**和**当前低点**
- 当前实现只是取 RSI 值最小的两个点，这两个点可能完全不相关（例如相隔 50 根 bar 的两个不相关低点）
- 只要找到两个 RSI 低点且价格关系满足，就会被误判为"背离"，产生大量假阳性

**后果**：
- T0 的背离信号几乎不可信
- 假阳性背离可能导致在错误时机触发买/卖信号

**方案**：重写背离检测，使用标准的峰谷识别 + 相邻低点比较。

```python
# 方案：标准背离检测
def detect_bullish_divergence(closes, rsi_values, lookback=20):
    """价格创新低但 RSI 未创新低 = 看多背离"""
    if len(closes) < lookback or len(rsi_values) < lookback:
        return False, None
    
    # 1. 找到 RSI 的局部极小值点（谷底）
    troughs = []
    for i in range(1, len(rsi_values) - 1):
        if rsi_values[i] < rsi_values[i-1] and rsi_values[i] < rsi_values[i+1]:
            troughs.append(i)
    
    if len(troughs) < 2:
        return False, None
    
    # 2. 取最近的两个谷底
    t1, t2 = troughs[-2], troughs[-1]
    
    # 3. 判断：价格创新低（close[t2] < close[t1]）但 RSI 未创新低（rsi[t2] > rsi[t1]）
    if closes[t2] < closes[t1] and rsi_values[t2] > rsi_values[t1]:
        return True, {"price_t1": closes[t1], "price_t2": closes[t2],
                      "rsi_t1": rsi_values[t1], "rsi_t2": rsi_values[t2]}
    
    return False, None
```

#### T0-3：T0 的趋势过滤器同样失效（C-13 的 T0 复现）

**严重程度**：🟡 中（P1 级）

**现状**：`price_point_engine.py` 第 429-439 行的 `_trend_filter` 也要求 `len(closes) >= 900`，但 T0 只取 30 天数据。与 C-13 完全相同的问题在 T0 模块复现。

**后果**：T0 的趋势过滤永远返回 `True`，即使大盘暴跌也不会降低 T0 的买入信号级别。

**方案**：与 C-13 统一修复，改为合理值（如 `TREND_MA_LONG = 60`）。

#### T0-4：detect_sell_trigger 上影线条件过于宽泛

**严重程度**：🟡 中（P1 级）

**现状**：`price_point_engine.py` 第 561 行：

```python
(state.get("volume_ratio") or 1) < VOLUME_SHRINK_RATIO or detect_upper_shadow(last)
```

只要出现上影线（`detect_upper_shadow` 返回 True），就触发"放量滞涨或缩量上攻"卖出信号。但上影线在上涨趋势中非常常见（如日内冲高回落），不代表趋势性卖出信号。

**后果**：
- 放量上涨但有上影线 → 被判为卖出信号，与趋势策略矛盾
- T0 可能在强势上涨中频繁给出"高抛"建议

**方案**：增加上影线强度阈值，或结合量比判断。

```python
# 方案：上影线 + 量能双重确认
upper_shadow = detect_upper_shadow(last)
if upper_shadow and (state.get("volume_ratio") or 1) < VOLUME_SHRINK_RATIO:
    # 缩量 + 上影线 = 真正的滞涨
    triggers.append("缩量上攻/放量滞涨")
elif upper_shadow and (state.get("volume_ratio") or 1) > 2.0:
    # 放量 + 长上影线 = 可能是派发
    triggers.append("放量上影线(警惕)")
# 单纯上影线不再触发卖出
```

#### T0-5：monitor.py 用 fcntl 文件锁，Windows 不可用

**严重程度**：🟡 中（P1 级）

**现状**：`monitor.py` 第 4 行 `import fcntl`，在 Windows 上直接 `ImportError`。代码未做平台适配。

**后果**：Windows 用户无法使用 T0 监控功能。

**方案**：平台适配。

```python
# 方案：跨平台文件锁
import sys
if sys.platform == "win32":
    import msvcrt
    def flock(file, flags):
        # Windows 文件锁实现
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    def flock_unlock(file):
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl
    def flock(file, flags):
        fcntl.flock(file, flags)
    def flock_unlock(file):
        fcntl.flock(file, fcntl.LOCK_UN)
```

#### T0-6：t0_run.py 的 reminder_level 检查不存在的 data_status 值

**严重程度**：🟡 低（P2 级）

**现状**：`t0_run.py` 第 123 行：

```python
if str(plan.get("data_status")) == "fresh":
```

但 T0 的 `data_status` 值为 `"full"` / `"degraded"` / `"partial"`（由 `price_point_engine.py` 设置），不存在 `"fresh"`。此条件永远为 `False`。

**后果**：提醒级别判断少了一个分支，数据新鲜度对提醒频率的影响被忽略。

**方案**：修正为实际值。

```python
if str(plan.get("data_status")) == "full":
```

#### T0-7：detect_buy_trigger 的 "趋势下行暂不低吸" 不在 STATUSES 集合中

**严重程度**：🟢 低（P2 级）

**现状**：`price_point_engine.py` 中 `detect_buy_trigger` 返回 status `"趋势下行暂不低吸"`，但 `STATUSES` 集合只有 `{"已触发", "观察中", "未进入候选区", "被阻断", "数据不足", "触发过期"}`。不匹配时被映射为默认的 `"观察中"`，丢失了"趋势下行"的信息。

**方案**：将 `"趋势下行暂不低吸"` 加入 `STATUSES`，或改为 `被阻断` + 原因字段。

#### T0-8：ict_execution.py 的 detect_structure_shift 边界条件

**严重程度**：🟢 低（P3 级）

**现状**：`detect_structure_shift` 第 94 行，当 `index == len(valid) - 1` 时，`after = [valid[index]]`，用当前 bar 自身判断"是否突破"无意义。

**方案**：`after` 为空时跳过判断，或至少排除当前 bar。

#### T0-9：T0 config 与 trader_shared/config.py 重复定义

**严重程度**：🟢 低（P3 级）

**现状**：`t0-trader/config.py` 独立定义了 `LOOKBACK_DAYS`、`ATR_PERIOD` 等常量，与 `trader_shared/config.py` 重复。修改一处时容易忘记同步另一处。

**方案**：T0 的 config 从 `trader_shared.config` 导入共享常量，只定义 T0 特有的参数。

### 10.3 选股池模块问题

#### POOL-1：pool_core.py 错误被静默吞掉

**严重程度**：🟡 低（P2 级）

**现状**：`pool_core.py` 中多处 `read_text()` 或 JSON 解析被 `try/except` 静默吞掉，加载失败时返回空数据，无任何日志提示。

**后果**：选股池文件损坏时，用户不知道为什么池子空了，排查困难。

**方案**：至少 `logging.warning` 记录异常信息。

### 10.4 指标计算一致性问题

#### POOL-2：三套 MACD/RSI/布林带实现不一致

**严重程度**：🟡 中（P1 级，与 I-11 关联）

**现状**：项目中存在三套独立的技术指标实现：

| 模块 | MACD | RSI | 布林带 |
|------|------|-----|--------|
| `trader_shared/momentum_core.py` | ✅ calc_macd | ✅ calc_rsi | ✅ |
| `structure_core.py` | ✅ 内嵌计算 | ❌ | ✅ 内嵌计算 |
| `t0-trader/indicators.py` | ✅ calc_macd | ✅ calc_rsi | ✅ calc_bollinger_bands |

三套实现的边界条件、初始值处理、EMA 平滑方式可能存在微小差异。例如：
- `structure_core.py` 的布林带使用总体方差（除以 N）
- `indicators.py` 的布林带也使用总体方差
- `momentum_core.py` 的布林带未独立实现（直接用 structure_core 的结果）

**后果**：同一只股票在同一时间点，三个模块可能给出不同的 MACD/RSI/布林带值，影响信号一致性。

**方案**：统一到 `trader_shared/` 下的单一指标库，所有模块调用同一套实现。

### 10.5 问题依赖关系图

```
T0-1（structure_result 未传入）
  ├─→ 与 S-3 叠加：T0 与 trader 定价体系完全独立
  └─→ 与 I-12 叠加：缠论价位不进 T0 的关键价位候选

T0-2（背离检测逻辑错误）
  └─→ T0 的背离信号大量假阳性，可能触发错误买卖

T0-3（趋势过滤失效）
  └─→ 与 C-13 同源 bug，T0 复现

T0-4（上影线条件宽泛）
  └─→ 强势上涨中频繁触发卖出信号

POOL-2（三套指标实现不一致）
  └─→ 与 I-11 关联：三套 MACD 可能给出不同结果
```

### 10.6 优先级更新（v6）

将 T0 模块和选股池问题纳入总表：

| # | ID | 标题 | 类型 | 影响 | 难度 | 优先级 |
|---|-----|------|------|------|------|--------|
| 1 | S-2 | fusion_result 未回传 status_for | 架构 | 决策脱节根因 | 中 | **P0** |
| 2 | S-1 | 两条独立决策路径 | 架构 | 决策不一致 | 中 | **P0** |
| 3 | C-12 | `_pool_count()` str.read_text() 必崩 | 代码 | 选股池计数失效 | 低 | **P0** |
| 4 | C-13 | TREND_MA_LONG=900 数据不足 | 代码 | 趋势过滤失效 | 低 | **P0** |
| 5 | C-7 | `build_structure_context` 调用链断裂 | 代码 | 融合层未传入 | 中 | **P0** |
| 6 | C-9 | `run_all` 执行顺序错误 | 代码 | 融合结果为 None | 中 | **P0** |
| 7 | C-11 | `fusion_regime` config key 错误 | 代码 | regime 判断失效 | 低 | **P0** |
| 8 | T-11 | 融合层 Action 映射不完整 | 代码 | 决策被静默丢弃 | 低 | **P0** |
| 9 | T0-1 | T0 未传入 structure_result | 代码 | T0 支撑/阻力完全脱离 trader | 低 | **P0** |
| 10 | T0-2 | T0 背离检测逻辑根本不对 | 代码 | 大量假阳性背离信号 | 中 | **P0** |
| 11 | T-1 | 缠论无卖点检测 | 理论 | 多空信号不对称 | 中 | **P1** |
| 12 | S-3 | T0 不共享日线级理论信号 | 架构 | T0 执行卡质量 | 中 | **P1** |
| 13 | S-4 | Signal Contract 丢失维度 | 架构 | 复盘回溯质量 | 低 | **P1** |
| 14 | T-12 | 筹码不参与结构分析 | 代码 | 筹码不影响核心决策 | 中 | **P1** |
| 15 | T-2 | 二类买验证时序错误 | 理论 | 误判二类买 | 低 | **P1** |
| 16 | T-5 | 威科夫缺阶段识别 | 理论 | Spring 信号可能误用 | 中 | **P1** |
| 17 | T-7 | 动量评分重复计算 | 代码 | 评分偏向看多 | 低 | **P1** |
| 18 | T-8 | MACD 金叉/死叉无回看窗口 | 理论 | 陈旧交叉等同新交叉 | 低 | **P1** |
| 19 | T0-3 | T0 趋势过滤器同样失效 | 代码 | T0 趋势过滤永远为 True | 低 | **P1** |
| 20 | T0-4 | T0 上影线卖出条件过于宽泛 | 代码 | 强势上涨频繁触发卖出 | 低 | **P1** |
| 21 | T0-5 | monitor.py fcntl 不可跨平台 | 代码 | Windows 无法监控 | 中 | **P1** |
| 22 | POOL-2 | 三套指标实现不一致 | 代码 | 同股不同指标值 | 中 | **P1** |
| 23 | C-14 | `_merge_dicts` 静默覆盖 | 代码 | 潜在信号丢失 | 低 | **P1** |
| 24 | I-12 | 缠论价位不参与支撑/阻力候选 | 理论 | 缠论分析白做 | 中 | **P1** |
| 25 | C-15 | 筹码函数 split 未校验 | 代码 | IndexError 崩溃 | 低 | **P1** |
| 26 | C-3 | `status_for` 分裂问题 | 代码 | 状态判断不一致 | 中 | **P1** |
| 27 | C-8 | `signal_state` 不读 fusion_result | 代码 | 信号源不一致 | 中 | **P1** |
| 28 | T-3 | 中枢重叠未处理 | 理论 | 过多无效中枢 | 低 | **P2** |
| 29 | T-4 | 背驰检测过于简化 | 理论 | 背驰信号不准 | 中 | **P2** |
| 30 | C-2 | `_theory_multipliers` 返回 int | 代码 | 微调效果打折 | 低 | **P2** |
| 31 | I-7 | ATR 安全距离改为滑点感知 | 理论 | 提高实战精度 | 低 | **P2** |
| 32 | I-3 | 理论微调改为渐变式 | 理论 | 提高精度 | 低 | **P2** |
| 33 | I-4 | 三信号交叉验证加安全边界 | 理论 | 防止过于激进 | 低 | **P2** |
| 34 | I-8 | 费波纳契回调位未参与支撑/阻力候选 | 理论 | 费波纳契只是展示不是决策 | 低 | **P2** |
| 35 | I-1 | 费波纳契加下跌笔反弹位 | 理论 | 补全理论维度 | 低 | **P2** |
| 36 | I-2 | 费波纳契笔有效性校验 | 理论 | 防止毛刺笔 | 低 | **P2** |
| 37 | I-9 | T0 zone 宽度仍用振幅而非 ATR | 理论 | 与 trader 体系不一致 | 低 | **P2** |
| 38 | C-10 | `score_for` 也分裂 | 代码 | 选股池排序不一致 | 低 | **P2** |
| 39 | I-13 | "很差" regime confidence=0 误导 | 理论 | 融合层结果被下游忽略 | 低 | **P2** |
| 40 | T0-6 | reminder_level 检查不存在的 data_status | 代码 | 提醒级别判断失效 | 低 | **P2** |
| 41 | T0-7 | "趋势下行暂不低吸" 不在 STATUSES | 代码 | 趋势信息丢失 | 低 | **P2** |
| 42 | POOL-1 | pool_core.py 错误被静默吞掉 | 代码 | 故障排查困难 | 低 | **P2** |
| 43 | T-6 | 威科夫缺 No Demand/No Supply | 理论 | 缺少短期信号 | 低 | **P3** |
| 44 | T-9 | BB squeeze 评分为 0 | 代码 | 信号无效 | 低 | **P3** |
| 45 | I-11 | 三套 MACD 实现可能不一致 | 理论 | 边界条件微小差异 | 中 | **P3** |
| 46 | I-10 | 融合层缺筹码维度 | 理论 | A 股特色理论缺失 | 中 | **P3** |
| 47 | C-5 | ATR 前置一根 bar | 代码 | 小幅提升准确度 | 低 | **P3** |
| 48 | C-6 | 时间窗口降级方案改进 | 代码 | 提高鲁棒性 | 低 | **P3** |
| 49 | I-5 | 时间窗口多级转折点 | 理论 | 提高时间窗口准确性 | 中 | **P3** |
| 50 | I-6 | 筹码信号接入 P3（依赖 I-10） | 理论 | 补全维度 | 中 | **P3** |
| 51 | C-16 | 验证 score_rules.yml / livermore_rules.yml 存在 | 代码 | 规则引擎加成不生效 | 低 | **P3** |
| 52 | T0-8 | ICT structure_shift 边界条件 | 代码 | 漏判突破 | 低 | **P3** |
| 53 | T0-9 | T0 config 与 shared config 重复 | 代码 | 维护需改两处 | 低 | **P3** |
| 54 | C-17 | `run_all` 策略间 key 冲突覆盖 | 代码 | 潜在数据丢失 | 低 | **P4** |
| 55 | C-1 | 函数签名改为 options dict | 代码 | 长期可维护性 | 低 | **P4** |
| 56 | C-4 | 新增单元测试 | 代码 | 防回归 | 中 | **P4** |

### 10.7 第六轮审查关键发现

1. **T0-1 是 T0 模块最严重的信号断裂**：`structure_result` 从未传入 `find_key_levels`，T0 的关键价位完全脱离 trader 的支撑/阻力体系。trader 说"支撑位 10.50"，T0 可能选了 VWAP 10.80 作为"低吸价"，两者毫无关联。

2. **T0-2 让 T0 的背离信号几乎不可信**：当前背离检测取 RSI 最小的两个点比较价格关系，这不是标准背离，会产生大量假阳性。实战中可能在不该买入时触发"看多背离"。

3. **T0-3 是 C-13 的 T0 复现**：同一个 bug（`TREND_MA_LONG=900` 数据不足）在两个模块都存在，说明趋势过滤是系统性地失效。

4. **POOL-2 让指标一致性无法保证**：三套 MACD/RSI/布林带实现可能给出不同值，同一只股票在不同模块可能得到不同的"金叉"/"超卖"判断。

5. **修复顺序建议**：
   - **P0 级**（立即修）：T0-1（一行代码修复影响最大）→ T0-2（重写背离检测）→ T-11 → C-7/C-9 → S-2/S-1
   - **P1 级**（尽快修）：T0-3/C-13 统一修复 → T0-4 → T0-5 → POOL-2 → T-1/T-12/T-7
   - **P2-P3 级**（迭代优化）

---

## 十一、全量问题统计与修复路线图

### 11.1 按优先级统计

| 优先级 | 数量 | 类型分布 | 一句话概括 |
|--------|------|----------|-----------|
| **P0** | 10 | 代码 8 + 架构 2 | 信号链断裂、决策被丢弃、必崩 bug |
| **P1** | 17 | 代码 8 + 理论 5 + 架构 3 + 理论 1 | 理论维度缺失、评分偏多、T0 质量差 |
| **P2** | 15 | 代码 5 + 理论 10 | 算法精度、理论完整性 |
| **P3** | 11 | 代码 4 + 理论 7 | 边界优化、跨平台、短期信号补充 |
| **P4** | 3 | 代码 3 | 可维护性、防回归 |
| **合计** | **56** | — | — |

### 11.2 按影响域统计

| 影响域 | 问题数 | 关键 ID |
|--------|--------|---------|
| 信号传递/决策链 | 12 | S-1, S-2, S-3, S-4, C-7, C-8, C-9, T-11, T0-1, T0-2, C-11, I-13 |
| 缠论分析 | 6 | T-1, T-2, T-3, T-4, I-12, I-1 |
| 威科夫分析 | 3 | T-5, T-6, T-12（筹码） |
| 动量分析 | 5 | T-7, T-8, T-9, POOL-2, I-11 |
| T0 模块 | 9 | T0-1~T0-9, S-3 |
| 选股池 | 3 | C-12, POOL-1, C-10 |
| 支撑/阻力体系 | 4 | I-8, I-12, T-12, I-7 |
| 系统稳定性 | 6 | C-12, C-13, C-15, T0-5, T0-6, POOL-1 |

### 11.3 推荐修复路线图

```
Phase 1 — P0 修复（1-2 天）
  ├─ T0-1: T0 传入 structure_result（1 行代码）
  ├─ T0-2: 重写背离检测
  ├─ T-11: 补全 _FUSION_ACTION_MAP
  ├─ C-7:  修正 build_structure_context 调用链
  ├─ C-9:  修正 run_all 执行顺序
  ├─ C-12: 修复 _pool_count read_text
  ├─ C-13/T0-3: 统一修复 TREND_MA_LONG
  ├─ C-11: 修正 fusion_regime config key
  └─ 验证: self_check.py 全部通过

Phase 2 — P0 架构修复（2-3 天）
  ├─ S-2: fusion_result 回传 status_for
  └─ S-1: 合并两条决策路径

Phase 3 — P1 修复（3-5 天）
  ├─ T-1:  缠论卖点检测
  ├─ T-12: 筹码分布前置到结构分析
  ├─ T-7:  动量评分去重
  ├─ T-2:  二类买时序修正
  ├─ T-5:  威科夫阶段识别
  ├─ T-8:  MACD 回看窗口
  ├─ T0-4: T0 上影线条件修正
  ├─ T0-5: monitor.py 跨平台文件锁
  ├─ POOL-2: 统一指标库
  ├─ S-3:  T0 接收日线级信号上下文
  ├─ S-4:  Signal Contract 扩展
  └─ 其余 P1 项

Phase 4 — P2 修复（迭代优化）
Phase 5 — P3/P4 修复（长期演进）
```
