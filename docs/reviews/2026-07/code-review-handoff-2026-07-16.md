# 代码审查交接文档

> **用途**：交给另一个 agent，审查 2026-07-14 ~ 2026-07-16 写的代码，**找 bug / 回归风险**，并重点核查「**代码改动是否真的接到业务逻辑**（代码↔业务关联）」。
> **审查范围**：仅找 bug，不要重构、不要加功能、**不要直接改代码**（只报告结论 + 建议 diff）。
> **代码状态**：已全部提交到 `main`。缠论/T0 部分 commit `162f5d6`（未 push）；威科夫部分 commit `aba3d51`（审计修复）+ `a7a7000`（P0-P6）。工作区与提交一致。
> **环境**：Python venv 在 `/Users/like/.workbuddy/binaries/python/envs/default/bin/python`；仓库根目录 `/Users/like/Documents/Opencode/Trader3.0`。

---

## 0. 一图看懂这次改了什么

本次审查覆盖**两条工作流**：

| 工作流 | 改动 | 文件 | commit |
|--------|------|------|--------|
| **A. T0 分钟级（5m）缠论接入 + 日线实时缠论读仓修复** | 5m 缠论接入 T0 盯盘；修 `get_realtime_chan` 读日线恒空 | `chan_plugin.py` / `monitor.py` / `realtime_chan.py` / 契约测试 | `162f5d6` |
| **B. 威科夫（Wyckoff）审计修复 + P0-P6 增强** | D1 phase 只进不退 / D2 中线回退日线 / D3 打分隐藏写盘 / D5 SOS 魔法数；P0-P6 五阶段机+事件簇+TR质量+过早信号 | `wyckoff_core.py` / `wyckoff_phase.py` / `wyckoff_events.py` / `wyckoff_plugin.py` + 消费方 | `aba3d51` + `a7a7000` |

**A 流核心背景（致命根因）**：上游 `light_data.py` 把分钟 K 的 `date` 截断成「日」，完整时间戳只在 `time` 字段。`ChanlunEngine._bar_id=("date",bar["date"])` 且 `update_bar` 只比最后一根 → 同日所有 5m 棒 date 相同 → 引擎塌缩成 1 根 → 缠论恒返回 `{}`。`_normalize_minute_bars` 用 `time/datetime/day` 回填唯一 `date` 是功能前提。

**B 流核心背景**：威科夫代码近一周高频改动（P0-P3 改进、`aba3d51` 审计修复、`a7a7000` P0-P6）。审计修复点（D1-D5）在 `a7a7000` 之后**仍完整存在且被下游消费**（已逐点核对，见 §4.6 关联表），但需审查 agent 独立验证「每个修复/feature 真的接到业务，没有改了却孤立」。

---

## 1. 先读规则与约定文档（**按序号顺序读**）

### 1a. 通用项目约定
| # | 文件 | 为何读 | 重点 |
|---|------|--------|------|
| 1 | `AGENTS.md`（仓库根） | 项目总纲 | 双轨报告契约、数据源、纪律层只收紧、四阶段定位 |
| 2 | `AGENTS_DEEP.md` | 深入架构 | 模块依赖、融合层、HMM 大势 |
| 3 | `ARCHITECTURE.md` | 模块划分 | `trader_shared/` vs `01-功能包-packages/` 边界 |
| 4 | `docs/ADR-002-route-via-plugin-registry.md` | **关键**：插件路由 + 周线透传 | `analyze_all` 如何把日线喂短线、周线喂中线；`weekly_bars` 仅作 higher_trend 过滤 |
| 5 | `01-功能包-packages/trader/references/output-template.md` | 输出契约 | 报告格式（七段模板、🧭 中线 / ⚡ 短线 分区） |
| 6 | `01-功能包-packages/trader/references/output-style-guide.md` | 输出风格 | 措辞/emoji/数字规范 |
| 7 | `~/.workbuddy/skills/trader/SKILL.md` | 单票分析 agent | 短线/中线双轨如何调用 chan/wyckoff |
| 8 | `~/.workbuddy/skills/t0/SKILL.md` | **T0 盘中 agent** | monitor 循环、预警格式、`T0_REALTIME_CHAN` 语义 |
| 9 | `~/.workbuddy/skills/review/SKILL.md` | 复盘/审查 agent | 本审查应遵守的流程 |
| 10 | `/Users/like/Documents/Workbuddy/Trader/t0_chan5m_plan.md` | **A 流设计稿** | 含「六、落地前核查清单与风险」 |

