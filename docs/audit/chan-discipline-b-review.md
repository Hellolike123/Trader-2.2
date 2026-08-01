# 方案 B 纪律拆分 Review

> 日期：2026-07-10  
> 规格：`docs/plans/done/chan-discipline-b-plan.md`  
> 审查范围：只读验收 Implementer 拆分；不改业务代码  
> 总判：**APPROVE**
>
> **路径勘误（本周期维护）**：报告挂接 / 渲染为 `attach_short_midline` →
> `report_renderer/short_midline.py`（历史文中 `report_core` 手拼路径已迁）。

---

## 总览

方案 B P0（B1–B6）已落地：`chan_discipline` 承载缠相关纪律，`mistery_gate` 保留 H 硬否决 / 阶段动能主表 / 520，`merge_discipline` 只收紧；现生产按 gate→chan→merge 挂在 `attach_short_midline`（历史验收记 monolith `run_analysis`），结论与报告消费 `discipline`。指定 pytest **61 passed**。红线三项均满足。

---

## §5 验收勾选（T1–T7）

| ID | 要求 | 结果 | 证据 |
|----|------|------|------|
| T1 | current 在回踩区外 + 日线一类买语义 → `allow_new_entry=False`，无「可按买点挂」 | **PASS** | `apply_chan_discipline`：`in_pb is False` → `_block_new(..., "pullback_out")`（`chan_discipline.py` L185–187）；单测 `TestT1PullbackOutside`；execution 文案走 `观望` → `gate_action_to_execution_text` 为「现价不买 · 不追」，不含「可按买点挂」 |
| T2 | 派发 + 缠多/三类买 → notes 含冲突或风控，不允许新开 | **PASS** | `stage in ("派发","衰退")` → `_block_new` + 有 `buy_point_types` 时 `stage_buy_conflict` notes（L224–234）；`TestT2PaifaConflict` |
| T3 | gate `action=观望` 时 merge 后不得变轻仓/回踩/持有 | **PASS** | `merge_discipline`：`_stricter_action` + `allow_new` 否决开仓类 + gate 观望/不做双保险（L348–364）；`TestT3MergeTightenOnly` 含恶意 chan 放宽用例 |
| T4 | report 含 `discipline`（及可选 `chan_discipline`） | **PASS** | 现：`attach_short_midline` 写 `report["chan_discipline"]` / `report["discipline"]`（历史行号曾指 `run_analysis`）；异常路径 `setdefault` 兜底 |
| T5 | 渲染/原因可见「不在回踩区」或「中线看法偏空」类 | **PASS** | `conclusion_block` 优先 `entry_block_reason` / `discipline_notes`；`attach_short_midline` → `short_midline` 出手/原因行；`TestT5ReasonVisible` |
| T6 | 中线 `mid_view` 暂缓 → `allow_new_entry=False` | **PASS** | `_is_mid_view_weak` 含「暂缓/偏空/…」（L62–66）；`TestT6MidViewWeak` |
| T7 | low conf → cap 下降或观望 | **PASS** | 缠侧 `mid_quality`/`structure_confidence=low` → conf_block 否决；仅 fusion/data → conf_down 砍半（L195–214）；`TestT7LowConfidence` |

---

## 切片对照（B1–B7）

| 切片 | 结果 | 说明 |
|------|------|------|
| B1 `chan_discipline` 契约 + 回踩/mid_view | **PASS** | 输出字段含 `allow_new_entry` / mid·short 预留 / `suggested_pct_cap*` / `action_override` / `discipline_notes` / `rules_fired` |
| B2 `merge_discipline` 只收紧 | **PASS** | False 赢；action rank；cap=min；notes 并集去重保序 |
| B3 gate 迁出缠规则 | **PASS** | 回踩 / mid_view / 筹码资金 / 缠侧 conf 已 `# migrated` 注释并删除逻辑；`test_mistery_gate` 迁出回归 |
| B4 报告挂接 + 砍仓（现 `attach_short_midline`） | **PASS** | 顺序 gate→chan→merge；`allow_new_entry=False` 时 `suggested_pct=0`（无仓）/ 禁止加仓语义（有仓） |
| B5 conclusion / report 读 discipline | **PASS** | `build_conclusion_block(discipline=…)`；`attach_short_midline` 出手用 conclusion.reason；失效优先 `discipline.invalidation` |
| B6 单测全家桶 | **PASS** | 见下方 pytest |
| B7 买点阶梯 + 盘整禁重仓 | **N/A（P1）** | 规格允许另开 PR；代码未伪装实现 |

