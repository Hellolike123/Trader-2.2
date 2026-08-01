# 威科夫 Point & Figure（P&F）因果目标 — Agent Handoff

> **status**: done（计数引擎）；**量度授权**见 L0–L3 门禁（2026-08-01）  
> **日期**: 2026-08-01  
> **产品法源**: `BUSINESS.md` §2.2；原典盘点 `docs/audit/wyckoff-original-concept-inventory.md` §一 / §六  
> **量度何时可出**: `docs/plans/wyckoff-tr-maturity-l0l3-handoff.md`（仅 `tr_maturity=L3`；L1 雏形 / 仅分位 TR **禁止**量度）  
> **目标**: 用可复现的 OHLC P&F **水平计数**估算因果目标价（短线日 K / 中线周 K 分轨）；高度 1:1 仅作显式 fallback  
> **读者**: 实现 / 对照 / 回归 Agent（只读本文 + 下列代码锚点即可）

---

## 0. 30 秒摘要

1. **只估目标价**，不改 SC/Spring/阶段机/出手/分道/fusion。  
2. 主路径：本轨 OHLC（日或周）→ 建 P&F 列 → 在本轨 TR 内做 **Horizontal Count** → 投射上下目标。  
3. 降级链：`horizontal` →（可选）`vertical` → `height_1to1_fallback`；失败时 **note 写明原因**，禁止静默假数字。  
4. `WYCKOFF_PNF_ENABLED=0` 强制旧 1:1，便于对照。  
5. 字段：保留 `cause_effect_*`；新增诊断 `pnf_box_size` / `pnf_columns` / `pnf_method`。

---

## 1. 数据与适用范围

| 项 | 合同 |
|----|------|
| K 线 | 调用方传入的 OHLC；**短线日 K** / **中线周 K** 分轨（同一 `compute_cause_effect_targets`；中线禁止用日线 TR 冒充） |
| 周线数据 | `fetch_weekly` 须通过间距体检；mootdx/sina 若吐日线间距 → `aggregate_daily_to_weekly` 纠偏（`data_source=daily_aggregate`） |
| 周线 TR/SC | `timeframe=weekly` 时缩放 TR 宽/回溯/振幅；SC/AR 用周线门槛（量比、close 定低位）；Phase A 种子箱 → 周线 P&F |
| TR 边界 | 调用方传入的 `tr_ctx`；**仅 L2/L3** 用 Phase A 种子（SC/ST+AR）作成熟箱；L1/分位不得授权量度 |
| TR 窗口 | 优先 `tr_start`..`tr_end`（含）；缺省则用传入 `bars` 全序列 |
| 量度门禁 | `tr_maturity==L3` 才保留 `cause_effect_*` 目标；见 `wyckoff-tr-maturity-l0l3-handoff.md` |
| 面板文案 | L3：`量度目标：上 x｜下 y（P&F，非出手）`；1:1 fallback 须标「高度1:1」勿冒充 P&F；L0–L2 不贴量度行 |
| 非目标 | 不改阶段/事件/打分/选股池注意力；不做实时分时 P&F |

---

## 2. 配置（`config.py`，均可 env 覆盖）

| 常量 | 默认 | Env | 含义 |
|------|------|-----|------|
| `WYCKOFF_PNF_ENABLED` | `true` | `WYCKOFF_PNF_ENABLED`（`0`/`false` 关） | 关则整段回退高度 1:1 |
| `WYCKOFF_PNF_BOX_PCT` | `0.01` | 同名 | Box = TR 中轴 × 该比例 |
| `WYCKOFF_PNF_BOX_MIN` | `0.01` | 同名 | Box 绝对下限（元） |
| `WYCKOFF_PNF_REVERSAL` | `3` | 同名 | 经典 3 格转向 |
| `WYCKOFF_PNF_MIN_COLUMNS` | `3` | 同名 | 水平计数最少列数；不足则尝试垂直/1:1；实现侧 `max(1, …)` |
| `WYCKOFF_PNF_VERTICAL_ENABLED` | `true` | 同名 | 是否允许垂直计数降级 |
| `WYCKOFF_PNF_INCLUDE_REVERSAL` | `false` | 同名 | `true` 时 effect = cols×box×reversal（Chartcraft 派）；默认 **不含** reversal |
| `WYCKOFF_PNF_MIN_TR_QUALITY` | `0.0` | 同名 | 默认 `0`＝不做质量门控。设为 `>0` 且 `tr_quality` 低于该阈值时 **强制** 高度 1:1（note 写明低质量，不假装 P&F） |

