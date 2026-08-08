# Wyckoff / 缠论 状态语义保真审计 — 查 Agent 输出报告

> **接手文档**: `docs/plans/wyckoff-chan-state-audit-handoff.md`（2026-08-08）
> **审计日期**: 2026-08-08
> **性质**: 只读审计，未改任何 `.py` / 测试 / fusion / decision_view / 出手 / 池分道
> **方法**: 7 项查法（D/E/A/B/C/F/G）逐项证据化验证 + 基线复跑

---

## 0. 总评

**状态机语义基本正确。** owner 担心的「数据算对没、状态确定好」在**逻辑层**得到确认：

- 信号→phase 映射、持久化翻转/隔离、事件检测器触发、中枢数值、volume 单位、周/日线隔离 **全部验证通过**；
- 自写验证脚本共 **73 项断言全绿**（D 19 + E 16 + A 7 + B 11 + F 10，含 2 项标记 FINDING 的非阻断观测）；
- 接手基线全绿：**wyckoff+report 179 passed**、**chan 187 passed**、**门禁 810 passed / 4 skipped**（handoff 基线 796，新增 14 项仍全绿）。

**「必须改」项：无。** 触发 handoff「必须改」门槛的条件均未成立（中线周线 `use_persisted_phase=False` 已确认；隔离有测；无非法中枢泄漏）。

**发现 4 项需改进（均非阻断性 bug）**，交父 Agent 决策：
- 建议改 ×3：`FINDING-1`（tr_upper/tr_lower 来源不一致）、`FINDING-2`（markup 簇兜底不对称）、`FINDING-3`（use_persisted_phase 默认 True 致日线持久化）；
- 需人工裁定 ×1：`FINDING-4`（真实票 K 线目检需联网数据，离线无法完成）。

---

## 1. 查法 D — 信号→phase 映射语义 【✅ 19/19 断言通过】

**锚点**: `wyckoff_phase.py` `_detect_phase` L273-839、`_apply_p2_phase_a_gates` L143-183

**方法**: monkeypatch 检测器为桩，纯由 `signals` dict 驱动 if/elif 映射，逐条核对威科夫五阶段叙事。

**映射核对结果（全部符合 handoff 表）**:
| 信号组合 | 期望 phase | 结果 |
|---|---|---|
| SC+AR | accumulation_a | ✅ |
| compression+SC/AR | accumulation_b | ✅ |
| Spring(有B背景) | accumulation_c | ✅ |
| Spring+Test | accumulation_d | ✅ |
| Spring+SOS+站上TR上沿 | markup | ✅ |
| BC+ARE | distribution_a | ✅ |
| ARE无BC | distribution_b | ✅ |
| UT+SOW(有BC) | distribution_c | ✅ |
| LPSY+派发背景 | distribution_d | ✅ |
| UTAD | markdown | ✅ |
| premature Spring/UT(无B背景) | none | ✅ |
| phase_a_status=failed | none+gated | ✅ |
| tr_quality 低 | none+gated | ✅ |
| dist_confirmed+反向SOS | none（簇兜底） | ✅ |
| forming+BC / 无established+markup信号 | none（P2 闸） | ✅ |

**结论**: `if/elif` 映射忠实实现五阶段叙事；premature 孤立性校验、phase_a_failed 门、low_tr_quality 门、P2 established 种子箱门、簇确认反向 SOS 兜底 均按原典工作。

### FINDING-1 【建议改 · 低】`tr_upper`(signals) 与 `tr_lower`(tr_ctx) 来源不一致
- **证据**: `wyckoff_phase.py` L576-577 读 `tr_upper = signals.get("tr_upper")`；L596 读 `tr_lower = (tr_ctx or {}).get("tr_lower")`。
- **影响**: 若某 caller 只把 `tr_lower` 放进 `signals`（不放 `tr_ctx`），markup 子条件工作但 markdown 的 `last_close < tr_lower` 子条件永不触发 → 停在 `distribution_c` 而非 `markdown`。
- **实测**: 将 `tr_lower` 仅放 `signals` 时，markdown 分支确实未触发（落到 distribution_c）。
- **生产影响**: **潜伏性**——`wyckoff_core.py` L775-793 / L1221 同时把 `tr_lower` 写入 `tr_ctx` 与 `signals`，故生产路径两处都填，不Trigger。属可维护性/健壮性隐患。
- **建议**: 统一两处 TR 边界价来源（均从 `tr_ctx` 或均从 `signals`），消除不对称。

