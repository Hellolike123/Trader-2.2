# 威科夫阶段辨识准确度 — Agent Handoff

> **status**: done（P0-A / P0-B 已落地；P1-RS 仍另开）  

> **日期**: 2026-07-31  
> **产品法源**: `BUSINESS.md` §2.0 / §2.2（中线状态 = **仅周线威科夫**）  
> **目标**: 提升中线阶段辨识，不是加分、不是改短线 fusion  
> **读者**: 下一任实现 Agent（只读本文 + 法源 + 下列代码锚点即可动手）

---

## 0. 给 Agent 的 30 秒摘要

1. 用户分工：**中线状态用周线威科夫**；短线交易用日线缠论；动量只参考。  
2. 文档合同已钉死；**阶段仍漂**，因算法缺口未做。  
3. 本 handoff 只做两刀（按序）：  
   - **P0-A** Spring 后确认测试（Test of Spring）与 ST 语义拆清，并接入阶段机  
   - **P0-B** 低质量 TR 不进 / 不抬升阶段  
4. **P1-RS**（个股 vs 大盘）另开任务；本文只留接口位，勿在本 PR 塞大盘管线。  
5. 禁止：日线回退定中线；改 fusion 席位；把动量写进阶段。

---

## 1. 现状（代码事实，勿再审计一遍）

| 点 | 现状 | 锚点 |
|----|------|------|
| 中线入口 | 周线独占；不足 → `insufficient` | `wyckoff_strategy_midline` |
| TR | 已有 `tr_quality` 0~1；打分层有质量微调 | `_detect_trading_range`；`calculate_wyckoff_score` |
| 阶段机 | `_detect_phase`；Spring 无 B 背景标 `spring_premature` | `wyckoff_phase.py` |
| 「ST」 | `_detect_st` **已经是** Spring 后 3–15 根缩量回测；字段名仍叫 `st_*` | `wyckoff_events._detect_st` |
| 缺口 A | 展示/链/阶段仍把「Test of Spring」叫成笼统 ST；**C→D 不要求确认测试**（Spring+SOS/LPS 即可 D） | `_detect_phase` accumulation_c/d 分支 |
| 缺口 B | `tr_quality` **只调分数**，**不挡阶段**；烂 TR 仍可判 accumulation_* / markup | `_detect_phase` 未读质量门槛 |
| SC 后二次测试 | 原典 ST（测 SC/AR）**未独立实现**；本 PR **不做**（见 §5 非目标） | — |

常量：`config.py` 中 `WYCKOFF_TR_*`、`WYCKOFF_PHASE_LOOKBACK`、`WYCKOFF_TR_QUALITY_NEUTRAL=0.5`。

---

## 2. P0-A — Spring 确认测试（Test of Spring）与 ST 语义分离

### 2.1 产品定义

| 名 | 含义 | 本仓落点 |
|----|------|----------|
| **Test of Spring** | Spring **之后**对支撑的缩量确认回测 | 现有 `_detect_st` 逻辑实质即此 |
| **ST（广义）** | 原典里还可指 SC/AR 后二次测试 | **本 PR 不新增**；勿再把 Spring 确认叫成唯一「ST」 |

### 2.2 必做

1. **新增显式字段**（与 `st_*` 并存一版，避免砸下游）：  
   - `spring_test_signal` / `spring_test_reason` / `spring_test_price`  
   - 实现：优先 **薄封装** `_detect_st` 结果映射（同源），或把 `_detect_st` 内部分成 `_detect_spring_test` 再让 `st_*` alias 兼容。  
   - 兼容：`st_signal == spring_test_signal` 至少一个发布周期（测试断言双写）。

2. **阶段机**（`_detect_phase`，仅改积累 C/D，勿重写整机）：  
   - **accumulation_c**：`有效 Spring` 且 **无** `spring_test`（且尚无 SOS/LPS/BU）→ 维持 C。  
   - **accumulation_d（确认优先）**：`有效 Spring` + `spring_test` → 可进 D（`phase_confidence_delta` ≥ 现 Spring+回踩档）。  
   - **保持**：`Spring + SOS/LPS` 仍可进 D（原典 Jump/强确认路径），但文案区分：  
     - 有 spring_test：`积累期 D（确认：Spring+Test）`  
     - 仅 SOS/LPS：`积累期 D（确认：Spring+SOS/LPS）`  
   - **禁止**：仅凭裸 Spring 直接 D。  
   - `spring_premature=True` 时：不得因 spring_test 抬升阶段（确认测试不能洗白孤立 Spring）。

3. **展示 / View / 链**（最小）：  
   - `WyckoffStateView` / 中线 oneline / 池链：事件名优先显示「Spring确认」或 `Test`，勿只写模糊「ST」。  
   - 吸筹链若有「还差 xxx」：Spring 已亮且无 test → 可写「还差Spring确认」（可选，有则更好）。

4. **打分**：`spring_test` 与现 `WYCKOFF_SCORE_ST` 同源计分，**勿双重加分**（若双写字段，只计一次）。

### 2.3 验收（必须有测）

| ID | 用例 | 期望 |
|----|------|------|
| A1 | 有效 Spring，其后无缩量回测 | `accumulation_c`；`spring_test_signal=False` |
| A2 | 有效 Spring + 3–15 根内缩量回测未破支撑 | `spring_test_signal=True`；阶段 ≥ C，优先 D（无 SOS 也可 D） |
| A3 | `spring_premature` + 假确认 | 阶段不进 accumulation_c/d |
| A4 | Spring + SOS，无 test | 仍可 D；文案走 SOS 路径 |
| A5 | `st_signal` 与 `spring_test_signal` 一致（兼容） | 同布尔 |

