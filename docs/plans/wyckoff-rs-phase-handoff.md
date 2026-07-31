# 威科夫 RS 相对强弱 — 周线阶段置信修正 Agent Handoff

> **status**: done  
> **日期**: 2026-08-01  
> **分支**: `feat/wyckoff-rs-phase`  
> **产品法源**: `BUSINESS.md` §2.0 / §2.2（中线状态 = **仅周线威科夫**；对照指数 = `resolve_board_index`）  
> **目标**: 把原典 **Relative Strength（RS）** 接入**周线威科夫阶段机**（置信修正）+ **选股池操盘权重**（同道排序；弱 RS→等齐慎跟），不是新阶段、不单独开仓、不替代箱体/SC/AR  
> **读者**: 下一任实现 Agent（只读本文 + 法源 + 下列代码锚点即可动手）  
> **操盘挂接**: `attach_wyckoff_chain_fields` 透传 `rs_*`；`sort_items_unified` = lane→共振→链→**RS**→可碰→分（strong=3>neutral=1>weak=0）；`classify_lane` 弱 RS 将可盯降为等齐

---

## 0. 给 Agent 的 30 秒摘要

1. **RS 是什么**：个股相对**所属板块对照指数**的价量强弱（周线窗口），用于微调 `_detect_phase` 输出的 `phase_confidence_delta` 与 `WyckoffStateView.confidence`；**不得**单独改 `phase` 枚举。  
2. **对照指数 SSOT**：`market_env.resolve_board_index(sec)` — 688→科创50；300/301→创业板指；60→上证；00x→深成；其余→`INDEX_CODE`（中证1000）。**禁止**另搞「统一跟上证」。  
3. **行业涨跌**：`sector_data` / meta 行业 ±% 最多 soft 参考（报告可选一句），**不作** RS 主输入。  
4. **路径**：仅 `wyckoff_strategy_midline`（周线 `wyckoff_analysis` + `use_persisted_phase=False`）；日线「威科夫：仅对照」**可不接** RS（或展示一句但不改日线阶段机）。  
5. **规则方向**：相对强 → 同阶段置信略升（封顶）；相对弱 → 置信下调，Spring/吸筹叙事更谨慎（可类比 `spring_premature` 降权）；**禁止**仅凭 RS 把 `phase` 从 `none` 抬成 `markup` / `accumulation_d`。  
6. **缺数**：指数周线拉不到 → `rs_gate=missing` / `rs_label=neutral`，阶段机照常跑，**不挡**阶段。  
7. **依赖已落地**：P0-A/B（Spring test + TR 门控）、P1/P2 Phase A 种子箱 — 见 `wyckoff-phase-accuracy-handoff-2026-07-31.md`、`wyckoff-phase-a-range-handoff.md`；本任务**只加 RS 修正层**。

---

## 1. 产品定义（已定合同）

### 1.1 RS 角色边界

| 是 | 否 |
|----|-----|
| 周线阶段机的**置信修正因子** | 新 Wyckoff 阶段（无 `rs_phase`） |
| 进入 `_detect_phase` 后置修正 `phase_confidence_delta` | 单独开仓 / 共振 / fusion 席位 |
| 可选报告短句「强于/弱于{指数短标签}」 | 替代 `phase_a_range` / SC / AR / 箱体 |
| 弱 RS 时 Spring/吸筹类叙事降权（类似 premature） | 仅凭 RS 把 `none` → `markup` / `accumulation_d` |
| 对照指数与报告 meta / 环境档**同源** | 硬编码「全 A 跟上证」或第二套指数表 |

### 1.2 对照指数映射（与现码一致，勿复制）

```text
resolve_board_index(code_or_sec) -> (ts_code, short_label)

688*     -> 000688.SH  科创
300/301  -> 399006.SZ  创业板
60*      -> 000001.SH  上证
000/001/002/003 -> 399001.SZ  深成
其余     -> INDEX_CODE   中证1000（默认 000852.SH）
```

实现时**只 import 调用**，禁止在 wyckoff 模块内再维护一份前缀表。

