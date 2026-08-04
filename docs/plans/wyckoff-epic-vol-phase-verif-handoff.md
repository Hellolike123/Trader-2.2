# 威科夫下一轮 epic — volume 单位(A) + 阶段机滑窗收尾(B) + 实票验证工程化(C) — Agent Handoff

> **status**: 待实现（交接说明 9 bug 已全闭环；本 epic 为三方向遗留收尾，用户批准「全做」）  
> **日期**: 2026-08-04  
> **外部法源**: WorkBuddy `wyckoff-sos-修复交接说明.md` Bug E（§5）+ §11 验证清单  
> **关联**: `wyckoff-sos-epic-fde-handoff.md`（E-P3 标注 mootdx 日线 out of scope）、`wyckoff-epic-phase-unify-handoff.md`（P-M4 保留子窗 AR 锚重算）  
> **读者**: 实现 / 查 Agent（只读本文 + 代码锚点）

---

## 0. 30 秒摘要

1. **A · volume 单位统一（数据层）**：日线 fallback 源（sina/mootdx/pytdx3）volume 单位=手、腾讯日线=股——腾讯失败走 fallback 时量比/基线均量 ×100 失真。修法：fallback 返回前 ×100 归一到股（与 FDE 轮周线同原则），新写缓存打 `vol_unit="share"` 标记。**日线文件缓存恒来自腾讯成功路径（fallback 不写缓存）→ 旧缓存天然是股，无需强制失效**。  
2. **B · 阶段机滑窗结构收尾（审计为主）**：P-M4 后子窗内 AR/ST 仍各自重算 SC 锚（历史定位语义）；周线半幅窗口（`_tf_scan_params`）在新架构下需自洽验证。交付撕裂点审计报告 + 可统一且低风险的统一。  
3. **C · 实票验证工程化**：交接 §11 四票（南网 688248/茅台 600519/宁德 300750/工行 601398）验证清单 → 基于 `~/.trader/cache` 缓存的离线回归测试（不触网、skip-if-missing）。四票缓存已确认存在（688248 日线 370 根 last=07-31、周线 171 根 last=08-03 旧格式）。  
4. **不改**：腾讯日线 volume（=股基准）、检测器逻辑、阶段权重/窗口参数、fusion/出手/池、渲染层。

---

## 1. 必须 / 禁止

### 方向 A — 日线 fallback volume 单位（`light_data.py`）

背景事实（已核实）：
- `_fetch_qfq_daily_raw`（light_data.py:1381）腾讯成功路径才写文件缓存（:1520-1526）；fallback（sina `:1534`、pytdx3 `:1544`、mootdx `:1553`）**不写文件缓存** → 日线缓存恒腾讯=股
- `_fetch_daily_sina`（:1310）：sina getKLineData scale=240，与周线同接口（交接已证 sina 周线=手）→ sina 日线=手
- `_fetch_qfq_mootdx`（:743）/ `_fetch_qfq_tdx3`（:367）：通达信协议，`vol` 字段=手
- 熔断分支（:1388-1413）读缓存——恒股

| # | 合同 |
|---|------|
| A-M1 | `fetch_qfq_daily` 各 fallback 分支（sina/mootdx/pytdx3）返回前 volume ×100 归一到股（与腾讯日线同单位）；以源码/协议证据为准，若某源实为股则跳过并注释理由 |
| A-M2 | 腾讯成功路径写缓存时，每根日线 bar 打 `vol_unit="share"` 标记（与周线 `_stamp_vol_unit_share` 同风格，可复用/抽公共 helper）；读取侧**不**做旧缓存强制失效（旧缓存恒股，无单位风险） |
| A-M3 | 归一后日线量比/基线均量与周线（已归一）跨周期可比 |
| A-M4 | 有 pytest：三个 fallback 源各自 ×100（构造行验证）；腾讯路径不乘；新缓存带标记；旧缓存（无标记）读取行为不变 |

