# 方案 B：缠论纪律层拆分实施计划

> 状态：**P0 已实施**（B1–B6；Review APPROVE 见 docs/audit/chan-discipline-b-review.md）  

> 日期：2026-07-10  
> 选型：**B** — `chan_discipline` + 通用门控（mistery_gate）+ **merge 只收紧**  
> 适用：**中线 + 短线**（各读各字段，仓位可分 cap）  
> 原则：不新开缠论大脑；不重写笔/段；纪律只收紧不放宽  
> 关联：`docs/discipline-layer-copy-plan.md` · `docs/mid-short-dual-track-plan.md` · 桌面操盘建议（可入库 `docs/chan-ops-playbook.md`）

---

## 0. 目标与非目标

### 0.1 目标

1. 物理拆分：  
   - **通用纪律** → `mistery_gate`（四不做/H 硬否决、520/失效、阶段×动能主表、盈亏比 H5 等）  
   - **缠论相关纪律** → 新建 `trader_shared/chan_discipline.py`  
2. **merge**：`merge_discipline(gate, chan_d)` → 单一出口 `report["discipline"]`，**只取更严**。  
3. **中短都适用**：chan 层读周线回踩/看法 + 日线买点/结构；可输出 mid/short 分 cap，P0 可先合并为一个 `allow_new_entry`。  
4. **真砍仓**：`suggested_pct = min(原, cap)`；禁止新开时开仓类 action 不得保留「试探买/挂单」语义。  
5. 单测：区外、派发冲突、fusion 观望不能改买、中线偏空否决、merge 单调性。

### 0.2 非目标

- 不改 `chan_core` 分型/笔/段算法。  
- 不在 `chan_core` 内写「禁止开仓」。  
- 不新中线主引擎。  
- 不把陪练 mi 人设写进报告。  
- P0 不强求中/短两套完整仓位 UI（字段预留即可）。

---

## 1. 架构

```text
                    ┌─ weekly: mid_key_prices / mid_view / zones
chan 日/周字段 ─────┤
                    └─ daily: buy_points / structure_type / low_zone
                              │
                              ▼
                    apply_chan_discipline(...)     ← 新建
                              │
fusion/stage/RR/520 ──► compute_mistery_gate(...)  ← 变瘦（迁出缠相关）
                              │
                              ▼
                    merge_discipline(gate, chan_d)  ← 只收紧
                              │
                              ▼
              report["discipline"] + 出手文案 + suggested_pct 裁剪
```

### 1.1 只收紧（merge 铁律）

| 维度 | 更严方向 |
|------|----------|
| allow_new_entry | False 覆盖 True |
| action | 开仓类 → 观望/不做/减仓；禁止 观望→买入 |
| suggested_pct_cap | 取 **min** |
| notes | **并集**（去重保序） |

开仓类 action 集合（收紧时砍掉）：  
`轻仓试错` / `回踩低吸` / `持有`（作新开/加仓语义时）→ 观望；  
`减仓` / `止损离场` / `不做` 不被「变松」替换成开仓。

```text
rank 从松到严（示意，用于 merge action）：
  持有 / 回踩低吸 / 轻仓试错  <  观望  <  减仓  <  止损离场 / 不做
取 rank 更大（更严）者；并列时优先非开仓。
```

---

## 2. 模块契约

### 2.1 `apply_chan_discipline(inputs) -> dict`

**文件：** `02-共享模块-shared/trader_shared/chan_discipline.py`

**输入（均可选，缺则跳过对应规则）：**

```text
current
# 中线回踩（优先）
mid_pullback_low, mid_pullback_high
mid_view                    # 周线看法文案
mid_quality                 # full|partial|insufficient
structure_confidence        # 周线缠 conf
# 短线/日线
buy_point_types             # list[str] 如 一类买/二类买/三类买
structure_type_daily        # 盘整/上涨趋势/...
structure_type_weekly
low_zone_lower, low_zone_upper   # P1 短线带，P0 可不启用
# 公共
data_status, fusion_disagreement, fusion_confidence
major_stage
chip_migration_warning, fund_flow_outflow_veto
has_position
suggested_pct               # 仅用于算 cap 上限参考
max_position_pct            # stage 上限
```

**输出：**

```python
{
  "allow_new_entry": bool,           # P0 总闸（中短合并）
  "allow_new_entry_mid": bool,       # 预留
  "allow_new_entry_short": bool,     # 预留
  "entry_block_reason": str | None,
  "suggested_pct_cap": int,          # 0–50
  "suggested_pct_cap_mid": int | None,
  "suggested_pct_cap_short": int | None,
  "action_override": str | None,     # 仅收紧建议，可为 观望
  "discipline_notes": list[str],
  "rules_fired": list[str],          # 调试：pullback_out / mid_weak / range / ...
}
```

### 2.2 从 `mistery_gate` **迁出**到 chan_discipline 的规则

| 规则 | 现位置（约） | 迁后 |
|------|--------------|------|
| 中线回踩区外不新开 | gate | **chan** |
| 中线看法偏空否决主开仓 | gate | **chan** |
| mid_quality / structure_confidence 低置信 | gate 部分 | **chan**（缠侧证据） |
| 盘整禁趋势重仓（P1） | 无 | **chan** |
| 一/二/三买 cap 阶梯（P1） | 无 | **chan** |
| 筹码/资金否决新开 | gate | 可留 gate 或 chan；**建议 chan 也读，merge 并集**（避免漏） |

### 2.3 `mistery_gate` **保留**

