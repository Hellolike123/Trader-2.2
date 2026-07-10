# 中线独立价位引擎计划（真双轨 P0）

> 状态：**规格冻结**（预审阻断项 B-1～B-8 用户全 A，见 §9）  
> 日期：2026-07-10  
> 动机：用户明确要求中线关键价必须上**独立引擎**，不得继续用日 K `key_levels` 代理冒充中线价  
> 前置已交付：`docs/mid-short-dual-track-plan.md`（理论/看法/报告分区双轨；价位仍为日 K 代理）  
> 协作：Implementer 实现 / Reviewer 持本规格验收  
> **价位验收真理：本文档（含 §9）优先于** `mid-short-dual-track-plan.md` 的 B4A / 日 K mid 取值表  


---

## 0. 问题陈述

### 0.1 现状缺口

| 层 | 双轨？ | 说明 |
|----|--------|------|
| 周/日缠论·威科夫 | ✅ | `*_midline` vs daily fusion |
| 中线看法 B1A | ✅ | 周线合成 |
| 报告 🧭/⚡ | ✅ | 分区展示 |
| **中线关键价** | ❌ 半轨 | `mid_key_prices` 读 **日 K** `find_key_levels`（10/60/120） |

用户裁决：**必须上独立引擎**——中线 life / pullback / resist / target 的**主计算路径**不得依赖日线 `key_levels`。

### 0.2 目标

1. 新建 **中线价位引擎**（`midline_structure.py` + `mid_key_prices` 薄封装），输入以 **`weekly_bars` + `chanlun_midline`（周线 strokes/segments/zones）** 为主。  
2. 短线 `key_prices` / `structure_core` **保持日线独立**，互不调用对方主路径。  
3. 报告字段仍输出 `mid_key_prices`（展示契约不变），`engine=weekly_v1` + `source=weekly_structure|weekly_swing_only`，**禁止**成功路径 `daily_key_levels_proxy`。  
4. 数据不足时有**显式降级策略**（不足 ≠ 静默日线冒充）；日线回退仅开关，默认关。

### 0.3 非目标

- 不重写日线 `build_key_prices` / fusion / 门控主逻辑。  
- 不把中线价单独变成「出手放行」条件（出手仍短线 + Mistery）。  
- 不强制上月线引擎（可 P2）。  
- 不改 🧭/⚡ 文案句式（生命线/回踩/压力/目标解释句沿用）。

---

## 1. 引擎契约

### 1.1 输入

```text
build_midline_levels(
  current: float,
  weekly_bars: list[Bar],          # 必填主源；建议 ≥ 40～80 根（与 data_provider 周线一致）
  chanlun_midline: dict,           # 已算好的周线缠结果（含 bi/segments/zones）
  wyckoff_midline: dict | None,    # 可选：spring/upthrust 价作旁证
  ma_weekly: dict | None,          # 可选：周 MA20/MA60；无则引擎内用 weekly_bars 现算
) -> MidlineLevels
```

**禁止主路径输入：** 日线 `key_levels`、日线 `stop`、`find_key_levels(daily_bars)`。

**允许仅出现在「显式降级分支」：** 且必须 `source` 含 `degraded_*`，默认 **P0 不启用日线 key_levels 回填**（见 §1.4 待 Review 确认）。

### 1.2 输出（兼容现 `mid_key_prices` 字段）

```python
{
  "life_line": float | None,
  "pullback_low": float | None,
  "pullback_high": float | None,
  "resist": float | None,
  "target": float | None,
  "current": float | None,
  "merge_resist_target": bool,
  "line_life": str,
  "line_pullback": str,
  "line_resist": str,
  "line_target": str,
  "notes": str,           # 必含 source=...
  "engine": "weekly_v1",
  "quality": "full" | "partial" | "insufficient",
  "components": {         # 调试/单测：各价从哪来
    "life_line": "seg_low" | "last_down_bi_end" | "zone_low" | "weekly_swing" | ...,
    ...
  },
}
```

展示句式**不变**（B2A 无 🌟）：

- `生命线 X（破则中线转弱）`  
- `回踩区 A-B（到了才谈低吸）`  
- `压力 X（靠近只减不加）` / `压力/目标` 合并  
- `目标 X（波段上看）`  

### 1.3 主算法（Weekly Structure Engine v1）

**以 §9 预审冻结补丁为准**（下列与 §9 冲突时以 §9 为准）。摘要：

#### 字段对齐（强制）

