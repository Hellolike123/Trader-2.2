# Full-repo adjudication — 2026-08-01

> **Role**: ADJUDICATOR merge of BUSINESS audit + CODE audit  
> **Branch**: `cursor/full-repo-audit-fix-54bc` (base `bc03b78`)  
> **法源优先级**: `BUSINESS.md` §2.0 岗位合同 → `docs/designs/resonance-and-orchestration.md` → 代码实现 → 旧文/AGENTS_DEEP 叙事  
> **范围**: 裁定 MUST-FIX-NOW vs DEFER；不在此文档内落地实现（由 write agent 执行）

---

## 0. Cross-check verdict (TOP claims)

| ID | Claim | Verdict | Evidence |
|----|-------|---------|----------|
| **B-F1** | `synthesize_midline_verdict` remaps stage via wyck×chan matrix（吸筹+SOS→主升）；`stage_line` / resonance 读 remapped stage | **CONFIRMED HIGH** | `conclusion_block.synthesize_midline_verdict` `(wyck_dir,chan_dir)=(1,1)→stage="主升"`；SOS→`strong_bull`→`wyck_dir=1` 即使 `phase=accumulation_*`（`wyck_phase_short=吸筹`）。`attach_short_midline` 写 `conclusion["stage_line"]=verdict["stage"]`、`midline_stage`。`resonance._background_stage` **优先** `midline_stage` / verdict.stage |
| **B-F2** | structure post 可仅凭 `mid_key_prices` 周线区绿灯 | **CONFIRMED MED** | `resonance._price_in_zones` 遍历 `key_prices` **与** `mid_key_prices`；`_eval_structure` 在 `in_zone` 且无卖点时可 `_post(True,"现价在回踩/买点区")` |
| **B-F3** | `wyckoff_midline_bias` 被日线 `major_stage` 洗 UT | **CONFIRMED MED（路径限定）** | `wyckoff_midline_bias(..., major_stage=)`：`major_stage in (主升,蓄势偏强)` 时 UT 不抬 `strong_bear`。`_midline_view_from_theory` / `midline_theory_dirs` 传入日线 `stage_result["major_stage"]`。**注**：`synthesize_midline_verdict` 自身调用 **未**传 `major_stage`（矩阵路径不受此洗） |
| **B-F4** | 阶段三真相（template major_stage / verdict matrix / wyckoff phase） | **CONFIRMED（并入 B-F1）** | 面板「阶段：」← verdict；威科夫行← `phase_label`；池/仓位仍读 `major_stage` |
| **C-F01** | `buy_point_lifecycle` 无锁 RMW | **CONFIRMED P0** | `_load_store` / `_save_store`：原子 `tmp.replace` 但 **无 flock**；`save_failed_record` / `clear_failed_record` / `reconcile_with_store` 读改写竞态 |
| **C-F02** | `track` / `low_buy_triggered` → cost → 假持仓/水位 | **CONFIRMED P1** | `signal_core.read_signals_for_report`：`sig_type in ("low_buy_triggered","track")` 取 trigger.price 为 `cost_price`；`attach_stage_pack`：`has_position = cost_price > 0`；`report_builder`：`_signal_cost_price > 0` 即设 `trailing_ratchet_symbol` → 无真实持仓也可落 watermark |
| **C-F03** | `t0_account` / `t0_ledger` 引擎仍在 skill 包 | **CONFIRMED P1** | `01-功能包-packages/t0/scripts/t0_account.py`（~245行）、`t0_ledger.py`（~145行）为完整实现；同目录 `t0_core.py` 等已是 identity shim。违 AGENTS「引擎只在 trader_shared / 包内 shim」 |
| **C-F04** | cards→classic silent fallback | **CLOSED（2026-08-02 / #53）** | 历史：曾 warning 后 classic。现行：生产失败 → `cards_failed` 中性占位，**禁止**静默 classic（`fusion-no-silent-classic`）；BUSINESS §2.7 已改 |
| **C-F05** | decision_stack 失败缺 fail-closed `decision_view`；persist 退纪律 | **CONFIRMED P1** | `attach_decision_stack` 外层 `except` 补 cards/resonance，**不写** `decision_view`；仅内层 `apply_decision_view` 失败才 setdefault fail-closed。`decision_persist_fields` 无 DV 时回退 `discipline.allow_new_entry` |
| **C-F06** | chip / wyckoff_phase / add-store 持久化竞态 | **CONFIRMED P1** | `chip_migration_monitor`：atomic replace 无锁；`wyckoff_phase._save_phase_state`：直接 `open(...,"w")` 非原子且无锁；`position_add_store._save`：atomic 但进程间无 flock（有线程锁不够） |
| **C-F07** | `mid_bullish_downgrade` 仍接线松开纪律 | **CONFIRMED P2** | `attach_short_midline`：中线 `midline_bias==bull` 时把「空仓/止损」改「减1/3」——违「纪律只收紧」 |