### 1b. 威科夫专项（B 流必读）
| # | 文件 | 为何读 | 重点 |
|---|------|--------|------|
| 11 | `docs/audit/wyckoff-audit-prompt.md` | 审计原始指令 | D1-D5 的发现与修复意图 |
| 12 | `docs/audit/wyckoff-original-concept-inventory.md` | 原典概念清单 | 哪些威科夫概念该被实现（对照检查是否真实现） |
| 13 | `docs/audit/wyckoff-review.md` | 审计结论 | 已修/待修项、🔴 高危项 |
| 14 | `01-功能包-packages/trader/specs/spec-wyckoff-classic-signals.md` | 经典信号 spec | Spring/SOS/UT/BC/SOW/AR/ST/LPS 优先级与语义 |
| 15 | `02-共享模块-shared/docs/wyckoff-p1-improvements.md` | P1 改进说明 | 一字板过滤/板块量能缩放/交易区间检查 |
| 16 | `02-共享模块-shared/docs/wyckoff-p2-p3-improvements.md` | P2/P3 说明 | Compression 压缩蓄势 / TrendPullback 趋势回踩 |

---

## 2. 本次改动的代码文件（审查重点）

### A 流（缠论 / T0）
| 文件 | 改动类型 | 关键行 |
|------|----------|--------|
| `02-共享模块-shared/trader_shared/plugins/chan_plugin.py` | 整文件重写 | `_MINUTE_MIN_BARS=20`(L20) · `_normalize_minute_bars`(L23) · `analyze`(L59-72) |
| `01-功能包-packages/t0/scripts/monitor.py` | 4 处 | `_check_5m_chan_t0`(L552) · 取源+声明(L673,L681) · 写 `chan5_signature`(L716) · 跨 tick(L728-736) · `prefix` 合并(L797,L802) |
| `02-共享模块-shared/trader_shared/realtime_chan.py` | 1 处 | `get_realtime_chan` 内 `daily =`(L96) |
| `02-共享模块-shared/tests/test_short_midline_chan_timeframe_contract.py` | 新增 | 4 例 |

### B 流（威科夫）
| 文件 | 改动类型 | 关键行 / commit |
|------|----------|----------------|
| `02-共享模块-shared/trader_shared/wyckoff_core.py` | 审计修复 + P0-P6 | D1 `_PHASE_ORDER`(L69)/`_transition_phase`(L76,L180)；D2 `wyckoff_strategy_midline`(L321,L339 insufficient)；D3 `calculate_wyckoff_score`(L352,L380 `use_persisted_phase=False`)；D5 `WYCKOFF_DIVERGENCE_BARS`(L28)/`_detect_sos`(L90,L148)；P0-P6 `_detect_event_cluster`(L100,L156)/`spring_premature`(L128)/`TR_QUALITY`(L548)；`format_wyckoff_oneline`(L586) | `aba3d51` + `a7a7000`(+135) |
| `02-共享模块-shared/trader_shared/wyckoff_phase.py` | P0-P6 阶段机 | +151 行（`a7a7000`） |
| `02-共享模块-shared/trader_shared/wyckoff_events.py` | P0-P6 事件簇 | +526 行（`a7a7000`） |
| `02-共享模块-shared/trader_shared/plugins/wyckoff_plugin.py` | 插件包装 | `analyze`→`wyckoff_strategy`(L26-27) |
| **消费方（验证「关联」用，只读不改）** | | `plugin_registry.py`(L159-165 midline / L132 daily) · `report_builder.py`(L353,L992-997,L1274,L1339,L1346,L1546) · `report_core.py`(L331,L337,L1096,L1102) · `report_presentation.py`(L473,L480) · `conclusion_block.py`(L226 `wyckoff_midline_bias`) · `mid_key_prices.py`(L59) · `fusion_core.py`(L322,L451 `wyckoff_score_to_direction`) · `final_pool.py`(L296,L1150) · `review_core.py`(L347,L373) · `daily_briefing/scripts/briefing.py`(L839) |
| **威科夫测试** | | `tests/test_wyckoff_core.py` · `tests/test_wyckoff_tr.py`(+549) · `tests/test_wyckoff_split_equivalence.py` |

