# 买入位可达性优化方案

> 创建日期：2026-05-14
> 状态：已规划，待实施
> 背景：用户反馈系统计算的买入位（低吸区）总是到不了，经全链路审查发现8个问题

---

## 核心诉求

让系统计算出的买入位（低吸区）不再是"只看得见但到不了"的价位，让状态判定在价格接近阻力位/确认位时给出合理的操作指引，而非一律判定"空间不足"或"防守观察"。

涉及三大维度：

1. 价位计算参数调整（低吸区宽度、确认位缓冲、止损间距）
2. 状态判定逻辑重构（"空间不足"优先级过高）
3. Trader与T0两套价位体系的统一（消除矛盾）

## Tech Stack

- 项目现有技术栈不变：Python 3.x
- 配置文件：`trader_shared/config.py`（共享常量中心）
- 核心计算：`structure_core.py`（结构分析）、`decision_core.py`（状态判定）、`t0_candidate_core.py`（T0价位）
- 修改不涉及外部依赖变化

## Implementation Approach

### 策略

分五阶段推进：**P0核心修复 → P1体系对齐 → P2 ATR 替换 → P3 理论微调 → P4 江恩/费波纳契**。每阶段独立可交付。

P0-P2 是"买入位到不了"的硬伤修复。P3/P4 是理论增强。

### 关键决策

**Fix 1（降低"空间不足"优先级）是最高优先级修复。**

- 当前逻辑：股价越接近确认位（剩余空间<0.8%），反而越不给买入信号 → 这是最核心的bug
- 解决方式：调整 `decision_core.status_for()` 中的判定顺序，不加新状态、不删旧状态，只改优先级
- ⚠️ 注意：移后优先级后，"空间不足"几乎不会在"等转强"型场景中触发（因为 position_ratio 接近1.0时会先被"等转强"截获）。但"空间不足"仍应保留——它应捕获"压力空间小 + 均线不配合"的场景。见 P2 的 ATR 动态阈值方案。

**Fix 2（放宽低吸区宽度上限）需要同时改config和计算逻辑。**

- 两个参数：`MAX_ZONE_WIDTH_PCT`（上限）和 波幅乘数
- 当前上限1.2%，放宽到2.0%
- **确认位缓冲**：`MIN_CONFIRM_SPACE_PCT` 改为 `0.005`（0.5%）

**Fix 3（ATR 替换振幅）是底层波动指标升级。**

- 当前用 `average_amplitude_pct()`：只算 `(high - low) / close`，跳空遗漏
- 改为 `average_atr_pct()`：`TR = max(high-low, |high-prev_close|, |low-prev_close|)`，跳空也纳入
- 为什么 ATR 更合理：跳空缺口是"买入位到不了"的重要原因，ATR 能捕捉到它。ATR ≥ 振幅，对含跳空的票更敏感。

**Fix 4（T0复用trader价位）是架构层面的统一。**

- 目前两套独立计算：trader用加权多指标、T0只用5日极值
- 改为T0优先接收外部传入的structure_core结果，缺少时仍用自有逻辑保底
- ⚠️ 同时需要改 `price_point_engine.py` 的 `find_key_levels()`：在其中增加可选参数 `optional_structure`

**Fix 5（理论信号微调价位参数）是 P3 的理论增强。**

- 当前所有计算全靠数学公式，没有理论判断参与
- 加入理论信号对价位参数的微调系数，实现"理论好时更积极，理论差时更保守"
- 详细方案见下方"P3 理论微调方案"章节

**Fix 6（江恩/费波纳契补充）是 P4 的新维度。**

- 现有体系缺两样东西：**费波纳契精确价位的标定** 和 **时间维度的预测**
- **费波纳契回撤**（最高优先级）：从缠论识别的笔（swing low → swing high）计算 38.2%/50%/61.8% 回撤位，作为现有支撑/阻力区域内的精确价位参考
- **时间窗口**（高优先级）：跟踪关键转折点后的 K 线计数，检测 90/144/360 bar 等常见江恩周期
- 费波纳契与 P3 天然互补：P3 改的是参数，费波纳契给的是新价位

### Trade-off

- Fix 1 会减少"空间不足"的出现频率，更多股票在阻力位附近被标为"等转强"→ 对大行情启动判断会更积极，但对假突破的识别需依赖其他条件（MA位置、量能）来过滤
- Fix 2+3 扩大低吸区宽度 → 更多价格区间被视为"可买入区"，但止损位与买入位的间距相应扩大（因为 ATR 更大的票止损也更宽），不会增加不对称风险
- Fix 5 引入理论微调 → 增加计算复杂度，需要融合层输出可靠的理论信号

## Implementation Notes

### 性能

