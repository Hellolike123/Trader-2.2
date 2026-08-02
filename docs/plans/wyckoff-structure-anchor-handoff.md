# 威科夫结构锚点搜索 — Agent Handoff（新方案 SSOT）

> **状态**: 规格冻结（用户 2026-08-02 确认采纳；Agent1 文档钉死）  
> **协作**: Agent1 完善本文与关联文档 → Agent2 按本文写码 → Agent3 查验+测 →（通过后）Agent4 全量复审  
> **取代 / 勿混**: 旧默认「日线只在最近 `WYCKOFF_CLIMAX_ANCHOR_BARS=15` 根内找 SC 且无结构钉住」**不再作为产品法源**。15 若仍出现在旧文，仅作历史；实现与验收以**本文**为准。  
> **相关**: `wyckoff-phase-a-range-handoff.md`（P1/P2 历史；文首勘误）、`wyckoff-tr-maturity-l0l3-handoff.md`（L0–L3；破位连带）、原典盘点；详析卡只渲染、不补灯。  
> **调参续篇**: `wyckoff-detect-tuning-next.md` 仅指向本文，**禁止**另起第二份搜索宇宙 SSOT。

---

## 0. 用户已锁定的产品裁决

1. **中线看大趋势** = 周线威科夫定战役；**短线看次级趋势做波段** = 日线结构对照 + 缠论扳机（既有 `BUSINESS.md` §2.0，不改出手/fusion）。  
2. **区间主规则**：有未失效 Phase A → 钉住 `[sc_bar_idx, 今]`，**不设到期日**（解决长横盘「假无状态」）。  
3. **冷启动盲搜硬封顶**：日线 **90** 根；周线 **39** 根（约 9 个月）。  
4. **破位收口（兜底，与钉住同包必做）**：收盘有效破 `sc_low` 未收回 → Phase A 失败；**禁止**再认后续 ST；并**连带**不得保持健康 `established`/雏形叙事（南网对照）。  
5. **50/200 均线不进威科夫法源**；结构靠事件边界，不是均线。  
6. **禁止**：肉眼低点补 SC；软确认当 ST；日线箱冒充中线；只加长窗不做破位收口；把方案退回「只加长到 45/60 且不破位收口」。

---

## 1. 问题与收益/风险（验收时对照）

| | |
|--|--|
| 旧痛点 | 固定近窗（15）→ 长横盘/窗外 SC 假无；ST 已判失败仍亮 SC+AR 雏形（假有） |
| 收益 | 结构可见、中短线分轨清晰、破位后一致 |
| 主风险 | 钉住后若失效漏检 → 坏结构挂太久；靠 §3 收口兜底 |
| 非目标 | 不改 fusion / decision_view / 池分道；不改详析手补灯；不用 50/200 MA 定箱 |

---

## 2. 区间怎么定（新方案唯一算法）

### 2.1 优先级

```text
若存在未失效结构锚（路径 A，alive Phase A）:
    搜索宇宙 = [anchor.sc_bar_idx, len(bars)-1]   # 可超过 90/39；不设到期
否则（路径 B 冷启动）:
    CAP = 日 90 / 周 39
    搜索宇宙 = bars[-CAP:]
    可选：在 CAP 内先切「寻底下跌段」再找最近合格 SC
          （实现可先整段 CAP；语义由 S-A2/S-A3 锁「不超出 CAP」）
在宇宙内用既有 SC 条件取最近合格锚 → 写 phase_a_range
若触发 §3 失效 → status=failed；清空 alive 锚（见 §3.2）→ 下一根起走路径 B
```

**alive 定义**：`phase_a_range.status ∈ {forming, established}` 且尚未触发 §3.1 有效破位。  
`failed` / `none` **不是** alive，不得走路径 A。

### 2.2 `CLIMAX_ANCHOR_BARS` 语义迁移表（钉死）