DOC claims（soft admit / AGENTS_DEEP fusion commander / fusion_regime docstring / P0 overclaim）→ 见 §3；代码 MUST 落地后已回写 BUSINESS §4.2/§5.1、output-template、AGENTS_DEEP（软入池 + fusion 仪表 + 阶段=周威科夫）。

---

## 1. MUST-FIX-NOW（8 项，有序）

实施顺序 = 依赖与伤害面：先阶段/出手契约，再持久化正确性，再架构铁律。

### M1 — 中线阶段钉死周线威科夫（B-F1 + B-F4）

- **Files / fns**: `conclusion_block.synthesize_midline_verdict`；调用方 `report_pipeline/attach_short_midline.py`（`stage_line` / `midline_stage`）；消费方 `resonance._background_stage` / `_eval_background`；渲染 `report_renderer/short_midline.py`「阶段：」行
- **Fix**: `verdict["stage"]`（及写入面板的 `stage_line` / `midline_stage`）**只**取周线威科夫阶段短词（现有 `_PHASE_SHORT` / `wyck_phase_short`）；周线不足/`phase_tr_gated` → `"无阶段"`（或等价不参与定论），**禁止** `(wyck_dir,chan_dir)` 矩阵改写 stage。矩阵仅可驱动 `bias` / `confidence` / `note`（结构副读）
- **Acceptance**（法源 `BUSINESS.md` §2.0 铁律1、§2.1「缠论不定中线阶段」、§2.2）:
  1. 单测：`phase=accumulation_*` + `sos_signal` + 周线缠多 → `stage` 仍为「吸筹」（不得「主升」）
  2. `phase=markup` →「主升」；`distribution_*` →「派发」；不足 →「无阶段」且 resonance background fail-closed
  3. 报告「阶段：」与威科夫 `phase` 同源；`major_stage`（日线四阶段）不得冒充中线阶段行
  4. golden / output-template 若骨架变了再刷（按 AGENTS 改输出清单）

### M2 — 买点盖生命周期锁内 RMW（C-F01）

- **Files / fns**: `buy_point_lifecycle._load_store` / `_save_store` / `save_failed_record` / `clear_failed_record` / `reconcile_with_store`
- **Fix**: 对齐 `structure_core.save_trailing_watermark`：`fcntl.flock(LOCK_EX)` 包住 load→mutate→tmp/fsync/replace；失败不得吞掉导致半写丢 failed 记录
- **Acceptance**（法源 `docs/designs/buy-point-lid-lifecycle.md` L2；AGENTS 持久化表）:
  1. 并发写测：两进程同时 `save_failed_record` 不同 symbol → 两者均保留
  2. `failed` 记录不被并发 `clear`/`save` 互相覆盖丢失
  3. 路径仍尊重 `TRADER_BUY_POINT_LIFECYCLE_PATH`

### M3 — 信号流不得冒充持仓成本 / 水位（C-F02）