| # | 禁止 |
|---|------|
| A-P1 | 不改腾讯主路径 volume（=股基准）；不改检测器（量比/均量消费方零改动） |
| A-P2 | 不强制失效/重写旧日线缓存（无单位风险，避免当天全量回源） |
| A-P3 | 不重复乘（fallback 若内部已有 ×100 逻辑需先确认——按源码事实为准） |
| A-P4 | 不改周线路径（FDE 轮已完成）与 `_fetch_mins_*` 共用函数内部（分钟线单位不在范围） |

### 方向 B — 阶段机滑窗结构收尾（`wyckoff_phase.py` 审计 + 低风险统一）

背景事实（已核实）：
- P-M4 剥离后，子窗内 `_detect_ar`（`_scan(_detect_ar, ...)` wp.py:358-360）仍调 `_find_sc_anchor(sub, ...)` 子窗重算锚——与主流程 AR 灯（完整序列锚）索引口径可能不同（历史定位语义）
- `_scan`/`_last` 其余事件（spring/ut/bc/sow/compression/trend_*）不消费 SC 锚（TR 已统一）
- 周线半幅（`_tf_scan_params` wp.py:122-138 + lookback 12 wc.py:615）是数据频率适配，非撕裂

| # | 合同 |
|---|------|
| B-M1 | 交付**撕裂点审计报告**（写入 `workflows/phase-scan-audit/`）：逐项列出 `_detect_phase` 滑窗内仍重算结构的检测器（AR/ST/…）、与主流程的索引/锚差异、影响面（哪些阶段判定受影响） |
| B-M2 | 对每个撕裂点给出结论：**统一方案**（低风险、有测试）→ 实现；**论证保留**（高风险/历史定位语义合理）→ 写明理由 |
| B-M3 | 若实现统一（如 AR 子窗锚）：须处理索引空间（子窗内消费统一锚需映射或检测器支持外部锚），有 pytest |
| B-M4 | 周线自洽验证：W-S1a~S3 测试（`test_wyckoff_weekly_scan_windows.py`）在新架构下重跑全绿；`_tf_scan_params` 半幅值**不得**改动 |

| # | 禁止 |
|---|------|
| B-P1 | 不改 `_tf_scan_params` 半幅规则与周线 lookback（数据频率适配，非撕裂） |
| B-P2 | 不改阶段权重/映射（`_PHASE_ORDER`、事件→阶段加分） |
| B-P3 | 不改 `_find_sc_anchor`/`_detect_ar`/`_detect_st` 主体（若统一需 events 侧配合 → 先列待裁决，不自行改） |
| B-P4 | 不因「审计发现撕裂」擅自扩大改动面（只统一 B-M2 判定为低风险的点） |

### 方向 C — 实票验证工程化（`tests/test_wyckoff_realstock_verification.py`）

背景事实（已核实）：
- 四票缓存存在：`~/.trader/cache/daily/{688248,600519,300750,601398}.json`（688248 日线 370 根 last=2026-07-31）；`~/.trader/cache/weekly/688248_SH.json`（171 根 last=08-03，旧格式无 vol_unit）
- 688248 日线缓存 last=07-31 → **08-03 突破日不在缓存** → SOS 断言以缓存数据边界为准（有则断、无则断 TR/BC/dist）

| # | 合同 |
|---|------|
| C-M1 | 新建 `tests/test_wyckoff_realstock_verification.py`：直接读缓存 JSON 构造 bars 列表（**不触网**、不经过 fetch 层），`wyckoff_analysis` 跑四票；缓存缺失 → `pytest.skip` |
| C-M2 | 南网 688248（日线 + 周线）：TR 非空（fallback 生效）、BC 亮（90 根窗口内 5-6 月派发顶）、`distribution_confirmed=False`、`sos_kind` 字段存在、周线 volume 单位与日线可比（若周线缓存为旧格式手单位 → 断言按缓存实际值注明） |
| C-M3 | 茅台 600519：SC 失效场景（若数据含）→ `ar_reason` 含「失效」不含「未检测到 SC」；否则断言字段结构完整（ar_reason 非空） |
| C-M4 | 宁德 300750 / 工行 601398：防误报——按数据实际断言（无明显异常事件簇 / 无矛盾字段：`accumulation_confirmed ∧ phase_a_status=failed` 不得并存） |
| C-M5 | 断言边界以缓存数据为准：缓存不可断的场景（如缺 08-03）在测试注释与报告中**明确标注**，不得臆造 |