---

## 3. 必须理解的关键不变量

### 3a. A 流（缠论 / T0）
1. **5m 棒 `date` 必须唯一且含时分秒**。`_normalize_minute_bars` 优先用 `time`/`datetime`/`day` 回填，绝不能用上游日级 `date`，否则引擎塌缩。
2. **`chanlun_strategy` 返回 `{"chanlun": result}` 包装层**，`_check_5m_chan_t0` 必须解包 `result["chanlun"]`。
3. **`_chan_realtime_alert(result, prev_sig)` 第二参是签名 tuple**，不是 dict。
4. **中线 `chanlun_strategy_midline`**：周线 `≥20` 根在周 K 跑，不足 `daily_fallback`；`weekly_bars` 在短线路径只作 higher_trend 过滤。
5. **5m 路径"始终开启"是有意设计**，独立于 `T0_REALTIME_CHAN` 与事件系统。
6. **运行时副本陷阱**：`~/.workbuddy/skills/t0/` 重装会覆盖，改动必须落在本仓库。

### 3b. B 流（威科夫）
1. **D1 phase 状态机"只进不退"→基于 `_PHASE_ORDER` 符号判断反向翻转**；仅 `use_persisted_phase=True`（日线路径）生效。中线 `use_persisted_phase=False` 跳过 `_transition_phase`、**不持久化 phase**（符合设计，非 bug）。
2. **D2 中线威科夫周线独占**：周线不足直接返回 `insufficient`，**无 daily_fallback**；`report_builder` L992-997 有兜底 dict（`timeframe:"insufficient"`/`phase:"none"`/`wyckoff_summary:"中线数据不足"`）。
3. **D3 `calculate_wyckoff_score` 是纯函数**：内部 `wyckoff_analysis(..., use_persisted_phase=False)`，**不再写 `~/.trader/wyckoff_phase.json`**。
4. **D5 `_detect_sos` 用 `WYCKOFF_DIVERGENCE_BARS` 派生**，不再硬编码 `closes[4]`/`opens[0]`/`4-of-5`。
5. **P0-P6 在 `wyckoff_analysis`（主引擎 L105）串联** `_detect_sos` / `_detect_event_cluster` / `spring_premature` / `upthrust_premature` / TR质量。这些**新产物必须真的进 `wyckoff_strategy` 输出并被 `format_wyckoff_oneline` + report + fusion 消费**——这是本次关联核查重点。
6. **`format_wyckoff_oneline`（L586）是报告单行展示入口**，被 `report_core.py:337/1102`、`report_presentation.py:480` 调用；其 SC/LPSY/P0-P6 分支必须被实际渲染。
7. **中线 `wyckoff_midline` 经 `plugin_registry`→`report_builder`→`conclusion_block.wyckoff_midline_bias`+`mid_key_prices`+`synthesize_midline_verdict`**，且 `insufficient` 不崩。

---

## 4. 逐文件审查清单（请逐条核对，给出证据）

### 4.1 `chan_plugin.py`（A 流）
- [ ] `_normalize_minute_bars`：bar 同时有 `time` 和日级 `date` 时，是否用 `time` 覆盖？（必须，否则同日塌缩）
- [ ] 边界：bars 为空 / 非 dict / 无 `time`/`day`/`datetime` → 安全不抛、不产重复 date
- [ ] `analyze`：5m 优先（≥`_MINUTE_MIN_BARS` 才走 5m）；日线兜底分支透传 `weekly_bars`（不可丢，否则破坏 ADR-002 中线回退）；`minute_bars` 默认 `None` → `plugin_registry` 经 `**extra` 只传 `weekly_bars`，日线路径输入不变