- `chan = unwrap_chan(chanlun_midline)`  
- 笔 = **`strokes`**（禁止 `bi`）  
- 段 = `segments[]`：`direction` / `high` / `low` / …  
- 中枢 life 用 **`zh_bottom`**（禁止 `last_valid_zone_*` 当 zone 下沿——其为 center）  
- **仅** `timeframe == "weekly"` 才用笔/段/zone；否则只周摆动（`daily_fallback` 不得进价）

#### A. 生命线（命中即停；候选仅 `price>0`，**无**现价上界过滤）

1. 最近 `direction=="up"` 的 segment 的 **`low`**  
2. 最近 `direction=="down"` 的 stroke 的 **`end_price`**  
3. 自尾向前第一个 valid zone 的 **`zh_bottom`**  
4. 周线近 20 根 2-touch 摆动低  
5. None → 省略  

`current < life` → notes 加 `already_below_life`。  
**废除 B4A 日线链主路径。**

#### B. 回踩区

- low = 最近 down stroke `end_price`；否则近 12 周摆动低  
- high = max(low, 周 MA20 或 5 周收盘均)  
- **强制** `pullback_low = max(pullback_low, life_line)`（life 非空）  

#### C/D. 压力 / 目标（P0 **无 fib**）

- resist：最近 up stroke end 或 up seg high；否则 20 周摆动高  
- target：最近 up seg high；否则 40 周摆动高；同价合并展示  
- **禁止**日线 fib  

#### E. 旁证

- 威科夫价 **P0 不兜底** 改写 life/resist  

### 1.4 降级策略（强制显式）

| 条件 | 行为 |
|------|------|
| `len(weekly_bars) < MIN_WEEKLY`（**26**） | `quality=insufficient`；四价尽量 None；不填日线 |
| 有周线但 timeframe≠weekly 或无笔段 | 仅周摆动；`partial`；`source=weekly_swing_only` |
| 周线缺失 | 不静默日 K；`weekly_missing`；报告「数据不足」 |
| `MIDLINE_PRICE_DAILY_FALLBACK=true`（**默认 false**） | 旧 B4A 日链；`source=degraded_daily_key_levels` |

### 1.5 与短线硬隔离

```text
日线 bars ──→ structure_core / key_prices ──→ ⚡ 短线关键价
周线 bars ──→ midline price engine ──────────→ 🧭 中线关键价
                ↑
         chanlun_midline (周笔/段，已并行计算)
```

单测铁律：

- mock 日线 `key_levels` 与周线摆动 **故意相反** → 渲染中线价必须等于周线引擎，**不得**出现日线 mid_support 数值。  

---

## 2. 模块与文件

| 优先级 | 文件 | 动作 |
|--------|------|------|
| P0 | `trader_shared/midline_structure.py` **新建** | 周线摆动 + 从 chan 笔/段提取 life/pullback/resist/target |
| P0 | `trader_shared/mid_key_prices.py` | 改为薄封装：调用引擎 + 拼 line_* 句式；删除日 K 主路径 |
| P0 | `run_analysis.py` | `build_mid_key_prices(..., weekly_bars=..., chanlun_midline=..., wyckoff_midline=...)`；传入 snapshot 周线 |
| P0 | `tests/test_midline_structure.py` **新建** | 笔/段/摆动/不足/隔离 |
| P0 | `tests/test_mid_key_prices.py` | 改为断言 weekly 源；删除「仅 daily key_levels」主用例或标 degraded |
| P0 | `tests/test_report_mid_short_sources.py` | 日周价交叉 mock |
| P1 | `weekly_frame`（完好\|紧张\|破坏） | 可与 life 失守联动看法（已有 B1A 槽位） |
| P1 | 报告 `notes` 用户可见一行「价源：周线结构」 | 可选，免误解 |
| P2 | 月线远端目标 | — |

**可复用：** `find_key_levels` 的「窗口+触及」思想 → 抽 `find_swing_levels(bars, short_n, mid_n, long_n)` 参数化，**调用时 bars=weekly**。禁止 `find_key_levels(daily)` 写入 mid 成功路径。

---

## 3. 接线（run_analysis）

```text
# 已有
f_chan_mid = chanlun_strategy_midline(weekly...)
f_wyk_mid  = wyckoff_strategy_midline(weekly...)

# 改为
mid_key_prices = build_mid_key_prices(
    current=current,
    weekly_bars=weekly_bars,
    chanlun_midline=chan_mid_result,
    wyckoff_midline=wyck_mid_body,  # 可选旁证
    # 删除 key_levels=daily, stop=daily 主参
)
```

