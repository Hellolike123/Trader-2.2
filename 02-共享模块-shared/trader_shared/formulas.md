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
- **MACD 柱来源**：`indicator_math.calc_macd_series` → `histogram = DIF−DEA`（×1，非通达信 2×）；
  `_calc_macd` 预热不足写 `None`（禁止 `0.0` 占位）；面积计算跳过 `None` 与反号柱

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

- **一类买/卖**：下跌/上涨趋势（≥2 个**严格不重叠**同向中枢，与 `classify_structure` 拓扑一致）
  + 最后中枢**离开段**背驰 + 末两段同向笔价格新低/高 + MACD 面积减弱
- **二类买/卖**：`down_a→up→down_b` 且 `low_b>low_a` 且 `low_b<up_high`（卖点对称），
  **且前置一类在时间轴上成立**——`down_a`/`up_a` 须满足历史一类结构
  （趋势 + 离开中枢 + 若存在更早同向笔则曾创新低/高 + 力度不更强），
  **禁止**用「同帧 `buy_points` 里已有一类」判定（一类要创新低、二类要不破前低，
  同一末笔几何互斥，旧实现导致二类永假）。
- **买侧分层（产品 C）**：正式「二类买」必须 `_historical_type1_buy_ok` + 力度/缩量齐备；
  历史一类不满足或力度未齐 → 降级「类二买」（无趋势中枢仍可出类二买）。
  fusion 强多 / C1「买点信号」/ 买点阶梯二档 **只认正式二类买**，不认类二买。
  卖侧「二类卖」仍要求历史一类（对称严格）。
- **三类买/卖**：离开中枢后回抽不入（末 3 笔内，上限 15%）

实现辅助：`_strict_down_trend_zones` / `_strict_up_trend_zones`、
`_historical_type1_buy_ok` / `_historical_type1_sell_ok`（`chan_structure.py`）。

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
| 二类前置一类 | 正式二类买/二类卖须时间轴历史一类；买侧无趋势可降级类二买 | — |
| 区间套未确认 | fusion 置信度降权（×0.65 / nesting ×0.55） | `TRADER_CHAN_NESTING` |

> 所有行为变更须在 `test_chanlun_correctness.py` / `test_chan_core` 增补语义 golden，并刷新
> `chan_split_baseline.json` / `report_render_baseline.txt` 等价闸门基线。

---

## 6.1 2026-07-16 买卖点 / 消费面修复记录

| 问题 | 修复 |
|------|------|
| 二类买要求同帧 `buy_points` 含一类 → 与一类「创新低」互斥，二类永假 | `_historical_type1_buy_ok` 在时间轴上认定 `down_a` |
| 一类趋势仅比 `zh_top`，允许重叠中枢假趋势 | `_strict_*_trend_zones` 要求末中枢整体在前中枢外 |
| 区间套 `lower_confirmed=False` 只展示、fusion 满置信 | `_chan_to_signal` 对未确认买点/背驰降权 |
| 单测仍用 1 中枢期望一类 / merge patch 错模块 | 刷新 `test_chan_core` |

---

## 9. 缠论原典严格口径（三角对照之规则源头）

> 本段把缠中说禅原典关于「走势类型 / 中枢 / 趋势 / 背驰」的文字定义，**结构化**为
> 可操作的判定清单。用途：与 `czsc` 工程实现、与本项目实现做**三角对照**时，
> 作为「规则源头」参照，区分「定义取舍分歧」与「真逻辑 bug」（详见 §9.4）。
> 原典本身有模糊地带（同级别分解边界等），凡原典即留白处，本段显式标注「交实战终审」。

### §9.1 中枢（原典定义）
- 某**固定级别**上，至少 **3 段（次级别走势类型）** 间产生**价格重叠**，构成该级别一个中枢。
- 中枢区间 `ZG=min(三段高点)`、`ZD=max(三段低点)`；有效中枢须 `ZG > ZD`。
- 两个以上中枢的**连接段**必须是**反向走势**（由反向线段/次级别走势隔开），否则不能算「两个中枢」。

### §9.2 走势类型（原典二分）
- **盘整（a+A）**：只有一个该级别中枢，或虽有多次重叠但合并后为一个中枢。
- **趋势（a+A+b+B+c）**：至少 **两个同方向、互不重叠** 的中枢，且两中枢之间由**反向走势段**
  严格连接。两中枢同向不重叠 → 趋势；方位由第二段相对第一段的高低定（上移=上涨趋势）。