### 4.2 `monitor.py`（A 流）
- [ ] `_check_5m_chan_t0`：取 `plan["data"]["kline_5m"]`；解包 `{"chanlun":...}`；5m<20 返回 `(None,None)`
- [ ] `run_once`：L673 取源、L681 初始化 `chan5_alert_line`
- [ ] `state_lock` 内 L716 写 `chan5_signature`（确认在锁内，与读 `previous` 无竞态）
- [ ] 跨 tick L728-736：`prev5 is not None` 守卫（首轮静默）；`_chan_realtime_alert(min5_result, prev5)` 第二参是签名 tuple
- [ ] 末尾 `prefix` 合并：**两条返回路径都并入 `chan5_line`**（L797 `vacuum_line+chan_line+chan5_line`；L802 同）
- [ ] 回归：事件系统 / `T0_REALTIME_CHAN` 日线路径 / 其他 prefix 行毫发无损

### 4.3 `realtime_chan.py`（A 流）
- [ ] L96 `daily = (plan.get("data") or {}).get("daily_bars") or plan.get("daily_bars") or []`：新布局能读到；顶层兜底仍在；两者皆无 → `[]` 不抛
- [ ] `quote` 双布局未被破坏；与 5m 路径无耦合

### 4.4 测试 `test_short_midline_chan_timeframe_contract.py`（A 流）
- [ ] 4 例覆盖：中线周线 / 周线不足回退日线 / 短线日线 / `analyze_all` 路由
- [ ] monkeypatch 干净

### 4.5 上游依赖（A 流，只读不改）
- [ ] `light_data.py`：确认 5m 棒 `date` 截成日（Sina `day`/mootdx `datetime` 在 `time` 字段）。追问：15m/30m 是否同截断？（另一议题）
- [ ] `chan_core.py`：`_bar_id` / `update_bar` 只比最后一根 / `chanlun_strategy` 返回包装层 / `chanlun_strategy_midline` 周线优先
- [ ] `plugin_registry.py`：`analyze_all` 路由

### 4.6 威科夫「代码↔业务关联」核查（B 流，**本次重点**）

> 下面每一行都必须验证「改动点确实被业务消费」，而不是改了却孤立/被覆盖/被后续 commit 抹掉。

#### 关联映射表（已核对，请独立复验）
| 改动点 | 代码位置 | 业务消费点 | 关联状态 |
|--------|----------|------------|----------|
| D1 phase 反向翻转 | `wyckoff_core` L180 `_transition_phase`（基于 `_PHASE_ORDER` 符号） | `wyckoff_analysis` phase → `format_wyckoff_oneline(show_phase=True)` `report_core:337` | ✅ 接上 |
| D2 中线 insufficient | `wyckoff_core` L339 `return {"timeframe":"insufficient",...}` | `plugin_registry` L160 → `report_builder` L992-997 兜底 | ✅ 接上 |
| D3 打分不写盘 | `wyckoff_core` L380 `use_persisted_phase=False` | `final_pool` L296、`review_core` L373、`daily_briefing` L839 | ✅ 接上 |
| D5 SOS 常量化 | `wyckoff_core` L148 `_detect_sos`（用 `WYCKOFF_DIVERGENCE_BARS`） | `wyckoff_strategy` → report + fusion `levels["wyckoff"]` | ✅ 接上 |
| P0-P6 事件簇 | `wyckoff_core` L156 `_detect_event_cluster` | `wyckoff_analysis` → `wyckoff_strategy` → report/fusion | ✅ 接上（验证） |
| P0-P6 过早信号 | `wyckoff_core` L128 `spring_premature`/`upthrust_premature` | `calculate_wyckoff_score` L397/410/428 用；`format_wyckoff_oneline` 展示 | ✅ 接上（验证） |
| 单行展示 | `wyckoff_core` L586 `format_wyckoff_oneline` | `report_core:337/1102`、`report_presentation:480` | ✅ 接上 |
| 中线 bias | `conclusion_block` L226 `wyckoff_midline_bias` | `report_builder` `wyckoff_midline`（L992/1274/1339/1346/1546） | ✅ 接上 |