性能：不新增网络请求；周线已在 snapshot。引擎应为 O(周线根数 + 笔数)，可忽略。

---

## 4. 验收（Reviewer R 表）

| ID | 要求 | 验证 |
|----|------|------|
| E1 | 成功路径 `notes`/`engine` 含 weekly，不含 `daily_key_levels_proxy` | 单测 + 真票 |
| E2 | 日线 key_levels 与周线结果刻意相反时，中线价 = 周线 | 交叉 mock |
| E3 | `life_line` 的 components ∈ 闭枚举，且能从 fixture 反算到同一 float（2 位） | components 断言 |
| E4 | 周线不足 → insufficient，不填日线 mid_support | 单测 |
| E5 | 短线 key_prices 数值/逻辑不被本改动破坏 | test_key_prices 回归 |
| E6 | 展示句式与 🧭 块不变（无 🌟、有解释半句） | render 测 |
| E7 | 出手仍不由中线 target 单独放行 | 结论测 |
| E8 | 南网/华工：不锁旧样例价；锁 engine/source/components 与逻辑 | 真票 |
| E9 | 默认 fallback 关时传入 daily key_levels **必须被忽略**；成功 source 不含 daily | 单测 |

---

## 5. 双 Agent 切片

### Implementer

| 切片 | 内容 |
|------|------|
| M1 | `find_swing_levels(bars, ...)` 或 `midline_structure` 周摆动 + 单测 |
| M2 | 从 `chanlun_midline` 抽 strokes/segments/zones（仅 weekly）→ life/resist/pullback |
| M3 | `build_mid_key_prices` 切主路径到周引擎；降级策略 |
| M4 | `run_analysis` 传 weekly_bars + mid 结果 |
| M5 | 报告源隔离测 + 南网/华工目视 |

### Reviewer

- 唯一真理：本文档  
- 产出：`docs/audit/midline-price-engine-review.md`  
- 发现「成功路径仍读 daily key_levels」→ **直接 FAIL**

### Prompt 摘要

**Implementer：** 按 `docs/midline-price-engine-plan.md` M1–M5；禁止日 K key_levels 作 mid 成功路径。  

**Reviewer：** 只读；勾 E1–E9；写 audit。  

---

## 6. 风险

| 风险 | 缓解 |
|------|------|
| 周线笔少，life 跳动 | quality=partial；优先段 low；单测固定 fixture |
| 中线价与短线止损距离 senseless | 允许；标签分离；不强制 life < stop |
| 与旧南网样例数字变化 | 文档声明「数字可变，源不可回退」；验收改看源与逻辑 |
| 重复实现 find_key_levels | 参数化复用，禁止 copy-paste 后改常量 |

---

## 7. 与已冻结双轨文档关系

- `mid-short-dual-track-plan.md` 的 **B3C/B1A/B2A 展示与看法** 继续有效。  
- **B4A 日线生命线回退链主路径废止**；仅 `MIDLINE_PRICE_DAILY_FALLBACK=true` 的 degraded 遗留。  
- **价位验收：本文档（含 §9）优先于双轨文档 B4A / §2.2 日 K 表。**  
- 本计划是双轨的 **价位闭环**；做完后「理论 + 看法 + 价位」才算完整双引擎。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-10 | 初版：用户要求中线价必须独立引擎；待 Reviewer 预审 |
| 2026-07-10 | Reviewer 预审 SPEC_NEEDS_CLARIFICATION；用户 **B-1～B-8 全 A** → 冻结 §9 |

---

## 9. 预审冻结补丁（2026-07-10 · 用户全 A）

### 9.0 决策台账

| 编号 | 冻结口径（全 A） |
|------|------------------|
| B-1 | 只认 `strokes`/`segments`/`zones` + `unwrap_chan`；禁止文档/代码主路径写 `bi` |
| B-2 | life zone 用 **`zh_bottom`** |
| B-3 | 仅 `timeframe=="weekly"` 用笔段；否则 `weekly_swing_only` |
| B-4 | **不做** `≤ current*1.02` 过滤 |
| B-5 | **强制** 回踩下沿夹到 `life_line` |
| B-6 | 常量全表写死（§9.2） |
| B-7 | P0 **无 fib**；target=段高/40 周摆动高 |
| B-8 | 本计划价位真理优先于双轨 B4A |

### 9.1 字段对齐（强制）

