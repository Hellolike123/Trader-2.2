# 威科夫（Wyckoff）代码变更 — 审查交接文档

> 用途：交给另一个 Agent 独立审查**威科夫相关改动**是否有 bug，重点查
> **「代码改动是不是真的接到业务逻辑上了」**（改了却被下游丢弃 = 没关联；
> 改了但下游读错字段 = 关联错乱）。
>
> **状态**：审查发现 + 关联修复已落地（见 **§十**）。后续 Agent 请以 §十 后代码为准，
> 勿再按 §四 旧表中「进 fusion」等过时表述验收。
>
> 本仓库曾以 `162f5d6` 为基线；威科夫主体在 `aba3d51`（D1–D5）与 `a7a7000`（P0–P6）。
> 行号可能漂移，以符号名 / grep 为准。

---

## 一、背景与改动范围

### 1.1 威科夫在系统中的真实角色（2026-07 对齐）

| 路径 | 角色 | 是否加权进短线 fusion |
|------|------|----------------------|
| `calculate_wyckoff_score` | 选股池 / 复盘打分（0–100 → 池内约 0–30） | ❌ |
| `format_wyckoff_oneline` | 报告中线「威科夫：…」一行白话 | ❌ |
| `wyckoff_strategy_midline` | 周线独占中线旁证；不足 → `insufficient` | ❌ |
| `wyckoff_midline_bias` | 中线看法合成（strong_bull/bear/neutral） | ❌ |
| `_wyckoff_to_signal` / `wyckoff_result` 入参 | **兼容/测试残留** | ❌ 不调用 |
| 短线 fusion 第三席 | **VPF（价量资金）** | ✅ |

> 历史文档曾写「短线日线威科夫进 fusion」——**已废**。以 `fusion_core.merge_decisions` 为准。

### 1.2 核心文件

| 文件 | 角色 |
|------|------|
| `02-共享模块-shared/trader_shared/wyckoff_core.py` | 主引擎：analysis / strategy / midline / score / oneline |
| `02-共享模块-shared/trader_shared/wyckoff_phase.py` | A–E phase 状态机、`spring_premature` / `upthrust_premature` |
| `02-共享模块-shared/trader_shared/wyckoff_events.py` | 事件簇 `_detect_event_cluster` 等 |
| `02-共享模块-shared/trader_shared/conclusion_block.py` | `wyckoff_midline_bias` |
| `02-共享模块-shared/trader_shared/fusion_core.py` | `_wyckoff_to_signal`（兼容）；merge 不消费 wyckoff |
| `docs/audit/wyckoff-review.md` | 审计结论全文（D1–D5） |
| `docs/audit/wyckoff-original-concept-inventory.md` | P0–P6 原典清单 |

关键 commit：
- **`aba3d51`**：审计修复 D1–D5
- **`a7a7000`**：P0–P6 五阶段机 + 事件簇 + TR 质量 / 过早信号

---

## 二、审查 Agent 应先读的文档（按序）

1. **本文 §一.1 + §十** — 消费面与已修复项（必读，防误报）。
2. `docs/audit/wyckoff-review.md` — D1–D5 原始证据。
3. `docs/audit/wyckoff-original-concept-inventory.md` — P0–P6 设计原意。
4. `AGENTS.md`（威科夫消费面 bullet）/ `AGENTS_DEEP.md` §5.3 — 以仓库当前正文为准。
5. `01-功能包-packages/trader/references/output-template.md` — 中线「威科夫：…」契约。
6. `docs/ADR-002-route-via-plugin-registry.md` — 周线透传。

---

## 三、文件地图（符号定位；行号易漂移）

### `wyckoff_core.py`
| 符号 | 说明 |
|------|------|
| `wyckoff_analysis` | 主引擎；cluster / premature / strength 透出 |
| `wyckoff_strategy` | 日线轨（**不**进 fusion 加权；池分/兼容） |
| `wyckoff_strategy_midline` | 周线独占；不足 → `timeframe=insufficient` |
| `calculate_wyckoff_score` | 纯函数打分（`use_persisted_phase=False`）；簇/premature/TR 进 raw |
| `format_wyckoff_oneline` | 一行白话；`insufficient` / premature / strength 展示 |

