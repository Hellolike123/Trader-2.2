# 威科夫 Phase A 区间边界（SC/AR）— Agent Handoff

**状态注（2026-08-07）**：短线威科夫与事件灯已并入同一 `威科夫：` 行，尾注「不作买点」；**不再**独立 `事件：` 行。实现以 `short_midline` + `output-template` 为准。

**状态注（2026-08-07）**：短线威科夫与事件灯已并入同一 `威科夫：` 行，尾注「不作买点」；**不再**独立 `事件：` 行。实现以 `short_midline` + `output-template` 为准。


> **status**: impl_done（种子史；非 SC 窗 SSOT）  
> **日期**: 2026-07-31（修订 2026-08-01 / 勘误 2026-08-02）  
> **产品法源**: `BUSINESS.md` §2.0 / §2.2（中线状态 = **仅周线威科夫**；短线日线威科夫只对照）  
> **目标**: 按 Wyckoff Analytics 原典，用 **SC 低点 + AR 高点**（理想再加 ST 测 SC）钉 Phase A / TR 种子边界；固定 15 根只作搜索/超时，**不定义周期**  
> **后续门禁**: `established`（SC+AR）≠ 可写成熟「箱体」/可量度 → 见 `docs/plans/wyckoff-tr-maturity-l0l3-handoff.md`  
> **读者**: 追溯种子史；**现行 SC 窗 / 钉住 / 破位只读 structure-anchor**

> **⚠️ 勘误 / 已被取代（2026-08-02）— 加粗必读**  
> **禁止按正文旧 `CLIMAX=15` 当 SC 窗。现行 SC 搜索宇宙 / 结构钉住 / 破位收口只读 [`wyckoff-structure-anchor-handoff.md`](./wyckoff-structure-anchor-handoff.md)。**  
> 本文凡写「`WYCKOFF_CLIMAX_ANCHOR_BARS=15` = SC/AR 共用锚点扫描上限 / SC 唯一搜索窗」之处，**仅作 P1/P2 历史**；  
> 新方案：未失效 Phase A 钉住 `[sc_bar_idx, 今]`；冷启动日 90 / 周 39；`CLIMAX=15` 仅 AR 等待默认种子与非 SC 短窗兼容别名。  
> **勿按本文 §3.2 / §3.3「扫描窗=CLIMAX」实现新代码。** 下文正文不删，供追溯。

---

## 短线「威科夫：」（展示合同，2026-07-31）

| 项 | 合同 |
|----|------|
| 用途 | **只给人看**；与中线同构算法（日线 K），分开展示 |
| 标签 | 短线 `威科夫：`（与中线点名同构；**禁止**「日线阶段：」；正文带「仅对照」）；事件另起 `事件：` |
| 无箱体 | 与中线同构：诚实「无 · 无清晰区间 · 暂定不出 · 仅对照」；L1/forming 写雏形或「箱体未成形」；**仅 L2/L3** 写「箱体 lo-hi」（SC+AR 无 ST 不得写成熟箱体） |
| 禁止 | 进共振背景岗 / fusion / 中线定论 / 单独开仓；面板写「日线阶段：」 |
| 实现 | `format_wyckoff_daily_phase_light` / `format_daily_phase_display` + `short_midline` 在「缠论：」后、「事件：」前 |
| 中线箱体 | 中线 `format_wyckoff_midline_light` **也**展示同款箱体价（结构「阶段 · [箱体] · 事件 · 含义」；共用 `_phase_a_box_phrase`） |

---

## 0. 给 Agent 的 30 秒摘要

1. 原典完整表述：**「lows of SC and ST + high of AR set TR」**（Phase A 停止行为钉区间上下沿）。  
2. **P1（本迭代）**：透出 `sc_low` / `ar_high`（及可选 `phase_a_range` 状态）；SC 与 AR **共用同一 SC 锚点扫描**；`forming` = 仅有 SC；`established` = SC+AR（无 AR 不得假 established）；AR 放量 1.2× 标为 **soft**，文档/后续可降级。  
3. **P2（已完成）**：种子箱挂 `phase_tr_gated`（forming / 无 established 叠加 P0-B）；广义 ST（测 SC）独立 `_detect_secondary_test_sc`。  
4. **禁止**：日线威科夫进中线定论 / fusion；用固定 N 日窗**定义** TR 周期；无 AR 仍输出 established。  
5. 日线威科夫：短线「威科夫：」对照 +「事件：」灯（`format_wyckoff_event_light`），与中线无关、不进 fusion。

