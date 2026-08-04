# 威科夫阶段机「统一结构上下文」— Agent Handoff

> **status**: 待实现（上一轮「统一结构上下文」重构的收尾——阶段机是最后未闭环的滑窗重算点）  
> **日期**: 2026-08-04  
> **关联**: `wyckoff-epic-context-refactor-handoff.md`（已合入：`_find_sc_anchor` 支持 `tr_ctx.sc_anchor` 全局锚 + 簇吃统一锚）——本轮把阶段机接入同一机制  
> **外部法源**: WorkBuddy `wyckoff-sos-修复交接说明.md` Bug I（§9，结构口径撕裂——阶段机滑窗是其一）  
> **用户批准**: plan 明确「阶段机（wp.py）下一轮单独验证」  
> **读者**: 实现 / 查 Agent（只读本文 + 代码锚点）

---

## 0. 30 秒摘要

1. **现状**：阶段机 `_detect_phase` 对 SC 有**两遍滑窗重算**——`sc_found`（`wyckoff_phase.py:367-369`，`_scan` 30 根内布尔扫）与 `sc_idx`（`:393`，`_last` step=1 末次索引）；`sc_idx` 只用作 spring/ut「SC 之后」次序校验（`:403-428`）。滑窗子序列上重算 SC → 与主流程锚不一致（Bug I 在阶段机的残留）。  
2. **修法**：wc.py 主流程把统一锚（`_find_sc_anchor(bars, event_tr_ctx, include_failed=True)`，与 SC 灯**同 ctx 同源**）注入 `phase_tr_ctx["sc_anchor"]`；`_detect_phase` 有锚时 `sc_found=True`、`sc_idx`=锚换算 wide_bars 偏移，**不再滑窗重算 SC**；**子窗口 ctx 剥离 `sc_anchor`**（防全序列索引越界）。  
3. **不改**：`_find_sc_anchor`/`_detect_selling_climax`/AR/ST 主体（上轮 I-M1 短路已就位）、簇、阶段权重/映射（`_PHASE_ORDER`、各事件→阶段加分）、渲染/fusion/池。  
4. **周线**：`timeframe="weekly"` 同样注入周线统一锚（周线 bars + 周线 tr_ctx；锚持久化键 `symbol::timeframe` 已隔离）。

---

## 1. 必须 / 禁止

### 必须

| # | 合同 |
|---|------|
| P-M1 | `wyckoff_core.py::wyckoff_analysis`：`phase_tr_ctx = _overlay_phase_a_seed_tr_ctx(...)`（现 `wc.py:728-730`）组装后、`_detect_phase` 调用前，注入 `phase_tr_ctx["sc_anchor"] = _find_sc_anchor(bars, event_tr_ctx, include_failed=True)`——**必须用 event_tr_ctx**（与主流程 SC 灯 `wc.py:654` 同 ctx 同源；SC 灯内部 `_find_sc_anchor` 的结果即此值）；返回 None 时不注入键 |
| P-M2 | `_detect_phase`（`wyckoff_phase.py:271`）读 `tr_ctx.get("sc_anchor")`：有锚（dict）→ `sc_found = True`、`sc_idx` = `int(anchor["sc_bar_idx"]) - (len(bars) - len(wide_bars))`（wide_bars = `bars[-lookback:]`，现 `:296-297`；换算结果不在 `[0, len(wide_bars))` 内 → -1）；**删除/短路** 原 `_scan(_detect_selling_climax, ...)`（`:367-369`）与 `_last(_detect_selling_climax, ...)`（`:393`）两遍 SC 滑窗调用 |
| P-M3 | 无 `sc_anchor` 键 → 原滑窗逻辑零改动（向后兼容；孤立调用 `_detect_phase` 的测试不受影响） |
| P-M4 | **子窗口 ctx 剥离**：`_scan`/`_last` 传给子窗口检测器的 tr_ctx 必须剥掉 `sc_anchor` 键（构造 `_sub_ctx = {k: v for k, v in tr_ctx.items() if k != "sc_anchor"}` 或 pop 拷贝）——否则子窗内 `_detect_selling_climax`/`_detect_ar` 短路返回全序列索引锚 → 访问子窗 bars 越界 → 异常被 `_scan_for_signal:267` 吞掉 → 静默无信号。阶段机门控（`phase_a_status`/`tr_quality`/`tr_lower`，`:298/:313/:460`）继续读**原 tr_ctx** |
| P-M5 | 其余事件滑窗（spring/ut/ar/are/bc/sow/lpsy/compression/trend_pullback/trend_rally/st）**不动**（它们不消费 SC 锚；TR 字段已由 tr_ctx 统一） |
| P-M6 | 周线：`timeframe="weekly"` 路径（`wyckoff_strategy_midline` → `wyckoff_analysis(weekly, timeframe="weekly")`）同样注入周线统一锚（周线 bars + 周线 tr_ctx 缩放参数），锚持久化键 `symbol::timeframe` 隔离不变 |
| P-M7 | 有 pytest：注入后 `sc_found`/`sc_idx` 与主流程锚同源（换算一致）；换算越界 → -1；无注入回归（阶段机行为与改前逐位一致）；子窗 AR 不越界仍亮；周线同源 |