- **Files / fns**: `signal_core.read_signals_for_report`（cost 提取）；`attach_stage_pack`（`has_position`）；`report_builder`（`trailing_ratchet_symbol` 门控）；相关单测
- **Fix**:
  1. **禁止**仅凭 `track` / `low_buy_triggered` 填 `cost_price` / `has_position`
  2. 持仓成本仅来自显式 `--cost` / 真实持仓源（如 `position.json` / 用户入参）；信号流可另字段展示「最近触发价」但不得驱动持仓态
  3. `trailing_ratchet_symbol` **仅**真实 `has_position` 时启用（AGENTS：无仓不落水位）
- **Acceptance**（法源 AGENTS「ATR 移动止损水位（仅持仓票）」；BUSINESS 持仓语义）:
  1. 仅有 `track`/`low_buy_triggered` 的 signals.jsonl → `has_position=False`、`cost_price=0`、不写 watermark
  2. 显式 cost>0 → 持仓路径与水位只紧不松仍成立
  3. 策略 `manage` 不因历史 T0 触发误进 active

### M4 — decision_stack 失败 fail-closed（C-F05）

- **Files / fns**: `report_pipeline/attach_decision_stack.attach_analysis_decision_stack`；`signal_core.decision_persist_fields`；渲染/日线裁定消费点
- **Fix**:
  1. 外层 stack 失败也必须写入 `decision_view`：`allow_new_recommend=False` + 可诊断 `summary_line`
  2. persist：**禁止**在缺 DV 时用 `discipline.allow_new_entry` 冒充 `allow_new_recommend`（保持未知或显式 false；与「出手听 decision_view」一致）
- **Acceptance**（法源 `BUSINESS.md` §2.0 铁律4；`resonance-and-orchestration.md` 新开铁律；AGENTS decision_view）:
  1. monkeypatch `match_strategies` / `apply_decision_view` 抛错 → report 仍有 `decision_view.allow_new_recommend is False`
  2. `decision_persist_fields` 在无 DV 时不写出「允许新开」真值
  3. 日线裁定 / 面板出手不因缺 DV 偏松

### M5 — 结构岗价区只认日线结构（B-F2）

- **Files / fns**: `resonance._price_in_zones` / `_eval_structure`
- **Fix**: 回踩/买点区绿灯 **只**读日线 `key_prices`（及日线缠论买点像）；`mid_key_prices` 周线区不得单独绿结构岗。中线价区留给背景/中线叙事，不洗白短线结构岗
- **Acceptance**（法源 `BUSINESS.md` §2.0「短线交易=日线缠论」；`resonance-and-orchestration.md` structure 岗）:
  1. 仅有周线 `mid_key_prices` 区间命中、无日线买点/日线区 → structure `ok=False`
  2. 日线买点像 + 日线区 → 可绿（既有正式一/二/三类规则不变）
  3. 既有 `test_a5_like_buys_do_not_green_structure_post` 等回归保持

### M6 — 中线威科夫偏置禁止日线 major_stage 洗 UT（B-F3）

- **Files / fns**: `conclusion_block.wyckoff_midline_bias`；`_midline_view_from_theory` / `midline_theory_dirs`；`attach_short_midline` 传入参
- **Fix**: 中线路径调用 **不得**传入日线 `major_stage` 做 UT 洗盘豁免；若需「主升中 UT=洗盘」，只允许基于**周线**威科夫 phase（如 `markup` / 周线阶段词），不得用日线四阶段
- **Acceptance**（法源 `BUSINESS.md` §2.0：日线不得冒充中线状态）:
  1. 周线 UT 非 premature + 日线 `major_stage=主升` → bias 仍可 `strong_bear`（除非周线 phase 本身为 markup 且产品明确豁免）
  2. `_midline_view_from_theory` 与 `synthesize_midline_verdict` 对 UT 态度一致、不依赖日线 stage
  3. 单测锁定「日线主升不得洗周线 UT」

### M7 — T0 账户/台账引擎迁入 shared（C-F03）