---

## 1. P1 后现状（2026-07-31）

| 点 | 现状 | 锚点 |
|----|------|------|
| SC 检测 | `_find_sc_anchor` SSOT；`_detect_selling_climax` 委托 anchor | `wyckoff_events._find_sc_anchor` |
| AR 检测 | 同一 anchor；SC 后 1–`anchor//2` 根反弹；`ar_high`=反弹棒 high | `wyckoff_events._detect_ar` |
| SC 价字段 | `sc_low` / `sc_price` 同值（SC K 最低价） | 同上 |
| AR 价字段 | `ar_high` 边界价；`ar_price` 保留 close 供旧消费 | 同上 |
| Phase A 边界 | `phase_a_range` + 顶栏 `phase_a_status`；`forming`/`established`/`none` | `wyckoff_core._build_phase_a_range` |
| TR 边界 | 分位带 `tr_upper`/`tr_lower` **并存**；established 前不得借假 TR 抬 B/C/D（**P2-A 已落地**） | `_detect_trading_range` |
| 阶段文案 | SC+AR →「停止：SC+AR」；仅 SC →「卖力高潮：SC，箱体未成形」（须过 P0-B TR 门控才赋 accumulation_a） | `wyckoff_phase._detect_phase` |
| AR 量能 | P2-C：prefer 弱于 SC；`ar_volume_soft=True`=量能偏强/非原典弱量；REQUIRE 默认关 | `_detect_ar` |
| 常量 | `WYCKOFF_CLIMAX_ANCHOR_BARS=15`；SC/AR/阶段扫描共用 | `config.py` |
| 日线事件灯 | AR 文案「钉潜在上沿，仅反弹不能当反转」；**不参与**中线阶段 | `format_wyckoff_event_light` |

**P1 已解（原 §6）**：SC/AR 锚点窗一致；`ar_high` 透出；无 AR 不假 `established`；AR 量能标 soft。  
**P2 已落地**：分位 TR 与 `phase_a_range` 种子箱门控（§4.3）；广义 ST `_detect_secondary_test_sc`（§4.4）；`wyckoff_view` 可选「箱体未成形」/ gate_reason 摘要。  

---

## 2. 原典对齐（产品定义）

| 概念 | 原典 | 本仓 P1 落点 |
|------|------|--------------|
| Phase A 下沿 | SC（及理想 ST）**低点** | `sc_low` ← `sc_price`（SC low） |
| Phase A 上沿 | AR **高点** | `ar_high`（新字段；取自 AR 反弹棒 high，非 close） |
| 搜索窗 | 小周期按**箱体/事件**，非固定 N 日周期 | `WYCKOFF_CLIMAX_ANCHOR_BARS=15`：**仅** SC/AR 锚点搜索上限与超时 |
| forming | 识别到 SC，TR 种子未钉全 | `phase_a_range.status=forming`（有 `sc_low`，无 `ar_high`） |
| established | SC + AR（+ 理想 ST 测 SC） | `phase_a_range.status=established`（**必须**有 `ar_high`） |
| AR 量能 | 原典偏「弱于 SC / 供应耗尽后反弹」 | 现码 `volume > sc_avg_vol * 1.2` = **工程 hard**；P1 保留计分，**文档 + 字段**标 `ar_volume_soft=True`，后续可改 soft |
| ST（广义） | SC/AR 后二次测试 SC 低点 | **P1 不做**；P1.5/P2 独立 `_detect_secondary_test_sc`（勿与 Spring Test 混） |

完整原典句：**「The lows of the SC and ST and the high of the AR set the boundaries of the TR.」**  
P1 先 SC+AR 两钉；ST 钉下沿为 P1.5/P2。

---

## 3. P1 — 字段合同与检测对齐（本迭代必做）

### 3.1 新增 / 规范化字段（`wyckoff_analysis` 或 `tr_ctx` 子对象）

建议结构（名可微调，语义不可变）：

```text
phase_a_range: {
  sc_low: float | None,          # SC 棒最低价（与 sc_price 同源）
  ar_high: float | None,         # AR 反弹棒最高价
  sc_bar_idx: int | None,        # 可选，调试/链排序
  ar_bar_idx: int | None,
  status: "none" | "forming" | "established",
  anchor_bars: int,              # = WYCKOFF_CLIMAX_ANCHOR_BARS
}
```