### FINDING-2 【建议改 · 中】`markup` 分支缺 `_dist_cluster` 簇兜底（与 accumulation_d 不对称）
- **证据**: `wyckoff_phase.py` L619-658 的 accumulation_c/d 分支均带 `not _dist_cluster` 守卫（派发簇确认后反向 SOS 不翻案）；但 L580-593 的 `markup` 分支**无此守卫**。
- **影响**: `distribution_confirmed=True` + `Spring+SOS+站上TR上沿` 时仍返回 `markup`（主升离开积累区），与「簇确认语境下 Spring 序列不得抬成积累」的防线不对称，可能把派发区的 bull-trap 误判为主升。
- **实测**: 注入 `distribution_confirmed + spring + sos + close>tr_upper + sc/ar` → 得 `markup`（FINDING-2 行已记录）。
- **建议**: 在 L580 的 markup 进入条件加 `and not _dist_cluster`（与 L619 对称），或显式文档化「markup 允许突破簇」的取舍。

---

## 2. 查法 E — 持久化污染 【✅ 16/16 断言通过】

**锚点**: `_transition_phase` L875-957、`_load/_save_phase_state` L845-873、`_phase_key` L841-843

**验证项**: 翻转及时性（accum→dist 反方向翻转）、first_seen 重置（反向翻转后重置为新 phase）、跨日确定性（_detect_phase 纯函数）、`symbol::timeframe` 隔离（日/周独立 key 互不覆盖）、force_apply_none 破位收口。

**结论**: 转移规则「无旧→用新 / none 保持旧 / 反方向翻转 / 同方向只升不降」全部成立；持久化键按 `symbol::timeframe` 隔离，first_seen 不被旧值污染。

### FINDING-3 【建议改 · 中】`use_persisted_phase` 默认 `True` + 日线路径依赖默认 → 日线阶段被持久化
- **证据**: `wyckoff_core.py:604` 默认 `use_persisted_phase: bool = True`；但以下**生产日线路径**未显式传参、依赖默认 `True`：
  - `wyckoff_core.py:1286` `wyckoff_analysis(bars, symbol=symbol)`
  - `review_core.py:350` / `review_core.py:602` `wyckoff_analysis(daily, symbol=symbol)`
  - `t0_run.py:195` `wyckoff_analysis(daily, symbol=...)`
- **对照**: 中线周线路径已显式 `use_persisted_phase=False`（`wyckoff_core.py:1319/1352`、`wyckoff_run.py:94/102`），故**中线周线污染风险休眠**（正确）。
- **影响**: 日线/日内 wyckoff phase **会**读写 `~/.trader/wyckoff_phase.json`；结合 `_transition_phase` 的「none 保持旧」平滑规则，日线阶段存在跨日黏住风险（与「中线周线常关阶段黏性」的既定意图不一致）。
- **结论**: 不触发 handoff「必须改」（中线周线=False 已满足、隔离有测），但默认与显式 False 不一致属设计债。
- **建议（已纠正）**: ⚠️ 原报告建议「默认改 False」**不成立**——日线 `use_persisted_phase=True` 是**有意为之的稳健层**（让日线 phase 跨日连续、翻转需确认，避免单日信号抖动导致 phase 跳变，即查法 E 验证的持久化机制）。中线周线用 False 是另一语义（周线战略依据不被单周污染）。正确处置：**不动默认值**，仅把日线路径 `wyckoff_core.py:1286` 显式写上 `use_persisted_phase=True` 消除隐式依赖（行为不变，风险≈0）。详见 §10 修复记录。

---

## 3. 查法 A — 事件检测器保真 【✅ 7/7 断言通过】

**锚点**: `wyckoff_events.py` `_detect_buying_climax` L639 / `_detect_spring` L1113 / `_detect_sos` L2077

