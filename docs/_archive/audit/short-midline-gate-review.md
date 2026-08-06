# 短中线报告 + Mistery 门控 审查报告

| 项 | 内容 |
|----|------|
| 日期 | 2026-07-10 |
| 审查角色 | Reviewer Agent（只读，未改业务代码） |
| 规格源 | `docs/short-midline-report-and-gate-plan.md` §5.B / §6 |
| 门控规格 | `~/.grok/skills/mistery-core/references/decision-subset.md` |
| 总结判定 | **有条件通过（Conditional PASS）** |

---

## 1. 总结判定

**有条件通过。** P0 产品契约与门控纪律主体已落地：纯函数门控不改写状态数字、短中线模板结构冻结、买卖点不依赖持仓、空仓「减仓」译义、双渲染入口默认共用 `report_core`、feature flag 可回退、单测覆盖华工否决路径与放行路径。

未发现阻塞级安全问题或明显会让生产输出直接违背微信红线的缺陷。以下问题均为 **P1**（建议修，不阻断合并），以及若干与本改动无关的既有 contract 失败（记为观察项）。

---

## 2. 审查清单（逐项）

### 2.1 是否改写了 major_stage / fusion 数值（禁止）

**PASS**

证据：

- `mistery_gate.compute_mistery_gate` 只读 `dict`/`kwargs`，返回新 dict；单测 `TestNoStateRewrite.test_gate_does_not_mutate_inputs` 断言输入不被改写。
- `run_analysis.build_report` 组装段（约 1433–1526 行）仅写入：
  - `report["weekly_frame"] = None`
  - `report["key_prices"]` / `report["mistery_gate"]` / `report["conclusion"]` / `report["daily_ruling"]`
- 未对 `stage_result["major_stage"]`、`report_fusion["weighted_score"]`、`support`/`stop` 赋值覆盖。
- 模块头注释与 `output-template.md` 均写明禁止改写。

---

### 2.2 买卖点是否在无仓时仍输出

**PASS**

证据：

- `key_prices.build_key_prices` 无 `has_position` 参数；始终计算 stop/买点/两句。
- `report_core.render_short_midline` 在「📍 关键价」段无仓位分支；缺 `key_prices` 时仍从 `support`/`stop`/`confirm` 回退拼装。
- 单测 `test_always_outputs_lines_without_position_param`、华工样例渲染含 `买点区` / `止损卖点` / 两句亏赚。
- 空仓样例全文（合成华工）仍有完整关键价地图。

---

### 2.3 是否出现 R:R 术语或「未授权隐藏买价」旧逻辑

**PASS（默认短中线路径）**

证据：

- `key_prices` / `render_short_midline` 输出句式为「亏约 X / 赚约 Y」，禁止「2.1R」「不足 1R」；单测断言。
- 全库无「未授权隐藏买价」实现残留（仅 plan 审查清单提及）。
- **边界说明（非 FAIL）**：`SHORT_MIDLINE_REPORT=false` 时 `render_single_legacy` / `run_analysis` 旧模板仍含「试探买」「盈亏比 x:1」——属计划内回退，不进默认主路径。默认 `SHORT_MIDLINE_REPORT=true`。

---

### 2.4 空仓主结论是否仍只写「减仓」

**PASS**

证据：

- `gate_action_to_execution_text("减仓", has_position=False)` → `"不宜追高 · 不新开"`。
- 有仓时才输出「减仓（点位见关键价）」/「止损离场…」。
- `build_daily_ruling` 将 fusion「减仓」类译为「不宜追高」。
- 渲染单测：出手行不得为裸「出手：减仓」。

---

### 2.5 门控是否覆盖 H1–H7 与阶段×动能表

**PASS（实现覆盖）；测试对 H6 为弱覆盖 → 见 P1-1**

证据：

| 规则 | 实现位置 | 单测 |
|------|----------|------|
| H1 很差 | `_check_hard_blocks` + action=不做 | `test_h1_regime_bad` |
| H2 衰退 | 同上 | `test_h2_decline` |
| H3 派发不加 | hard_block + 强制不新开/cap0 | `test_h3_distribution_no_add` |
| H4 无止损 | 同上 | `test_h4_no_stop` |
| H5 盈亏比 | reward_near ≤ min_rr×risk | `test_h5_poor_rr` |
| H6 四不做 | 多因叠加 / 追高+H5 | **无独立 assert「H6」** |
| H7 禁止摊平 | `wants_average_down` | `test_h7_average_down_forbidden` |
| 阶段×动能表 | `_STAGE_MOMENTUM_TABLE` + `_action_from_table` | `test_accum_strong_try` / `test_markup_hold` |
| 情绪/不明降档 | style 分支 | 间接 |
| 520 近似 | `_apply_520_invalidation` + notes | `test_ma20_proxy_note` |
| 偏弱降档 | `_position_cap_for` ×0.5 | `test_regime_weak_cuts_try_size` |
| cap≤50 | `_POSITION_CAP_CEILING` | 持有路径 |