兼容：

- 保留 `sc_price` / `ar_price` / `sc_signal` / `ar_signal` 一发布周期。  
- `sc_low` 与 `sc_price` **同值**（或 sc_low 为 SSOT，sc_price alias）。  
- `ar_high` 新；`ar_price` 可保留 close 供旧消费，文档注明「边界用 ar_high」。

### 3.2 常量（`config.py`）

```text
WYCKOFF_CLIMAX_ANCHOR_BARS = 15   # SC/AR 共用锚点扫描上限（搜索/超时，非 TR 周期定义）
```

`_detect_selling_climax`、`_detect_ar`、阶段机 `_scan_last_event(..., window=...)` **统一读此常量**（AR 现 18 可收敛为 15 或 anchor+3，须单测说明）。

### 3.3 检测器改造（最小 diff 思路）

1. **抽取** `_find_sc_anchor(bars, tr_ctx) -> (idx, sc_low, sc_close, sc_avg_vol) | None`  
   - 条件与现 `_detect_ar` 内 SC 块一致（或与 `_detect_selling_climax` 对齐后二选一 SSOT）。  
   - 扫描窗 = `WYCKOFF_CLIMAX_ANCHOR_BARS`。  
2. `_detect_selling_climax`：调用 `_find_sc_anchor`，返回 `sc_signal` + `sc_price=sc_low`。  
3. `_detect_ar`：同一 anchor；SC 后 1–3 根（或 configurable）找反弹；`ar_high = rally_bar.high`；`ar_signal` 条件保留，量能门控标 soft。  
4. **`wyckoff_core.wyckoff_analysis`**：组装 `phase_a_range`；`status` 规则见 §3.4。  
5. **`_detect_phase`**（可选 P1 小改）：  
   - `established` 才允许 SC+AR 标签为「停止：SC+AR」并参与 `acc_b_ctx` 的 **边界语义**（信号 bool 可仍亮）。  
   - 仅 SC（forming）→ 积累 A 文案区分「卖力高潮：SC（箱体未成形）」；**禁止**文案/View 写「TR 已建立」。  
6. **不改** fusion / 日线中线 fallback / `format_wyckoff_event_light` 主路径（仍日线灯）。

### 3.4 status 规则

| 条件 | `phase_a_range.status` |
|------|-------------------------|
| 无 SC | `none` |
| 有 SC，无 AR | `forming` |
| 有 SC + AR（`ar_high` 有效） | `established` |
| 有 SC，AR 扫描超时（anchor 内无有效 AR） | `forming`（`ar_high=None`） |

**硬规则**：无 `ar_high` → **不得** `established`；不得用分位 TR 冒充 Phase A established。

### 3.5 验收用例（必须有测）

| ID | 用例 | 期望 |
|----|------|------|
| R1 | **南网类**：瀑布 SC 后 ~1 周才 AR（fixture 或 recorded bars） | 15 根 anchor 内 SC+AR 均亮；`sc_low`/`ar_high` 与手工读高低一致 |
| R2 | SC 与 AR **锚点一致** | 同一次 `_find_sc_anchor`；`sc_signal` 真时 AR 用的 `sc_bar_idx` 与 SC 检测相同 |
| R3 | 仅 SC、无 AR | `status=forming`；**非** `established`；阶段不得写「停止：SC+AR」 |
| R4 | SC+AR 均有效 | `status=established`；`sc_low < ar_high`；`phase_a_range` 透出 |
| R5 | `_detect_selling_climax` 与 `_detect_ar` 对同一 SC 不打架 | 同一 fixture 下 SC 窗一致（修 R1 回归） |
| R6 | 周线 `wyckoff_strategy_midline` | `phase_a_range` 仅在 weekly 路径；日线 analysis 可有事件灯但无中线 `established` 定论 |

测试文件：扩 `tests/test_wyckoff_*.py`；南网 fixture 可放 `tests/fixtures/wyckoff/`（禁全网抓数）。

### 3.6 实现顺序与白名单

```text
1) config：WYCKOFF_CLIMAX_ANCHOR_BARS
2) wyckoff_events：_find_sc_anchor；对齐 _detect_selling_climax / _detect_ar
3) wyckoff_core：phase_a_range 组装
4) wyckoff_phase：forming/established 文案与 acc_b_ctx 边界语义（最小）
5) wyckoff_view：summary 可选反映「箱体未成形」（微信红线）
6) tests
```

