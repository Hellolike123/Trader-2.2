# Wyckoff / 缠论 状态语义保真审计 — Agent Handoff

> **status**: active（2026-08-08）
> **任务性质**: 只读「查 Agent」审计，**不改任何代码**
> **范围**: 事件检测器保真度、信号→phase 映射语义、持久化污染、跨周期隔离、真实行情验收
> **禁止**: 改任何 .py；动 fusion / decision_view / 出手 / 池分道；把「仓库已声明取舍」当 bug

---

## 0. 背景与动机

本系统的核心链路：**K线数据 → 事件检测器(BC/Spring/SOS…) → 中枢/段 → 状态机(_detect_phase/_transition_phase) → 报告**。

前序审计（commit `0c58ed6`，2026-08-08）已验证**状态机自洽性**：
- Wyckoff `_PHASE_ORDER` 11 phase 枚举齐全，`_detect_phase` 产出的字面量全部覆盖
- `_transition_phase` 全配对 121 组合不变量成立（同方向只加深 / 反方向允许翻转 / none 保持旧 / force_apply_none 生效）
- `classify_structure` 主状态严格落在 {无结构/单边上涨/单边下跌/盘整/上涨趋势/下跌趋势}
- `build_segments` 不变量成立（3笔成段 / 尾部护栏 / 第二类破坏对称）
- 方向单源：`format_chanlun_theory_line` 复用 `resolve_chanlun_primary`
- formulas.md §3.6/§3.7/§4.3/§9.4/§11A 阈值与代码逐条对齐
- 测试全绿：wyckoff+report 179 passed，缠论 187 passed，门禁 796 passed/4 skipped

**关键认知：自洽 ≠ 正确。** 状态机可以完美自洽（转移规则无矛盾、枚举齐全）但语义全错（该进 D 时进了 C，该判 Spring 时漏判）。前序审计查的是「代码不会自相矛盾」，本 handoff 要查的是「代码判的是不是真相」——即**数据保真度**与**状态语义正确性**。

owner 原话担心：「数据它有没有算对，状态有没有确定好」。

---

## 1. 已查边界（勿重复）

| 维度 | 前序结论 | 是否需复查 |
|------|----------|-----------|
| `_transition_phase` 转移规则不变量 | 121 配对全成立 | 否（已穷举） |
| `_PHASE_ORDER` 枚举齐全 | 11 phase 全覆盖 | 否 |
| `classify_structure` 主状态枚举 | 6 值闭环，无发明 | 否 |
| `build_segments` 结构不变量 | 3笔/护栏/对称全成立 | 否 |
| 方向单源 | theory_line 复用 resolve_primary | 否 |
| formulas.md 阈值-代码对齐 | §3.6/3.7/4.3/9.4/11A 逐条对上 | 否 |
| 渲染层读写契约 SSOT | 70 读 × 161 写，无硬孤儿 | 否 |
| 渲染层死代码 | 7 处疑似（_rr_chase_verdict/key_levels 等） | 已记录，本 handoff 不重复 |

---

## 2. 待查项（7 项查法，按优先级排序）

### 查法 D — 信号→phase 映射语义【优先级最高，成本低】

**目标**：验证 `_detect_phase` 的 20+ 个 if/elif 决定的「信号组合 → phase」映射合不合威科夫原典五阶段叙事（A停止→B建仓→C测试→D确认→E趋势）。

**锚点**：`02-共享模块-shared/trader_shared/wyckoff_phase.py` `_detect_phase` L273-839

**关键映射逐条核对**（法源：威科夫原典 + `wyckoff_phase.py` docstring L282-296）：
- SC+AR → `accumulation_a`（L679-691）— 停止行为
- 压缩+SC/AR 背景 → `accumulation_b`（L669-676）— 建仓区
- Spring（非premature） → `accumulation_c`（L649-658）— 测试
- Spring+Test / Spring+SOS / Spring+LPS / Spring+TrendPullback → `accumulation_d`（L619-648）— 确认
- Spring+SOS+站上TR上沿 / BU → `markup`（L580-593）— 离开积累区
- BC+ARE → `distribution_a`（L765-772）— 派发停止
- ARE无BC → `distribution_b`（L790-797）
- UT+SOW → `distribution_c`（L746-753）
- LPSY+派发背景 → `distribution_d`（L728-735）
- UTAD / UT+SOW+跌破TR下沿 → `markdown`（L595-608）
- premature Spring/UT → `none`（L515-572 孤立性校验）