| 符号 | 新默认 | 谁读 | 含义（现行） | 禁止 |
|------|--------|------|--------------|------|
| `WYCKOFF_SC_COLD_START_BARS_DAILY` | **90** | `_find_sc_anchor` / `_sc_detector_params`（`timeframe=daily`）路径 B | 日线冷启动 SC 搜索宇宙硬封顶 | 当 TR 周期；当 AR 等待窗 |
| `WYCKOFF_SC_COLD_START_BARS_WEEKLY` | **39** | 同上（`timeframe=weekly`）路径 B | 周线冷启动 SC 搜索宇宙硬封顶 | 同上 |
| `WYCKOFF_AR_MAX_BARS` | **15**（env 可覆） | `_detect_ar`（及对称 ARE 若共用） | **AR 等待窗**：SC 后最多扫几根找首段 AR；周线可半幅缩放（既有） | 当 SC 搜索宇宙 |
| `WYCKOFF_CLIMAX_ANCHOR_BARS` | **15**（保留名） | ① 无 env 时作 `WYCKOFF_AR_MAX_BARS` 的默认种子；② BC/ARE/阶段机短事件 lookback（既有 `wyckoff_phase` 扫描窗） | **仅** AR 等待默认种子 / 非 SC 短窗兼容别名 | **禁止**再当「SC 唯一搜索宇宙=15」；`_find_sc_anchor` **不得**再用它当 Path B CAP |
| `phase_a_range.anchor_bars` | 日 90 / 周 39 | 透出/调试 | = 该 timeframe 的冷启动 CAP（非 15） | 写回 15 冒充 SC 宇宙 |
| （可选）`phase_a_range.search_mode` | `"pinned"` \| `"cold_start"` | 透出 | 路径 A / B；实现可加，验收不强制字段名 | — |

**迁移动作（Agent2）**：

1. `config.py`：新增两 CAP 常量；改 `CLIMAX` 注释指向本文；`AR_MAX` 默认仍可读 `CLIMAX` 数值 15，但注释写明「AR 窗，非法源 SC 宇宙」。  
2. `_sc_detector_params`：`anchor_bars`（供 `_find_sc_anchor` Path B）← 日 90 / 周 39；**不再** `= WYCKOFF_CLIMAX_ANCHOR_BARS`。  
3. Path A：若调用方 / 分析层持有 alive `sc_bar_idx`，搜索下界钉该 idx（可越过 CAP）。  
4. 既有断言 `WYCKOFF_CLIMAX_ANCHOR_BARS == 15` 且语义为「SC 窗」的测例 → 改为断言冷启动 CAP 或 AR_MAX。  
5. **不得**把 Path B CAP 改成 45/60 折中而不做 §3。

### 2.3 中线 / 短线分轨

| 轨 | 数据 | CAP | 区间 | 消费 |
|----|------|-----|------|------|
| 中线大趋势 | 周 K | 39 | 周线锚钉住；破位收口同包 | 中线定论 / 池链；**禁止**日线冒充 |
| 短线次级波段 | 日 K | 90 | 日线锚钉住；破位收口同包 | 短线「威科夫：」仅对照；**不进**中线定论 / fusion |

两轨**各自**跑 §2.1；日线 `phase_a_range` 不得写入周线中线字段。

---

## 3. 破位收口（与钉住同包）

### 3.1 失效条件（与广义 ST 同一刺穿语义）

自 `sc_bar_idx+1` 起，任一棒满足（常量既有）：

- `low < sc_low * (1 - WYCKOFF_ST_SC_MAX_PIERCE)` **且** `close < sc_low`  
→ **Phase A 失败**（有效跌破未收回）。

失败后硬规则：

1. **禁止** `secondary_test_sc_signal=True`（既有 `_detect_secondary_test_sc`；不得 `continue` 跳过破位棒另找假 ST）。  
2. **连带收口（本迭代必做，取值钉死如下）** — 见 §3.2。

### 3.2 `phase_a_range.status` / 成熟度 / 文案合同（钉死）