**可改**：`config.py`、`wyckoff_events.py`、`wyckoff_core.py`、`wyckoff_phase.py`、`wyckoff_view.py`、相关 tests。  
**勿改**：`fusion_core`、中线改回日线、Spring Test/ST 语义（见 accuracy handoff）。

自测：

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest 02-共享模块-shared/tests/test_wyckoff_*.py -q
```

---

## 4. P2 — 种子箱 × 阶段门控 + 广义 ST（本迭代）

> 依赖 P1 字段（`phase_a_range` / `phase_a_status`）；**勿在 P1 分支塞满 P2 逻辑**。  
> P0-B（`WYCKOFF_PHASE_MIN_TR_QUALITY` + `phase_tr_gated`）已落地；P2 **叠加**种子箱语义，不替换 P0-B。

### 4.1 产品定义

| 子项 | 原典 / 产品意图 | P2 落点 |
|------|-----------------|---------|
| **P2-A 种子箱门控** | 「SC low + AR high（+ ST low）set TR」— 无 AR 不得假 established；分位 TR 不得冒充种子抬阶段 | `phase_a_status` + `phase_tr_gated` 叠加；forming / 无 established 时事件可亮、**禁止**抬 B/C/D / 派发 / markup/markdown |
| **P2-B 广义 ST** | SC(+AR) 后二次缩量回测 SC 区；**非** Spring 后 Test | 新检测器 `_detect_secondary_test_sc`；字段 `secondary_test_sc_*`；与 `spring_test_*` / `st_*` **分离** |
| **P2-C AR 量能 soft**（✅ 已落地） | 原典偏「弱于 SC / 供应耗尽后反弹」 | `WYCKOFF_AR_PREFER_WEAK_VS_SC` 默认 True；`REQUIRE` 默认 False；`WEAK_VS_SC_RATIO`≈1.0；`ar_volume_soft`=量能偏强/非原典弱量 |

**forming 时阶段文案（二选一，本合同选定）**：

| 方案 | 行为 | 结论 |
|------|------|------|
| A | `phase=accumulation_a`，文案「卖力高潮：SC，箱体未成形」 | ✅ **选用** |
| B | `phase=none` + `phase_tr_gated=True`，gate_reason=`forming_phase_a` | ❌ 不选 |

**选用 A 的理由**：SC 是原典 Phase A 停止行为，P1 已诚实透出；P2 要禁的是**借假 TR 抬 B/C/D**，不是抹掉 SC 语义；若改 B 会与 P0-B「无 TR → none」混淆，且 View/链排序丢失「有 SC 待 AR」可读性。

### 4.2 新增 / 扩展字段

**P2-A（门控 + 种子 TR 叠加）** — 写入 `wyckoff_analysis` / 传入 `_detect_phase` 的 `tr_ctx` overlay：

```text
phase_tr_gated: bool              # P0-B 已有；P2 扩展触发条件
phase_tr_gate_reason: str         # 枚举见 §4.3.3
phase_a_status: str               # P1 已有：none | forming | established
tr_seed_source: str | None        # 新增调试： "percentile" | "phase_a_seed" | None
tr_upper / tr_lower               # established 时优先种子边界（§4.3.4）
```

**P2-B（广义 ST）** — 新前缀，**禁止**复用 `st_*` 作 Phase A ST 主字段：

```text
secondary_test_sc_signal: bool
secondary_test_sc_reason: str
secondary_test_sc_price: float | None    # 测试棒 close 或代表价
secondary_test_sc_low: float | None      # 测试棒 low；可 refine 种子/TR 下沿
secondary_test_sc_bar_idx: int | None    # 可选，调试
```

兼容：`st_*` / `spring_test_*` **保持** Spring 后确认语义（P0-A 已双写）；链展示 ST 槽位仍指 Spring Test，**不**把广义 ST 塞进 `_CHAIN_DISPLAY["ST"]`。

### 4.3 P2-A — 种子箱门控

#### 4.3.1 门控总表（事件可亮 vs 阶段可抬）

| `phase_a_status` | 分位 TR | 事件灯（SC/AR/Spring…） | 允许阶段 | 禁止阶段 |
|------------------|---------|-------------------------|----------|----------|
| `none` | 任意 | 可亮 | 依 P0-B + 现逻辑 | — |
| `forming` | 任意（含高质量分位 TR） | **可亮** | **`accumulation_a`（箱体未成形）仅此** | `accumulation_b/c/d`、`distribution_*`、`markup`、`markdown` |
| `forming` | 无 / 低质量 | 可亮 | 同上或 P0-B 早退 `none`（取更严） | 同上 + P0-B 禁止项 |
| 非 `established` | 仅有分位 TR（`tr_quality ≥ MIN`） | 可亮 | 最高 `accumulation_a`（若 SC）或 P0-B 允许的 `none` | **不得**因分位 TR alone 进 B/C/D / 派发 / markup/markdown |
| `established` | 分位 TR 并存 | 可亮 | 正常阶段机（P0-B 通过后） | — |

**硬规则**：

1. `forming` → **禁止**抬升 `accumulation_b/c/d`、`distribution_*`、`markup`、`markdown`（compression / Spring / SOS 等事件仍可亮）。  
2. 仅有分位 TR、**无** `phase_a_status=established` → **不得**因「看起来像区间」抬 B/C/D（与 P0-B 叠加，见 §4.3.3）。  
3. `established` → 种子边界参与 `tr_ctx`（§4.3.4），阶段机可读 SC+AR 停止背景进 B。  
4. **禁止**用分位 `tr_upper`/`tr_lower` 单独把 `phase_a_range.status` 标成 `established`。

#### 4.3.2 `_detect_phase` 改造（最小 diff）

1. **入参**：除 `tr_ctx` 外，传入 `phase_a_range`（或 `signals` 内 `phase_a_status`）。建议在 `wyckoff_core.wyckoff_analysis` 组装 `phase_a_range` **后**调 `_detect_phase(..., phase_a_range=phase_a_range)`。  
2. **早退顺序**（先严后宽）：  
   - P0-B：`no_tr` / `low_quality` → 现有 gated 早退（保留）。  
   - P2-A：`forming` → 允许落到 §4.3.1 允许的 `accumulation_a` 分支；**在** B/C/D / markup / markdown / distribution 分支前 **短路**（或统一后置 clamp：`forming` 时 phase 最高 `accumulation_a`）。  
   - P2-A：`phase_a_status != established` 且试图进 B/C/D（含 compression→B、Spring→C/D、SOS→D、markup 等）→ gated，`gate_reason=no_established_seed`。  
3. **forming + SC**：保留现文案「积累期 A（卖力高潮：SC，箱体未成形）」；`phase_tr_gated=False`（forming 本身不是 gate，而是阶段上限）。  
4. **SC+AR + established**：保留「停止：SC+AR」→ `accumulation_a`；并可作为 `acc_b_ctx` 边界语义（P1 已部分落地）。

#### 4.3.3 `phase_tr_gate_reason` 枚举（P0-B + P2-A 叠加）

| 值 | 含义 | 来源 |
|----|------|------|
| `no_tr` | 无 `tr_ctx` / 无 `tr_quality` | P0-B |
| `low_quality` | `tr_quality < WYCKOFF_PHASE_MIN_TR_QUALITY` | P0-B |
| `forming_phase_a` | 有 SC、无 AR；阶段被 clamp 到 A（可选透出，**非** forming 默认 reason） | P2-A |
| `no_established_seed` | 有分位 TR 但 Phase A 未 established；禁止借假 TR 抬 B/C/D+ | P2-A |

**叠加规则**：

- 多条件同时满足时，`gate_reason` 取 **优先级最高** 一项（实现简单：字符串优先级 `no_tr` > `low_quality` > `no_established_seed` > `forming_phase_a` > `""`）。  
- `phase_tr_gated=True` 当且仅当阶段输出被门控为 `none` 或「不参与定论」类（P0-B 早退 **或** P2-A 因无 established 拒绝抬升 **且** 最终 phase 不为允许的 `accumulation_a`）。  
- **forming 且仅 accumulation_a**：`phase_tr_gated=False`；若因 B+ 被 clamp 到 A 则 `phase_tr_gated=True`、`gate_reason=forming_phase_a`（可选透出）。  

#### 4.3.4 established → 种子 `tr_ctx` 优先级

当 `phase_a_range.status == established` 且 `sc_low` / `ar_high` 有效：

```text
tr_lower_seed = secondary_test_sc_low if (P2-B 检出) else sc_low
tr_upper_seed = ar_high
```

**overlay 规则**（`wyckoff_core` 组装传给检测器 / 阶段机的 `tr_ctx`）：

| 字段 | established | forming / none |
|------|-------------|----------------|
| `tr_lower` | `min(tr_lower_seed, 分位 tr_lower)` 或 **直接替换**为种子下沿（推荐：**替换**，`tr_seed_source=phase_a_seed`） | 仍用分位 TR（仅展示/事件容器） |
| `tr_upper` | `tr_upper_seed`（AR high）优先于分位上沿 | 分位 TR |
| `tr_quality` | 可 boost：种子钉定后不低于 `MIN`（可选，须单测） | 不变 |
| `cause_effect_*` | 宽度用种子上下沿重算（若 established） | 仍用分位 |

**优先级一句话**：**established 时 TR 边界以 SC/AR（+ 可选 ST low refine）为准**；分位带降级为辅助/质量输入，不得覆盖种子上沿 `ar_high`。

### 4.4 P2-B — 广义 ST（测 SC）

#### 4.4.1 检测器 `_detect_secondary_test_sc(bars, tr_ctx, sc_anchor, ar_anchor?)`

**语义**：SC（+ 理想 AR）之后，价格**缩量**回测 SC 区域（SC low 附近），供应二次测试。

**触发条件（建议，可调常量）**：

1. 有效 SC anchor（同 `_find_sc_anchor` SSOT）；AR 已出现则测试窗从 AR 之后计，否则从 SC 之后计。  
2. 测试窗：SC/AR 后 `3 … WYCKOFF_ST_SC_LOOKBACK` 根（建议默认 15，写入 `config.py`）。  
3. 价格：测试棒 `low` 进入 SC 区（`sc_low ± max(ATR_pct, 固定%)`）。  
4. 量能：测试棒量 `< sc_avg_vol * WYCKOFF_ST_SC_VOL_RATIO`（建议 0.8）或 `< tr_baseline * ratio`。  
5. **不得**要求先出现 Spring（与 `_detect_st` 根本分离）。

**输出**：§4.2 字段；`secondary_test_sc_low = test_bar.low`。

#### 4.4.2 与 Spring Test / `st_*` 分离

| | 广义 ST（P2-B） | Spring Test（P0-A） |
|--|-----------------|---------------------|
| 检测器 | `_detect_secondary_test_sc` | `_detect_st` / `_detect_spring_test` |
| 字段 | `secondary_test_sc_*` | `spring_test_*` + `st_*` 双写 |
| 时序 | SC(+AR) 后测 SC 区 | Spring 后测支撑 |
| 阶段机 | **不**直接进 C/D；仅 refine 下沿 / View 事件 | Spring+Test → accumulation_c/d |
| 链 ST 槽 | **不进**吸筹链 ST 槽（或另开「测SC」展示，非本迭代必须） | 链 ST = Spring 确认 |

**硬规则**：**禁止**把 Spring 确认改名为 ST；**禁止**让 `_detect_st` 兼测 SC（避免 P0-A 回归）。

#### 4.4.3 `st_low` refine 下沿

- 当 `secondary_test_sc_signal` 且 `phase_a_status=established`：`tr_lower` overlay 取 `min(sc_low, secondary_test_sc_low)`（或合同 §4.3.4 的 `tr_lower_seed`）。  
- 更新 `phase_a_range.sc_low` **仅当** refine 更低且同源 SC anchor（可选字段 `sc_low_refined`，避免覆盖原始 SC 棒价）。  
- Spring / SOS / cause_effect 读 overlay 后 `tr_ctx`，与 established 种子一致。

### 4.5 View / 报告（最小）

- `wyckoff_view`：`phase_a_status=forming` → summary 可含「箱体未成形」；`phase_tr_gated` + reason 映射人话（微信红线）。  
- `tr` 子对象：established 时优先展示种子 `sc_low`/`ar_high`（及 refine 下沿），分位带来源标注可选。  
- 日线 `format_wyckoff_event_light`：**不改**主路径；广义 ST 若亮灯用独立文案（非「Spring确认」）。  
- 中线 `format_wyckoff_midline_light` / 短线 `format_wyckoff_daily_phase_light`：共用 `_phase_a_box_phrase` 写出箱体上下沿（`箱体 lo-hi` / `箱体未成形 · 下沿…（上沿未出）`）。

### 4.6 验收用例（必须有测）

| ID | 用例 | 期望 |
|----|------|------|
| P2-R1 | **forming**：SC 无 AR + 高质量分位 TR + Spring 形态 | `spring_signal` 可 True；`phase` **仅** `accumulation_a`（箱体未成形）；**非** b/c/d/markup |
| P2-R2 | **无 established**：`tr_quality=0.6` 分位 TR + SC+AR 信号但 `phase_a_status=forming`（无 ar_high） | `gate_reason` 含 `no_established_seed` 或 phase clamp；**非** accumulation_b/c/d |
| P2-R3 | **established**：SC+AR + 种子 overlay | `phase_a_status=established`；`tr_lower`/`tr_upper` 来自 `sc_low`/`ar_high`（`tr_seed_source=phase_a_seed`）；可进 accumulation_b（若有 B 事件） |
| P2-R4 | P0-B 叠加：forming + `tr_quality=0.2` | P0-B 优先：`phase=none`，`gate_reason=low_quality`（严于 forming 的 A） |
| P2-R5 | **广义 ST**：SC+AR 后缩量回测 SC 区 | `secondary_test_sc_signal=True`；`spring_test_signal`/`st_signal` **不**因此为 True |
| P2-R6 | **refine**：established + secondary_test_sc 更低 | overlay `tr_lower` ≤ `sc_low`；cause_effect 宽度基于种子边界 |
| P2-R7 | 周线 `wyckoff_strategy_midline` | P2 门控与字段仅在 weekly 路径；日线仍无中线 established 定论 |

测试：扩 `tests/test_wyckoff_*.py`；fixture 可复用 `TestPhaseARangeP1._nanwang_like_bars` + 人工 forming/假 TR 条。

### 4.7 实现顺序与白名单

```text
1) config：WYCKOFF_ST_SC_LOOKBACK、WYCKOFF_ST_SC_VOL_RATIO（P2-B）；可选 AR soft flag（P2-C）
2) wyckoff_events：_detect_secondary_test_sc（独立文件段，勿改 _detect_st 语义）
3) wyckoff_core：phase_a_range 后 tr_ctx overlay（established 种子优先）；透传 secondary_test_sc_*
4) wyckoff_phase：P2-A 门控/clamp + gate_reason 枚举扩展；传入 phase_a_range
5) wyckoff_view：forming / gate_reason / 种子 TR 摘要（最小）
6) tests：P2-R1…R7
```

**可改**：`config.py`、`wyckoff_events.py`、`wyckoff_core.py`、`wyckoff_phase.py`、`wyckoff_view.py`、相关 tests。  
**勿改**：`fusion_core`、日线中线 fallback、`_detect_st` / `spring_test_*` 语义、删分位 TR。

自测：

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest 02-共享模块-shared/tests/test_wyckoff_*.py -q
```