### 1.3 时框与数据

| 项 | 合同 |
|----|------|
| 个股序列 | 已有 `weekly_bars`（`WEEKLY_LOOKBACK_BARS=260`） |
| 指数序列 | 同 provider `fetch_weekly(Security(ts_code=idx))`，窗口与个股对齐 |
| RS 计算窗 | 可配置，建议默认 **6 周**（允许 4～8）；常量名见 §3.2 |
| 聚合备选 | 若周线指数缺 bar，可尝试日线聚合为周（**非必须**，缺则 neutral） |
| 行业 | `sector_change_pct` 等**不得**作为主 RS；最多 View/报告 footnote |

### 1.4 典型修正规则（实现可调阈值，语义不可变）

**输入**：`rs_score` ∈ [-1, 1]（或分档 strong / neutral / weak）；`phase` 已由事件+TR 门控得出。

| RS 档 | 对已有非 `none` 阶段 | 对 Spring / 吸筹叙事 | 对 `none` |
|-------|----------------------|----------------------|-----------|
| **strong** | `phase_confidence_delta` += `Δ_up`（封顶，如 +0.05） | 不洗白 `spring_premature` | **仍 none**；仅 delta 可微升上限内 |
| **neutral** | 不改 | 不改 | 不改 |
| **weak** | `phase_confidence_delta` += `Δ_down`（如 -0.05～-0.08） | 等效加强 cautious：可与 weak 叠加 clamp View confidence | **仍 none**；禁止抬阶段 |

**硬规则**：

1. RS **只改** `phase_confidence_delta` / View `confidence` / 可选 `rs_*` 展示字段；**不改** `phase` 字符串（除既有 P0-B/P2 门控外）。  
2. `spring_premature=True` 时，RS strong **不得**取消 premature 或抬进 `accumulation_c/d`。  
3. `phase_tr_gated=True` 时，RS **不得**解锁门控或抬阶段。  
4. 弱 RS + Spring 亮灯：允许额外 `-0.05` 级 confidence 惩罚（文档化，与 premature -0.15 可叠加 clamp）。

---

## 2. 现状（代码事实）

| 点 | 现状 | 锚点 |
|----|------|------|
| 中线入口 | 周线独占；`use_persisted_phase=False` | `wyckoff_strategy_midline` |
| 阶段机 | `_detect_phase` 已输出 `phase_confidence_delta`（事件档 ±0.05～0.12） | `wyckoff_phase.py` |
| View 置信 | `base += phase_confidence_delta`；premature / tr_quality / gated 叠加 | `wyckoff_view._confidence` |
| 池打分 | `phase_confidence_delta * 20` 微调 raw | `calculate_wyckoff_score` |
| 对照指数 | `resolve_board_index` 已用于 meta / `context_stage` 环境档 | `market_env.py`；`context_stage._fetch_market_env` |
| 指数行情 | 实时 `_fetch_index_data`（腾讯）；**无**周线指数 SSOT  helper | `market_env._fetch_index_data` |
| 周线拉数 | `DataProvider.fetch_weekly(sec)` 支持任意 `Security` | `data_provider.py` |
| RS 占位 | accuracy handoff 预留 P1-RS；**现码无** `rs_*` 字段 | `wyckoff-phase-accuracy-handoff-2026-07-31.md` §5 |
| 行业 | `get_stock_sector_snapshot_cached`；与 RS **未接** | `context_stage._fetch_sector_data` |

---

## 3. 字段合同

### 3.1 写入 `wyckoff_analysis`（中线周线路径）

建议结构（名可微调，语义不可变）：

```text
rs_index: str | None           # 对照指数 ts_code，如 399006.SZ
rs_index_label: str | None     # 短标签，如 创业板（来自 resolve_board_index[1]）
rs_window_weeks: int             # 实际使用的窗口长度
rs_score: float | None         # 连续分 [-1, 1]；缺数 None
rs_label: str                  # "strong" | "neutral" | "weak" | "missing"
rs_gate: str                   # "" | "missing" | "insufficient_bars" | "disabled"
rs_confidence_delta: float     # RS 贡献的增量（与事件 delta 分账，便于审计）
rs_stock_return: float | None  # 窗口内个股涨跌幅（可选，调试/报告）
rs_index_return: float | None# 窗口内指数涨跌幅（可选）
rs_relative_return: float | None  # 差值或比值（可选）
```