| 字段 | 破位后合同值 | 说明 |
|------|--------------|------|
| `phase_a_range.status` | **`failed`** | 四态：`none` \| `forming` \| `established` \| **`failed`**；顶栏 `phase_a_status` 同值 |
| `tr_maturity` | **`L0`** | 失败 Phase A ≠ 健康雏形；**禁止**停在可推进的健康 `L1` proto |
| `box_display_mode` | **`none`** | 不写「雏形 x-y」「箱体 lo-hi」 |
| `measure_allowed` | `False` | 清空可展示量度目标 |
| 阶段 / 中短线威科夫文案 | 不得「停止：SC+AR」健康叙事 | 可写失败语义（如「Phase A 失败 / 破位」）；微信红线仍守 |
| `sc_signal` / `ar_signal` | 可保留历史事实旗 | **maturity / box / 阶段文案**不得装未失败 |
| alive 锚 | **清空** | 下一决策走路径 B；重新搜 SC 时 **排除** `sc_bar_idx ≤ fail_bar_idx` 的旧锚（避免同一已破 SC 被冷启动再次钉成 forming/established） |
| （建议）`fail_bar_idx` / `fail_reason` | 透出可选 | 调试；验收不强制字段名，但 S-A5 须能区分失败态 |

**与 L0–L3 handoff 关系**：`wyckoff-tr-maturity-l0l3-handoff.md` §1.1 增 `failed → L0`；§1.3「仍 L0–L1」在破位失败场景收紧为 **L0**（本文优先）。

**禁止**：破位后仍 `status=established` 或健康 `forming`；破位后 `box_display_mode=proto` 无失败语义；仅把 ST 关掉却继续「停止：SC+AR」推进叙事。

### 3.3 南网对照（必须有测）

手工锚（日线）：

- SC ≈ **2026-07-16**，`sc_low ≈ 41.02`  
- 次日低 ≈ 37.8 / 收 ≈ 38.14 → 有效跌破未收回 → **`status=failed`**  
- 其后低 ≈ 40.3 **不得** ST  
- 失败后不得同时呈现健康 `established` + 可推进雏形而无失败语义  

合成夹具（已有，须扩展断言）：

- `02-共享模块-shared/tests/test_wyckoff_tr_maturity.py` → `_sc_breakdown_then_fake_st_bars()` / `test_m_r9_breakdown_aborts_st_no_l2`  
- 本迭代：在 M-R9 或新 `test_wyckoff_structure_anchor.py` 上**加严**为 `phase_a_status/status == "failed"` 且 `tr_maturity == "L0"`（旧断言「L0 或 L1」对失败场景过宽，须收紧）。

---

## 4. 可改 / 勿改

### 可改

- `config.py`（新 CAP 常量；`CLIMAX` / `AR_MAX` 注释与默认种子关系）  
- `wyckoff_events.py`（`_find_sc_anchor` / `_sc_detector_params` 搜索宇宙；失效与 ST 一致；排除已失败锚）  
- `wyckoff_core.py`（`_build_phase_a_range` 四态含 `failed`；`tr_maturity`/`box_display_mode` 收口；透传）  
- `wyckoff_phase.py`（失败态文案/阶段，最小；扫描窗勿把 CLIMAX 写回 SC 宇宙）  
- `wyckoff_view.py`（失败态 summary，最小）  
- 关联 plans / `BUSINESS.md` §2.2 一行指针（Agent1：本文 SSOT + 旧文勘误）  
- `tests/test_wyckoff_*.py` + 必要 fixture（优先扩 `test_wyckoff_tr_maturity.py` 或新建 `test_wyckoff_structure_anchor.py`）

### 勿改

- fusion / decision_view / 池分道 / mistery_gate  
- 详析 render 手补 SC  
- Spring Test（`st_*`）vs 广义 ST（`secondary_test_sc_*`）字段分离  
- 用分位 TR 当搜 SC 宇宙；用 50/200 MA 定区间  
- 把 Path B 做成「只加长 45/60、无钉住、无破位收口」旧折中  
- 大段删除 phase-a / maturity 历史正文（只加勘误/取代声明）

---

## 5. 验收表（不可删锁项；细节可增）

