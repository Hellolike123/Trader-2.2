# 系统可观测性 + 隐式状态治理 — Agent Handoff

> **status**: active（2026-08-08）
> **任务性质**: 工程优化（可改代码，但分阶段；先调研后改码）
> **范围**: 隐式状态地图、决策日志/可解释性、语义级回归、异常可见性、数据源溯源链
> **禁止**: 动 fusion / decision_view / 出手 / 池分道的**语义**；改报告面板的可见结构；把容错性 `except` 一刀切删（先计数后定夺）

---

## 0. 背景与动机

前序两轮审计已穷尽「静态·结构」象限（状态机自洽、枚举闭环、读写契约、文档对齐，见 `docs/plans/wyckoff-chan-state-audit-handoff.md` 与 commit `0c58ed6`）。但系统的真正风险藏在「动态·结构」与「动态·行为」两个象限——运行时才暴露的隐式状态污染、决策黑盒、语义退化、静默吞异常、混源不可溯源。

owner 原话：「数据它有没有算对，状态有没有确定好」+「还能够怎么样去优化和找问题」。

本 handoff 是 5 个工程方向 + 2 个简提，目标：**让系统自己把问题暴露出来，而不是靠人一个个去查**。优先级排序见 §6。

---

## 1. 隐式状态地图【先调研，后补防护】

### 问题
系统有多处跨会话/跨进程隐式状态，无版本号、无 schema 迁移、无统一失效策略。已知踩坑：TencentFetcher 跨进程偶发 100× 缩放坏点（MEMORY 已记）；改检测器阈值后旧缓存仍用老结论。

### 锚点
- `~/.trader/wyckoff_phase.json` — phase 持久化 + first_seen（`wyckoff_phase.py` `_load/_save_phase_state` L845-873）
- `~/.trader/backtest_cache/` — 回测落盘缓存（`scripts/backtest_engine.py`，已做跨进程坏点防护）
- `~/.trader/intraday_cache/` — 日内缓存（`scripts/intraday_backtest_engine.py`）
- `light_data.py` `_stamp_vol_unit` — 缓存 bar 打 vol_unit 标记
- golden 文件 — 渲染回归基准
- fund_flow 缓存 `{"data":[...], "cached_at":...}`（MEMORY 记的格式）

### 必须行为（分两阶段）
**阶段一（调研，不改码）**：grep 全仓所有 `~/.trader/` 落盘点 + 缓存读写，产出一张表：`文件/目录 | 写谁(文件:行) | 读谁(文件:行) | 有无版本号 | 失效条件 | 跨进程是否安全`。重点标红「写和读的假设不一致」「无版本号」「无失效策略」。
**阶段二（补防护，可改码）**：对阶段一标红的项，补 schema 版本号 + 失效策略（版本不符即作废重算）。参照 `backtest_engine.py` 已有的跨进程坏点防护写法（写前读后跑 >5× 中位数断言）。

### 验收
- 阶段一：隐式状态地图表（≥8 项），每项标风险等级
- 阶段二：标红项补版本号 + 失效测（改 schema 版本号 → 旧缓存被作废 → 重算）

---

## 2. 决策日志 / 可解释性【杠杆点，一举解决多查法】

### 问题
报告只给结论（`accumulation_d`、`fusion 分 72`），**为什么进这个 phase、为什么这个分**完全黑盒。复盘只能靠人工对 K 线猜。前序 handoff 的查法 D/E/F（信号→phase 映射、持久化污染、黄金样本回放）全靠人工，成本极高。

### 锚点
- `wyckoff_phase.py` `_detect_phase` L273-839（20+ if/elif 信号→phase 映射）
- `wyckoff_phase.py` `_transition_phase` L875-957（转移决策）
- `fusion_core.py` / `analysis/cards.py`（fusion 决策）
- `chan_core.py` `resolve_chanlun_primary` L854-977（方向优先级）