---

## 3. P&F 列构建（High-Low 法）

实现：`trader_shared/wyckoff_pnf.py` → `build_pnf_columns`。

1. `box_index(price) = floor(price / box_size)`（价格→格）。  
2. 首根用 **close** 定初始格；方向未定，直至价格相对初始格移动 ≥1 格：上涨开 **X** 列，下跌开 **O** 列。  
3. **X 列**：若 high 能向上加格 → **只延伸，当日不再看 low**；否则若 low ≤ 列顶 − `reversal`，转向新 **O** 列（从顶−1 向下填到 low）。  
4. **O 列**：若 low 能向下加格 → **只延伸，当日不再看 high**；否则若 high ≥ 列底 + `reversal`，转向新 **X** 列。  
5. 每列记录 `direction`（`X`/`O`）、`top`/`bottom`（格索引）、`box_count`。

可复现：同一 OHLC + box + reversal → 同一列序列。

---

## 4. 水平计数（主路径）

1. 仅用 TR 窗口内 bars 建图（见 §1）。  
2. **计哪些列**：列的价格带与 `[tr_lower, tr_upper]` **有交集**（`bottom*box ≤ tr_upper` 且 `(top+1)*box > tr_lower`，实现以代码为准）。  
3. `n_columns =` 交集列数；须 ≥ `WYCKOFF_PNF_MIN_COLUMNS`。  
4. `effect = n_columns × box_size`；若 `INCLUDE_REVERSAL` 再 × `reversal`。  
5. **投射**（与旧 1:1 同锚、不同幅度）：  
   - `up_target = tr_upper + effect`  
   - `down_target = tr_lower - effect`  
   - `cause_effect_range = effect`（因果幅度，**不是** TR 高度）  
6. `pnf_method = "horizontal"`。

---

## 5. 垂直计数与 1:1 回退

| 次序 | `pnf_method` | 何时 | 公式 |
|------|--------------|------|------|
| 1 | `horizontal` | 交集列 ≥ MIN_COLUMNS | §4 |
| 2 | `vertical` | 水平失败且 `VERTICAL_ENABLED`；取 TR 内最高列的 `box_count` | `effect = box_count × box_size`（可选 × reversal）；投射同 §4 |
| 3 | `height_1to1_fallback` | 上两者失败 / 无 bars / 建图失败 / `ENABLED=0` | `effect = tr_upper - tr_lower`；`up=upper+effect`；`down=lower-effect`（旧行为） |

垂直计数在本仓是 **降级路径**，不是主叙事；note 须写明「垂直计数降级」。

---

## 6. 字段契约

### 6.1 `wyckoff_analysis` / `_cause_effect_targets` 返回

| 字段 | 类型 | 说明 |
|------|------|------|
| `cause_effect_up_target` | `float \| None` | 上侧目标；无 TR 时 `None` |
| `cause_effect_down_target` | `float \| None` | 下侧目标 |
| `cause_effect_range` | `float \| None` | 因果幅度（P&F effect 或 1:1 高度） |
| `cause_effect_note` | `str` | 人话说明方法 + 关键参数；失败原因必填 |
| `pnf_box_size` | `float \| None` | 实际使用的 box；1:1/无 TR 可为 `None` |
| `pnf_columns` | `int \| None` | 水平计数列数；非水平路径可为 `None` 或 0 |
| `pnf_method` | `str \| None` | `horizontal` \| `vertical` \| `height_1to1_fallback`；无 TR 时 `None` |