- **Files**: 新建 `trader_shared/t0_account.py` / `t0_ledger.py`（或合并进既有 t0_*）；`01-功能包-packages/t0/scripts/t0_account.py` / `t0_ledger.py` 改为 identity shim（与 `t0_core.py` 同构）；更新 import / pack_all
- **Acceptance**（法源 AGENTS 铁律1「引擎只在 trader_shared」）:
  1. skill 包文件为 shim：`sys.modules[__name__] = _impl`
  2. monkeypatch `trader_shared.t0_account` 对包入口生效
  3. `pack_all` / 既有 t0 测通过

### M8 — 其余 JSON 持久化锁齐（C-F06，与 M2 同模式）

- **Files / fns**: `chip_migration_monitor._load_history/_save_history`；`wyckoff_phase._load_phase_state/_save_phase_state`；`position_add_store._load/_save`（加进程 flock）
- **Fix**: 统一「锁 + 读改写 + tmp/fsync/replace」；`wyckoff_phase` 必须先改成原子 replace（当前裸 `open("w")` 最差）
- **Acceptance**（法源 AGENTS 持久化表；与 trailing watermark 同级正确性）:
  1. 并发写不同 key 不丢记录
  2. `wyckoff_phase.json` 无截断半文件
  3. 加仓日 store 跨进程不丢

---

## 2. DEFER（为何现在不做）

| ID | Item | Why defer |
|----|------|-----------|
| **D1 / C-F04** | cards→classic fallback | BUSINESS §2.7 **允许** warning 后 classic；已有 warning。若要「cards 失败硬失败」属产品加严，另开任务，非审计违约 |
| **D2 / C-F07** | `mid_bullish_downgrade` 松开空仓 | 确违「纪律只收紧」，但属持仓减仓语义调档、非阶段/新开主契约；M1–M4 优先。随后单独：删除该分支或改为「仅文案提示、不改 discipline.action」 |
| **D3 / C-F08** | pool `watch` 仍按 `status==执行` 分流 | 分道（lane）已是注意力主序；`执行` 为旧三关诊断残留。改 watch UX 不阻塞出手正确性 |
| **D4 / C-F09** | strategy `entry_reason` 文案 | ✅ 已改为 `可扳机`（闸门仍 `executable=True`；避免与 T0「可执行」禁令混淆） |
| **D5 / C-F10** | `FUSION_LOG_ONLY` import-time 常量 | 调试开关；生产默认 false。改为函数内读 env 属洁癖 |
| **D6 / C-F11** | 其它 P2（日志噪音、死路径注释等） | 不改决策正确性 |
| **D7** | 全面刷新全部 golden / 用户指南旧「三关硬拒」叙事页 | DOC 批处理；代码以 M1 验收测为准，骨架变了再刷 template |
| **D8** | Fusion override / Bayesian 深改 | 已默认关；不在本审计 MUST 范围 |

---

## 3. DOC 矛盾裁定（冲突优先级）

冲突法源：`BUSINESS.md` 文首「冲突时以 §2.0 与代码为准」+ `resonance-and-orchestration.md`「旧文 fusion 总司令视为过时」。

| 矛盾 | Winner | Loser / action |
|------|--------|----------------|
| 入池 **软门槛+分道** vs BUSINESS §1.3 / 旧指南「三关硬拒」 | **软门槛 wins**（代码 `scoring.record_from_report`：`admission_result` 恒「入池」，旧三关仅 `admission_diag`；AGENTS / resonance 设计已写软门槛） | 回写 BUSINESS §1.3：流程改为「软入池 → 分道/排序 → …」；`user-guide`「衰退拒绝入池」改为「可进池但 lane=先别碰 / 诊断拒绝」 |
| AGENTS_DEEP §5.5「融合层=终极裁判」 vs §2.0 / 共振法源 | **§2.0 wins**：fusion=`weighted_score` **仅仪表**；出手=`decision_view` | 删改 AGENTS_DEEP「终极裁判 / 决策融合层打穿」叙事；图注「决策融合层」改为「融合仪表」 |
| `fusion_regime` 模块 docstring「决策阈值映射」 vs 仪表定位 | **仪表 wins** | docstring 改为「仪表权重/动作映射（不覆盖 theory_status；出手听 decision_view）」；权重表本身可保留 |
| 各 audit「P0 已完成」过度宣称 vs 本裁定仍见 P0 持久化洞 | **本裁定 wins** | 旧 P0 报告加注「历史批次；持久化锁/阶段钉死以 2026-08-01 adjudication 为准」；不改写历史结论数字，只加指向 |