**方法**: 合成 bars 直验检测器（绕过状态机）。
- BC：高位天量滞涨（量比 3×、涨幅 2%<5%、区间上沿）→ 触发，命中 idx=15；量比 1.2×（<阈 1.5）→ 不触发。✅
- Spring：跌破 TR 下沿(10) 后收回、正常量能 → 触发（"收回60%"）。✅
- SOS：放量站上 TR 上沿 thrust → 触发（"强势突破，5/5 阳线"）。✅
- 平稳序列对 BC/Spring/SOS **均不误触发**（边界抑制）。✅

**现有单测盘点**: `test_wyckoff_core.py` L131-212（BC 多场景）、L265-456（SOS/upthrust/SOW/thrust 边界）——**已有隔离的单事件触发测，非「漏网」**。

### FINDING-4 【需人工裁定】真实票 K 线目检
- 合成 + 单测证据强烈指示检测器在正确 bar 触发，但 owner 原话「数据算对没」要求对**真实历史走势**目检（如茅台 2021 初 BC、某票清晰 Spring）。
- 离线环境无法拉取真实 K 线逐 bar 回放（需联网 / 离线缓存）；建议父 Agent 或 owner 用 `scripts/diagnose_chan_triangulation.py` 思路扩到威科夫，抽 3-5 只已知 BC/Spring/SOS 票人工核对检测器命中位置。

---

## 4. 查法 B — 中枢/段数值正确性 【✅ 11/11 断言通过】

**锚点**: `chan_geometry.py` `build_zones` L1202 / `_merge_zones` L1100

**验证项**:
- `build_zones` 单窗 `zh_top=min(highs)`、`zh_bottom=max(lows)`，严格绑定 3 段实际极值。✅
- 非法中枢窗口（high<low）被**直接丢弃**（raw 空），输出绝无 `zh_top<=zh_bottom`。✅
- `_merge_zones` 仅合并**真价格重叠 + 时间连续**（Bug Q 护栏 L1152），取交集（zh_top=min, zh_bottom=max）；纯 gap 不合并。✅
- 合法输入合并后所有中枢均 `top>bottom`（L1163 兜底）。✅

**MACD 面积坐标雷（handoff §B #2）**:
- **证据**: `chan_core.py:160` `macd_divergence_buy = _check_macd_for_2nd_buy(cleaned, strokes)`；L151 注释「笔 start_index/end_index 相对 cleaned；背驰/二类确认/买卖点一律吃 cleaned」；`cleaned = _calc_macd(handle_inclusion(raw))`（L414/490）。
- **结论**: `_stroke_macd_area` 收到的 `bars` 与 `stroke` 索引**同源 cleaned**，无 raw 日线 + 笔 index 错位（handoff 点名的雷未实际发生）。

---

## 5. 查法 C — volume 单位一致性 【✅ 验证清洁】

**锚点**: `wyckoff_events.py` 全检测器；MEMORY「腾讯日线 volume=手」

**验证**: grep `wyckoff_events.py` 绝对 volume 阈值（如 `volume > 100000`）→ **无匹配**。所有 volume 用法均为**量比**（vol_ratio=cur/avg；Spring 的 `current_volume < avg*LOW_VOL_RATIO` / `>= avg*BULLISH_VOL_RATIO`）。
- **结论**: 量比单位无关——即使 volume 单位为股（×100），分子分母同缩放，比值不变。**手/股差异不可能造成 100× 检测错误**。
- MEMORY「volume=手」结论仍有效，但对检测器正确性**非载荷**（ratios 天然消除单位）。查法 C 无 bug。

---

## 6. 查法 F — 黄金样本回放（合成版） 【✅ 10/10 断言通过】

**方法**: 信号注入模拟「积累→markup」「派发→markdown」两条完整轨迹，验 `_detect_phase` 产出顺序。

**结果**:
- 积累轨迹 A→B→C→D→markup 严格按序推进；派发轨迹 A'→C'→D'→markdown 严格按序推进。✅
- 反向翻转不黏住：先 accumulation_d 再给派发信号 → 落到 `distribution_c`（非滞留 accumulation）。✅

**局限**: 真实 10 票 K 线逐 bar 回放需联网 + 目检，同 FINDING-4，离线无法完成，标记**需人工裁定**。

---

## 7. 查法 G — 周/日线隔离实测 【✅ 验证清洁】