**合并规则**（写入 analysis 顶栏）：

```text
phase_confidence_delta_final =
    phase_confidence_delta_event   # _detect_phase 事件档
  + rs_confidence_delta            # RS 后置修正（本任务）
```

对外兼容：短期可只暴露合并后的 `phase_confidence_delta` + 保留 `rs_confidence_delta` 分账；View / 打分读合并值。

### 3.2 建议常量（`config.py`）

```text
WYCKOFF_RS_ENABLED = True                    # 总开关；False 时 rs_gate=disabled
WYCKOFF_RS_WINDOW_WEEKS = 6                  # 默认 6；合法范围 4～8
WYCKOFF_RS_STRONG_THRESHOLD = 0.03           # 相对收益 ≥ 此 → strong（示例，须单测标定）
WYCKOFF_RS_WEAK_THRESHOLD = -0.03            # 相对收益 ≤ 此 → weak
WYCKOFF_RS_DELTA_STRONG = 0.05               # 置信上调封顶
WYCKOFF_RS_DELTA_WEAK = -0.06                # 置信下调
WYCKOFF_RS_SPRING_WEAK_EXTRA = -0.05         # 弱 RS + Spring 叙事额外惩罚（可选）
```

阈值须用 fixture 标定；**禁止** magic number 散落多处。

### 3.3 报告展示（可选，微信红线）

- 中线 `format_wyckoff_midline_light` / View `summary_oneline`：**可选**追加短片段，如 `强于创业板` / `弱于上证`（用 `rs_index_label`）。  
- **禁止** `#`、`**`、表格；与现有「阶段 · 箱体 · 事件 · 含义」并列时用全角 `｜` 或括号。  
- 日线 `format_wyckoff_daily_phase_light`：默认**不接** RS；若展示仅一句对照、**不改**日线 `_detect_phase` 入参。

---

## 4. 建议实现落点

### 4.1 模块切分（最小 diff）

```text
1) wyckoff_rs.py（新，或 wyckoff_core 内私有段）
   - compute_relative_strength(stock_weekly, index_weekly, window) -> rs dict
   - apply_rs_confidence_delta(phase_result, rs_dict) -> merged deltas

2) wyckoff_core.wyckoff_analysis
   - 仅当 timeframe=="weekly" 且 WYCKOFF_RS_ENABLED：
     idx_code, idx_label = resolve_board_index(symbol)
     index_weekly = provider.fetch_weekly(Security(...))  # 调用方注入或 lazy fetch
     rs = compute_relative_strength(...)
     phase = apply_rs after _detect_phase

3) wyckoff_strategy_midline
   - 传入 symbol/ts_code；负责拉指数周线（或接受 preloaded index_weekly）

4) wyckoff_view._confidence
   - 已读 phase_confidence_delta；合并后自动生效
   - 可选：weak + spring_premature 额外 clamp（若未在 phase 层做）

5) tests/test_wyckoff_rs.py
```

**指数拉数**：优先在 `wyckoff_strategy_midline` 层拉一次（与个股 weekly 同 provider），避免 `wyckoff_analysis` 隐式全局 provider。可复用 `get_provider()` + `Security(ts_code=idx_code, code=...)`。

### 4.2 接入 `_detect_phase` 的方式

**推荐**：`_detect_phase` **保持纯事件+TR**；RS 在 `wyckoff_analysis` 内 **post-process**：

```python
phase = _detect_phase(...)
rs = compute_rs(...)
phase = apply_rs_confidence(phase, rs)  # 只动 delta / rs_* 字段，不动 phase 键
```

**禁止**：在 `_detect_phase` 分支里写 `if rs_strong: phase = "markup"`。

### 4.3 与 premature / gated 的交互

