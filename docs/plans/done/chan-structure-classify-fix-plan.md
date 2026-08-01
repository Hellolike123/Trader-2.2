# 缠论结构分类修复计划（中枢主状态 / 消灭线段不足主文案）

> 日期：2026-07-10  
> 模式：双 Agent（Implementer → Reviewer）  
> 业务与代码必须一一对应，审查按清单验收。
>
> **Supersession（2026-08 / P1）**：勿再按本文 §1.3「0 中枢+有线段→盘整」施工。
> 现行法源：`formulas.md` **§11A** → 0 中枢+有线段 = **无结构**；**§9** 假趋势
> （连接段非反向）已在 `classify_structure` demote→**盘整**（非 `structure_type=假趋势`）。
> Review：`docs/audit/chan-structure-classify-review.md`。

---

## 1. 业务逻辑（唯一真理）

### 1.1 用户永远先看到什么

- **有没有中枢、偏趋势还是盘整**
- 段数只是 **证据强弱**，不能让界面像「没结构」

### 1.2 structure_type 主状态允许值（用户主文案）

仅允许（中文主状态）：

| structure_type | 业务含义 |
|----------------|----------|
| 无结构 | 笔不足，谈不上走势 |
| 单边上涨 / 单边下跌 | 0 中枢 + 单边启发式 |
| 盘整 | 1 中枢，或 2+ 重叠/混乱中枢 |
| 上涨趋势 / 下跌趋势 | 2+ 同向不重叠中枢 |

**禁止** 作为 `structure_type` 主值：

- `线段不足n/11`
- `线段不足n/5`
- 任何以「线段不足」开头的主状态

### 1.3 中枢拓扑规则（业务 = 代码）

与现有拓扑判断一致，**只改「段数硬卡」的后果**：

1. `strokes < 3` → `无结构`
2. `0` 个有效中枢：
   - 单边启发式命中 → `单边上涨` / `单边下跌`
   - 有线段 → `盘整`（弱盘整/观察语义，主状态仍用「盘整」；可用 conf=low）
   - 否则 → `无结构`
3. `1` 个有效中枢 → `盘整`
4. `2+` 同向不重叠中枢 → `上涨趋势` 或 `下跌趋势`（**即使段数只有 4～6 也给趋势名**）
5. `2+` 重叠/方向混乱 → `盘整`

### 1.4 段数只影响置信/证据，不改主状态名

新增（或等价字段）：

| 字段 | 含义 |
|------|------|
| `structure_confidence` | `high` / `mid` / `low` |
| `structure_evidence` | 可选短串，如 `segments=5,pivots=2` |

**置信规则（建议，写入 config 可配）：**

趋势类（上涨/下跌趋势）：

- `seg_count >= trend_segs_high` → high  
- `seg_count >= trend_segs_mid` → mid  
- 否则 → low（**仍输出上涨/下跌趋势**）

盘整类：

- `seg_count >= consol_segs_high` → high  
- `seg_count >= consol_segs_mid` → mid  
- 否则 → low  

**日线 / 周线两套参数（禁止共用 11）：**

| 参数 | 日线短线建议 | 周线中线建议 |
|------|--------------|--------------|
| trend_segs_high | 8～11（默认 8） | 5～6（默认 5） |
| trend_segs_mid | 5～6（默认 5） | 3～4（默认 3） |
| consol_segs_high | 5（默认 5） | 3（默认 3） |
| consol_segs_mid | 3（默认 3） | 2（默认 2） |

更推荐实现路径：**趋势/盘整主名完全由中枢拓扑决定；上表只调 conf。**

### 1.5 展示契约（业务）

- 主显示：`structure_type`（如 `上涨趋势`）
- 可选旁注：`structure_confidence=low` → 渲染 `上涨趋势(段偏少)`  
- **禁止** 主显示 `线段不足5/11`
- 报告：
  - 理论区缠论 ← **仅** `chanlun_midline`（周线优先）
  - 短线专家缠论 ← **仅** 日线 fusion / `chanlun_daily`
  - 禁止交叉引用

### 1.6 双源（业务已定，代码保持）

| 源 | 计算 | 用途 |
|----|------|------|
| 短线 | 日 K `chanlun_strategy` | fusion、短线专家、买卖点 |
| 中线 | 周 K `chanlun_strategy_midline` | 理论：缠论 |

`classify_structure` 可接收 `timeframe="daily"|"weekly"` 选 conf 门槛参数。

---

## 2. 代码逻辑映射（必须对应）

| 业务规则 | 代码落点 |
|----------|----------|
| 消灭线段不足主状态 | `chan_core.classify_structure` 删除/改写返回 `线段不足*` 的分支 |
| 中枢拓扑定名 | 保留现有 zones 同向/重叠判断；2+ 同向 → 直接 `上涨趋势`/`下跌趋势` |
| conf / evidence | `classify_structure` 返回字段；`chanlun_analysis` 透传 |
| 日/周门槛 | `config.py` 新常量；`classify_structure(..., timeframe=)` 或 `params=` |
| 中线/短线引用分离 | `report_core` 理论只读 midline；短线只读 daily fusion |
| 包装层 unwrap | 已有 `unwrap_chan`；理论行用 `format_chanlun_theory_line` 读 midline |
| 展示段偏少 | `format_chanlun_theory_line` 或 report 拼 `(段偏少)` 当 conf=low |

### 不要做

- 为凑 11 段去改 `build_segments` 乱切
- 日周共用 `MIN_SEGMENTS_TREND=11` 硬失败
- 用线段不足当用户错误码

---

## 3. 回归标准（Reviewer 验收）

1. 正常逻辑下 `structure_type` **几乎不再** 为 `线段不足*`（单测 0 处主状态期望线段不足）  
2. 2 上移中枢 + 4～6 段 → `上涨趋势`，conf 可为 low  
3. 周线样本可稳定给出 盘整/趋势，而非长期线段不足  
4. 下游 unwrap 不读空  
5. 单测：日线趋势不因 seg&lt;11 变线段不足；周线参数独立；报告理论≠短线同源冒充（timeframe 字段）

---

## 4. Agent 分工

### Agent A — Implementer

1. 读本计划 + 现有 `classify_structure` / 相关单测  
2. 改 `config.py` 增加日/周 conf 门槛常量  
3. 改 `classify_structure` 实现 §1.2–1.4  
4. 透传 conf/evidence 到 `chanlun_analysis` 输出  
5. 更新 `format_chanlun_theory_line` 支持 conf 旁注  
6. 改 `test_chan_core.py` 中线段不足断言；补新单测  
7. 跑 pytest 相关文件  
8. 回报：改动列表、测试结果、业务-代码对照表  

### Agent B — Reviewer（只读 + 测，默认不改代码）

对照本计划 §1–§3：

- [ ] 业务：主状态无线段不足  
- [ ] 业务：2 中枢同向 + 少段 = 趋势  
- [ ] 代码：classify 无 11 硬失败路径  
- [ ] 代码：日周参数分离或拓扑-only conf  
- [ ] 代码：midline/daily 报告引用不交叉  
- [ ] 单测覆盖 §3  
- [ ] 无乱切线段  

产出：`docs/audit/chan-structure-classify-review.md`（通过/有条件通过/不通过 + P0/P1）

---

## 5. 协作流程

```text
1. 本计划落盘（已完成）
2. Implementer 实施 P0
3. Reviewer 审查 + 跑测
4. 阻塞项回 Implementer
5. 人工抽一眼华工：理论缠 ≠ 短线缠（若结构不同）
```