### 4.8 P2 非目标（本迭代不做）

| 项 | 说明 |
|----|------|
| 日线进中线 / fusion | 已定稿禁止 |
| 删除 `tr_upper`/`tr_lower` 分位 TR | 并存；established 时种子优先 |
| P&F 因果目标 | **已另开并落地** → `docs/plans/wyckoff-pnf-handoff.md`；RS 仍另开 |
| Spring Test / `st_*` 重命名或合并进广义 ST | 见 `done/wyckoff-phase-accuracy-handoff-2026-07-31.md` |
| 吸筹链 ST 槽改指广义 ST | 链 ST 仍 = Spring 确认 |

---

## 5. 非目标

| 项 | 说明 |
|----|------|
| 日线进中线 / fusion | 已定稿禁止 |
| 用 15 日**定义** TR 宽度 | 15 仅 anchor 搜索 |
| RS（个股 vs 大盘） | 另开；P&F 已落地见 `wyckoff-pnf-handoff.md` |
| Spring Test / `st_*` 重命名 | 见 `done/wyckoff-phase-accuracy-handoff-2026-07-31.md` |
| 删除 `tr_upper`/`tr_lower` 分位 TR | P1 并存；长期可「established 时优先 SC/AR 种子」 |

---

## 6. 与代码现状冲突（P1 后）

