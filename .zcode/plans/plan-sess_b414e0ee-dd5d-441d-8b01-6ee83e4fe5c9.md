# 威科夫「统一结构上下文」重构（Bug H + I 机制根）

## 背景与根因（已实证）

外部交接更新版新增 Bug H（BC 失灵）+ Bug I（结构口径撕裂）。调研确认：**7 个逻辑 bug 的机制根 = 事件检测器不共享统一结构上下文**：

- `_scan_last_event`（`wyckoff_events.py:2427-2461`）对每个 15 根子窗口传**截断 bars**，检测器在子序列上各自重算 SC 锚/局部量基线 → 簇的「SC 重置锚」（`we.py:2516` 滑窗重算 SC）与主流程 `sc.sc_bar_idx`（全序列 `_find_sc_anchor`）不一致 → Bug C/G/I 同源
- `tr_upper/tr_lower/tr_baseline_volume` 其实已通过 `tr_ctx` 全传（19 个检测器消费）——**SC 锚是最后的撕裂点**
- BC（`we.py:630-707`）只扫最近 5 根、`tr_ctx` 完全忽略、滞涨硬门槛 1.0% 卡死 +6.8% 的 06-25

## 目标架构

「单次结构解析 → 各事件查询」：TR（已有）+ **SC 锚（本轮新增）** 只在完整序列算一次，簇确认/历史事件定位共享同一 ctx，不在子窗口重算结构。

## 层 1：统一 SC 锚（Bug I + C/G 机制根）— commit 1

1. **`_find_sc_anchor` 支持 ctx 全局锚**：`tr_ctx` 新增可选 `sc_anchor` 字段（完整序列算好的锚 dict：sc_bar_idx/sc_low/sc_close/sc_avg_vol/vol_ratio/change_pct/pos/phase_a_failed/fail_bar_idx/fail_reason）；`_find_sc_anchor` 开头检测到即**直接返回**（不重算、不冷启动）。无该字段 → 现有逻辑不变（阶段机下轮仍走旧路径，向后兼容）
2. **`_detect_event_cluster` 改用统一锚**：开头用完整序列 `_find_sc_anchor(bars, tr_ctx, include_failed=True)` 算一次，换算成 scan 内偏移（`sc_bar_idx - (len(bars) - len(scan))`，不在 scan 内则 -1）；**删除** `_scan_last_event(scan, _detect_selling_climax, ...)` 滑窗重算行（`we.py:2516`）；`_after_sc` 语义不变（SC 之后才认事件）
3. 行为收益：簇的 SC 重置锚与主流程 phase_a 锚一致 → C/G 字段矛盾从机制消除（`wc.py:714-723` 的 G 覆写保留为兜底）
4. **不改**：`_scan_last_event` 签名（`TestEventClusterBugCG` monkeypatch 依赖）、AR/ST（F 已修）、阶段机（wp.py，用户已确认下一轮）

## 层 2：BC 重构（Bug H）— commit 2

1. **窗口**：新常量 `WYCKOFF_BC_SCAN_BARS = 90`（config.py，env 可覆）；`_detect_buying_climax` 的 `scan_start = len(bars)-5` → 90 根回溯，从新到旧找**最近一次** BC（与 SC 灯对称语义）
2. **判定结构**：`WYCKOFF_BC_CHANGE_THRESHOLD` 1.0 → **5.0**；新增 `WYCKOFF_BC_STRONG_UPPER_SHADOW_RATIO = 0.25`（显著长上影 = 上影 ≥ 25% 区间高）；触发 = 量比≥1.5 ∧ 高位 pos≥0.65 ∧（滞涨 <5.0 ∨ 显著长上影 ∨ 收阴）→ 05-29（+2.2%/上影 0.70）与 06-25（+6.8%/上影 0.31）均可判 BC
3. **ARE 去重复**：`_detect_are`（`we.py:1710-1781`）内联复制的 BC 判定改为复用 `_detect_buying_climax`（同常量同分支，消漂移）；UTAD/PSY 自动受益（回归验证）
4. **防误报护栏保留**：pos≥0.65、量比≥1.5、低位天量拒

## 层 3：测试、基线刷新与验证

- **新增测例**：H——60 根前历史顶部可扫到、+6.8%+上影 0.31 触发、+2.2% 无上影触发、上影 0.24/0.26 边界、量比 1.4 拒、低位拒；I——构造「完整序列锚 ≠ 滑窗重算锚」场景断言簇锚 == 主流程锚
- **基线刷新（必须先验证漂移是有意的再 capture，禁止无脑刷新）**：golden `600000.fields.json`（bc_signal 等漂移 → 验证浦发数据合理后刷新）、`wyckoff_split_baseline.json`（gen_bars 平坦序列验证后刷新）
- **test_wyckoff_tr.py 簇夹具重审**：统一锚后若测试红（SOW 尾巴与 SC 锚耦合注释），按新合同先改测再改码
- 门禁 `scripts/run-gate-tests.sh` 全绿；相关回归 198+ 测全绿

## 文档与流程

- 新 handoff：`docs/plans/wyckoff-epic-context-refactor-handoff.md`（必须/禁止/字段/白名单/验收表/回滚）
- 双 Agent：写 Agent 按 handoff 实现 → 查 Agent 独立逐项对照（默认不改码，列必须再改）→ 父 Agent 收尾
- 两个 commit（层 1、层 2）同一轮 push，便于独立回滚

## 白名单

可改：`trader_shared/config.py`（BC 常量）、`trader_shared/wyckoff_events.py`（`_find_sc_anchor`/`_detect_event_cluster`/`_detect_buying_climax`/`_detect_are`）、`tests/test_wyckoff_core.py`、`tests/test_wyckoff_tr.py`（夹具重审）、基线 fixture（有意刷新）、docs/plans + workflows/
勿改：`wyckoff_core.py`、`wyckoff_phase.py`（阶段机下轮）、`wyckoff_render.py`、`light_data.py`/`cache_utils.py`、fusion/出手/池

## 实票验证（有行情时人工，不阻塞合入）

南网科技（BC 亮 + 派发链 BC→ARE→SOW + 簇/主流程 SC 一致 + TR/SOS 回归）、贵州茅台（F 失效文案回归）、宁德时代/工商银行（防误报）