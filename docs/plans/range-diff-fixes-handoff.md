# 区间定义硬伤修复 — Agent Handoff（W-DIFF-1/2 · C-DIFF-1/2）

> **状态**: done（2026-08-02）  
> **触发**: 双查 + 裁定：存在「区间定义算错」（见会话终裁）  
> **顺序（强制）**: W-DIFF-1 → C-DIFF-1 → W-DIFF-2 → C-DIFF-2  
> **方法**: 写 Agent 落地 + 测；查 Agent 对照本文；**同步文档**；再 PR。  
> **禁止**: 改 fusion / decision_view / 池分道；不重开报告四区；不发明软确认 ST。

---

## 0. 母法源

| ID | 母法源 |
|----|--------|
| W-DIFF-1 | `wyckoff-tr-maturity-l0l3-handoff.md` §1.1 / §2.3（forming 上沿未出；雏形上下沿来自 SC/AR） |
| W-DIFF-2 | `wyckoff-structure-anchor-handoff.md` §3.2 / S-A5（重搜排除 `sc_bar_idx ≤ fail_bar_idx`） |
| C-DIFF-1 | `formulas.md` §4.1 / §9.1：`ZG=min(高点)` `ZD=max(低点)`；段用极值 |
| C-DIFF-2 | 同 formulas 离开段时间约束；`_last_pivot_anchor_bar` 已有映射范式 |

---

## 1. W-DIFF-1 — forming 禁止分位上沿冒充

### 必须

1. `_phase_a_box_bounds`（或等价）：**无有效 `ar_high` 时，不得用 `tr_upper` 填上沿**（proto/L1/forming）。  
2. 无 `ar_high` 且有 `sc_low` → 短语走「雏形 下沿 x（上沿未出）」，**禁止** `雏形 lo-hi（待 ST）` 其中 hi 来自分位。  
3. L2/L3 成熟箱上沿仍须来自 `ar_high`（种子）；不得靠分位 `tr_upper` 冒充成熟上沿。  
4. pytest：forming + 有分位 `tr_upper` → bounds hi is None；phrase 含「上沿未出」、不含假双沿。

### 文档同步

- `wyckoff-tr-maturity-l0l3-handoff.md`：明示 proto 边界**只认** SC/ST 低 + AR 高；分位 TR 不得填雏形上沿。  
- `wyckoff_core._phase_a_box_bounds` docstring 改掉「再 tr_upper」误导。

---

## 2. C-DIFF-1 — 段中枢用 high/low

### 必须

1. `build_zones`：取每段/笔高低时，**优先** `item["high"]` / `item["low"]`（有限数值）；缺省再回退 `max/min(start_price, end_price)`。  
2. `level` 笔/段同一取值函数（笔通常 high/low≈端点，行为不变；段可纠偏）。  
3. pytest：三段 `high/low` ≠ 端点 → ZG/ZD = min(highs)/max(lows)，且 ≠ 纯端点结果。

### 文档同步

- `formulas.md` §4.1 / §9.1：写明实现取「段/笔的 high/low 极值字段；无则回退端点价」。

---

## 3. W-DIFF-2 — 破位后排除 fail_bar 及更早锚

### 必须

1. Path B 冷启动（`include_failed=False`）时：若 `tr_ctx` / `phase_a_range` 带 `fail_bar_idx`（或 status=failed 且有该字段），则 **跳过** `sc_bar_idx ≤ fail_bar_idx` 的候选。  
2. `include_failed=True`（汇报已失败 SC）**不**套此排除，以免找不到失败锚本身。  
3. pytest（S-A5 类）：构造 fail_bar 后，冷启动不得把 fail 棒或更早旧 SC 钉成 forming/established。

### 文档同步

- `wyckoff-structure-anchor-handoff.md`：S-A5 / §3.2 标注已实现；实现锚点指向 `_find_sc_anchor` 排除逻辑。

---

## 4. C-DIFF-2 — 段中枢索引映到 bar

### 必须

1. `_zone_last_end_index` / `_zone_first_start_index`（或调用处）在**段级中枢**上，将成员 `start_index/end_index`（笔序）**映射为 bar 索引**（范式对齐 `_last_pivot_anchor_bar`）；笔级中枢则索引已是 bar，直接用。  
2. `_stroke_leaves_after_zone` / `_bc_stroke_pair` / 连接段时间窗使用**同一 bar 坐标系**。  
3. pytest：段中枢 + 区内笔 → `leaves_after` 为 False；strict b/c 在合理夹具上不再恒空（至少一对可解析，或文档化仍空的合法条件）。

### 文档同步

- `formulas.md` 或 deep-card：一句「离开段时间比较用 K 线索引；段中枢成员索引须映到 bar」。  
- `chan_structure` 相关 docstring 更新。

---

## 5. 禁止 / 勿改

| 禁止 | 勿改文件（除非手递点名） |
|------|--------------------------|
| 软确认 ST | fusion / 池分道 / decision_view |
| 报告四区 | short_midline 骨架大改 |
| 砍原典 L0–L3 | 检测阈值大挪（本 PR 只修定义/映射） |

可改白名单：

- `wyckoff_core.py`（`_phase_a_box_bounds` / phrase / docstring）  
- `wyckoff_events.py`（`_find_sc_anchor` 排除）  
- `chan_geometry.py`（`build_zones`）  
- `chan_structure.py`（zone 索引映射 + 调用）  
- 相关 pytest  
- 上述法源文档 + 本文

---

## 6. 验收表

| ID | 项 | 如何验 |
|----|-----|--------|
| M-R1 | forming+分位 TR → 上沿未出 | pytest |
| M-R2 | 段 high/low → 正确 ZG/ZD | pytest |
| M-R3 | fail_bar 排除旧锚 | pytest |
| M-R4 | 段中枢离开用 bar 序 | pytest |
| M-R5 | 门禁绿 | `TRADER_CI_PYTHON=python3 bash scripts/run-gate-tests.sh` |
| M-R6 | 文档已同步四点 | diff 含 formulas / maturity / structure-anchor |
| M-R7 | 未碰 fusion/出手/分道 | `git diff` |

---

## 7. 双 Agent

- **写 Agent**：按 §1→§4 顺序改 + 测 + 文档同步 + commit/push（分支 `cursor/range-diff-fixes-514d`）。  
- **查 Agent**：逐条 M-R* / 禁止项；复现 W-DIFF-1/C-DIFF-1 旧坏例应已修；列 must-fix。