| # | 原冲突 | P1 状态 |
|---|--------|---------|
| 1 | SC 5 根 vs AR 15 根 | ✅ `_find_sc_anchor` + `WYCKOFF_CLIMAX_ANCHOR_BARS` |
| 2 | `ar_price`=close | ✅ `ar_high` 边界价；close 保留 alias |
| 3 | 仅 SC 即 accumulation_a / 无 forming | ✅ `phase_a_range.status=forming`；文案「箱体未成形」（须过 TR 门控才赋 A） |
| 4 | 分位 TR ≠ SC/AR | ✅ 并存；P2-A 种子 overlay + forming/no_established 门控 |
| 5 | AR 放量 1.2× hard | ✅ 结构为主 + `ar_volume_soft`；P2-C 已落地（prefer/REQUIRE flag） |
| 6 | AR 后窗 1–7 根 | ⚠️ 现为 1–7 根（`max(3, anchor//2)`）；超长延迟仍 forming |
| 7 | forming 仍可进 accumulation_b/c/d | ✅ P2-A：forming clamp 最高 A；派发/markdown 亦闸 |
| 8 | 无 established 时分位 TR 可抬阶段 | ✅ P2-A：`_detect_phase` 读 `phase_a_status` + `_apply_p2_phase_a_gates` |
| 9 | `st_*` 语义 = Spring Test | ✅ P0-A 已分离；P2-B 广义 ST 独立 `secondary_test_sc_*` |