| 条件 | RS strong | RS weak |
|------|-----------|---------|
| `spring_premature=True` | 不得抬阶段；delta 上调封顶更小（如 max +0.02） | 额外 `rs_confidence_delta` 负向 |
| `phase_tr_gated=True` | 不得抬阶段 | 仅降 confidence |
| `phase=="none"` | 不得改 phase | 不得改 phase |

---

## 5. 验收表

| ID | 用例 | 期望 |
|----|------|------|
| R1 | 688 个股，窗口内个股涨 8%、科创50 涨 2% | `rs_index=000688.SH`；`rs_label=strong`；`rs_confidence_delta>0`；`phase` 与无 RS 时相同 |
| R2 | 60 开头个股弱于上证（相对收益 ≤ weak 阈） | `rs_index=000001.SH`；`rs_label=weak`；`phase_confidence_delta` 低于无 RS 基线 |
| R3 | 300 个股对照创业板指 | `rs_index=399006.SZ`；**非**上证 |
| R4 | 指数周线拉取失败 | `rs_label=neutral` 或 `missing`；`rs_gate=missing`；阶段机仍输出 `phase` |
| R5 | `phase=none` + RS strong | `phase` 仍为 `none`；仅 delta 在允许范围内 |
| R6 | `spring_premature=True` + RS strong | 仍不进 `accumulation_c/d`；premature 仍为 True |
| R7 | `phase_tr_gated=True` + RS strong | 仍 gated；不抬阶段 |
| R8 | 弱 RS + 有效 Spring（非 premature） | 阶段不低于 P0-A 规则，但 `phase_confidence_delta` / View confidence ≤ 无 RS 对照 |
| R9 | `wyckoff_strategy_midline` 路径 | `rs_*` 仅出现在 `timeframe=weekly` analysis；日线 `wyckoff_strategy` 无 RS 或 `rs_gate=disabled` |
| R10 | `WYCKOFF_RS_ENABLED=False` | `rs_gate=disabled`；行为与现 main 一致（回归） |
| R11 | View `confidence` | 合并 delta 后 `_confidence` 与手工预期一致（strong > neutral > weak） |
| R12 | `calculate_wyckoff_score` | 使用合并后 `phase_confidence_delta`；RS 不双重加分 |

测试：新建 `tests/test_wyckoff_rs.py` + 扩 `test_wyckoff_tr.py`；fixture 用合成 weekly bars（**禁**全网抓数）。

---

## 6. 实现顺序与白名单

```text
1) config：WYCKOFF_RS_* 常量
2) wyckoff_rs.py：compute + apply（纯函数，易测）
3) wyckoff_core / wyckoff_strategy_midline：weekly 路径拉指数 + 挂 RS
4) wyckoff_view / format_wyckoff_midline_light：可选展示短句
5) tests R1–R12
6) BUSINESS.md §2.2 + inventory §七 标 done
```

**可改**：

- `trader_shared/config.py`
- `wyckoff_rs.py`（新）或 `wyckoff_core.py` 内 RS 段
- `wyckoff_strategy_midline` 签名/拉数（最小）
- `wyckoff_view.py`、`format_wyckoff_midline_light`（可选展示）
- `tests/test_wyckoff_rs.py`、`tests/test_wyckoff_*.py`

**勿改**：

- `fusion_core` 短线三席  
- 日线威科夫进中线定论  
- `resolve_board_index` 映射表（除非产品另开任务）  
- `_detect_phase` 内用 RS **改 phase 枚举**  
- 行业涨跌作主 RS  
- 选股池排序王 / 共振公式（RS 不进 fusion）

