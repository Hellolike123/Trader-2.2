# 威科夫「统一结构上下文」重构 — Bug H(BC) + I(结构口径撕裂) — Agent Handoff

> **status**: 待实现（用户批准 plan：层 1 统一 SC 锚 → 层 2 BC 重构；阶段机下轮）  
> **日期**: 2026-08-04  
> **外部法源**: WorkBuddy `wyckoff-sos-修复交接说明.md` Bug H（§8）+ Bug I（§9）  
> **架构法源**: `docs/designs/resonance-and-orchestration.md`（五层+编排）——本 epic 只动 wyckoff 事件层内部一致性，不改 fusion/出手/池  
> **关联**: `wyckoff-sos-epic-fde-handoff.md`（F/D/E 已合入）——F 已修 AR/ST 锚一致性；本 epic 是机制根（I）  
> **用户批准**: plan（BC 判定=放宽阈值 5%+显著长上影 OR 分支；BC 窗口=90 对齐 SC；阶段机本轮不做）  
> **读者**: 实现 / 查 Agent（只读本文 + 代码锚点）

---

## 0. 30 秒摘要

1. **机制根（Bug I）**：`_scan_last_event` 对每个 15 根子窗口传**截断 bars**，检测器在子序列上各自重算 SC 锚（`_find_sc_anchor` 冷启动）→ 簇的「SC 重置锚」与主流程全序列锚不一致 → C/G/I 同源。`tr_upper/tr_lower/tr_baseline_volume` 已经 `tr_ctx` 全传，**SC 锚是最后的撕裂点**。  
2. **层 1（commit 1）**：`_find_sc_anchor` 支持 `tr_ctx.sc_anchor` 全局锚（直接返回，不重算）；`_detect_event_cluster` 用完整序列算一次锚并换算 scan 偏移，**删除**滑窗重算 SC 行。  
3. **层 2（commit 2）**：BC 窗口 5 根 → `WYCKOFF_BC_SCAN_BARS=90` 回溯；滞涨阈值 1.0 → 5.0；新增「显著长上影」OR 分支（`WYCKOFF_BC_STRONG_UPPER_SHADOW_RATIO=0.25`）；ARE 去重复复用 `_detect_buying_climax`。  
4. **不改**：`_scan_last_event` 签名、AR/ST（F 已修）、阶段机（wp.py 下轮）、`wyckoff_core.py`、渲染层、fusion/出手/池。

---

## 1. 必须 / 禁止

### 层 1 — 统一 SC 锚（`wyckoff_events.py`）

| # | 合同 |
|---|------|
| I-M1 | `_find_sc_anchor` 开头检测 `tr_ctx.get("sc_anchor")` 为 dict → **直接返回该锚**（含全部既有键：sc_bar_idx/sc_low/sc_close/sc_avg_vol/vol_ratio/change_pct/pos/cur_high/cur_open/anchor_bars/search_mode + 可选 phase_a_failed/fail_bar_idx/fail_reason），不重算、不冷启动 |
| I-M2 | 无 `sc_anchor` 字段 → 现有逻辑完全不变（阶段机等下轮仍走旧路径；向后兼容） |
| I-M3 | `_detect_event_cluster`：开头用**完整序列** `_find_sc_anchor(bars, tr_ctx, include_failed=True)` 算一次统一锚；换算 scan 内偏移 `sc_scan_idx = sc_bar_idx - (len(bars) - len(scan))`（锚不在 scan 内 → -1）；**删除** `_scan_last_event(scan, _detect_selling_climax, ...)` 滑窗重算行（现 `we.py:2516`） |
| I-M4 | `_after_sc(idx)` 比较改用 `sc_scan_idx`，语义不变（SC 之后才认事件；无锚时 sc_scan_idx=-1 → 全部事件可认，与原行为一致） |
| I-M5 | 簇的 SC 重置锚与主流程 `sc.sc_bar_idx` 同源（行为收益：C/G 字段矛盾机制消除；`wc.py:714-723` 的 G 覆写保留为兜底，不改） |
| I-M6 | 有 pytest：构造「完整序列锚 ≠ 旧滑窗重算锚」场景，断言簇锚 == 主流程锚 |

| # | 禁止 |
|---|------|
| I-P1 | 不改 `_scan_last_event` 签名/行为（`TestEventClusterBugCG` monkeypatch 依赖 `(scan, fn, tr_ctx, window, step=1, **kw)`） |
| I-P2 | 不改 `wyckoff_core.py`（主流程不动，锚由 wc 场景外调用方显式传） |
| I-P3 | 不改 `wyckoff_phase.py` 阶段机（下轮） |
| I-P4 | 簇内其余 5 个事件滑窗（spring/st/ut/sos/sow）保持 `_scan_last_event`（其 TR/量基线已吃外层 tr_ctx） |

### 层 2 — BC 重构（`wyckoff_events.py` + `config.py`）

| # | 合同 |
|---|------|
| H-M1 | 新常量 `WYCKOFF_BC_SCAN_BARS = 90`（config.py，env 可覆）——`_detect_buying_climax` 的 `scan_start = max(1, len(bars) - 5)` 改为 `max(1, len(bars) - WYCKOFF_BC_SCAN_BARS)`，从新到旧找**最近一次** BC（与 SC 灯对称） |
| H-M2 | `WYCKOFF_BC_CHANGE_THRESHOLD` 1.0 → **5.0** |
| H-M3 | 新常量 `WYCKOFF_BC_STRONG_UPPER_SHADOW_RATIO = 0.25`（显著长上影 = upper_shadow / price_range ≥ 0.25） |
| H-M4 | 触发条件 = 量比≥1.5 ∧ 高位 pos≥0.65 ∧（`change_pct < 5.0`（滞涨）∨ 显著长上影 ∨ 收阴 `cur_close < cur_open`）——05-29（+2.2%/上影 0.70）与 06-25（+6.8%/上影 0.31）均可判 BC |
| H-M5 | `_detect_are` 内联复制的 BC 判定改为**复用** `_detect_buying_climax`（同常量同分支，消漂移）；ARE 锚窗口跟随新窗口（90 根内最近 BC） |
| H-M6 | 防误报护栏保留：`_is_bc_high_position`（pos≥0.65）、量比≥1.5、低位天量拒 |
| H-M7 | 有 pytest：60 根前历史顶部可扫到；+6.8%+上影 0.31 触发；+2.2% 无上影触发（滞涨 5.0）；上影 0.24/0.26 边界；量比 1.4 拒；低位拒 |

