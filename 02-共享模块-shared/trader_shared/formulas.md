# 缠论计算规则与业务取舍（formulas.md）

> 本文件是 `chan_geometry.py` / `chan_structure.py` / `chan_core.py` 中缠论算法的**权威规则说明**，
> 消除代码中 `formulas.md 1.x` 注释引用的「空引用」问题。所有规则以**当前实现**为准，
> 协议级参数见 `config.py` 的 `CHAN_*` 常量。
>
> 缠论是交易决策的地基（威科夫/动能/缠论 三评委融合的输入之一），故规则必须严格、
> 可审计、可回退。任何行为变更须同步更新本文件并刷新等价闸门基线。

---

## 0. 处理管线（K 线 → 买卖点）

```
raw bars
  → handle_inclusion        # 包含处理（K 线）
  → find_fractions          # 1. 分型
  → build_strokes           # 2. 笔（P2：裁左端悬空笔）
  → build_segments          # 3. 线段（特征序列三分型终结）
  → build_zones             # 4. 中枢（连续 3 段重叠）
  → classify_structure      # 走势分类（无结构/单边/盘整/趋势）
  → detect_divergence       # 5. 背驰（P3：锚定最后中枢）
  → detect_buy/sell_points  # 6. 一/二/三类买卖点
```

批量接口（`chanlun_analysis`）与增量引擎（`ChanlunEngine`）共用内核 `_chanlun_compute`，
字节级一致。

---

## 1. 分型（find_fractions）

**§1.1 定义**：在 `bars[i]`（不含首尾，扫描 `range(1, n-1)`）上，与左右相邻 K 线比较：
- 顶分型：`high` 与 `low` **双侧**均高于左右（`h_mid>h_left and h_mid>h_right and l_mid>l_left and l_mid>l_right`）
- 底分型：双侧均低于左右

**§1.2 双侧严格（与特征序列终结一致）**：顶/底分型必须 `high` 和 `low` 同时满足双侧条件，
单侧假分型（仅 `low` 达标而 `high` 不达标，或反之）**不**构成分型。这是线段终结与分型
共用的硬约束（见 §3 的 A-2 规则）。

缺口（缺失 `high/low/close`）的分型跳过，不参与。

---

## 2. 笔（build_strokes）

**§2.1 成笔条件**：从起点出发，取**第一个**距离合格的反向分型成笔：
- `end.index - start.index >= CHANLUN_MIN_BARS_PER_STROKE - 1`（默认 5，即 ≥5 根 K 线）
- 方向须与上一笔**交替**（强制交替，过滤同向连续分型取极值）
- 起点取连续同向分型的极值（顶取最高 `high`，底取最低 `low`）；终点取**第一个**合格反向分型，
  **不向前延伸至最极端分型**（过度延伸会吞掉独立笔，导致全链路失真）

**§2.2 力度字段**：每笔带 `power_price`（绝对价差）、`length`（K 线根数）、`power_volume`
（笔内成交量之和，需传入 `bars`）。

**§2.3 P2 边界处理 — 前导悬空笔**：序列首笔必从数据起点（第一个分型）起算，其左侧无任何
分型可确认起点，属**悬空不可信笔**。标准做法（czsc 等）视首笔/首段为「不确定」，不参与
趋势判定与背驰比较。实现上在 `_chanlun_compute` / `ChanlunEngine._recompute` 中裁掉
`strokes[0]`（`_drop_leading_dangling_strokes`），从第一个完整支点起读。
开关：`CHAN_DROP_LEADING_DANGLING_STROKE`（默认开）。

---

## 3. 线段（build_segments）

**§3.1 定义**：至少 3 笔构成一段，用**特征序列 + 三分型终结**判断线段终结。
- 向上线段：取所有向下笔构成特征序列，最后三根形成标准双侧底分型（`mid.low` 三者最低
  且 `mid.high` 三者最低）时终结
- 向下线段：取所有向上笔，最后三根形成标准双侧顶分型时终结
- 特征序列含包含处理（按方向合并，规则同 K 线包含）

**§3.2 A-2 双侧分型（缠论 1.2 合规）**：终结分型须 `high` 与 `low` 双侧同时满足，
单侧假分型不终结（与 §1.2 一致），减少误判。

**§3.3 启动门槛**：`CHAN_SEGMENT_RELAX_OVERLAP=True`（默认）时从首笔直接起段；
关闭则要求前三笔严格价格重叠才启动（一键回退路径）。

---

## 4. 中枢（build_zones / _merge_zones）

**§4.1 定义**：连续 3 段（线段或笔）重叠区间 = 中枢。`zh_top=min(highs)`，
`zh_bottom=max(lows)`，`valid = zh_top > zh_bottom`。