| 规则 | 说明 |
|------|------|
| H1–H7 硬否决 | 大盘/衰退/派发表/无止损/RR/追高/摊平等 |
| 阶段×动能主表 | 蓄势/主升/派发/衰退 × 动能 |
| 520 / invalidation 文案 | 失效行 |
| 类型闸 style | 趋势/情绪/不明 |
| fusion_disagreement / data_status 低置信 | 可与 chan 重复判定，merge 取严 |

P0 搬家策略：  
- **先实现 chan_discipline 含回踩+中线偏空+（可选）低置信缠侧**  
- gate 内 **删除或 `# migrated` 关掉** 对应块，避免双触发矛盾（notes 重复可接受，action 双砍需幂等）

### 2.4 `merge_discipline(gate_out, chan_out) -> discipline`

**文件：** 同 `chan_discipline.py` 或 `discipline_merge.py`（建议同文件减少文件数）

```text
allow_new_entry = gate允许新开 and chan.allow_new_entry
  （gate：action 不在 开仓类 且 cap>0 可视为允许；或显式字段）

action = stricter(gate.action, chan.action_override)

suggested_pct_cap = min(
  gate.position_cap_pct,
  chan.suggested_pct_cap,
  max_position_pct or 50,
)

notes = unique(gate.notes.split + chan.discipline_notes)
entry_block_reason = chan.entry_block_reason or 从 notes 抽首条
```

### 2.5 `run_analysis` 挂载顺序

```text
1. fusion / stage / mid_key_prices / mid_view 文案
2. gate = compute_mistery_gate(... 无回踩/无 mid_view 缠规则 ...)
3. chan_d = apply_chan_discipline(... 周回踩 mid_view 买点 盘整 ...)
4. disc = merge_discipline(gate, chan_d)
5. report["mistery_gate"] = gate          # 兼容
6. report["chan_discipline"] = chan_d    # 调试
7. report["discipline"] = disc           # 产品主字段
8. 若 not disc.allow_new_entry:
     出手用观望语义；suggested_pct = 0（无仓）或 min(原, cap)
9. conclusion / render 读 disc.discipline_notes + 出手
```

**只收紧：** 若 gate 已是观望，chan 不得改为轻仓试错。

---

## 3. 中线 / 短线规则归属（B 内）

| 规则 | 中线输入 | 短线输入 | P0 |
|------|----------|----------|-----|
| 回踩区不新开 | mid_pullback_* | — | **必做** |
| 中线看法偏空 | mid_view | — | **必做** |
| 低置信 | mid_quality, 周 conf | disagreement, fusion conf, data_status | **必做**（可与 gate 分摊） |
| 冲突风控 | stage/chip/fund + mid 偏多 | 有买点时 notes | **必做**（说明可在 merge/conclusion） |
| 一买试三买主 | 可选周买点 | buy_point_types | P1 |
| 盘整禁重仓 | structure_type_weekly | structure_type_daily | P1 |
| 中枢位置展示 | zones 周 | zones 日 | P2 展示 |
| 短线 low_zone 门禁 | — | low_zone_* | P1 可选第二道 |

P0 `allow_new_entry`：  
中线否决 **或** 短线侧总闸否决 → False（主开仓禁止）。  
有持仓：不拦减仓/止损；只拦新开/加仓类。

---

## 4. 实施切片

| 切片 | 内容 | 完成定义 |
|------|------|----------|
| B1 | 新建 `chan_discipline.py`：回踩 + mid_view 弱 + 输出契约 | 单测绿 |
| B2 | `merge_discipline` + 只收紧单测 | fusion 观望不能变买 |
| B3 | 从 `mistery_gate` 删除已迁规则；入参瘦身 | 无双份冲突逻辑 |
| B4 | `run_analysis` 接线 + `report["discipline"]` + 砍 suggested_pct | 集成字段存在 |
| B5 | `conclusion_block` / `report_core` 优先读 discipline.notes | 出手区可见原因 |
| B6 | 单测全家桶 + 回归 test_mistery_gate / mid short | pytest 绿 |
| B7（P1） | 买点阶梯 + 盘整禁重仓 | 另开 PR 可 |

---

## 5. 验收（代码层）

| ID | 要求 |
|----|------|
| T1 | current 在回踩区外 + 日线一类买语义 → allow_new_entry=False，无「可按买点挂」 |
| T2 | 派发 + 缠多/三类买 → notes 含冲突或风控，不允许新开 |
| T3 | gate action=观望 时 merge 后不得变轻仓/回踩/持有 |
| T4 | report 含 `discipline`（及可选 chan_discipline） |
| T5 | 渲染/原因可见「不在回踩区」或「中线看法偏空」类 |
| T6 | 中线 mid_view 暂缓 → allow_new_entry=False |
| T7 | low conf → cap 下降或观望 |

---

## 6. 与双源 Agent 分工（写进协作）

| 他做 | 纪律 B 做 |
|------|-----------|
| 日/周 chan 字段干净 | apply_chan_discipline 只读 |
| 报告双列展示 | 开仓门禁用 zone/回踩，不用「有一买」单独决定 |
| 段数 conf | 读 conf，不读线段不足主串 |
| **禁止在 chan_core 写禁止开仓** | **唯一开仓裁剪在 merge 后** |

---

## 7. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 双模块漏规则 | 搬家清单打勾；迁移期 gate 与 chan 暂双重 notes 但 action 只经 merge |
| 过严全市场不做 | 缺回踩数据 → 跳过回踩规则（与现一致） |
| 名字 mistery 残留 | 对外 discipline；对内可保留 mistery_gate 兼容 |

回滚：`run_analysis` 只调 gate、跳过 chan+merge 即可降级。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-10 | 用户确认策略中短通用 + 选型 **B**；本计划落盘 |