测试文件：扩 `tests/test_wyckoff_core.py` / `test_wyckoff_original_gaps.py`；必要时小 fixture，禁全网抓数。

### 2.4 非目标（A）

- 不实现「SC 后 Secondary Test」独立检测器（可留 TODO）。  
- 不改日线 fusion 权重。  
- 不强制删除 `st_*` 字段（本 PR 双写即可）。

---

## 3. P0-B — 低质量 TR 不抬升阶段

### 3.1 产品定义

烂区间（窄、碎、质量低）上的事件 **可以亮灯**，但 **不得把中线阶段抬成明确积累/派发/主升主跌**。  
状态岗宁可 `none` / 低置信，不可「假阶段」。

### 3.2 门槛（写入 `config.py`，可调）

```text
WYCKOFF_PHASE_MIN_TR_QUALITY = 0.35   # 建议默认；低于此 = 低质量
```

规则：

| `tr_ctx` | 阶段机行为 |
|----------|------------|
| `None`（无 TR） | **允许** phase=`none` / 不足类；**禁止** 因孤立事件进 `accumulation_*` / `distribution_*` / `markup` / `markdown`（已有 premature 逻辑的继续保留）。例外：若现码在无 TR 时仍给 A/B，本 PR **收紧为**：无 TR 或低质量 → 最高只保留事件灯，阶段输出 `none` 或现有「无明确阶段」类，并设 `phase_tr_gate=low_quality\|no_tr`。 |
| `tr_quality < MIN` | 同上：事件可出；**阶段不抬升**到 A–E / markup / markdown |
| `tr_quality ≥ MIN` | 现有 `_detect_phase` 逻辑 |

注意：

- 打分层已有 `tr_quality` 微调 → **保留**；本刀是 **阶段门控**，别删打分逻辑。  
- 周线路径：`timeframe=weekly` 时同样适用（中线主路径）。  
- `tr_quality` 已在 `wyckoff_analysis` 透出；阶段入口读 `tr_ctx["tr_quality"]`。

### 3.3 建议实现落点

1. `_detect_phase(...)` 开头：算 `tr_ok`；若否，早退到 gated 结果（保留 `spring_premature` / `upthrust_premature` 计算所需的扫描可简化：门控时可不赋阶段）。  
2. 透出：`phase_tr_gated: bool`、`phase_tr_gate_reason: str`（便于报告/调试）。  
3. View：`summary_oneline` 或 confidence 反映「TR 质量不足，阶段不参与定论」类语义（微信红线：无 `#`/`**`/表格）。

### 3.4 验收

| ID | 用例 | 期望 |
|----|------|------|
| B1 | 人工 fixture：`tr_quality=0.2` + Spring 形态 | 可有 `spring_signal`；`phase` 不为 accumulation_c/d/markup |
| B2 | `tr_quality=0.6` + 有效 Spring+test | 可按 P0-A 进 C/D |
| B3 | `tr_ctx=None` + 一堆事件 | `phase` 不进明确 A–E（gated） |
| B4 | 周线 `wyckoff_strategy_midline` 路径跑通门控 | `timeframe=weekly` 或 insufficient 行为不变 |

---

## 4. 实现顺序与文件白名单

```text
1) config：WYCKOFF_PHASE_MIN_TR_QUALITY
2) wyckoff_events：spring_test_* 双写（封装 _detect_st）
3) wyckoff_core：analysis 透出 spring_test_*、phase_tr_*
4) wyckoff_phase：P0-B 门控 → P0-A C/D 条件
5) wyckoff_view / 链展示（最小）
6) tests + 刷新必要 baseline（仅因字段新增时）
```

**可改**：

- `trader_shared/config.py`
- `wyckoff_events.py` / `wyckoff_core.py` / `wyckoff_phase.py` / `wyckoff_view.py`
- 池链若只读事件名：`wyckoff_chain.py`（仅展示，勿改排序王）
- `tests/test_wyckoff_*.py`、相关 fixtures

**勿改**：

- `fusion_core` 短线三席权重  
- `chan_*` 买卖点  
- 中线威科夫改回日线 fallback  
- 完整 P&F / RS 大盘接入（P1）

自测：

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest 02-共享模块-shared/tests/test_wyckoff_*.py -q
```

---

## 5. 非目标 / 下一迭代

| 项 | 说明 |
|----|------|
| P1 RS | 个股 vs 大盘相对强弱注入 `wyckoff_analysis`；需稳定指数周线序列。本 PR 只可留 `rs_vs_market=None` 占位，**不要**假数据。 |
| SC 后 ST | 与 Test of Spring 不同；另开计划 |
| P&F | 已有 TR 1:1 投射；非本 PR |
| 改 BUSINESS 岗位合同 | 已定稿；勿削弱「周线独占」 |

---

## 6. 完成定义（DoD）

- [x] P0-A / P0-B 验收表全绿  
- [x] 中线仍周线独占（`test_no_daily_fallback` 类不回归）  
- [x] inventory：`Test of Spring` → ✅；§五 TR 门控阶段可注一句「阶段机读 MIN_TR_QUALITY」  
- [x] `BUSINESS.md` §2.2 演进清单 2、3 可标「已落地」或链到本文件 done  
- [x] 不扩大 scope 到 RS/P&F  

---

## 7. 交接检查清单（开干前勾选）

- [ ] 已读 `BUSINESS.md` §2.0、§2.2  
- [ ] 已打开 `_detect_st` / `_detect_phase` / `_detect_trading_range`  
- [ ] 确认本 PR **不**做 RS  
- [ ] 阈值默认 `0.35`；若单测夹具大量误伤，只调 config，不删门控  