- 入口：`chan = unwrap_chan(chanlun_midline)`。  
- 笔序列字段名：**`strokes`**。  
- 线段：`segments[]` 使用 `direction` / `high` / `low` / `start_price` / `end_price`。  
- 中枢：仅 `zones[i].valid` 且 **`zh_bottom` / `zh_top`**；**禁止**把 `last_valid_zone_first_price`（实为 zh_center）当 zone 下沿。  
- 仅当 `chan.get("timeframe") == "weekly"` 时，才允许用 strokes/segments/zones 填价；否则忽略笔段，走周线摆动，`source=weekly_swing_only`，`quality=partial`。  
  （`daily_fallback` 的 mid 缠结果**不得**进入价位主路径。）

### 9.2 常量冻结

| 常量 | 值 |
|------|-----|
| MIN_WEEKLY | 26 |
| SWING_N_LIFE / RESIST | 20 |
| SWING_N_PULLBACK | 12 |
| SWING_N_TARGET | 40 |
| MA_WEEKLY | 20（不足则 5 周收盘均，partial） |
| TOUCH_TOL_PCT | 0.015 |
| UNBROKEN_PCT | 0.03 |
| SWING_HALF_WINDOW | 3 |
| MIDLINE_PRICE_DAILY_FALLBACK | 默认 **false** |

引擎不扩拉周线；用 provider 已有 `weekly_bars`（约 80 根）。

### 9.3 生命线优先级（命中即停；候选仅要求 price>0）

1. 最近 `segments` 中 `direction=="up"` 的 `low`  
2. 最近 `strokes` 中 `direction=="down"` 的 `end_price`  
3. 自尾向前第一个 `valid` zone 的 `zh_bottom`  
4. 周线近 20 根 2-touch 摆动低（思想同 find_key_levels，**bars=weekly**）  
5. None → 省略 `line_life`  

不做 `≤ current*1.02` 过滤。`current < life_line` 时 notes 追加 `already_below_life`。  
废除 B4A 日线链作主路径。

### 9.4 回踩区

- low = 最近 down stroke `end_price`；若无，则近 12 周摆动低（或近 12 周 min low）  
- high = max(low, 周 MA20 或 5 周收盘均)  
- **强制** low = max(low, life_line)（life 非空时）；必要时 high 上抬到 low  
- \|high-low\|<1e-9 → `回踩区 X（到了才谈低吸）`

### 9.5 压力 / 目标（P0 无 fib）

- resist：最近 up stroke `end_price` 或 最近 up seg `high`；否则 20 周 2-touch 高  
- target：最近 up seg `high`（若与 resist 同价则合并展示）；否则 40 周摆动高  
- **禁止**读取日线 fib_retrace / structure_core fib  
- 同价合并逻辑保持现 mid_key_prices 展示

### 9.6 quality

- **insufficient**：`len(weekly_bars) < 26` 或 weekly 缺失 → 四价尽量 None，notes 含 `weekly_missing` 或 `weekly_too_short`，**不**填日线  
- **partial**：仅 swing 或 timeframe≠weekly 笔段被丢弃  
- **full**：至少 life 或 resist 的 components 属于 `{seg_low, last_down_stroke_end, zone_zh_bottom, last_up_stroke_end, seg_high}` 等笔段/zone 源（非纯 swing）

### 9.7 components 闭枚举

`seg_low | last_down_stroke_end | zone_zh_bottom | weekly_swing_n20 | weekly_ma20 | weekly_close_mean5 | last_up_stroke_end | seg_high | weekly_swing_n20_high | weekly_swing_n40_high | none`

### 9.8 notes / engine

- 成功：`engine=weekly_v1` + `source=weekly_structure` 或 `weekly_swing_only`  
- 禁止成功路径出现 `daily_key_levels_proxy`  
- degraded：`source=degraded_daily_key_levels`（仅开关开）

### 9.9 API

- `build_mid_key_prices` / `build_midline_levels` 主参：`current, weekly_bars, chanlun_midline, wyckoff_midline?`  
- 旧参 `key_levels/stop/stop_losses`：**默认忽略**；仅 degraded 开关开时使用  
- `**_extra` 不得静默启用日链  

### 9.10 Implementer 红线

1. 成功路径禁止日线 key_levels / find_key_levels(daily) / stop / stage_based 填四价  
2. 只认真周线笔段（timeframe==weekly）  
3. strokes 不是 bi；zone life 用 zh_bottom  
4. 短线零耦合；中线价不放行出手  
5. 常量与优先级按 §9.2–9.5 写死可测；E2 交叉 mock 必须过  

### 9.11 验收真票

不锁旧日代理价（如 46.88）；锁 `engine` / `source` / `components` 与「不得等于刻意 mock 的日线 mid_support」。