- 关键点（本项目的「区间近似」最易在此犯错）：
  - 两中枢区间**哪怕只略重叠**，按原典严格口径**不是干净趋势**（归盘整/更大级别中枢）；
  - 两中枢区间不重叠，但中间夹了**同向小中枢**（即连接段自身不是反向走势）→ 仍非趋势，是「假趋势」。

### §9.3 背驰与买卖点（原典定位）
- **趋势背驰**：趋势中**最后一个中枢的离开段 c** 与**进入段 b** 比较力度（MACD 面积 / 黄白线 / 成交量），
  c 段力度衰减即背驰；背驰后至少回拉最后中枢 ZG/ZD 才算完成。
- **盘整背驰**：仅一个中枢时，离开段与进入段比较，意义弱于趋势背驰，通常只产生类买卖点。
- **一类买卖**：趋势背驰的绝对转折点（最后中枢 c 段末端）。
- **二类买卖**：一类之后回抽，**不跌破**一类低点（买）/ **不升破**一类高点（卖）。
- **三类买卖**：离开中枢后回抽**不重新进入**中枢区间（ZG/ZD），确认中枢完毕 / 新趋势启动。

### §9.4 三角对照判定清单（操作化）
对任一标的，按以下顺序给「原典口径」定论（交实战终审处由用户凭 K 线经验裁决）：

1. 列出该级别所有中枢 `[ZD_i, ZG_i]` 及其中心位置。
2. 若中枢数 < 2 → **盘整**（除非无中枢且纯单边，但单边在日线罕见）。
3. 若中枢数 ≥ 2：
   - 取**最后两个中枢** A（前）、B（后）；
   - B 与 A **不重叠** 且 **同向**（B 中心 > A 中心 → 上移；< → 下移）→ **趋势**；
   - B 与 A **重叠** 或 **高低交叉**（一上一下）→ **盘整 / 更大级别中枢**（非趋势）；
   - 中间连接段若夹有同向小中枢 → 降为盘整（假趋势）。
4. 趋势方向 = B 相对 A 的方向；背驰只看 B 的离开段 c。

> **三角对照判读规则**（区分两类问题）：
> - 我们实现 与 czsc 都偏离本清单 → 属「定义取舍分歧」（可接受，但须标注）；
> - 我们实现 偏离 czsc，但 czsc 贴合本清单 → 可能是「我们真写偏」（P3 递归要修的重点）；
> - 三者一致 → 高置信，现状可靠；
> - 三者全分歧 → 「定义分歧区」，交用户实战终审，不自动定罪。

---

## 10. 三角对照实测记录（P3 递归决策依据）

> 见 `scripts/diagnose_chan_triangulation.py` 输出。当前样本：代表性 7 只（2024-01~2026-07 日线）。
> 结论格式：共识区 / 定义分歧区，供是否上 P3 递归走势类型重写做决策。
>
> **后续扩展（见 §11 / §12）**：样本已扩至 30 只跨行业，并新增原典合规修复 A+B 与区间套生产接入及命中率验证。

---

## 11. 原典合规修复 A+B（commit ca2610f）

> 背景：30 只跨行业日线离线对照（新浪源 + 完整原典规则），初版共识率仅 51.7%，
> 定位到两类偏离原典的问题，均已修复并复测 30/30 共识。

### A — 0 中枢标签偏差（chan_structure.py · classify_structure）
- 原：`valid_zones` 为空但有线段时，兜底返回 `"盘整"`。
- 问题：原典中「盘整」严格 = `a+A`（至少 1 个中枢），**0 中枢应为「无结构」**。
- 修：改为返回 `"无结构"`，docstring 同步更正。

### B — 笔级中枢漏检（chan_core.py · 走势分解路径）
- 原：`if len(segments) >= 3: 走段路径 else: 走笔路径`。宽幅震荡股恰好只划出
  **3 段且端点价不重叠** → 段路径 `build_zones` 造不出中枢 → 误报 0 中枢 / 无结构。
- 但同票笔级别（20+ 笔）明显有重叠中枢——典型「胡算」漏检。
- 修：**段路径造不出中枢时回退笔路径**（笔是日线最小走势单元，笔中枢系合法原典概念）；
  段路径有中枢时仍优先段（原行为不变）→ 只救漏检票，零回归。
