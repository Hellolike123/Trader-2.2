# 威科夫结构锚点搜索 — Agent Handoff（新方案 SSOT）

> **状态**: 规格冻结（用户 2026-08-02 确认采纳）  
> **协作**: Agent1 完善本文与关联文档 → Agent2 按本文写码 → Agent3 查验+测 →（通过后）Agent4 全量复审  
> **取代 / 勿混**: 旧默认「日线只在最近 `WYCKOFF_CLIMAX_ANCHOR_BARS=15` 根内找 SC 且无结构钉住」**不再作为产品法源**。15 若仍出现在旧文，仅作历史；实现与验收以**本文**为准。  
> **相关**: `wyckoff-phase-a-range-handoff.md`、`wyckoff-tr-maturity-l0l3-handoff.md`、原典盘点；详析卡只渲染、不补灯。

---

## 0. 用户已锁定的产品裁决

1. **中线看大趋势** = 周线威科夫定战役；**短线看次级趋势做波段** = 日线结构对照 + 缠论扳机（既有 `BUSINESS.md` §2.0，不改出手/fusion）。  
2. **区间主规则**：有未失效 Phase A → 钉住 `[sc_bar_idx, 今]`，**不设到期日**（解决长横盘「假无状态」）。  
3. **冷启动盲搜硬封顶**：日线 **90** 根；周线 **39** 根（约 9 个月）。  
4. **破位收口（兜底，与钉住同包必做）**：收盘有效破 `sc_low` 未收回 → Phase A 失败；**禁止**再认后续 ST；并**连带**不得保持健康 `established`/雏形叙事（南网对照）。  
5. **50/200 均线不进威科夫法源**；结构靠事件边界，不是均线。  
6. **禁止**：肉眼低点补 SC；软确认当 ST；日线箱冒充中线；只加长窗不做破位收口。

---

## 1. 问题与收益/风险（验收时对照）

| | |
|--|--|
| 旧痛点 | 固定近窗（15）→ 长横盘/窗外 SC 假无；ST 已判失败仍亮 SC+AR 雏形（假有） |
| 收益 | 结构可见、中短线分轨清晰、破位后一致 |
| 主风险 | 钉住后若失效漏检 → 坏结构挂太久；靠 §3 收口兜底 |
| 非目标 | 不改 fusion / decision_view / 池分道；不改详析手补灯 |

---

## 2. 区间怎么定（新方案唯一算法）

### 2.1 优先级

```text
若存在未失效结构锚（路径 A）:
    搜索宇宙 = [anchor.sc_bar_idx, len(bars)-1]   # 可超过 90/39
否则（路径 B 冷启动）:
    搜索宇宙 = bars[-CAP:]   # 日 CAP=90，周 CAP=39
    可选：在 CAP 内先切「寻底下跌段」再找最近合格 SC（实现可先整段 CAP，测例锁语义）
在宇宙内用既有 SC 条件取最近合格锚 → 写 phase_a_range
若触发 §3 失效 → 清空锚，回到 B
```

### 2.2 常量（新）

| 常量 | 值 | 含义 |
|------|-----|------|
| `WYCKOFF_SC_COLD_START_BARS_DAILY` | 90 | 日线冷启动硬封顶 |
| `WYCKOFF_SC_COLD_START_BARS_WEEKLY` | 39 | 周线冷启动硬封顶 |
| `WYCKOFF_CLIMAX_ANCHOR_BARS` | **重新定义**或弃用为「仅 AR 等待/兼容别名」 | **禁止**再当「SC 唯一搜索宇宙=15」 |

Agent1 须在本文钉死：旧 `CLIMAX_ANCHOR_BARS=15` 的语义迁移表（谁读新常量、谁保留作 AR 窗）。

### 2.3 中线 / 短线