字段输出与 subset §7 一致：`hard_block, style, action, invalidation, position_cap_pct, notes`。

---

### 2.6 微信红线（# ** --- 表格等）

**PASS（渲染输出）**

证据：

- `report_core` 模块注释与 `render_short_midline` 仅用 emoji 分段。
- `test_no_markdown_syntax`：无 `**`、`---`、行首 `#`、行首 `|`。
- `validate_trader` 对华工样例 markdown 返回 `[]`。
- 注：`output-template.md` 文档自身含 Markdown 表格（契约说明用），不进入终端渲染。

---

### 2.7 双渲染入口是否漂移

**PASS（有轻微残余风险 → P1-2）**

证据：

| 入口 | 路径 |
|------|------|
| 生产 | `final_report.py` → `trader_shared.report_core.render_single` |
| 兼容 | `run_analysis.render_markdown` 在 `SHORT_MIDLINE_REPORT=true` 时 **直接委托** `report_core.render_single` |
| 回退 | `render_single` → `render_single_legacy`；`run_analysis` 在 flag false 时走自有旧模板体 |

结论：默认路径已消除双模板主输出漂移。残余：`run_analysis` 判断 flag 用 **import 时固化** 的 `config.SHORT_MIDLINE_REPORT`，`report_core._short_midline_enabled()` **优先读实时 env**——进程内先 import config 再改 env 时可能不一致（测试/热切换场景）。

---

### 2.8 测试是否覆盖华工否决路径与放行路径至少各 1

**PASS**

| 路径 | 用例 |
|------|------|
| 否决/不追 | `TestHuagongScenario.test_huagong_like_block`（H5 → 不做/cap0）；`TestRenderShortMidline` 合成华工全文 |
| 放行 | `TestStageMomentumTable.test_accum_strong_try`（蓄势×走强 → 轻仓试错，cap>0） |

运行结果：

```text
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_mistery_gate.py \
  02-共享模块-shared/tests/test_key_prices.py -q
# 21 passed in 0.04s
```

---

### 2.9 P1 周线框 weekly_frame 是否有 TODO/扩展点

**PASS（未静默遗漏）**

证据：

- `mistery_gate.py` 文件头与 `compute_mistery_gate` 末尾明确 P1：`weekly_frame` 仅 notes、不完整改 action。
- `run_analysis.build_report`：`report["weekly_frame"] = None  # P1: compute_weekly_frame...`
- `conclusion_block`：预留 `weekly_frame` 字段；若传入 `"破坏"` 会改中线文案（见 P1-3 半实现）。
- 单测 `TestWeeklyFrameP1Hook.test_weekly_frame_recorded_not_crash`。

---

### 2.10 与 decision-subset 字段名一致

**PASS**

| subset §7 | 实现 |
|-----------|------|
| `hard_block` | ✅ `none` \| `H1`… 及组合如 `H5+H6` |
| `style` | ✅ `趋势`\|`情绪`\|`不明` |
| `action` | ✅ 观望/轻仓试错/回踩低吸/持有/减仓/止损离场/不做 |
| `invalidation` | ✅ |
| `position_cap_pct` | ✅ ≤50 |
| `notes` | ✅；无 MA20 时含 `520口径未直接验证(用stop/support近似)` |

输入别名：`short_term_momentum`/`momentum`、`theory_status`/`scene` 均支持。

---

### 2.11 计划 §1 产品契约：结论五行、🗳️、关键价两句亏赚、出手人话

**PASS**

合成华工渲染对照：

```text
分析报告 — 华工科技（000988）｜短中线
🎯 结论
  中线看法：可跟踪 / 故事未结束
  短线看法：不适合追，偏冲高减
  出手：现价不买 · 不追
  原因：…
  本周：…
  说明：…（冲突时）
🗳️ 日线三专家 + 日线裁定
📍 关键价 + 两句亏赚
🗺 空间参考（不指挥下单）
```

- 无独立门控 YAML 块；无 raw weighted_score 主卡展示。
- `output-template.md` 已更新为 2.5.0 短中线契约。

---

### 2.12 SHORT_MIDLINE_REPORT 回退是否可用

**PASS**

证据：

- `config.SHORT_MIDLINE_REPORT` 默认 true；env `false`/`0` 可关。
- 实测 `SHORT_MIDLINE_REPORT=false`：`_short_midline_enabled()==False`，首行无 `｜短中线`，走 legacy「📍 决策 / 试探买」。
- `output-template.md` 记录回退命令。

---

## 3. 验收标准（计划 §6）对照

| # | 标准 | 结果 |
|---|------|------|
| 1 | 输出含短中线结构关键字 | PASS（模板+单测；未强制 live 华工网络拉数） |
| 2 | 华工类：不买不追；关键价仍有买卖点 | PASS |
| 3 | 单测 H5/H6、阶段观望、亏赚 | PASS（H6 仅逻辑存在，单测弱） |
| 4 | JSON 仍含原 fusion/stage；新增字段兼容 | PASS（只追加字段） |