- 受影响样本：恒瑞医药 / 迈瑞医疗 / 比亚迪 / 宝钢股份 / 格力电器（修复后分别判为
  盘整 / 下跌趋势 / 盘整 / 盘整 / 盘整，符合实际走势）。

### 复测结论
- 30 只跨行业离线 CSV，A+B 后 **30/30 共识（100%）**；其余 25 只结构类型零回归。

---

## 12. 区间套生产接入与命中率验证（commit 5f2a28b 验证 / 66322bc 接入）

### 验证方法（scripts/diagnose_chan_nesting.py）
- 对称「截至日期 d」快照法：日线一/二类买 + 底背驰信号 → 定位同价位 → 下钻 30m
  窗口确认小级别结构 → 统计确认组 vs 未确认组的 `+10 日` 前向收益。
- 数据：新浪 30m（沙箱白名单可达），`datalen=800` 覆盖约 5 个月，落盘 `chan_csv_30m/` 离线可复现。

### 验证结论（30 只跨行业，step=5 / step=10 结论一致）
| 分组 | 样本 | 均值收益 | 胜率 |
|------|------|---------|------|
| 30m 确认组 | 32 | **+1.99%** | **50.0%** |
| 未确认组 | 121 | -1.27% | 33.9% |
| 全部日线信号 | 153 | -0.73% | 36.6% |

- 纯日线底背驰/买点中，约 4/5 是假信号或下跌中继；经 30m 确认后才转正期望。
- 区间套确实**过滤假信号、提升日线买点质量**（日线买点更准 + 为 T0 提供小级别底座）。

### 生产接入（chan_nesting.py + report_builder.py + report_core.py）
- 新增 `chan_nesting.confirm_daily_with_lower(daily_result, lower_bars, lower_timeframe="30m")`：
  复用 `chanlun_analysis` 跑小级别确认日线 `buy_points` / 底背驰，加 `lower_confirmed`
  标注 + 顶层 `nesting_confirmation` 汇总（单级别兼容入口）。
- 新增 `chan_nesting.confirm_nested_chain(daily_result, lower_series, ...)`：**多级别区间套**
  （粗→细，如 `[("30m",b30),("5m",b5),("1m",b1)]`）。每个日线买点产出
  `nesting_chain`（各级别 `{timeframe,confirmed,type}`）+ `nesting_confirmed`（所有可用级别
  均确认 = T0 高置信入场），底层仍复用 `chanlun_analysis`。等价性闸门：`lower_series=[]`
  或各级均无数据 → 原样返回。
- `report_builder`：日线 chanlun 出结果后，按 `TRADER_CHAN_NESTING_LEVELS`（逗号分隔，默认 `"30m"`；
  设 `"30m,5m,1m"` 开启 T0）逐层 `fetch_kline(sec,code,datalen)`（`30m→800 / 5m→1000 / 1m→1200`）
  + `confirm_nested_chain`。受 **`TRADER_CHAN_NESTING`（= `0` 跳过）** 守卫 + 异常降级；某级别
  取数失败仅该级别 skipped，连累不到其它级别。生产环境本机 eastmoney / tdx 取数。
- `report_core`：日线缠论行末尾加 `30m✓ 5m✓ 1m✓`（或各级 `✗`）链路标注，**仅确认流程跑过才显示**，
  不改既有格式。
- 等价性闸门 + 门禁：`lower_series` 为空 / 各级缺失 / 异常时原样返回；门禁设 `TRADER_CHAN_NESTING=0`，
  新增自包含单测 `test_chan_nesting_chain.py`（monkeypatch chanlun_analysis，CI 可跑），
  全量门禁 **0 failed** 零回归。

### 边界与下一步
- 当前为「标注增强」，**不改任何价格 / 结构 / 评分**；日线 + 30m + 5m + 1m 多级别链路已打通。
- 沙箱实测得：新浪 30m / 5m 可达（`scale=30/5&datalen=800/1000`），**1m 沙箱不可达**
  （HTTP 000，需在你 Mac 本机 eastmoney / tdx 取 1m）；T0 实战验证请在 Mac 上跑
  `TRADER_CHAN_NESTING_LEVELS=30m,5m,1m`。
- 命中率结论（§12 上表）仍基于 30m 单层确认；5m / 1m 多级 AND 的命中率增益待 Mac 实盘样本积累后回填。