### 6.2 View（`WyckoffCauseEffectView`）

在既有 `up_target` / `down_target` / `range` / `note` 上增加：

- `pnf_box_size` / `pnf_columns` / `pnf_method`

`to_wyckoff_state_view` 从 analysis 薄透传，不重算。

---

## 7. 降级与诚实 note（禁止静默假数字）

| 情形 | 目标 | note 要点 |
|------|------|-----------|
| 无 `tr_ctx` / 上下沿非法 | 全 `None` | `无有效 TR，无法做因果目标` |
| `ENABLED=0` / `enabled=False` | 1:1 | 写明「P&F 已关闭」+ 高度 1:1（不冒充水平计数） |
| 无 bars / OHLC 不足 | 1:1 | 写明缺 K 线、回退 1:1 |
| 低质量 TR（&lt; MIN_TR_QUALITY 且阈值&gt;0） | 可配置强制 1:1 | 写明低质量 |
| 水平列不足且垂直失败/关闭 | 1:1 | 写明计数失败原因 |
| 水平/垂直成功 | 有数字 | 写方法、box、列数/格数、effect |

---

## 8. 与旧 1:1 的差异（一句话）

旧：`effect = TR 高度`；新主路径：`effect = TR 内 P&F 水平列数 × box`（可关回旧）。

---

## 9. 代码锚点

| 职责 | 路径 |
|------|------|
| 规格（本文） | `docs/plans/wyckoff-pnf-handoff.md` |
| 建图 + 计数 | `trader_shared/wyckoff_pnf.py` |
| 薄委托 | `wyckoff_events._cause_effect_targets` |
| 挂载字段 | `wyckoff_core.wyckoff_analysis` |
| View | `wyckoff_view.WyckoffCauseEffectView` / `to_wyckoff_state_view` |
| 配置 | `config.py` → `WYCKOFF_PNF_*` |
| 测试 | `tests/test_wyckoff_pnf.py` |

---

## 10. 已知局限 / 工程取舍

1. **非原典 count line**：水平计数 = TR 价格带内「有交集」的列数，不是沿某一水平 count line 只计触线列；长横盘时 `effect` 可明显大于 TR 高度（因果律本意，但比教科书偏宽）。  
2. **双向投射**：始终 `↑ tr_upper+effect` / `↓ tr_lower-effect`，不按积累/派发阶段只投一侧（与旧 1:1 同锚）。  
3. **首根只用 close 定初始格**：首根 high/low 不参与建列，直至后续 K 线相对初始格移动 ≥1 格（High-Low 常见简化）。  
4. **垂直计数取 TR 内最高列格数**：降级启发式，不是原典「指定数浪列」。  
5. **Box 默认**：`BOX_PCT=1%` × TR 中轴、`BOX_MIN=0.01` 元；env 把 box 调极小会增多列数——勿无无下限的超小 box 跑长历史。  
6. **`MIN_COLUMNS` 实现侧 `max(1, …)`**：配置 ≤0 时按 1 处理，避免 0 列 effect=0 假成功。  
7. **计数引擎 ≠ 量度授权**：有 TR 就能算 P&F，但产品层须 `tr_maturity=L3` 才展示；见 `wyckoff-tr-maturity-l0l3-handoff.md`。

---

## 11. 验收清单

- [x] handoff 与代码同语义（计数）  
- [x] 合成 bars：列数、水平目标、fallback、开关  
- [x] 盘点文档 §一/§五/§六 + `BUSINESS.md` §2.2 不再写「未做/非优先」  
- [x] 不改阶段机 / 出手 / 池分道  
- [x] `WYCKOFF_PNF_ENABLED=0` 可对照旧 1:1  
- [x] **L0–L3 量度门禁**落地（`wyckoff-tr-maturity-l0l3-handoff.md` M-R1…R8） 