---

## 7. 代码锚点速查

| 用途 | 符号 |
|------|------|
| SC | `wyckoff_events._detect_selling_climax` |
| AR | `wyckoff_events._detect_ar` |
| 阶段机 | `wyckoff_phase._detect_phase` |
| 日线事件灯 | `wyckoff_core.format_wyckoff_event_light` |
| 短线威科夫只读 | `format_wyckoff_daily_phase_light` / `format_daily_phase_display` |
| 中线威科夫+箱体 | `format_wyckoff_midline_light`（阶段 · [箱体] · 事件 · 含义） |
| 箱体人话片段 | `_phase_a_box_phrase`（中短线共用；旧词「区间未钉」仅兼容） |
| TR 分位 | `wyckoff_events._detect_trading_range` |
| 中线入口 | `wyckoff_strategy_midline`（weekly only） |

---

## 8. 完成定义（DoD）

**P1（已完成）**

- [x] P1 验收表 R1–R6 全绿（`TestPhaseARangeP1` + 193 wyckoff tests pass）  
- [x] `WYCKOFF_CLIMAX_ANCHOR_BARS` 单源；SC/AR 共用 anchor  
- [x] `phase_a_range` 透出；无 AR 不假 established  
- [x] `BUSINESS.md` §2.2 已补 Phase A 边界句  
- [x] `wyckoff-original-concept-inventory.md` AR/TR ⚠️ 已更新（P1 后）  