### 必须行为
在关键决策分支加一层 **trace**（不改变量、不改语义，只记「这一步走了哪个 if、命中了哪个信号、old/new phase 各是什么」），落盘成决策链 JSON。结构建议：
```json
{"bar": "2026-08-07", "signals": {"sc":true,"ar":true,"spring":false},
 "phase_path": [{"step":"sc_ar_b_ctx","hit":true}, {"step":"spring_premature","hit":false},
                 {"step":"acc_d_spring_test","hit":true,"out":"accumulation_d"}],
 "transition": {"old":"accumulation_b","new":"accumulation_d","rule":"same_dir_upgrade"},
 "fusion": {"cards":[...], "weighted":72}}
```
复盘某票时能回放：bar N 检测到 SC+AR → 进 A；bar M Spring 但 premature → 落 none；bar K Spring+Test → 进 D。

### 验收
- 一只票跑完，决策链 JSON 完整可读
- 前序 handoff 查法 D（信号→phase 映射）可用决策链自动断言，无需人工对 K 线
- trace 关闭时（默认生产可关）零性能损耗、零输出变化

### 边界
trace 是**只增不改语义**的旁路。不得用 trace 结果反过来改 phase 判定。开关默认关，调试/复盘时开。

---

## 3. 语义级回归测【防退化滑落】

### 问题
现靠 golden 文件防回归（`short_midline.py` 改了要刷新 golden）。但 golden 是**字符串 diff**——放过语义退化：输出字符串差不多（过 golden），但 phase 从 `accumulation_d` 退化成 `accumulation_c`，语义变了却无感。

### 必须行为
对一批固定票（10-20 只，跨行业），冻结期望的 **phase 轨迹序列** + **fusion 决策路径**（可复用 §2 的决策链输出）。改代码后跑这批票比对轨迹：
- 字符串可以变（格式调整合法）
- 语义轨迹（phase 序列 + 关键决策点）变了 → 报红，必须人工确认是「改进」还是「退化」

### 验收
- `tests/test_semantic_regression.py`：10+ 只票的 phase 轨迹快照
- 故意改坏一个阈值 → 轨迹快照报红（证明闸门有效）
- golden 仍保留作字符串层闸门，语义快照是第二道闸

---

## 4. 异常可见性【成本最低，收益快】

### 问题
全仓大量 `except Exception: pass` / `except: continue`（`_scan_for_signal` L269、`_detect_phase` 内多处、`_ar_verdict` L399 等）。数据层容错合理，但**全部静默吞掉**意味着 bug 永远看不见——检测器抛异常你都不知道，只看到「信号没检出」以为是行情没到。

### 必须行为（分两步）
1. **盘点**：grep 全仓 `except.*pass` / `except.*continue` / `except.*:` 后跟空或 return，分类：
   - 数据容错（保留，但加计数）
   - 逻辑兜底（改成计数 + 一次告警摘要）
2. **告警面板**：在 report 末尾或日志加「本次分析异常摘要」——把吞掉的异常按类型计数输出。改造成本极低，但把一批「沉默的错误」变可见。

### 验收
- 全仓 except 盘点表（分类 + 计数）
- 故意注入一个异常 → 异常摘要面板可见
- 生产路径默认开计数，不开抛出（保持容错）

### 边界
**禁止一刀切删 except**（会破坏数据层容错）。只加计数 + 摘要，不改变量控制流。

---

## 5. 数据源溯源链【出问题能定位源】

### 问题
tushare/腾讯/mootdx/akshare 四源 fallback，同一只票可能拿到不同源的混合数据。volume 单位踩坑史（FDE 轮错误假设被推翻，MEMORY 已记）的根因就是**混源时无溯源标记**，出问题不知道是哪个源的锅。

### 锚点
- `light_data.py` / `data_provider.py`（取数 + fallback）
- `get_provider` / `UnifiedProvider` / `TencentFetcher` / `TushareProvider`

### 必须行为
给每条 report 加一个 `_meta` 字段（不影响面板渲染）：
```json
{"daily_source": "tencent", "daily_cached": true, "vol_unit": "lot",
 "5m_source": "sina", "weekly_source": "tencent",
 "tushare_available": false, "fetched_at": "..."}
```
出问题 `print(report["_meta"])` 立刻定位是哪个源、哪个单位、缓存命中没。