自测：

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest 02-共享模块-shared/tests/test_wyckoff_rs.py 02-共享模块-shared/tests/test_wyckoff_*.py -q
```

---

## 7. 非目标

| 项 | 说明 |
|----|------|
| RS 作新阶段 / 开仓信号 | 已定禁止 |
| 统一跟上证 / 第二套指数表 | 必须 `resolve_board_index` |
| 行业板块 RS 作主输入 | 最多 soft 展示 |
| 日线阶段机接 RS | 短线仅可选一句对照 |
| CM 行为显式建模 | 另开 |
| 完整 P&F | 另开 |
| 改 fusion / 共振权重 | 本任务不做 |

---

## 8. 与现码张力（开干前必读）

| # | 张力 | 建议 |
|---|------|------|
| 1 | `_detect_phase` 已大量输出 `phase_confidence_delta` | RS 用 **post-process 分账** `rs_confidence_delta`，再合并；避免在阶段机内叠床架屋 |
| 2 | `market_env` 有实时指数、**无**周线 helper | 用 `data_provider.fetch_weekly(Security(ts_code=idx))`；勿把 RS 塞进 `assess()` 日频环境档 |
| 3 | `wyckoff_analysis(bars, symbol=...)` 当前**不**拉外部序列 | 指数 weekly 在 `wyckoff_strategy_midline` 拉完传入，或给 analysis 增可选 `index_weekly_bars` 参数 |
| 4 | `plugin_registry` 调 midline 时未必传 ts_code | 确认 `symbol` / `sec` 传到 `wyckoff_strategy_midline` 以 resolve 指数 |
| 5 | View `_confidence` 已有 premature -0.15、tr_quality ±0.08 | RS 合并进 `phase_confidence_delta` 即可；弱 RS + Spring 额外惩罚避免重复计数 |
| 6 | `calculate_wyckoff_score` 走**日线** bars | 日线打分**可不接** RS，或仅当 analysis 已带 rs 字段且显式 weekly 路径；默认不改变池分 |
| 7 | accuracy handoff 写「勿假数据」 | 缺指数 → neutral + gate，**禁止**随机/常量伪造 strong |
| 8 | 北交所等回退 `INDEX_CODE` | 与 meta 一致；文档注明即可 |

---

## 9. 代码锚点速查

| 用途 | 符号 |
|------|------|
| 对照指数 SSOT | `market_env.resolve_board_index` |
| 环境档接线 | `context_stage._fetch_market_env` |
| 中线威科夫入口 | `wyckoff_core.wyckoff_strategy_midline` |
| 分析主路径 | `wyckoff_core.wyckoff_analysis` |
| 阶段机 | `wyckoff_phase._detect_phase` |
| 阶段置信 → View | `wyckoff_view._confidence` |
| 池打分阶段修正 | `wyckoff_core.calculate_wyckoff_score`（`phase_delta * 20`） |
| 中线面板 | `format_wyckoff_midline_light` |
| 周线拉数 | `data_provider.fetch_weekly` |
| 前置 handoff | `wyckoff-phase-accuracy-handoff-2026-07-31.md`（P0-A/B）；`wyckoff-phase-a-range-handoff.md`（Phase A） |

---

## 10. 完成定义（DoD）

- [x] 验收表 R1–R12 全绿  
- [x] `rs_*` 字段合同 §3.1 透出（weekly 路径）  
- [x] 对照指数 **仅** `resolve_board_index`；R3 单测锁映射  
- [x] 禁止 RS 单独抬 `phase`（R5/R6/R7 回归）  
- [x] 缺指数数据 neutral，不挡阶段（R4）  
- [x] `BUSINESS.md` §2.2 RS 标「已落地」并链本文  
- [x] `wyckoff-original-concept-inventory.md` §七 RS 行标 ✅  
- [x] 不扩大 scope 到 fusion / 日线阶段 / 行业主 RS  

---

## 11. 交接检查清单

- [x] 已读 `BUSINESS.md` §2.0、§2.2  
- [x] 已读 `wyckoff-phase-accuracy-handoff-2026-07-31.md` §5（P1-RS 占位）  
- [x] 已打开 `resolve_board_index` / `wyckoff_strategy_midline` / `_detect_phase` / `_confidence`  
- [x] 确认 RS **post-process**，不改 phase 枚举  
- [x] 确认日线 fusion / 池打分默认行为（是否接 RS）与 §4 一致  
- [x] fixture 就绪后再标 status=`done`