#### 逐点核查清单
- [ ] **D1**：`_transition_phase` 真的基于 `_PHASE_ORDER` 符号判断反向翻转；清晰派发信号能翻掉积累阶段；同方向只升不降、无信号平滑不抖动。确认 `use_persisted_phase=False`（中线）时确实跳过 → 中线 phase 不持久化（符合设计）。
- [ ] **D2**：`wyckoff_strategy_midline` 周线不足返回 `insufficient` dict（结构含 `timeframe`/`phase`/`wyckoff_summary`）；**无 daily_fallback 残留分支**；`report_builder` L992-997 兜底一致；`conclusion_block.wyckoff_midline_bias` / `synthesize_midline_verdict` 对 `insufficient` 不 KeyError/crash。
- [ ] **D3**：`calculate_wyckoff_score` 内确认无持久化写盘（搜 `json.dump`/`open(` 在持久化分支应为空）；`final_pool`/`review_core` 拿到的 score 是纯函数（同输入同输出，无副作用）。
- [ ] **D5**：`_detect_sos` 内 `WYCKOFF_DIVERGENCE_BARS` 引用覆盖原 4/5 魔法数；边界：bars 不足 `DIV_BARS` 根时不崩。
- [ ] **P0-P6 关联（最关键）**：`wyckoff_analysis` 里 `spring_premature`/`upthrust_premature`/`_detect_event_cluster` 的输出是否被 `wyckoff_strategy` 透传 → 被 `format_wyckoff_oneline` 展示 → 被 fusion 使用。**重点查"新增字段是否真在报告里出现"**：构造一个能触发 SC/LPSY/事件簇的样例，跑 `build_report`，确认报告真的出现对应一行白话，避免"改了展示逻辑却无数据流入"。
- [ ] **P0-P6 回归**：`test_wyckoff_tr.py`（+549 行）是否真覆盖五阶段机/事件簇/TR质量/过早信号；有无 pre-existing drift（已知 `test_wyckoff_core` 历史有 2 failed/91 passed 漂移，与审计无关，勿误报）。
- [ ] **`format_wyckoff_oneline`**：SC/LPSY 分支（commit `82b3fb9`）+ P0-P6 分支能否触发并渲染；空 dict 入参不崩（`test_wyckoff_core:1071` `format_wyckoff_oneline({})`）。
- [ ] **中线 robustness**：`wyckoff_midline` 进 `mid_key_prices`(L59)/`conclusion_block`/`synthesize_midline_verdict` 的字段提取对 `insufficient` dict（缺某些键）不崩。
- [ ] **配置**：`config.py` 被 `a7a7000` 改 56 行（+P0-P6 配置项），确认新配置项有默认值、不影响旧路径。
- [ ] **`wyckoff_phase.py` / `wyckoff_events.py`**：P0-P6 新增的 +677 行是否真被 `wyckoff_core` import 并调用（非孤儿模块）；`wyckoff_phase.py` 的五阶段机是否与 `wyckoff_core._transition_phase` 协调（是否两套 phase 状态机冲突/重复）。

### 4.7 威科夫测试运行（B 流）
```bash
cd /Users/like/Documents/Opencode/Trader3.0
PY=/Users/like/.workbuddy/binaries/python/envs/default/bin/python
$PY -m pytest \
  "02-共享模块-shared/tests/test_wyckoff_core.py" \
  "02-共享模块-shared/tests/test_wyckoff_tr.py" \
  "02-共享模块-shared/tests/test_wyckoff_split_equivalence.py" -q
```

---

## 5. 如何运行测试 / 自测

```bash
cd /Users/like/Documents/Opencode/Trader3.0
PY=/Users/like/.workbuddy/binaries/python/envs/default/bin/python

# A 流：本次新增的契约测试
$PY -m pytest "02-共享模块-shared/tests/test_short_midline_chan_timeframe_contract.py" -q

# A 流：编译 + 导入冒烟
$PY -m py_compile \
  "02-共享模块-shared/trader_shared/plugins/chan_plugin.py" \
  "01-功能包-packages/t0/scripts/monitor.py" \
  "02-共享模块-shared/trader_shared/realtime_chan.py"
$PY -c "import sys; sys.path.insert(0,'01-功能包-packages/t0/scripts'); import monitor; print('monitor import OK')"

# B 流：威科夫测试（见 §4.7）

# 全量门禁（A+B 共用，锁 7 个离线测试）
bash scripts/run-gate-tests.sh
```