| # | 禁止 |
|---|------|
| H-P1 | 不砍原典语义：BC 仍须「天量+高位」，长上影分支不得让「无上影的小涨」触发 |
| H-P2 | 不改 `WYCKOFF_BC_VOL_RATIO_THRESHOLD`(1.5) / `WYCKOFF_BC_MIN_POS_PCT`(0.65)（SC 共用量阈） |
| H-P3 | 不在 `_detect_buying_climax` 读 tr_ctx 做新判定（本轮无需求；窗口/阈值即修复面） |
| H-P4 | 不改 fusion/出手/池/渲染层 |

---

## 2. 字段合同

```text
# I — tr_ctx 新增可选字段（层 1）
sc_anchor: dict | None   # 完整序列算好的 SC 锚（_find_sc_anchor 返回同构 dict）
                         # 含 sc_bar_idx（完整序列索引）；簇内部负责换算 scan 偏移

# H — 新/改常量（config.py，env 可覆）
WYCKOFF_BC_SCAN_BARS = 90                    # 新增：BC 回溯窗口（对齐 SC 冷启动日 90）
WYCKOFF_BC_CHANGE_THRESHOLD = 5.0            # 1.0 → 5.0：滞涨门槛
WYCKOFF_BC_STRONG_UPPER_SHADOW_RATIO = 0.25  # 新增：显著长上影阈值

# H — _detect_buying_climax 触发（bc_signal=True 当且仅当）
vol_ratio ≥ 1.5  ∧  pos ≥ 0.65  ∧  (change_pct < 5.0 ∨ 上影比 ≥ 0.25 ∨ 收阴)
```

---

## 3. 可改文件白名单

| 文件 | 动作 |
|------|------|
| `02-共享模块-shared/trader_shared/config.py` | H 常量（3 个） |
| `02-共享模块-shared/trader_shared/wyckoff_events.py` | `_find_sc_anchor`（I-M1/M2）、`_detect_event_cluster`（I-M3~M5）、`_detect_buying_climax`（H-M1~M4）、`_detect_are`（H-M5） |
| `02-共享模块-shared/tests/test_wyckoff_core.py` | I-M6 / H-M7 测例 |
| `02-共享模块-shared/tests/test_wyckoff_tr.py` | 簇夹具重审（统一锚后若红，先改测再改码——纪律） |
| `02-共享模块-shared/tests/golden/600000.fields.json` | 有意漂移验证后刷新（见 §5） |
| `02-共享模块-shared/tests/fixtures/wyckoff_split_baseline.json` | 有意漂移验证后刷新（见 §5） |
| 本文 + `workflows/` | 文档 |

勿改：`wyckoff_core.py`、`wyckoff_phase.py`、`wyckoff_render.py`、`light_data.py`/`cache_utils.py`、`indicator_math.py`、fusion/出手/池分道、`_scan_last_event` 签名。

---

## 4. 验收表

| ID | 场景 | 期望 |
|----|------|------|
| I1 | 簇与主流程 SC 锚同源 | 构造「完整序列锚 ≠ 滑窗重算锚」→ 簇锚 == 主流程锚 |
| I2 | 无 sc_anchor 字段 | `_find_sc_anchor` 现有行为不变（回归） |
| I3 | 簇 6 场景（test_wyckoff_tr） | 全绿或按新合同改夹具后全绿 |
| H1 | 60 根前历史顶部 | BC 亮（回溯窗口生效） |
| H2 | +6.8% + 上影 0.31（06-25 型） | BC 亮（长上影分支） |
| H3 | +2.2% 无长上影（05-29 型） | BC 亮（滞涨 5.0） |
| H4 | 上影 0.24 / 0.26 边界 | False / True |
| H5 | 量比 1.4 / 低位天量 | BC 不亮（护栏） |
| H6 | ARE 复用 BC 判定 | ARE 行为合理（回归：ARE 锚 = 最近 BC） |
| H7 | 门禁 | `scripts/run-gate-tests.sh` 全绿 |

---

## 5. 基线刷新纪律（重要）

1. 实现后先跑全量测试，**记录** golden / split 基线的漂移清单（`python scripts/golden_diff_gate.py check` + `pytest test_wyckoff_split_equivalence.py`）
2. **逐项验证漂移是有意的**（如 bc_signal False→True 需对照 600000 构造数据合理性）后才可 capture
3. 刷新：`python scripts/golden_diff_gate.py capture`；split 基线按 FDE epic 已确立的流程（当前模块等价捕获，`.bak` 机制已失效）
4. 禁止无脑刷新掩盖非预期漂移

---

## 6. 回滚

- commit 1（层 1）与 commit 2（层 2）独立，`git revert` 各自可回滚
- 层 2 可单独用 env 关：`WYCKOFF_BC_SCAN_BARS=5 WYCKOFF_BC_CHANGE_THRESHOLD=1.0` 恢复旧行为（常量 env 可覆）