| ID | 必须 | 测/验细节 | fixture / 锚点 |
|----|------|-----------|----------------|
| **S-A1** | 未失效锚：搜索可越过冷启动 CAP（钉住） | 构造：合格 SC 在 `len-100`（日线，超出 90）；其后无 §3 破位；断言同一 `sc_bar_idx`，`status∈{forming,established}`，`search_mode` 若有则为 `pinned` | 新单测（合成 bars）；文件建议 `test_wyckoff_structure_anchor.py` |
| **S-A2** | 无锚：日线只在最近 90 内冷启动 | 无 alive 锚；唯一合格 SC 在 `len-100` → **不得**认该 SC（`sc_signal` 假或锚在窗内另一根）；CAP 内有合格 SC → 可认且 `sc_bar_idx >= len-90` | 合成；断言读 `WYCKOFF_SC_COLD_START_BARS_DAILY` |
| **S-A3** | 无锚：周线只在最近 39 内冷启动 | 同 S-A2，CAP=39，`timeframe=weekly` | 合成；`WYCKOFF_SC_COLD_START_BARS_WEEKLY` |
| **S-A4** | 有效破位 → 禁止后续 ST | 破位后缩量回测棒 → `secondary_test_sc_signal is not True`；reason 含跌破/失败类 | 既有 `_sc_breakdown_then_fake_st_bars` + M-R9；可复用 |
| **S-A5** | 有效破位 → 不得健康 established/雏形推进叙事 | `phase_a_range.status == "failed"`；`phase_a_status == "failed"`；`tr_maturity == "L0"`；`box_display_mode == "none"`；文案无健康「停止：SC+AR」/无「雏形」推进；`measure_allowed is False` | 同上夹具加严；南网手工点 §3.3 作对照说明（单测以合成准，禁默认全网抓数） |
| **S-A6** | 中线周 / 短线日 宇宙分离 | 日线 analysis 的 `phase_a_range` 不进中线定论；周线路径 CAP/钉住独立；契约：短线「仅对照」 | 既有 R6 / midline 契约测 + 文档对照；必要时补「日 CAP≠周 CAP」单元 |
| **S-A7** | 相关 wyckoff pytest 绿 | 至少：`test_wyckoff_tr_maturity.py`、`test_wyckoff_core.py`、结构锚新测；门禁子集不塞全历史红项 | `pytest` 本地 / CI |
| **S-A8** | 文档无「SC 唯一窗=15」作为现行法源 | Agent3 查：本文 + phase-a 文首勘误 + maturity 短注 + `config.py` 注释 + `wyckoff-detect-tuning-next.md`；历史正文可保留但须标明历史 | 文档 diff 审查 |

**关联既有 ID（不替代 S-A\*）**：M-R9（破位禁 ST）加严后与 S-A4/S-A5 对齐；M-R1…R8 回归不得因 CAP 迁移误红（窗外假 SC 夹具须改用钉住或挪进 90）。

---

## 6. 四 Agent 分工

| 角色 | 职责 |
|------|------|
| **Agent1 方案** | 只改文档（+ config **注释**）：完善本文；勘误 phase-a / maturity / CLIMAX 注释中与本文冲突的「15=SC 宇宙」；**禁止**写回旧方案；**禁止**实现检测逻辑 |
| **Agent2 写码** | 只读本文 + 勘误后法源；实现 + 测例 S-A1…S-A7；禁止发明未写行为（均线定箱、改 fusion 等） |
| **Agent3 查验** | 对照本文逐项 ✅/❌；跑测；抓「文档写了没做 / 做了违禁止 / 与旧15混淆」 |
| **Agent4 复审** | 仅当 Agent3 PASS；独立再读同一法源与 diff，防查 Agent 漏判 |

父 Agent：Agent3/4 通过后再开/更新 PR。

---

## 7. Agent2 开工清单（最小路径）

```text
1) config：WYCKOFF_SC_COLD_START_BARS_{DAILY,WEEKLY}；CLIMAX/AR_MAX 注释按 §2.2
2) wyckoff_events：_sc_detector_params / _find_sc_anchor 路径 A/B；破位与排除失败锚
3) wyckoff_core：phase_a_range 四态 failed；tr_maturity=L0 / box=none 收口
4) wyckoff_phase / wyckoff_view：失败文案最小改
5) tests：S-A1…S-A5 单测 + M-R9 加严；S-A7 回归绿
```

自测建议：

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest \
  02-共享模块-shared/tests/test_wyckoff_tr_maturity.py \
  02-共享模块-shared/tests/test_wyckoff_core.py \
  02-共享模块-shared/tests/test_wyckoff_structure_anchor.py -q
```

（若尚未建 `test_wyckoff_structure_anchor.py`，测例可暂放 maturity/core，但验收 ID 仍用 S-A\*。）
