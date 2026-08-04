# 阶段机滑窗结构撕裂点审计报告（wyckoff-epic-vol-phase-verif-handoff 方向 B）

- 日期：2026-08-04
- 法源：`wyckoff-epic-vol-phase-verif-handoff.md` §1 方向 B（B-M1~B-M4 / B-P1~B-P4）
- 关联：`wyckoff-epic-phase-unify-handoff.md`（P-M2/P-M3/P-M4）、`wyckoff-sos-epic-fde-handoff.md`（E）
- 结论速览：**1 个撕裂点（AR 子窗锚）→ 已统一（低风险 + 测试）**；其余 6 项论证为非撕裂 / 已统一 / 保留。

---

## 0. 审计对象与术语

`_detect_phase`（`trader_shared/wyckoff_phase.py`）在**主流程注入统一 SC 锚**（`tr_ctx.sc_anchor`，P-M2）的
前提下，对部分事件仍用 `_scan` / `_last` 在 `bars[start:start+window]` **子窗**上运行检测器。
P-M4 为防止「全序列索引进子窗越界」把子窗 ctx 中的 `sc_anchor` 剥掉（`_sub_ctx`），
于是消费 SC 锚的检测器在子窗内**重新冷启动计算自己的 SC 锚**——这就是「撕裂」的来源：
同一批数据，主流程与子窗可能给出两个不同的 SC。

「撕裂点」判定标准：检测器消费**跨切面结构锚**（SC/BC 等），且子窗重算结果可能与主流程
统一锚不一致。自包含检测器（只读 bars 自身，如 spring/compression）在子窗上求值属于
滑窗设计的固有语义，**不算撕裂**（与 spring/ut/sos 的历史定位语义一致）。

## 1. 撕裂点清单与逐项结论

### TP-1 / TP-2 — AR：子窗重算 SC 锚（**已统一**）

- 位置：`wyckoff_phase.py` `ar_found`（原 `_scan(_detect_ar, WYCKOFF_CLIMAX_ANCHOR_BARS+3)`）
  与 `ar_idx`（原 `_last(_detect_ar, ...)`）。
- 机制：`_detect_ar`（`wyckoff_events.py:1448`）经 `_find_sc_anchor(sub, _sub_ctx, ...)`
  在**子窗**上冷启动找 SC → 与主流程 `_detect_selling_climax`（完整序列 + I-M1 统一锚）可能
  给出**不同 SC** → AR 被绑到历史 SC 上（如：统一 SC2 后无 AR，但 30 根内历史 SC1+AR1
  被子窗检出 → 阶段机报「停止：SC+AR」）。
- 影响面：`ar_found`/`ar_idx` → `sc_ar_b_ctx`（Phase B 背景）→ `spring_premature` 次序判定 →
  `accumulation_a/b` 阶段 label（「SC+AR」vs「SC，箱体未成形」）。
- **结论：统一（B-M3，低风险）。** 实现：新增 `_ar_verdict()`——统一锚存在时把锚 remap 进
  `wide_bars` 局部索引（`sc_bar_idx - (len(bars)-len(wide_bars))`），单次 `_detect_ar(wide_bars,
  {**_sub_ctx, "sc_anchor": remapped})` 评估；锚出界（早于 lookback）→ 退化为 `signals.ar_signal`。
  无锚（孤立调用）→ 原滑窗重算原样保留（P-M3 向后兼容）。
  - 索引空间：`_detect_ar` 的 `ar_bar_idx` 天然是 `wide_bars` 相对索引，与 `spring_idx`（`_last`
    返回值）同空间，无需额外映射。
  - 不触碰 `_find_sc_anchor` / `_detect_ar` 主体（B-P3 ✓）；不改 `_scan_for_signal` /
    `_scan_last_event` 共用函数（B-P4 ✓）。
  - 测试：`tests/test_wyckoff_phase_timeframe.py::TestArUnifiedAnchorB`（B1：统一锚忽略历史
    SC；B2：统一 SC 后 AR 仍亮；B3：锚出界退化 signals；B4：无锚保持原滑窗）。
- 为什么这不算「擅自扩大改动面」：统一后 `ar_found` 在主流程路径 ≈ `signals.ar_signal`——
  而 `signals.ar_signal` 本就是主流程以**同一统一锚**在完整序列上的结论；子窗重算在锚存在时
  只会增加「非统一 SC 的 AR」，正是本 epic 要消灭的撕裂。改动仅发生在统一锚存在路径，
  无锚路径零改动，且被 `wyckoff_core.py` 全量回归（161 项）与 wyckoff 全量（397 项）锁定。

### TP-3 — ARE：子窗重算 BC 锚（**非撕裂，保留**）