DOC 批处理可与 M1–M8 **并行**，但不阻塞 write agent 先交代码 MUST。

---

## 4. Ordered fix plan（write agent）

```text
Phase A (contract correctness)  M1 → M5 → M6
Phase B (safety / state)        M3 → M4 → M2 → M8
Phase C (architecture iron)     M7
Phase D (docs, parallel OK)     §3 DOC table
Phase E (defer queue)           D2 mid_bullish_downgrade → D3/D4 文案
```

依赖说明：
- M5/M6 可与 M1 同 PR 或紧随：皆属中线/共振岗位合同
- M3 先于依赖 `has_position` 的策略/水位测
- M2/M8 同持久化模式，可共用小 helper（若已有 `cache_utils`/`DataManager` 锁原语则复用，禁止再造第三套）
- M7 独立，避免与 M1 大 diff 缠车

验证门槛（每项落地后）：
- 对应单测绿
- `scripts/run-gate-tests.sh` 离线子集绿
- 改面板骨架则刷 golden +（必要时）`output-template.md` / BUSINESS §5.1

---

## 5. Explicit instructions for WRITE agent

1. **只做 MUST-FIX M1–M8**；勿顺手重构 fusion 权重、勿删 classic 路径、勿改 T0 v2 产品叙事以外的大面积文案。
2. **法源优先**：改阶段/共振时先满足 `BUSINESS.md` §2.0；禁止发明「缠论领先→主升初期」类回潮。
3. **M1**：矩阵可留 bias/confidence；`stage` 字段与面板阶段行必须 = 周线威科夫短词；补单测锁 吸筹+SOS≠主升。
4. **M3**：切断 `track`/`low_buy_triggered`→`cost_price`/`has_position`/`trailing_ratchet`；保留信号展示若需要请用独立字段。
5. **M4**：任何 decision_stack 异常路径都要有 fail-closed `decision_view`；persist 不得用纪律字段冒充推荐新开。
6. **M2/M8**：锁模式对齐 `structure_core.save_trailing_watermark`（flock + RMW + fsync/replace）。
7. **M5**：`_price_in_zones` 结构岗路径去掉对 `mid_key_prices` 的单独绿灯（或拆函数：结构岗日线-only）。
8. **M6**：中线调用链停止传入日线 `major_stage` 洗 UT；若保留豁免，键必须来自周线 phase。
9. **M7**：引擎搬 `trader_shared/`，包内 identity shim；跑 pack/相关测。
10. **DOC（§3）**：可另 commit；BUSINESS §1.3 与 AGENTS_DEEP §5.5 按上表改 Winner 侧。
11. **不要**实现 DEFER 项除非它阻塞 M1–M8 测试。
12. 完成后：相关测 + gate 子集；按仓库惯例 commit（本 adjudication 已单独提交）。

---

## 6. Summary for parent

**MUST-FIX-NOW**: M1 阶段钉威科夫 · M2 lifecycle 锁 · M3 假持仓/水位 · M4 decision_view fail-closed · M5 结构岗日线区 · M6 禁日线洗周线 UT · M7 t0_account/ledger 迁 shared · M8 其它 JSON 锁  

**DEFER**: classic 回退（法源允许）· mid_bullish_downgrade · FUSION_LOG_ONLY · 其它 P2/DOC 深刷  
（已落地：watch 优先 `lane==ready`；策略 `entry_reason=可扳机`）  

**DOC winners**: 软入池+分道 · fusion 仅仪表 · fusion_regime 文案降级为仪表 · 本裁定覆盖历史 P0 过度宣称  

**本文件**: `docs/audit/full-repo-adjudication-2026-08-01.md`