- 所有修改均不涉及额外的网络请求或数据库查询
- `average_atr_pct()` 的计算量与 `average_amplitude_pct()` 相当（多一个 prev_close 追踪）
- `decision_core.py` 中的判定顺序调整不会增加计算量

### 向后兼容

- Fix 4（T0复用trader）需要保留回退逻辑
- 所有config参数变更需要在 `structure_core.py` 和 `t0_candidate_core.py` 的fallback值中同步更新

### 测试

- 修改后建议手动验证一只典型股票（如三花智控）的输出
- Fix 1 建议写一个简单的场景测试代码（单独脚本或在终端跑验证），构造如下数据：

```
support=10.00, resistance=10.50, current=10.52
→ 预期返回 "等转强"（已突破阻力位，距确认位0.6%）
→ 旧逻辑返回 "空间不足"（pressure_space_pct=0.6% < 0.8%）
```

这可以清晰验证判定顺序调整是否生效。

## Architecture Design

### 数据流（修改后，含 P3 + P4）

```
用户输入（股票代码）
        ↓
trader skill 入口（final_report.py）
        ↓
build_structure_context()
  ├─ average_atr_pct() → base波动率 (P2)
  ├─ 读取fusion_core的理论信号 (P3)
  ├─ 读取chan_core的笔数据 → 费波纳契回调位 (P4)
  └─ 理论微调 → 最终zone_width/confirm_buffer (P3)
        ↓
status_for() ← 判定顺序调整（Fix 1）+ ATR动态阈值（P2）+ 时间窗口检测 (P4)
        ↓
├── render_markdown() → 输出报告（含 fib_levels + time_window）
└── signal_state() → 写入 signal_contract（含 fib 字段）
        ↓
T0 skill（final_t0.py / t0_candidate_core.py）← 复用trader价位（Fix 4）
        ↓
price_point_engine.py → 盘中执行卡
```

### 状态判定流程（修改前后对比）

修改前（decision_core.py:159-175）：

```
1. 跌破止损       → "暂不碰"
2. 大跌超-7%     → "暂不碰"
3. 在低吸区内     → "低吸观察"
4. 突破确认位     → "冲高减仓"/"等转强"
5. 空间不足0.8%  → "空间不足" ★问题在此
6. MA5/MA10上方  → "等转强"
7. 破3条均线     → "防守观察"
8. 仓位位置高     → "等转强"
9. 默认           → "防守观察"
```

修改后：

```
1. 跌破止损       → "暂不碰"
2. 大跌超-7%     → "暂不碰"
3. 在低吸区内     → "低吸观察"
4. 突破确认位     → "冲高减仓"/"等转强"
5. MA5/MA10上方  → "等转强"
6. 破3条均线     → "防守观察"
7. 仓位位置高     → "等转强"
8. 空间不足ATR动态阈值 → "空间不足"
9. 默认           → "防守观察"
```

## ATR 替换振幅 — 详细方案

### 为什么 ATR 比振幅更适合？

| 场景 | 振幅 | ATR | 对低吸区的影响 |
|------|------|-----|---------------|
| 窄幅震荡无跳空 | 2.0% | ≈2.0% | 相同 |
| 跳空高开+窄幅震荡 | 1.2%（当天窄） | 3.2%（含跳空） | ATR更准确，低吸区更宽 ↑ |
| 趋势加速+大K线 | 4.5% | ≈4.8% | 接近，ATR略大 |
| 盘中瞬间砸低拉起 | 5.0%（毛刺） | 5.0% | 相同，毛刺被EMA平滑 |

ATR 对跳空更敏感，而跳空是"买入位到不了"的主要原因之一。

### 新增函数 `average_atr_pct()`

```
在 structure_core.py 中添加：
def average_atr_pct(bars: list[BarData], period: int = 20) -> float | None:
    遍历最近 period 根K线
    计算每根 TR = max(high-low, |high-prev_close|, |low-prev_close|)
    求和平均 → TR_pct = avg_TR / close
    返回 TR_pct
```

与现有 `average_amplitude_pct()` 并行保留，便于对比调试。

### 公式变更

| 指标 | 当前（振幅） | 改为（ATR） |
|------|------------|------------|
| zone_width | `amplitude * 0.28` | `atr_pct * 0.25` |
| stop_buffer | `amplitude * 0.45` | `atr_pct * 0.40` |
| P2 space阈值 | `max(0.003, amplitude*0.15)` | `max(0.002, atr_pct * 0.35)` |
| MIN_ZONE_WIDTH | 0.005 | 保持0.005 |
| MAX_ZONE_WIDTH | 0.012 → **0.020** | 0.020 |

**设计说明**：