---

## 4. 问题列表

### P0（阻塞）

无。

### P1（建议修）

| ID | 问题 | 建议 |
|----|------|------|
| **P1-1** | H6 无独立单测（仅能通过 H5+追高组合间接触发；清单要求 H1–H7 覆盖时测试不对称） | 增加 `test_h6_chase_and_poor_rr` 断言 `"H6" in hard_block` |
| **P1-2** | 双入口 flag 读取不一致：`config` 导入时固化 vs `report_core` 实时 env | `run_analysis.render_markdown` 改为调用 `report_core._short_midline_enabled()` 或始终委托 `render_single` |
| **P1-3** | `weekly_frame` 半实现：`conclusion_block` 在「破坏」时已改中线文案，但 `mistery_gate` 明确不改 action，且 build_report 恒为 `None` | P1 真周线落地前：要么 conclusion 也不消费破坏语义，要么 gate 同步裁切；避免「中线已战略减、出手仍持有」的理论不一致 |
| **P1-4** | H5 用 **买点** risk/reward；现价追亏赚差时 hard_block 可能仍为 `none`（华工真实 key_prices 合成：买区 RR 尚可 → 靠阶段表「观望」而非 H5） | 可接受；若产品希望「追不划算」进硬否决，可增加 chase 维度的 H5/H6 输入（`risk_chase`/`reward_chase`），并在原因句补「近端空间不划算」 |
| **P1-5** | `trader/tests/test_contract.py` 3 失败与短中线无直接关系（`hard_stop` 浮点、`build_signal` scene「转弱」映射、`structure_weak` flag） | 另开修复；合并本功能时勿误判为本 diff 回归 |

失败摘要（观察，非本 diff 引入判定）：

```text
FAILED test_dynamic_low_zone_and_stop_use_volatility_buffer  # 10.33 vs 10.32
FAILED test_build_signal_for_scene_转弱                     # wait_for_confirmation vs defensive
FAILED test_build_signal_risk_flags_structure_weak            # structure_weak not in []
# 34 passed, 3 failed
```

### P2（可选）

| ID | 说明 |
|----|------|
| P2-1 | skill 侧 `~/.agents/skills/trader/references/output-template.md` 是否与包内同步未在本审查中核验（计划提到 pack 同步） |
| P2-2 | 缺字段时 style 易变「不明」导致全市场偏观望——与「门控过严」风险一致，已有 min_rr 配置缓解 |
| P2-3 | AGENTS.md 满分示例仍是旧「📍 决策 / 试探买」叙事，与 2.5 短中线未同步（文档债） |

---

## 5. 建议修复优先级（给 Implementer）

1. **P1-1**：补 H6 单测（小、锁契约）。
2. **P1-2**：统一 flag 读取，杜绝双入口漂移边角。
3. **P1-3**：明确 weekly_frame 在 P0 的行为边界（建议 gate 与 conclusion 一致：未实现则都不消费「破坏」动作语义，仅 notes）。
4. **P1-4**（可选增强）：chase 维度写入 hard_block/原因，贴近华工样例文案「近端空间不划算」。
5. **P1-5**：独立修 contract 三测，避免 CI 红灯掩盖后续变更。

---

## 6. 已读 / 已跑清单

### 必读

- [x] `docs/short-midline-report-and-gate-plan.md`
- [x] `~/.grok/skills/mistery-core/references/decision-subset.md`
- [x] `trader_shared/mistery_gate.py`
- [x] `trader_shared/key_prices.py`
- [x] `trader_shared/conclusion_block.py`
- [x] `trader_shared/report_core.py`（短中线 + legacy 入口）
- [x] `run_analysis.py` 组装段 + `render_markdown` 委托
- [x] `final_report.py` 生产入口
- [x] `output-template.md`
- [x] `tests/test_mistery_gate.py` / `tests/test_key_prices.py`
- [x] `config.py` `SHORT_MIDLINE_REPORT` / `MISTERY_MIN_RR`

### 测试

```bash
# 核心：21 passed
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_mistery_gate.py \
  02-共享模块-shared/tests/test_key_prices.py -q

# 契约：34 passed / 3 failed（见 P1-5，与本功能弱相关）
PYTHONPATH=02-共享模块-shared:01-功能包-packages/trader/scripts python3 -m pytest \
  01-功能包-packages/trader/tests/test_contract.py -q
```

### 可选 live 华工

未跑网络 `final_report --target 华工科技`（审查环境不依赖行情）；用合成数据验证了 §9 样例锚点结构与语义。

---

## 7. 审查结论一句话

短中线 + Mistery 门控 **P0 可合并（有条件通过）**：纪律层只读、模板契约与回退齐全、关键单测绿；合并后优先补 H6 单测、统一 flag 读取、收敛 weekly_frame 半实现，并另案清理 `test_contract` 三处红灯。