| # | 禁止 |
|---|------|
| C-P1 | 测试不得触网（mock/直接读缓存；失败只 skip 不报红） |
| C-P2 | 不修改缓存文件、不写真实 `~/.trader` 状态（临时目录隔离） |
| C-P3 | 不把「数据不足」伪装成通过（skip 或明确标注，不硬断言） |

---

## 2. 字段合同

```text
# A — 日线 bar（腾讯成功路径写缓存前）
vol_unit: "share"          # 每根日线 bar；fallback 归一后同样打标
# fallback 归一：volume ×100（sina/mootdx/pytdx3，单位=手 → 股）

# B — 无新字段（审计报告 + 可选统一，统一时按 A 轮 tr_ctx.sc_anchor 同风格设计）

# C — 无新字段（测试断言消费既有输出）
```

---

## 3. 可改文件白名单

| 文件 | 方向 |
|------|------|
| `02-共享模块-shared/trader_shared/light_data.py` | A（fallback 归一 + 标记；仅 `fetch_qfq_daily` 相关函数） |
| `02-共享模块-shared/trader_shared/wyckoff_phase.py` | B（仅审计结论批准的低风险统一点） |
| `02-共享模块-shared/tests/test_light_data_weekly.py` | A 测例（或新建 test_daily_fallback_volume.py） |
| `02-共享模块-shared/tests/test_wyckoff_phase_timeframe.py` | B 回归（若需） |
| `02-共享模块-shared/tests/test_wyckoff_realstock_verification.py` | C（新建） |
| `workflows/phase-scan-audit/` | B 审计报告 |
| 本文 + docs | 文档 |

勿改：`wyckoff_events.py`（除非 B 审计结论明确需 events 配合 → 先列待裁决）、`wyckoff_core.py`、`wyckoff_render.py`、`indicator_math.py`、`cache_utils.py`、`_fetch_mins_*` 共用函数、fusion/出手/池、阶段权重/`_tf_scan_params`。

---

## 4. 验收表

| ID | 场景 | 期望 |
|----|------|------|
| A1 | sina/mootdx/pytdx3 日线 fallback | volume ×100（=股），腾讯路径不乘 |
| A2 | 新日线缓存 | 每根 bar 带 `vol_unit="share"`；旧缓存读取行为不变 |
| A3 | 跨周期可比 | 日线量比与周线（已归一）同单位（构造验证） |
| A4 | 门禁 | `scripts/run-gate-tests.sh` 全绿（golden/split 若有漂移：先验证再刷新，禁止无脑） |
| B1 | 审计报告 | `workflows/phase-scan-audit/` 撕裂点清单 + 每点结论（统一/保留+理由） |
| B2 | 低风险统一点 | 实现 + pytest + 回归全绿 |
| B3 | 周线自洽 | W-S1a~S3 全绿，`_tf_scan_params` 未动 |
| C1 | 四票离线回归 | 全过或 skip（缓存缺失场景）；断言边界注明 |
| C2 | 南网关键断言 | TR 非空 / BC 亮 / dist 不误确认 / sos_kind 存在 |
| C3 | 防误报 | 茅台文案 / 宁德·工行无矛盾字段 |

---

## 5. 基线刷新纪律（沿用前几轮）

1. 实现后跑全量测试，记录 golden/split 漂移清单（`python scripts/golden_diff_gate.py check` + split equivalence）
2. 逐项验证漂移是有意的才 capture；禁止无脑刷新
3. 门禁全绿为合入前提

---

## 6. 流程与提交纪律

1. **双 Agent 闭环**：写 Agent 按本文实现（分方向 commit：A/B/C 各自独立 commit，便于回滚）→ 查 Agent 独立逐项对照（默认不改码，列必须再改）→ 父 Agent 修完再 push
2. commit message 附法源链接 + 对照条款编号
3. 本文（handoff）与审计报告随实现 commit 入库

---

## 7. 回滚

- A：`git revert` 实现 commit；`vol_unit` 标记无破坏性（旧缓存不受影响）
- B：`git revert`；审计报告为文档，无回滚需求
- C：`git revert`（纯测试文件）