**方法**：构造信号组合（手工 bars 或 mock signals dict + tr_ctx），断言 `_detect_phase` 输出的 phase 符合上表。现有 `test_wyckoff_phase_transition.py` 只测转移规则，**缺这类映射测**——这是状态机层最大的语义漏洞。

**重点验证的边界**：
- `_dist_cluster`（L614）派发确认后反向 SOS 不翻案 — 簇标志兜底是否真生效
- `spring_premature`（L518-538）— Spring 无 Phase B 背景时是否真落到 none 而非 C
- `phase_a_status="failed"`（L306-315）— 破位未收回是否真落 none + gate
- `tr_quality` 低于 `WYCKOFF_PHASE_MIN_TR_QUALITY`（L326-345）— 低质量 TR 是否真闸住阶段抬升
- `_apply_p2_phase_a_gates`（L143-183）— forming/established 门控是否真拦住无种子箱的 B+ 抬升

**验收**：每个映射至少 1 个断言；premature/gate 路径各 1 个断言。输出「映射对/错」清单 + 证据行号。

---

### 查法 E — 持久化污染【最隐蔽，优先级高】

**目标**：验证 `_transition_phase` 的「none 保持旧状态」平滑规则不会导致脏 phase 跨日黏住，`first_seen` 不会钉死错误阶段。

**锚点**：
- `wyckoff_phase.py` `_transition_phase` L875-957（none 保持 L906-914；first_seen L897/903/922/942/953）
- `wyckoff_phase.py` `_load_phase_state` L845-856 / `_save_phase_state` L858-873（持久化 `~/.trader/wyckoff_phase.json`）
- `wyckoff_phase.py` `_phase_key` L841-843（`symbol::timeframe` 隔离）

**方法**：
1. **翻转及时性**：取一只从「积累」走向「派发」的票，逐 bar 回放，看 BC+UT+SOW 出现后 phase 是否及时翻转到 distribution，还是被旧 first_seen 黏在 accumulation。重点看 `_transition_phase` 反方向分支（L948 `old_order * new_order < 0`）是否真翻转。
2. **跨日一致性**：同一批 bars 跑两次 `_detect_phase`，比对持久化前后 phase 是否一致（防脏读/并发）。
3. **first_seen 污染**：构造 old_state 含 `first_seen="accumulation_d"`，喂新信号为派发，验 first_seen 是否被正确重置为 new_phase（L953）而非残留。
4. **use_persisted_phase 默认值**：确认生产路径中线周线 `use_persisted_phase` 是否仍为 False（前序 handoff 要求保持 False）；若已被改为 True，持久化污染风险激活。

**验收**：翻转及时性 / 跨日一致 / first_seen 重置 各 1 个证据样本。若 `use_persisted_phase=True` 且无隔离测 → 标「必须改」。

---

### 查法 A — 事件检测器阈值保真【数据根，成本中】

**目标**：验证 `_detect_*` 检测器在真实 K 线上触发位置对不对（不是阈值数值对不对——那已核对）。

**锚点**：`02-共享模块-shared/trader_shared/wyckoff_events.py`（`_detect_buying_climax` / `_detect_selling_climax` / `_detect_spring` / `_detect_sos` / `_detect_sign_of_weakness` / `_detect_upthrust` / `_detect_are` / `_detect_ar` / `_detect_lpsy` / `_detect_lps` / `_detect_st` / `_detect_compression` / `_detect_trend_pullback` / `_detect_trend_rally` / `_detect_volume_divergence`）；阈值源 `config.py`（`WYCKOFF_BC_VOL_RATIO_THRESHOLD` / `WYCKOFF_SPRING_ATR_MULTIPLE` / `WYCKOFF_SOW_CONSECUTIVE_DAYS` 等）。