### 禁止

| # | 禁止 |
|---|------|
| P-P1 | 不改 `_find_sc_anchor` / `_detect_selling_climax` / `_detect_ar` / `_detect_st` 主体（上轮 I-M1 短路已就位，本轮只消费） |
| P-P2 | 不注入 `event_tr_ctx`（簇与主流程事件保持现状——已同源；本轮只动阶段机路径） |
| P-P3 | 不改 `_detect_event_cluster` / `_scan_last_event` / `_scan_for_signal` 签名 |
| P-P4 | 不改阶段权重与映射：`_PHASE_ORDER`（`wp.py:93-104`）、各事件→阶段加分（`:444-680`）、`_tf_scan_params` 周线半幅——只统一 SC 输入 |
| P-P5 | 不砍持久化锚语义（`_pinned_sc_bar_idx_from_ctx` 钉住路径保留；统一锚含钉住结果） |
| P-P6 | 不改渲染层 / fusion / 出手 / 池分道 / `wyckoff_render.py` |

---

## 2. 字段合同

```text
# P-M1 注入（wc.py，_detect_phase 调用前）
phase_tr_ctx["sc_anchor"] = _find_sc_anchor(bars, event_tr_ctx, include_failed=True)  # 或 None 不注入

# P-M2 消费（wp.py _detect_phase）
sc_found = anchor is not None                        # 统一锚存在即 True（不再滑窗扫）
sc_idx   = int(anchor["sc_bar_idx"]) - (len(bars) - len(wide_bars))   # 全序列→wide_bars 偏移
           # 越界（持久化钉锚可能在 lookback 之外）→ -1（与原「滑窗未检出 SC」同义）

# P-M4 剥离
_scan/_last 子窗口 tr_ctx 不含 sc_anchor 键（其余键原样）
```

---

## 3. 可改文件白名单

| 文件 | 动作 |
|------|------|
| `02-共享模块-shared/trader_shared/wyckoff_core.py` | P-M1 注入（`_detect_phase` 调用前几行）+ P-M6 周线同路径 |
| `02-共享模块-shared/trader_shared/wyckoff_phase.py` | P-M2/M3/M4（`_detect_phase` SC 行 + 子窗 ctx 剥离） |
| `02-共享模块-shared/tests/test_wyckoff_core.py` | P-M7 测例（统一锚阶段机 + 越界 + 子窗 AR） |
| `02-共享模块-shared/tests/test_wyckoff_phase_timeframe.py` | 阶段机透传回归（若需） |
| `02-共享模块-shared/tests/test_wyckoff_tr.py` | 阶段部分回归（若有断言受影响） |
| `02-共享模块-shared/tests/golden/600000.fields.json` | 有意漂移验证后刷新（见 §5） |
| `02-共享模块-shared/tests/fixtures/wyckoff_split_baseline.json` | 有意漂移验证后刷新（见 §5） |
| 本文 + `workflows/` | 文档 |

勿改：`_find_sc_anchor`/`_detect_selling_climax`/`_detect_ar`/`_detect_st` 主体、`_detect_event_cluster`、`_scan_last_event`/`_scan_for_signal` 签名、`wyckoff_render.py`、`wyckoff_events.py`（本轮零改动——除非发现 P-M4 需在 events 侧配合，先列待裁决）、阶段权重/映射。

---

## 4. 验收表

| ID | 场景 | 期望 |
|----|------|------|
| P1 | 注入场景 | `sc_found`/`sc_idx` == 主流程锚换算（同源） |
| P2 | 无注入回归 | `_detect_phase` 孤立调用（无 sc_anchor）行为与改前逐位一致 |
| P3 | 越界防护 | 持久化锚在 lookback 外 → `sc_idx=-1`，不崩 |
| P4 | 子窗 AR | 带 sc_anchor 的 phase_tr_ctx 下 `_scan(_detect_ar, ...)` 不越界、仍可亮 |
| P5 | 周线 | weekly 阶段机吃周线统一锚（39 帽），与日线互不污染 |
| P6 | 阶段权重 | 各事件→阶段加分逐行未动（diff 核） |
| P7 | 门禁 | `scripts/run-gate-tests.sh` 全绿 |
| P8 | 基线 | split/golden 漂移先验证再刷新（§5） |

---

## 5. 基线刷新纪律（同上一轮）

1. 实现后跑全量测试，**记录** golden/split 漂移清单
2. 逐项验证漂移是有意的（如 phase/sc_found 变化需对照构造数据合理性）后才 capture
3. 禁止无脑刷新掩盖非预期漂移

---

## 6. 回滚

`git revert` 实现 commit（单 commit 或两个：wc 注入 + wp 消费——建议**一个 commit**，注入与消费必须同进退，否则注入而无消费 = 死字段、消费而无注入 = 永远走旧路径）。