> `monitor.py` 依赖本地目录 `t0_run`/`t0_config` 与 `trader_shared`，跑测试时 `PYTHONPATH` 需含 `02-共享模块-shared`。

---

## 6. 已知非目标 & 已确认 OK（避免重复劳动 / 误报）

- ✅ **A 流不碰日线实时缠论与事件系统**：5m 路径独立，自测确认日线/事件零波及。
- ✅ **A 流不做 push**：commit `162f5d6` 已含全部 4 文件。
- ✅ **上游 `light_data` 截断日级 `date` 是既有行为、非本次引入**；本次用 `_normalize_minute_bars` 在 chan 入口补偿。是否根治上游属另一议题。
- ✅ **B 流 D1-D5 在 `a7a7000` 之后仍存在且被消费**（关联表已逐点核对）。
- ✅ **`format_wyckoff_oneline` 非死代码**：报告确在调用（report_core/report_presentation），SC/LPSY/P0-P6 一行白话已接展示。
- ⚠️ **B 流 `test_wyckoff_core` 历史有 2 failed/91 passed 漂移**（审计时即存在，与 D1-D5 无关）；审查 agent 遇到这 2 个失败先确认是否"既有漂移"再报。
- ⚠️ **`wyckoff_phase.py` 与 `wyckoff_core._transition_phase` 是否双 phase 机**：需审查确认二者不冲突（见 §4.6 末条）。

---

## 7. 交付要求（审查 agent 输出格式）

请输出 **bug 清单**，每条含：

```
文件:行号 | 现象描述 | 严重度(致命/高/中/低) | 复现步骤或证据(代码引用)
```

- **致命**：报错 / 静默失效 / 数据错误（如 5m 塌缩成 1 根、跨 tick 误报漏报、`analyze_all` 路由错乱、威科夫修复点被覆盖/孤立导致业务无效果）。
- **高**：边界崩溃、竞态、回归既有功能。
- **中/低**：风格、冗余、可维护性。

**特别要求（B 流）**：对每个威科夫修复点/feature，明确给出「**代码↔业务关联**」结论——是已接上（附消费点行号）、还是**孤立/未消费/被覆盖**（即"代码改了但业务没关联上"，这是本次最高优先级的 bug 类型）。

**不要直接改代码**；如需改，给出**建议 diff 片段**即可。

若逐条核对后**未发现 bug**，请明确写："已按 §4 清单逐条核对（含 B 流关联表），未发现 bug，证据：…（附测试输出/关键代码引用）"，不要只回"看起来没问题"。

---

## 8. A 流（缠论/T0）审查修复记录（已由审查 agent 落地，备查）

> 本章节记录另一个审查 agent 对 A 流（缠论/T0）的审查结论与已落地修复，供 B 流审查参考。来源：`.workbuddy/memory/2026-07-16.md`「审查修复：5m 缠论告警差分 + 基线保留」。

根据审查结论，A 流已由审查 agent 修复并验证（相关测试 **20 passed**）：

1. `monitor._chan_realtime_alert`：买卖点文案改为对比 prev/cur type 集合；末笔价微动不再误报「出现买点」。
2. `run_once`：`chan5_signature` 仅在 `min5_sig is not None` 时更新，失败保留上一轮基线。
3. 空 `chanlun={}` 解包不用 `or`；`_MINUTE_MIN_BARS` 对齐 `CHANLUN_MIN_BARS`；分钟结果 `timeframe=5m`。
4. 测试：`test_realtime_chan` 增 tip-only / list prev_sig 用例；新增 `test_chan_plugin_minute.py`。

→ **B 流（威科夫）尚未经此审查，是本次交接文档的重点**。请审查 agent 按 §4.6 关联核查表 + §4.7 测试，独立验证「代码↔业务是否真关联上」。
