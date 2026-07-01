# Spec: 威科夫经典信号扩展 (AR / SOS / ST / LPS)

## 概述

在现有 5 个威科夫单 bar 检测器（Spring、Upthrust、BC、SOW、量价背离）基础上，
按 Accumulation Cycle 理论顺序新增 4 个经典信号，使威科夫分析覆盖完整的
**Accumulation → Markup 转换链**。

## 现有状态

### 已有检测器

| 信号 | 类型 | 权重 |
|------|------|------|
| Spring (弹簧洗盘) | 单 bar | +25 |
| Upthrust (上冲回落) | 单 bar | -20 |
| 看多背离 | 单 bar | +10 |
| 看空背离 | 单 bar | -10 |
| BC (购买高潮) | 单 bar | -15 |
| SOW (弱势信号) | 单 bar | -10 |

**最大正值**: +70 (Spring + Spring×看多 + 看多背离 = 25+5+10=40... 实际最大 +70 当 Spring + BC + 看多背离都触发)

**最大负值**: -55 (BC + SOW + 看空背离 = 15+10+10=35... 实际最大 -55)

### 缺失信号

| 信号 | 威科夫含义 | Accumulation 阶段位置 |
|------|-----------|---------------------|
| AR | Buying Climax 后抛售枯竭的快速反弹 | 紧接 BC 之后 |
| SOS | 连续放量突破，确认进入 Markup | 上涨确认段 |
| ST | 二次测试支撑/阻力，缩量确认有效性 | 回测确认段 |
| LPS | SOS 突破后回调不破前低，最后买点 | 回测结束段 |

## 新增信号规范

### AR (Automatic Rally 自动反弹)

**触发条件**：
1. 最近 N 根 K 线内检测到了 BC 信号（BC 提供时间锚点）
2. 在 BC 发生后的 1-3 根 K 线内，存在至少 1 根满足：
   - `close > bc_close * 1.02`（较 BC 收盘价上涨 ≥ 2%）
   - `volume > avg_volume(BC 前 10 根) * 1.2`（放量）

**权重**：`+10`

**输出字段**：
- `ar_signal`: bool
- `ar_reason`: str (e.g. "BC 后自动反弹，放量 +3.2%")
- `ar_price`: float | None

**记忆依赖**：需要记录 BC 的 `bc_price` 和发生 bar 索引。

---

### SOS (Sign of Strength 强势信号)

**触发条件**：
1. 最近 5 根 K 线窗口满足：
   - 全部 5 根为阳线（`close > open`）
   - `close[4] >= open[0]`（总体抬高）
   - 平均成交量 > 前 10 日均量 * 1.2
   - `(close[4] - open[0]) / open[0] >= 0.02`（累计涨幅 ≥ 2%）

**权重**：`+15`

**输出字段**：
- `sos_signal`: bool
- `sos_reason`: str
- `sos_price`: float | None

**记忆依赖**：无，纯窗口检测。

---

### ST (Secondary Test 二次测试)

**触发条件**：
1. 最近 N 根 K 线内检测到了 Spring 信号（Spring 提供支撑锚点）
2. 在 Spring 发生后的 3-15 根 K 线内：
   - 存在 1-2 根 K 线的最低价进入支撑区域：`low <= support * 1.01`（±1%）
   - 该区域的平均成交量 < 前 10 日均量 * 0.8（缩量确认）
   - 进入支撑区域的最低价 ≥ support（未破支撑）

**权重**：`+8`

**输出字段**：
- `st_signal`: bool
- `st_reason`: str (e.g. "Spring 支撑二次测试，缩量确认")
- `st_price`: float | None

**记忆依赖**：需要记录 Spring 的 `support` 价格和发生 bar 索引。

---

### LPS (Last Point of Support 最后支撑点)

**触发条件**：
1. 最近 N 根 K 线内检测到了 SOS 信号（SOS 提供起涨锚点）
2. SOS 发生后 2-10 根 K 线内出现回调：
   - 连续 2-5 根 K 线价格下行或横盘（`close[i] <= close[i-1]`）
   - 回调末期最低价 > SOS 起涨点前 5 根 K 线的最低价（不破前低）
   - 回调末期成交量 < 均量 * 0.7（缩量确认）

**权重**：`+12`

**输出字段**：
- `lps_signal`: bool
- `lps_reason`: str (e.g. "SOS 后缩量回调，不破前低")
- `lps_price`: float | None

**记忆依赖**：需要记录 SOS 的起始 bar 索引。

## 与缠论的关系

LPS 和缠论二类买点**互补独立**：
- 各自独立检测、各自打分
- 不互斥、不覆盖
- LPS 仅依赖量价行为（不依赖缠论结构）

## 新增打分体系

```
看多: Spring +25, Spring×看多 +5, 看多背离 +10, AR +10, SOS +15, ST +8, LPS +12
      理论最大正值 = 25+5+10+10+15+8+12 = 85

看空: Upthrust -20, 看空背离 -10, BC -15, SOW -10
      理论最大负值 = 20+10+15+10 = 55

归一化: WYCKOFF_SCORE_MAX_ABS 从 80 → 95 (取 max(85, 55) * 1.1 ≈ 95 留余量)
```

## 文件改动清单

### 必须改动

| 文件 | 改动 |
|------|------|
| `trader_shared/config.py` | 新增 4 个权重常量，更新 `WYCKOFF_SCORE_MAX_ABS = 95`，更新 `__all__` |
| `trader_shared/wyckoff_core.py` | 新增 `_detect_ar()`, `_detect_sos()`, `_detect_st()`, `_detect_lps()` 四个检测函数，修改 `wyckoff_analysis()` 整合，修改 `calculate_wyckoff_score()` 消费新信号 |

### 自动受益（不改）

| 文件 | 行为 |
|------|------|
| `final_pool.py` | `score_report()` 通过 `calculate_wyckoff_score()` 自动获得新信号加分 |
| `review_core.py` | `theory_verdicts()` 通过 `calculate_wyckoff_score()` 自动获得新信号加分 |
| `fusion_core.py` | `wyckoff_score_to_direction()` 自动反映新分数 |

### 新增测试

| 文件 | 测试 |
|------|------|
| `test_wyckoff_core.py` | `TestDetectAR`, `TestDetectSOS`, `TestDetectST`, `TestDetectLPS` 四个新类 |

## 向后兼容

- `wyckoff_analysis()` 原有返回字段不变，新增字段追加
- `calculate_wyckoff_score()` 原有行为不变，新增信号自动加权
- 下游 `final_pool.py` / `review_core.py` 无需改动
- 所有已有测试必须通过

## 验收标准

1. 新增 4 个信号在对应场景下正确触发
2. 无信号时返回分数不受影响（中性 50 分）
3. 所有已有测试通过（124 个核心测试）
4. 新增 4 个信号各 ≥ 4 个测试用例
5. `calculate_wyckoff_score()` 返回的 `score` 范围仍在 [0, 100]
6. 新增信号在输出 summary 中正确显示