### `wyckoff_phase.py` / `wyckoff_events.py`
- `_transition_phase`、premature 判定、`_detect_event_cluster`：grep 符号即可。

### 下游
| 消费点 | 读什么 |
|--------|--------|
| `final_pool.py` | `calculate_wyckoff_score` → `wyckoff_score` |
| `review_core.py` | 同上 |
| `report_core.py` | `format_wyckoff_oneline(wyckoff_midline)` |
| `conclusion_block.py` | `wyckoff_midline_bias` |
| `merge_decisions` | **不读** wyckoff（第三席 vpf） |

---

## 四、代码 ↔ 业务关联表（修订版）

### 审计修复（aba3d51）

| # | 修复点 | 下游消费 | 关联状态 |
|---|--------|----------|----------|
| **D1** | phase 只进不退 | oneline `show_phase` / 打分 phase 修正 | ✅ 已确认 |
| **D2** | 中线不回退日线 → `insufficient` | report_builder 兜底 + oneline「不参与定论」 | ✅ 已确认（§十 修展示） |
| **D3** | 打分不写盘 | final_pool / review | ✅ 已确认 |
| **D5** | SOS 常量派生 | analysis signals → **score**（非 fusion） | ✅ 改表述：进打分 |

### P0–P6

| # | 改动点 | 下游消费 | 关联状态 |
|---|--------|----------|----------|
| **P0 簇** | `accumulation_confirmed` 等 | **仅** `calculate_wyckoff_score` raw | ✅ 进池分；❌ 不进 fusion |
| **P0-3** | TR 质量 `tr_adj` | score | ✅ 已确认 |
| **P0-4** | `spring_strength` 等 | oneline 说明增强（§十） | ✅ 展示已接；打分仍主看 vol_class |
| **P0-5** | 事件簇加减分 | score → 池/复盘 | ✅ **勿写「抑制 fusion」** |
| **P0-6** | LPSY 须派发背景 | score 门控 | ✅ 已确认 |
| **premature** | spring/ut 孤立 | score 减半 + oneline 中性 + midline_bias 不抬 strong | ✅ §十 三处对齐 |

### 刻意不接 / 残留

| 项 | 说明 |
|----|------|
| `_wyckoff_to_signal` | 兼容/测试；`merge_decisions` 不调用。premature 时跳过抬多/抬空（§十） |
| `daily_fallback` 文案 | 中线已禁止回退；oneline 仍兼容旧字段后缀 |

---

## 五、逐项审查清单（后续 Agent）

- [x] **D1** phase 只进不退仍在 phase 模块
- [x] **D2** 中线无 daily_fallback；insufficient 展示诚实
- [x] **D3** score 路径 `use_persisted_phase=False`
- [x] **D5** SOS 无硬编码 magic（配置常量）
- [x] **P0-5** 簇只改 score，不改 fusion `weighted_score`
- [x] **premature** score / oneline / bias 三处一致
- [ ] **回归**：跑 §七 命令；关注 `test_conclusion_midline` 中 B1A 看法文案是否与中线策略漂移（与威科夫关联修复无关的 3 例可能红，见 §八）

---

## 六、关键不变量（违反即 bug）

1. **包装层**：`wyckoff_strategy*` 返回 `{"wyckoff": {...}}`，下游须解包。
2. **中线周线独占**：禁止「周线不足→日线兜底」回归。
3. **`calculate_wyckoff_score` 纯函数**：禁止 `use_persisted_phase=True` 写盘。
4. **报告 `阶段：` ≠ A–E phase**：`阶段：` 只来自 major_stage。
5. **premature 默认 False**：数据不足不得误标 True。
6. **短线 fusion 不吃威科夫**：第三席 VPF；勿把 score/cluster「当 fusion 修复」验收。
7. **`timeframe=insufficient` 展示**：必须含「不参与定论」，禁止「暂无事件」。

---

## 七、运行测试