### 验收
- `_meta` 字段在所有 report 产物中存在且非空
- 一只票走 tencent fallback 时 `_meta.daily_source=="tencent"`
- 面板渲染不受 `_meta` 影响（`short_midline.py` 不读 `_meta`）

---

## 6. 简提（本 handoff 不展开，登记待排期）

- **配置敏感性扫描**：60+ `WYCKOFF_*` 阈值（`config.py`）做一次 `--scan` 参数扫描（回测引擎已支持），找哪些阈值对结论影响最大、标定置信度。重点验 BC/Spring 量比类阈值。
- **跨周期压测**：日线/周线/月线 phase + 缠论中枢 + EXPMA 动能，三个「阶段」字段并存（`midline_stage`/`stage_line`/`major_stage`/`short_term_momentum`，见 `stage_fields.py`）。构造「日线积累但周线派发」的边界票，验是否真不串台、面板是否自洽。

---

## 7. 法源（必读）

- 前序审计 handoff：`docs/plans/wyckoff-chan-state-audit-handoff.md`（状态语义保真，只读查）
- 前序修复 handoff：`docs/plans/report-wyckoff-state-fixes-handoff.md`（状态机修复，已完成）
- MEMORY（`.workbuddy/memory/MEMORY.md`）：volume=手、tushare/腾讯数据源取舍、跨进程坏点史
- `02-共享模块-shared/trader_shared/formulas.md`：缠论法源
- `AGENTS.md`「改代码去哪」表：引擎只在 `trader_shared/`，skill 包是 shim

---

## 8. 可改 / 勿改

**可改**：
- `wyckoff_phase.py` / `fusion_core.py` / `analysis/cards.py` / `chan_core.py`（加 trace，不改语义）
- `light_data.py` / `data_provider.py`（加 `_meta` 溯源字段）
- `tests/`（新增语义回归测、异常计数测）
- `config.py`（若补 schema 版本号）
- 新增 `scripts/` 调研脚本（隐式状态地图扫描）

**勿改**：
- fusion / decision_view / 出手 / 池分道的**判定语义**（可加 trace，不改 if/elif 分支条件与结论）
- 报告面板的可见结构（`short_midline.py` 的 lines 输出格式）
- 阶段机主枚举语义
- 一刀切删容错性 `except`（先计数后定夺）
- 中线周线 `use_persisted_phase` 保持 False

---

## 9. 可运行验证（基线，确保不回归）

```bash
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_wyckoff_core.py \
  02-共享模块-shared/tests/test_report_mid_short_sources.py -q --tb=short
# 期望: 179 passed

PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_chan_core.py \
  02-共享模块-shared/tests/test_chan_segments_bug_r.py \
  02-共享模块-shared/tests/test_chan_segments_no_overcut.py \
  02-共享模块-shared/tests/test_chan_split_equivalence.py -q --tb=short
# 期望: 187 passed

bash scripts/run-gate-tests.sh
# 期望: 796 passed, 4 skipped
```

---

## 10. 优先级与杠杆点

| 序 | 方向 | 性质 | 杠杆 |
|----|------|------|------|
| 1 | 隐式状态地图 | 先调研后补防护 | 排雷，根治跨进程坏点类问题 |
| 2 | 决策日志 | 加 trace 旁路 | **最大杠杆**：做完后前序 handoff 的查法 D/E/F 全自动化 |
| 3 | 异常可见性 | 加计数+摘要 | 成本最低，沉默错误变可见 |
| 4 | 语义级回归 | 加测试 | 防 golden 放过退化 |
| 5 | 数据源溯源链 | 加 _meta | 出问题能定位源 |

**一句话**：前序查了「代码会不会自相矛盾」，本 handoff 做完，系统会自己把「哪里算错、为什么进这个状态、哪个源出了问题」暴露出来——从「人找问题」变成「问题找人」。