- 位置：`are_found` / `are_idx`（`_scan/_last(_detect_are, ...)`）。
- 机制：`_detect_are`（`wyckoff_events.py:1747`）复用 `_detect_buying_climax` 找 BC。
  **BC 检测器自包含**（不消费任何跨切面锚；无 I-M1 式统一 BC 锚），子窗内 BC 重算与
  主流程 BC 灯的关系，和 spring/ut 的子窗重算完全相同——属于滑窗设计的固有历史定位语义。
- 结论：非撕裂。与 spring/ut/sos 同等对待，保留。若未来引入统一 BC 锚，再做同 TP-1 处理。

### TP-4 — SC：无锚路径子窗重算（**非撕裂/legacy，保留**）

- 位置：`sc_found`（`_scan(_detect_selling_climax, ...)`）/ `sc_idx`（`_last(...)`）。
- 机制：P-M2 已规定统一锚存在 → `sc_found=True` 短路，**不跑** SC 滑窗；仅**无锚**（孤立
  调用/向后兼容，P-M3）才走子窗重算。子窗重算在无锚场景是唯一 SC 来源，属设计内行为。
- 结论：非撕裂/legacy，保留。主流程（`wyckoff_core.py`）恒注入统一锚，生产路径不触发。

### TP-5 — ST：广义 ST 已统一 / `_detect_st` 不消费 SC 锚（**非撕裂，保留**）

- 位置：`spring_test`（`_scan(_detect_st, ...)`）、`_detect_secondary_test_sc`（结构分析层）。
- 机制：
  - 阶段机内的 `_detect_st`（`wyckoff_events.py:2075`）**不调 `_find_sc_anchor`**，支撑位用
    `tr_ctx.tr_lower`（统一 TR 语境）→ 子窗求值与 spring 同理，非撕裂。
  - 广义 ST（`_detect_secondary_test_sc`，`wyckoff_events.py:1610`）消费 SC 锚，但只在结构
    分析层（`wyckoff_core.py:705`）以**完整序列 + I-M1 统一锚**调用——已是统一路径，不进
    阶段机子窗。handoff 所述「AR/ST 各自重算 SC 锚」中的 ST 即指此，已闭环。
- 结论：非撕裂/已统一，保留。

### TP-6 — 事件簇确认（**已统一，参考**）

- `_detect_event_cluster`（`wyckoff_events.py:2519`）：I-M3 已改为完整序列算一次 SC 锚再换算
  scan 内偏移（`sc_idx = sc_full - (len(bars)-len(scan))`），不再对截断子序列滑窗重算 SC。
  与本次 AR 统一同构——作为「已完成统一」的参考实现。

### TP-7 — 周线半幅窗口（**非撕裂，保留；测试锁定**）

- `_tf_scan_params`（`wyckoff_phase.py:122-138`）+ 周线 lookback=12（`wyckoff_core.py:616`）
  是**数据频率适配**（周线叙事窗约 12 根，日线 window=15 会系统性失效），不是撕裂。
- 验证：`tests/test_wyckoff_weekly_scan_windows.py`（W-S1a~S3）全绿；`_tf_scan_params` 未改动。

## 2. 方向 A 遗留（超本轮范围，需裁决）

- 本轮实测（`light_data.py` 审计注释 + `tests/test_daily_fallback_volume.py` docstring）：
  **腾讯日线 volume=手**（amount 交叉验证 + 实时 qfqday 同量级），与 sina/mootdx/pytdx3/
  tushare 一致。FDE 轮基于「腾讯日线=股」把周线 sina/mootdx 出口 ×100（=股），
  与日线（手）形成跨周期绝对值 100× 差异（周线聚合路径 E-M2 不乘，反而仍是手）。
- 本轮按 A-M1「以源码/协议证据为准」跳过日线 fallback 的 ×100（避免反向制造失真），
  vol_unit 打 "lot"（手）。**周线 ×100 的存废**（改回手 = 与日线一致 / 维持股）涉及 FDE
  合同（A-P4 冻结），建议下轮单独裁决，并同步复核 `test_light_data_weekly.py` E 组断言。

## 3. 交付物

| 项 | 位置 |
|----|------|
| AR 统一实现 | `trader_shared/wyckoff_phase.py` `_ar_verdict` + `ar_idx` 分支 |
| B 测试 | `tests/test_wyckoff_phase_timeframe.py::TestArUnifiedAnchorB`（4 项） |
| 既有测试适配 | `tests/test_wyckoff_core.py::TestPhaseUnifiedScAnchor._run_with_fakes`（补 `_detect_ar` fake，语义不变） |
| 回归 | `test_wyckoff_*.py` 全量 397 passed；`test_daily_fallback_volume.py` 6 passed |
| 本文档 | `workflows/phase-scan-audit/` |