- ATR ≥ 振幅（通常大10-30%），所以乘数略微下调使无跳空票的 zone_width ≈ 不变
- 有跳空时：ATR 明显更大 → 低吸区自动加宽 → 防止跳空跳过买入区
- 同时止损 buffer 也随 ATR 变宽 → 入场间距更合理

## P3 理论信号微调方案

### 设计思想

把 `structure_core.py` 的价位计算从"纯数学公式"升级为"理论指导的数学公式"：

```
base_value = atr_pct * 0.25           # 数学基础值
adjustment = theory_multiplier() - 1.0 # 理论微调(0% 到 +20%)
final_value = base_value * adjustment
```

理论好时 → 低吸区更宽、确认缓冲更小 → 更积极
理论差时 → 维持或收窄 → 更保守

### 理论信号 → 参数调整映射

| 理论源 | 信号检测 | 影响参数 | 调整幅度 |
|--------|---------|---------|---------|
| 缠论 | 上攻笔延续中 / 三买结构确认 | zone_width 乘数放大 | +15% |
| 缠论 | 下跌笔未结束 / 中枢下沿未站稳 | zone_width 乘数缩小 | -10% |
| 威科夫 | 吸筹区检测 / Spring 确认 | confirm_buffer 收窄 | -30%（0.005→0.0035）|
| 威科夫 | 派发区检测 / UT 出现 | confirm_buffer 维持 | 不变（0.005）|
| 动量 | RSI>60 且 ADX>25（强势延续） | space 阈值收窄 | -20%（更激进）|
| 动量 | RSI<40 且 ADX<20（弱势震荡） | space 阈值加宽 | +30%（更保守）|
| 筹码 | 筹码峰密集在支撑位附近 | support_level 权重提升 | +0.10 |
| 筹码 | 大量套牢盘在阻力位上方 | confirm 不做调整 | 不变 |

### 向后兼容

- P3 若检测不到理论信号（fusion_core 未输出或数据不足），所有 multiplier 取 1.0，退化为纯数学计算
- 完全向后兼容，不改变现有接口签名

## P4 江恩/费波纳契引入方案

### 现有体系覆盖 vs 盲区

| 维度 | 已有（缠/威科夫/动量/筹码） | 缺什么 |
|------|---------------------------|--------|
| 价格结构 | 分型/笔/中枢/买卖点/背驰 | 费波纳契精确回调位 |
| 量价关系 | 弹簧/上冲回落/量价背离 | 完整 |
| 动量 | RSI/MACD/ADX/布林带 | 完整 |
| 波动率 | ATR | 完整 |
| 仓位管理 | 利弗莫尔金字塔 | 完整 |
| **时间** | **完全没有** | 时间转折窗口 |
| **价位精度** | 区域性的支撑/阻力 | 百分比精确位（38.2/50/61.8） |
| **趋势斜率** | MA 均线 | 江恩角度线 1×1 |

### 子项 A：费波纳契回调位（最高优先级）

**数据来源**：现有 `chan_core.py` 已能识别笔（bi）的高低点，直接复用。

**计算公式**：

```
给定一个完整的笔/浪（swing_low → swing_high）:
retrace_382 = swing_high - (swing_high - swing_low) * 0.382
retrace_500 = swing_high - (swing_high - swing_low) * 0.500
retrace_618 = swing_high - (swing_high - swing_low) * 0.618
```

**与现有体系的结合**：

| 场景 | 现有行为 | 补充费波纳契后 |
|------|---------|---------------|
| 支撑区判定 | 支撑区域 [10.00, 10.05] | 支撑区域 + 费波纳契 50%=10.12, 61.8%=10.08 |
| 确认突破 | 确认价=阻力×1.005 | 确认价 + 费波纳契拓展 138.2%=目标价 |
| 低吸区 | [支撑, 支撑+zone_width] | 若费波纳契 61.8% 在区内，标注为**最佳低吸位** |

**新增输出字段**（在 `build_structure_context()` 的返回值中）：

```
"fib_retrace": {
    "swing_high": 12.50,
    "swing_low": 10.00,
    "382": 11.55,
    "500": 11.25,
    "618": 10.96
}
```

### 子项 B：时间窗口（高优先级）

**核心思想**：从关键转折点（缠论笔的终点/中枢突破点）开始计数 K 线，检测常见江恩时间周期。

**实现方式**：新增 `time_window_detector.py`（或集成进 `decision_core.py`）

```
def check_time_windows(bars: list[BarData], pivot_index: int) -> dict:
    从 pivot_index 到当前 bar 计数
    检查bar_count 是否靠近已知时间窗口:
    - 短周期: 21 / 34 / 55 bars（费波纳契天数）
    - 中周期: 90 / 144 bars（江恩重要循环）
    - 长周期: 360 bars（天文年）
    返回: { "window_active": bool, "window_type": "90/144/360", "bars_since_pivot": int }
```