**§4.2 合并**：`CHAN_ZONE_MERGE_ENABLED=True`（默认）时，仅当两中枢**价格真正重叠**
（`zh_top > last.bottom and zh_bottom < last.top`）才合并为 consolidated pivot，
取交集（`zh_top=min`，`zh_bottom=max`）。**纯 gap（不重叠）不再合并**，
避免 `zh_top < zh_bottom` 的非法中枢（这是历史 bug 根因之一）。

**§4.3 中枢方向关系（拓扑）**：`classify_structure` 据合并中枢的上下位置关系判定
走势类型——同向不重叠中枢 → 上涨/下跌趋势；重叠/混乱 → 盘整；单中枢 → 盘整；
无中枢且有线段 → 盘整/单边。段数只调 `structure_confidence`，不决定主状态。

---

## 5. 背驰（detect_divergence）

**§5.1 主路径 — 笔级 MACD 面积**：比较**最后两段同向笔**的 MACD 柱面积
（`_stroke_macd_area`，只累加同侧柱；`side='neg'` 底背驰 / `'pos'` 顶背驰）。
- 向下背驰：`|area_curr| < |area_prev|`
- 向上背驰：`area_curr < area_prev`
- 多维（`power_price`/`length` 兼备时）用 `_stroke_force_weaker_multi`：≥2 维度衰减即判更弱

**§5.2 fallback — 峰谷（仅对笔级未评估侧）**：无笔/无 index/面积不可算时，扫近期峰谷
（最近 `CHAN_DIVERGENCE_FALLBACK_WINDOW=120` 根），比较末两个峰/谷的价与 MACD 柱。

**§5.3 P3 边界处理 — 锚定最后中枢**：背驰只应反映**最后中枢之后的趋势 legs**
（离开段 c 及其次级别同向段），而非整段历史。`_chanlun_compute` 计算最后中枢右边界的
bar 索引 `anchor_bar`（经 `_last_pivot_anchor_bar` 映射），传入 `detect_divergence`：
- 笔级比较只取 `end_index >= anchor_bar` 的 legs（不足两段则回退全序列，避免漏判）
- fallback 窗口从 `anchor_bar` 起算（替代固定 120 根窗口）

开关：`CHAN_DIVERGENCE_ANCHOR_LAST_PIVOT`（默认开）。`anchor_bar=None` 时回退到 §5.2 窗口逻辑。

> ⚠️ 历史上背驰曾用「全图扫描」fallback 直接 gate 买卖信号，导致陈旧历史背离污染买卖点
> （见 P0b/P0c 修复）。现背驰仅作展示标签与严格买卖点判定的辅助，信号合成以 `detect_buy/sell_points` 为准。

---

## 6. 买卖点（detect_buy_points / detect_sell_points）

严格定义 + 离开段约束 + 前置条件 + 降级，输入为已去悬空（`§2.3`）的笔与中枢：

- **一类买/卖**：下跌/上涨趋势（≥2 个同向中枢）+ 最后中枢**离开段**背驰 + 末两段同向笔
  价格新低/高 + MACD 面积减弱
- **二类买/卖**：`down_a→up→down_b` 且 `low_b>low_a` 且 `low_b<up_high`，**且前置一类买**
  才报；面积不满足 → 降级「类二买」
- **三类买/卖**：离开中枢后回抽不入（末 3 笔内，上限 15%）

---

## 7. 多级别区间套（_higher_level_trend）

优先用真实周线（`weekly_bars`）估计上级别趋势；不可用时回退日线 chunk 聚合
（`CHAN_MULTILEVEL_CHUNK=5`）。末 3 段多数决，`confidence = 同向段数/3`。
上级明确反向时，下级仅保留「一类」背驰点并清理无对应一类的背离（`higher_trend_conflict`
标记真冲突）。`CHAN_MULTILEVEL_ENABLED` 控制开关。

---

## 8. 已知边界与业务取舍小结

| 项 | 处理 | 开关 |
|----|------|------|
| 首笔悬空（无左支点） | 裁掉首笔，从完整支点起读 | `CHAN_DROP_LEADING_DANGLING_STROKE` |
| 背驰陈旧历史污染 | 锚定最后中枢，只比趋势 legs | `CHAN_DIVERGENCE_ANCHOR_LAST_PIVOT` |
| 中枢纯 gap 合并 | 禁用，仅价格重叠才合并 | `CHAN_ZONE_MERGE_ENABLED` |
| 线段启动门槛 | 默认从首笔起段（放宽） | `CHAN_SEGMENT_RELAX_OVERLAP` |
| 背驰 fallback 窗口 | 最近 120 根（P3 锚定后从中枢起） | `CHAN_DIVERGENCE_FALLBACK_WINDOW` |
| 买卖信号合成 | 只走严格 detect_buy/sell_points | — |

> 所有行为变更须在 `test_chanlun_correctness.py` 增补语义 golden，并刷新
> `chan_split_baseline.json` / `report_render_baseline.txt` 等价闸门基线。