**锚点**: `_phase_key` L841-843（`f"{symbol}::{timeframe}"`）

**验证**（复用查法 E case 8）: 同 symbol 日线/周线分别 `_save_phase_state` → `_load_phase_state` 返回各自独立 phase；first_seen 互不覆盖。`_detect_phase` 本身无状态（每次调用由 bars 决定），串台仅可能经持久化键——键已隔离。
**结论**: 周/日线不串台，隔离生效。

---

## 8. 必须再改清单（交父 Agent）

| 编号 | 严重度 | 项 | 文件:行 | 建议动作 |
|---|---|---|---|---|
| FINDING-1 | 建议改(低) | tr_upper(signals)/tr_lower(tr_ctx) 来源不一致 | wyckoff_phase.py:576-577,596 | 统一 TR 边界价来源 |
| FINDING-2 | 建议改(中) | markup 分支缺 `_dist_cluster` 簇兜底（与 accumulation_d 不对称） | wyckoff_phase.py:580 | 加 `not _dist_cluster` 守卫或文档化 |
| FINDING-3 | 建议改(中) | `use_persisted_phase` 默认 True，日线路径依赖默认致持久化 | wyckoff_core.py:604,1286；review_core.py:350,602；t0_run.py:195 | 默认改 False，显式按需开 |
| FINDING-4 | 需人工裁定 | 真实票 K 线目检（BC/Spring/SOS 命中位置） | — | 抽 3-5 只已知票联网核对 |

**无「必须改」项。**

---

## 9. 验证记录（跑了哪些、多少 passed）

- 基线复跑：wyckoff+report **179 passed**；chan **187 passed**；门禁 **810 passed / 4 skipped**（handoff 基线 796）。
- 自写只读验证脚本（落 `/tmp`，未入仓、未改源码）：
  - 查法 D `audit_d_phase_mapping.py`：19/19
  - 查法 E `audit_e_persistence.py`：16/16
  - 查法 A `audit_a_events.py`：7/7
  - 查法 B `audit_b_zones.py`：11/11
  - 查法 F `audit_f_trajectory.py`：10/10
- 合计自写断言 **73 项全绿**。

---

## 10. 修复记录（2026-08-08 父 Agent 决策后动手改）

父 Agent 在收益/风险权衡后决策：**改 F2 + 顺手 F1/F3（仅显式化，不动默认值）**。F4 真实票目检留待后续人工裁定。

### 已落地（本地 commit，未 push）
| 项 | 文件:行 | 改动 | 验证 |
|---|---|---|---|
| FINDING-2 | wyckoff_phase.py L574-593 | 把 `_dist_cluster` 定义从 L614 提前到 markup 段；markup 进入条件加 `and not _dist_cluster`（与 accumulation_d 的 Spring 分支对称） | 新增单测 `test_wyckoff_phase_dist_guard.py::test_distribution_cluster_guards_markup` 钉死「派发确认 + Spring+SOS+突破上沿 ≠ markup」 |
| FINDING-1 | wyckoff_phase.py L576 | markup 的 `tr_upper` 从 `signals` 改读 `tr_ctx`（与 markdown L596 对称，统一 TR 边界价来源） | 新增单测 `::test_finding1_tr_upper_read_from_tr_ctx` 钉死「tr_upper 仅存 tr_ctx 时仍能判 markup」 |
| FINDING-3 | wyckoff_core.py L1286 | 日线 `wyckoff_analysis(bars, symbol=symbol)` 显式加 `use_persisted_phase=True`（消除隐式依赖，行为不变，默认值不动） | 门禁 + wyckoff 系列全绿 |

### 回归结果（改后）
- wyckoff+report 系列：**199 passed**（含新增 2 项）
- 门禁 `run-gate-tests.sh`：**810 passed / 4 skipped**（与改前一致，零回归）
- 新增单测 `test_wyckoff_phase_dist_guard.py`：**2/2 passed**

### 刻意未改
- 不动 `use_persisted_phase` 默认值（改 False 会破坏日线 phase 稳健性，使池/复盘 wyckoff_score 更跳）
- 不动 fusion / decision_view / 出手 / 池分道（handoff 边界）
- FINDING-4 真实票目检未做（需联网拉 K 线，留待后续人工裁定）