**P2（已完成）**

- [x] P2 验收表 P2-R1–R7 全绿（P2-R4 补测于检查轮）  
- [x] P2-A：`forming` / 无 `established` 不得抬 B/C/D / 派发 / markup/markdown；`gate_reason` 含 `no_established_seed`  
- [x] P2-A：`established` 时种子 `sc_low`/`ar_high` overlay `tr_ctx`，优先于分位 TR  
- [x] P2-B：`_detect_secondary_test_sc` + `secondary_test_sc_*`；与 `spring_test_*`/`st_*` 分离  
- [x] `BUSINESS.md` §2.2 + inventory ST/TR 行标 P2 完成  
- [x] 不扩大 scope 到删分位 TR / 日线 fusion（P&F 已另开落地）
- [x] P2-C：AR prefer 弱于 SC + `ar_volume_soft` 语义（偏强）+ REQUIRE 默认关（见 config `WYCKOFF_AR_*`） 

---

## 9. 交接检查清单

**P1（已完成）**

- [x] 已读 `BUSINESS.md` §2.0、§2.2  
- [x] 已打开 `_detect_ar` / `_detect_selling_climax` / `_detect_phase` / `format_wyckoff_event_light`  
- [x] 确认 P1 **不**改 fusion / 日线中线  
- [x] 南网类 fixture：`TestPhaseARangeP1._nanwang_like_bars`

**P2（已完成）**

- [x] 已读本文 §4 + P0-B handoff §3  
- [x] 已打开 `_detect_phase`（P0-B 早退 + accumulation 分支）、`_detect_trading_range`、`_build_phase_a_range`  
- [x] 确认 forming 保留 `accumulation_a` 文案，只 clamp B/C/D+  
- [x] 确认 `_detect_st` **不**兼测 SC；新增 `_detect_secondary_test_sc`  
- [x] 跑通 P2-R1…R7 后再标 status=`p2_done`