**在 report 中的输出位置**（现有 "关键价位" 行下方）：

```
⏰ 时间窗口：自最近高点已过 144 个交易日，处于关键时间窗
```

### 子项 C：江恩角度线（中优先级）

- 1×1 角 = 45°，含义是"每 1 个时间单位价格变化 1 个单位"
- 需要根据股价本身计算 price scale（例如 ATR 作为 price unit，bar 数作为 time unit）
- 角度线作为现有支撑/阻力的参考系，在报告附注中提及

### 向后兼容

- 费波纳契依赖缠论笔数据，无笔数据时不输出
- 时间窗口依赖 pivot 标记，无 pivot 时静默不提示
- 均为纯附加信息，不改变现有判定逻辑

## Directory Structure

影响文件清单（含 P4 新增文件）：

```
02-共享模块-shared/
├── trader_shared/
│   └── config.py                     # [MODIFY] 低吸区/确认位/止损/ATR相关常量
├── 02-候选逻辑-candidate/
│   ├── structure_core.py             # [MODIFY] 新增 average_atr_pct() + 公式改用ATR + 乘数调整 + 理论信号接口 + 费波纳契计算
│   ├── decision_core.py              # [MODIFY] status_for()判定顺序 + ATR动态space阈值 + 理论微调 + 时间窗口逻辑
│   ├── t0_candidate_core.py          # [MODIFY] 接收外部structure_core结果 + 动态low_zone宽度
│   ├── price_point_engine.py         # [MODIFY] find_key_levels()增加optional_structure参数
│   └── time_window_detector.py       # [NEW]   江恩时间窗检测
```

无需修改的文件（仅提供上下文）：

- `fusion_core.py` — 融合层是并行系统，P3从中读取理论信号
- `fusion_regime.py` — regime权重在"很差"时一票否决是合理行为
- `chan_core.py` — P4从中读取笔数据计算费波纳契回调，无需修改

新增依赖：

- `structure_core.py` → 读取已算好的缠论/威科夫/动量结果 (P3)
- `structure_core.py` → 读取 chan_core 的笔数据计算费波纳契 (P4)

---

## Todo 清单

| 优先级 | ID | 内容 | 依赖 |
|--------|-----|------|------|
| P0 | fix-decision-order | decision_core.status_for()判定顺序，将"空间不足"移到最后 | - |
| P0 | fix-zone-params | config.py常量调整（MAX_ZONE_WIDTH=0.020, MIN_CONFIRM_SPACE=0.005） | - |
| P2 | fix-atr | structure_core新增average_atr_pct() + 全面替换振幅计算 | fix-zone-params |
| P1 | fix-t0-unify | t0_candidate_core + price_point_engine 复用trader价位 | fix-zone-params |
| P2 | fix-dynamic-space | decision_core ATR动态space阈值 + 降分 | fix-decision-order, fix-atr |
| P3 | fix-theory-signals | structure_core接入理论信号微调（缠/威科夫/动量→参数） | fix-atr |
| P4 | fix-fib-levels | structure_core读取缠论笔数据计算费波纳契回调位 | fix-atr |
| P4 | fix-time-windows | 新增time_window_detector.py + 集成到decision_core | fix-decision-order |
| - | verify | 终端跑场景测试验证 | fix-decision-order, fix-zone-params, fix-atr |

---

## 注意事项

### 1. pack_all.py 需同步更新

`time_window_detector.py` 必须加入 `pack_all.py` 的打包清单，否则 Hermes/Uberduck 环境找不到这个文件。参考之前 fusion_core.py 漏打的教训。

修改位置：`02-共享模块-shared/scripts/pack_all.py`，在候选逻辑文件列表中追加 `time_window_detector.py`。

### 2. 检查 status_rules.yml 规则引擎

`decision_core.py` 的 `_get_engine()` 会加载 `trader_shared/status_rules.yml`。如果规则引擎里也有"空间不足"判定且优先级未改，Fix 1 可能被覆盖失效。实施前需要确认该文件是否存在、其中是否有 space 相关规则。

### 3. calibrator.py 历史基线需重置

`02-共享模块-shared/scripts/calibrator.py` 会跑历史回测评估信号准确率。P0+P2 改了 zone_width 和 confirm_buffer → 历史信号的"低吸观察"次数会变化 → 新旧对比有偏差。建议所有 P0-P2 修改完成后重新跑一次校准器，把新结果作为基线。

### 4. P3 增加 `THEORY_ADJUST_LOG_ONLY` 安全开关

类似 fusion_core 已有的 `FUSION_LOG_ONLY` 模式——只打日志不实际生效。P3 首次上线时先开这个模式跑一周，观察理论信号对参数的微调幅度是否合理，确认没问题再正式启用。