**方法**：
1. **单事件隔离测**：选 3-5 只历史走势清晰的票（如茅台 2021 初 BC、某票 Spring），人工对 K 线标「这里应该是 BC/Spring」，跑检测器看 `*_signal=True` 的 bar 位置对不对。**绕过状态机**，直验检测器。
2. **边界测**：每个关键检测器喂手工构造的 K 线序列，验触发边界（如 BC 的 `WYCKOFF_BC_UPPER_SHADOW_RATIO` / `WYCKOFF_BC_MIN_POS_PCT` 临界值）。
3. **现有单测盘点**：grep `tests/` 里是否有「喂构造 bars → 验单事件触发」的测；若只有端到端测而无数测 → 标「漏网」。

**验收**：至少 BC / Spring / SOS 三个关键事件各 1 个真实票样本 + 1 个边界断言。输出「触发对/错/漏」清单。

---

### 查法 B — 中枢/段数据正确性【成本中】

**目标**：验证 `build_zones` / `build_segments` 算出的数值对不对（不是结构不变量——那已查）。

**锚点**：
- `chan_geometry.py` `build_zones` / `_merge_zones` / `build_segments`（L684-1003）
- `chan_structure.py` `_stroke_macd_area` L195-234（**已知雷**：文档 L203-205 警告「禁止 raw 日线 + 笔 index 错位」）
- `chan_structure.py` `_stroke_force_weaker` L236-252

**方法**：
1. 落盘中间产物：取一只票，dump `build_zones` 输出的 `zh_top/zh_bottom/valid` + `build_segments` 的 `start_index/end_index/high/low`，肉眼对照 K 线图核区间对不对。
2. **MACD 面积坐标雷**：重点验 `_stroke_macd_area` 的 `start_index/end_index` 是否和传入 `bars` 同源坐标系。文档点名「chanlun_analysis 传入的是 inclusion 后并已 _calc_macd 重算的 cleaned（禁止用 raw 日线 + 笔 index，否则面积会错位）」——核实调用方是否真传 cleaned bars。
3. **中枢合并**：验 `_merge_zones` 的「纯 gap 不合并」(formulas §4.2) 是否真生效，有无 `zh_top < zh_bottom` 非法中枢漏过。

**验收**：1 只票的 zones/segments 落盘对照 + MACD 坐标系溯源 1 条。输出「数值对/错」清单。

---

### 查法 C — volume 单位一致性【成本低，但影响面大】

**目标**：确认事件检测器拿到的 bars 的 volume 单位和阈值标定时的单位一致。

**锚点**：
- `light_data.py` / `data_provider.py`（volume 取数）
- MEMORY 已记：「腾讯日线 volume=手」(2026-08-04 实测裁决)
- 事件检测器量比阈值：`WYCKOFF_BC_VOL_RATIO_THRESHOLD` / `WYCKOFF_SOW_VOL_RATIO_THRESHOLD` / `WYCKOFF_SPRING_BULLISH_VOL_RATIO` 等

**方法**：
1. 取一只票，dump 事件检测器实际收到的 bars 的 volume 值，对照腾讯/mootdx 原始值，确认单位（手 vs 股，差 100×）。
2. 核阈值标定时的假设单位（查 config 注释 / git blame 阈值引入 commit）。
3. 若单位不一致 → 所有量比类事件（BC/SOW/Spring 量比）全错 → 标「必须改」。

**验收**：1 只票 volume 值溯源 + 阈值单位假设核对。MEMORY 已有结论（=手），复核生产路径是否真的拿到手单位。

---

### 查法 F — 黄金样本回放【终极验收，成本高】

**目标**：端到端验 phase 轨迹是否符合威科夫叙事顺序。

**锚点**：`scripts/diagnose_chan_triangulation.py`（formulas §10 已有 czsc 三角对照 30 只样本，可参照扩到威科夫）。

**方法**：选 10 只完整走完「积累→markup」或「派发→markdown」的票，逐 bar 喂 `_detect_phase`，画 phase 轨迹时间线，人工对照 K 线图核「转折点对不对、滞后几根」。重点看：该进 D 时是否提前进了 C（Spring 未确认就抬 C）；该翻转时是否被黏住（与查法 E 交叉）。

**验收**：10 只票 phase 轨迹 + 人工裁决。输出「轨迹对/错/滞后」清单。

---

### 查法 G — 周线/日线隔离实测【成本低】

**目标**：验 `_phase_key` 的 `symbol::timeframe` 隔离是否真不串台。

**锚点**：`wyckoff_phase.py` `_phase_key` L841-843 / `_load_phase_state` L845 / `_save_phase_state` L858。