```bash
cd /Users/like/Documents/Opencode/Trader3.0
export PYTHONPATH=02-共享模块-shared
PY=/Users/like/.workbuddy/binaries/python/envs/default/bin/python

$PY -m pytest \
  02-共享模块-shared/tests/test_wyckoff_core.py \
  02-共享模块-shared/tests/test_wyckoff_tr.py \
  02-共享模块-shared/tests/test_wyckoff_split_equivalence.py \
  02-共享模块-shared/tests/test_conclusion_midline.py \
  -q

$PY -m py_compile \
  02-共享模块-shared/trader_shared/wyckoff_core.py \
  02-共享模块-shared/trader_shared/wyckoff_phase.py \
  02-共享模块-shared/trader_shared/wyckoff_events.py \
  02-共享模块-shared/trader_shared/conclusion_block.py
```

---

## 八、已知非目标 / 勿误报

- 不要改 `light_data` 分钟 date 截断（另文档 5m 缠论范围）。
- 不要把日线/T0 5m 缠论与威科夫混审。
- **不要**要求把威科夫重新塞回 `merge_decisions` 第三席——除非另开 ADR + 产品决策。
- `test_conclusion_midline::TestMidlineViewB1A` 部分用例可能因中线看法话术演进失败（「可跟踪/暂缓」vs「中线观察」），属 conclusion 文案契约，**不**等于威科夫关联断裂；修法另议。
- 未要求 push。

---

## 九、交付格式（审查时）

```
文件:符号或行号 | 现象 | 严重度 | 证据 | 关联标签(断裂/错乱/覆盖/已修复)
```

关联类须写清：期望消费点 / 实际为何未读到。

若未发现新 bug：
> 「已按 §五 核对（对照 §四 修订表与 §十），未发现新 bug，证据：…」

---

## 十、审查发现 + 已落地修复（2026-07-16）

### 10.1 审查结论摘要

| 严重度 | 现象 | 处理 |
|--------|------|------|
| High（文档/验收） | 多处写「簇/信号进 fusion」；实际第三席 VPF | 改 handoff / AGENTS / AGENTS_DEEP / 代码注释 |
| Medium | `insufficient` oneline 变成「暂无事件 · 中性」 | `format_wyckoff_oneline` 特判 |
| Medium | premature 只降分、展示仍「偏多洗盘」；bias 仍 strong_bull | oneline + midline_bias 对齐 |
| Medium（半接） | strength 字段透出未展示 | oneline 接 strong/weak/failure 说明 |
| Low | `_wyckoff_to_signal` 当主线 | docstring 标兼容；premature 跳过抬分 |
| Low | score 注释「抑制 fusion 误出手」 | 改为「仅改池/复盘分」 |

### 10.2 代码改动清单

| 文件 | 改动 |
|------|------|
| `wyckoff_core.py` | insufficient oneline；premature/strength 展示；score/strategy 注释 |
| `conclusion_block.py` | insufficient / premature → bias 不抬 strong |
| `fusion_core.py` | `_wyckoff_to_signal` 兼容说明 + premature 守卫 |
| `AGENTS.md` / `AGENTS_DEEP.md` | 消费面与第三席 VPF 对齐 |
| `tests/test_wyckoff_core.py` | insufficient / premature oneline |
| `tests/test_conclusion_midline.py` | premature / insufficient bias |

### 10.3 后续 Agent 若继续改威科夫

1. 先 `rg "merge_decisions|_wyckoff_to_signal|calculate_wyckoff_score|format_wyckoff_oneline"` 确认消费面。  
2. 新字段必须写进 §四 表，并标注四类之一：`score` / `oneline` / `midline_bias` / `fusion(禁止默认)`。  
3. 改展示后补 `test_wyckoff_core.TestFormatWyckoffOneline`；改 bias 补 `test_conclusion_midline.TestMidlineTheoryDirs`。  
4. 禁止在未开 ADR 时把 wyckoff 重新塞进 `merge_decisions` 加权。  
5. 中线不足链路黄金断言：
   - strategy → `timeframe == "insufficient"`
   - oneline → 含「不参与定论」
   - bias → `neutral`

### 10.4 建议但未做（可选 backlog）

- strength 进 `calculate_wyckoff_score` 微调（当前仍以 vol_class + premature 为主）。
- 删除或迁出 `_wyckoff_to_signal` 死路径（需评估测试依赖）。
- 刷新 `TestMidlineViewB1A` 看法文案 golden（conclusion 层，非本轮威科夫关联）。
- 15m/30m 若接威科夫：独立 ADR，勿混中线周线契约。