| 轨 | 数据 | CAP | 区间 |
|----|------|-----|------|
| 中线大趋势 | 周 K | 39 | 周线锚钉住；禁止日线冒充 |
| 短线次级波段 | 日 K | 90 | 日线锚钉住；只对照，不进中线定论 |

---

## 3. 破位收口（与钉住同包）

### 3.1 失效条件（已有 ST 语义，须推广到 Phase A 状态）

- 自 SC+1 起：`low < sc_low*(1-MAX_PIERCE)` **且** `close < sc_low` → **Phase A 失败**  
- 失败后：**禁止** `secondary_test_sc_signal=True`（已有）  
- 失败后**必须**连带（本迭代必做，二选一或组合，Agent1 定一种写进验收表）：  
  - **推荐**：`phase_a_range.status` → `failed`（或 `none`）+ 清空/降级不得展示「停止：SC+AR」健康雏形；`tr_maturity`→`L0` 或等价「Phase A 已失败」  
  - `ar_signal` 可保留历史事实旗，但 **maturity/box/阶段文案**不得装未失败  

### 3.2 南网对照（必须有测）

- SC≈2026-07-16 `sc_low≈41.02`；次日低 37.8 / 收 38.14 → 失败  
- 其后低≈40.3 **不得** ST  
- 失败后不得同时呈现健康 `established` + 可推进雏形而无失败语义  

---

## 4. 可改 / 勿改

### 可改
- `config.py`（新 CAP 常量；CLIMAX 语义迁移）  
- `wyckoff_events.py`（`_find_sc_anchor` 搜索宇宙；失效与 ST 一致）  
- `wyckoff_core.py`（`phase_a_range` status/`tr_maturity` 收口；透传）  
- `wyckoff_phase.py`（失败态文案/阶段，最小）  
- `wyckoff_view.py`（失败态 summary，最小）  
- 关联 plans 文档（Agent1：本文 SSOT + 旧文「15=搜索宇宙」勘误）  
- `tests/test_wyckoff_*.py` + 必要 fixture  

### 勿改
- fusion / decision_view / 池分道 / mistery_gate  
- 详析 render 手补 SC  
- Spring Test vs 广义 ST 字段分离  
- 用分位 TR 当搜 SC 宇宙；用 50/200 MA 定区间  

---

## 5. 验收表（Agent1 可增行，不可删锁项）

| ID | 必须 | 测/验 |
|----|------|-------|
| S-A1 | 未失效锚：搜索可越过冷启动 CAP（钉住） | 单测：SC 在 -100，今仍认同一 sc_bar_idx |
| S-A2 | 无锚：日线只在最近 90 内冷启动 | 单测 |
| S-A3 | 无锚：周线只在最近 39 内冷启动 | 单测 |
| S-A4 | 有效破位 → 禁止后续 ST | 南网类 / 既有 M-R* |
| S-A5 | 有效破位 → 不得健康 established/雏形推进叙事 | 南网类新测 |
| S-A6 | 中线周 / 短线日 宇宙分离，日不进中线定论 | 契约测或文档+既有 |
| S-A7 | 相关 wyckoff pytest 绿 | CI/本地 |
| S-A8 | 文档无「SC 唯一窗=15」作为现行法源 | Agent3 查文档 |

---

## 6. 四 Agent 分工

| 角色 | 职责 |
|------|------|
| **Agent1 方案** | 只改文档：完善本文；勘误 phase-a / maturity / config 注释中与本文冲突的「15=SC 宇宙」；**禁止**写回旧方案 |
| **Agent2 写码** | 只读本文 + 勘误后法源；实现 + 测例；禁止发明未写行为 |
| **Agent3 查验** | 对照本文逐项 ✅/❌；跑测；抓「文档写了没做 / 做了违禁止 / 与旧15混淆」 |
| **Agent4 复审** | 仅当 Agent3 PASS；独立再读同一法源与 diff，防查 Agent 漏判 |

父 Agent：Agent3/4 通过后再开/更新 PR。