---

## 红线

| 红线 | 结果 | 证据 |
|------|------|------|
| 未在 `chan_core` 写禁止开仓 | **PASS** | `chan_core.py` 无 `allow_new_entry` / `discipline` /「禁止开仓」匹配；开仓裁剪仅在 merge 后 + 报告挂接砍 `suggested_pct` |
| merge 只收紧（gate 观望不能变买） | **PASS** | `_OPEN_ACTIONS` 仅可被收紧；gate 观望/减仓/止损被强制保留；单测恶意 override「轻仓试错」仍得「观望」 |
| 无双模块 action 矛盾设计 | **PASS** | 缠规则单源在 chan；gate 不再产出「不在中线回踩区」「中线看法偏空」「筹码…」notes；阶段派发 gate H3 与 chan `stage_risk` 均为收紧侧，经 merge 幂等 |

---

## 关键代码核对

### `chan_discipline.py`

- 纯函数：`apply_chan_discipline` + 同文件 `merge_discipline`（符合「建议同文件」）。
- P0 必做：回踩区外、mid_view 弱、低置信（缠侧 hard / 通用 soft）、筹码/资金否决、派发/衰退冲突 notes。
- 缺回踩数据跳过（`in_pb is None`），与规格「过严全市场不做」缓解一致。
- 有持仓：`action_override=观望` 拦新开，不强制改减仓（减仓更严侧由 gate 保留）。

### `mistery_gate.py`

- 保留：H1–H7、阶段×动能主表、520/invalidation、style、RR、追高、fusion/data 通用低置信。
- 迁出清单与模块头注释一致；`in_midline_pullback` 固定 `None` 兼容字段，避免伪信号。

### 接线顺序（现生产：`attach_short_midline`；历史曾记 `run_analysis`）

```text
mid_key_prices / mid_view 文案
→ compute_mistery_gate（无回踩/mid_view/筹码入参）
→ apply_chan_discipline（周回踩 + mid_view + conf + chip/fund + stage）
→ merge_discipline
→ report[mistery_gate|chan_discipline|discipline]
→ 禁止新开时裁 suggested_pct / 出手语义
→ build_conclusion_block(discipline=…)
```

与规格 §2.5 顺序一致；挂接点见文首路径勘误。

### 消费链

- `conclusion_block`：`discipline` 优先于 gate 决定 action/cap；reason 注入 entry_block / 回踩 / 偏空 / 置信 / 筹码 / 资金。
- `attach_short_midline` → `short_midline.py`：出手/原因来自 conclusion；失效读 `discipline` 再回退 gate。

---

## Pytest

```bash
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_chan_discipline.py \
  02-共享模块-shared/tests/test_mistery_gate.py \
  02-共享模块-shared/tests/test_key_prices.py \
  02-共享模块-shared/tests/test_conclusion_midline.py \
  02-共享模块-shared/tests/test_report_mid_short_sources.py -q
```

**结果：61 passed in 0.20s**

---

## 阻断项

无。

---

## 非阻断建议

1. **fusion/data 低置信双读**：gate 与 chan 均读 `fusion_disagreement` / `data_status` / `fusion_confidence`，规格允许「可重复、merge 取严」。notes 可能重复同类文案；`_unique_notes` 可消完全相同串，语义近似串仍可能并列。可接受；若嫌吵可后续只在一侧保留 fusion 类 conf。
2. **`merge_discipline` cap 分支略绕**（L377–384）：逻辑正确但可读性一般，后续可压成「`not allow_new` 或非开仓 action → cap=0」。
3. **P1 预留**：`suggested_pct_cap_mid/short` 仍为 `None`，`allow_new_entry_mid/short` 与总闸同步合并——符合 P0；买点阶梯 / 盘整禁重仓勿在未开 PR 时半实现。
4. **集成冒烟（可选）**：单元与接线已绿；若有环境，可再跑一只真票 `final_report` 目视「出手」括号内是否出现回踩/偏空原因（非本验收阻断）。
5. **计划文档状态**：规格头仍写「规格待实施」，落地后可改为「P0 已实施」以免后人重复开工（文档维护，非代码缺陷）。

---

## 总判

**APPROVE** — 方案 B P0 纪律拆分符合 `chan-discipline-b-plan.md` 架构、契约、只收紧铁律与 T1–T7；红线无违规；指定测试全绿。可合并 / 进入后续 P1（B7）。