**方法**：取一只日线积累、周线派发的票，同时跑日线和周线 `_detect_phase`，验两个 phase 互不污染（持久化文件里是两个独立 key）。再验同一 symbol 不同 timeframe 的 first_seen 不互相覆盖。

**验收**：1 只票日线/周线 phase 独立性证据。若串台 → 标「必须改」。

---

## 3. 法源（必读，按文档开发铁则）

- **威科夫原典**：五阶段叙事顺序 A停止→B建仓→C测试→D确认→E趋势；Spring/UT 必须在 Phase B 之后才有效（premature 判噪声）
- `02-共享模块-shared/trader_shared/formulas.md` §4.3 / §9.4（中枢拓扑）/ §11A（单边启发式）
- `02-共享模块-shared/trader_shared/wyckoff_phase.py` docstring L282-296（_detect_phase 原典约束）
- `docs/plans/report-wyckoff-state-fixes-handoff.md`（前序状态机修复 handoff）
- `docs/plans/wyckoff-cluster-reverse-event-handoff.md`（簇确认反向 SOS 不翻案）
- MEMORY（`.workbuddy/memory/MEMORY.md`）：volume 单位=手、tushare/腾讯数据源取舍

---

## 4. 可运行验证（只读、离线）

```bash
# 前序已跑全绿，接手 Agent 复跑确认基线
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_wyckoff_core.py \
  02-共享模块-shared/tests/test_report_mid_short_sources.py -q --tb=short
# 期望: 179 passed

PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_chan_core.py \
  02-共享模块-shared/tests/test_chan_segments_bug_r.py \
  02-共享模块-shared/tests/test_chan_segments_no_overcut.py \
  02-共享模块-shared/tests/test_chan_split_equivalence.py -q --tb=short
# 期望: 187 passed

bash scripts/run-gate-tests.sh
# 期望: 796 passed, 4 skipped

# 信号→phase 映射盘点（查法 D 辅助）
PYTHONPATH=02-共享模块-shared python3 -c "
from trader_shared.wyckoff_phase import _PHASE_ORDER, _detect_phase
import inspect
print(inspect.getsource(_detect_phase))  # 通读 20+ if/elif 映射
"
```

---

## 5. 查 Agent 边界（可改 / 勿改）

**可改**：仅本 handoff 文档 + 审计输出报告（写 `docs/plans/` 或对话内）。

**勿改**：
- 任何 `.py` 源码 / 测试（纯审计，发现问题列清单交父 Agent）
- fusion / decision_view / 出手 / 池分道
- 中线周线 `use_persisted_phase` 保持 False（若发现已被改 True，标「必须改」并报告，但不自行改回）
- 阶段机主枚举语义（只核查，不重定义）

**输出**：每项查法给「文件:行号、证据、影响、严重度（必须改/建议改/需人工裁定）」；最后给总评 + 「必须再改」清单；明确跑了哪些验证、多少 passed。

---

## 6. 前序审计遗留的「建议改」项（本 handoff 不处理，仅登记）

接手 Agent 若在核查中发现这些加剧了状态错误，可一并报告：
- `short_midline.py:1430` `_mom_dir2 = int(_msig.get("direction",0))` 应走 `_safe_int`（与 L1429 不对称，commit 0c58ed6 漏修）
- `short_midline.py:1536` `_rr_chase_verdict` 死代码（计算未用）
- `short_midline.py:1732` `key_levels` 死代码（读出未用）
- `pool_count`/`pool_cap`（short_midline L1876-1877）渲染层读但 build_report 不写，需注释注入方

---

## 7. 接手 Agent 优先级建议

时间有限时按此序：
1. **查法 D**（信号→phase 映射）— 成本低收益高，纯写断言即可堵状态机最大语义漏洞
2. **查法 E**（持久化污染）— 最隐蔽，跨日难复现
3. **查法 A**（事件检测器保真）— 数据根，需人工对 K 线，先抽 BC/Spring 验
4. **查法 F/G**（黄金样本 + 隔离）— 终极验收，等前面堵住再做
5. 查法 B/C — 数据正确性，按机会插空

一句话：**前序查了「状态机不会自相矛盾」，本 handoff 要查「状态机判的是不是真相」。**
