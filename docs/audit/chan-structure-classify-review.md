# 缠论结构分类修复 — Reviewer 审查报告

> 日期：2026-07-10  
> 审查人：Reviewer Agent（只读 + 跑测，未改业务代码）  
> 计划：`docs/chan-structure-classify-fix-plan.md`  
> 判定：**通过**

---

## 1. 总判

| 项 | 结果 |
|----|------|
| 总判定 | **通过** |
| P0 阻塞 | **无** |
| P1 改进 | 2 项（非阻塞） |
| 相关 pytest | **102 passed**（0.07s） |

业务真理（§1 中枢拓扑定名、段数只调 conf、消灭「线段不足」主状态、日周 conf 分离、报告 midline/daily 不交叉）与当前实现一致，回归标准 §3 单测覆盖充分。

---

## 2. 验收清单（逐项）

### [PASS] 业务：structure_type 主状态无线段不足

**证据**

- `classify_structure` 文档与实现仅允许：
  `无结构 / 单边上涨 / 单边下跌 / 盘整 / 上涨趋势 / 下跌趋势`
- 主路径 `return` 全部经 `_ok(st)`，无任何 `f"线段不足..."` 返回
- `rg "线段不足"` 在 `chan_core.py` 仅剩：
  - 文档注释「禁止返回」
  - `format_chanlun_theory_line` **兼容历史缓存**（映射为「结构未成型」，非新主状态产出）
- 全仓除计划文档外，**无** `return ...线段不足` / `MIN_SEGMENTS_TREND` 残留

### [PASS] 业务：2 中枢同向 + 4～6 段 → 上涨/下跌趋势

**证据**

```text
# classify_structure（拓扑后）
if zones_trend in ("上涨趋势", "下跌趋势"):
    return _ok(zones_trend)   # 不再 seg_count < 11 硬失败
```

单测：

| 用例 | 期望 |
|------|------|
| `test_two_ascending_pivots_five_segs_is_uptrend` | 5 段 → `上涨趋势`，daily conf=`mid` |
| `test_trend_low_conf_with_four_segments` | 4 段 → `上涨趋势`，daily conf=`low` |
| `test_uptrend` / `test_downtrend` | 11 段 → 趋势 + conf=`high` |

### [PASS] 代码：classify 无 11/5 硬失败返回线段不足

**证据（diff 删除路径）**

```diff
- MIN_SEGMENTS_CONSOLIDATION = 5
- MIN_SEGMENTS_TREND = 11
- if seg_count < MIN_SEGMENTS_TREND:
-     return _ok(f"线段不足{seg_count}/{MIN_SEGMENTS_TREND}")
- if seg_count < MIN_SEGMENTS_CONSOLIDATION:
-     return _ok(f"线段不足{seg_count}/{MIN_SEGMENTS_CONSOLIDATION}")
```

段数仅进入 `_structure_confidence` → `high|mid|low`。

### [PASS] 代码：日周 conf 参数分离（config）

**`config.py`**

| 常量 | 值 | 与计划建议 |
|------|-----|-----------|
| `CHAN_DAILY_TREND_SEGS_HIGH/MID` | 8 / 5 | 一致 |
| `CHAN_DAILY_CONSOL_SEGS_HIGH/MID` | 5 / 3 | 一致 |
| `CHAN_WEEKLY_TREND_SEGS_HIGH/MID` | 5 / 3 | 一致 |
| `CHAN_WEEKLY_CONSOL_SEGS_HIGH/MID` | 3 / 2 | 一致 |

**消费点**

- `_structure_conf_thresholds(timeframe)` → weekly vs daily 两套
- `chanlun_strategy` → `timeframe="daily"`
- `chanlun_strategy_midline` 周 K 足 → `conf_tf="weekly"`；日 K 回退 → `conf_tf="daily"`

单测：`test_daily_vs_weekly_conf_thresholds`（同拓扑 5 段：daily=`mid`，weekly=`high`）。

### [PASS] 代码：段数只影响 conf/evidence

**证据**

- 主名：中枢拓扑（0/1/2+ 同向或重叠）
- `structure_confidence`：段数 × timeframe 门槛
- `structure_evidence`：`segments={n},pivots={m}`
- `chanlun_analysis` 透传 `structure_confidence` / `structure_evidence`
- 0 中枢有线段 → `盘整` + conf 通常 `low`（弱盘整，符合 §1.3）

### [PASS] 代码：midline/daily 报告引用不交叉

**`report_core.py` 理论区（约 168–178 行）**

```python
_chan_mid = r.get("chanlun_midline")
# 严格用中线缠结果，禁止回退到日线 fusion
_chan_compact = format_chanlun_theory_line(_chan_mid)
```

**短线专家区（约 189–199 行）**

```python
_csig2 = fusion_signals.get("chan")  # 日线 fusion 事件信号
```

**双源策略**

| 函数 | timeframe 标记 | 用途 |
|------|----------------|------|
| `chanlun_strategy` | `daily` | fusion / 短线 |
| `chanlun_strategy_midline` | `weekly` / `daily_fallback` / `insufficient` | 理论行 |

单测：`test_daily_and_midline_timeframe_separated`、`test_theory_line_*`。

说明：本轮相关测试**未**直接 import `report_core` 断言理论字段源；以代码静态审查 + midline 单元测试为准，**PASS**。P1 见下。

### [PASS] 单测覆盖计划 §3

| §3 回归项 | 覆盖 |
|-----------|------|
| 主状态几乎不再 `线段不足*` | `test_chan_core` 多处 `assert not startswith`；`test_midline_structure_not_segment_insufficient`；全流水线 `test_full_pipeline_has_segments` |
| 2 中枢 + 4～6 段 → 趋势，conf 可 low | `test_two_ascending...`、`test_trend_low_conf_with_four_segments` |
| 周线稳定给盘整/趋势而非线段不足 | `test_midline_structure_not_segment_insufficient`（允许集仅限合法主状态） |
| 下游 unwrap 不读空 | `format_chanlun_theory_line` + unwrap；不足数据 → 「结构未成型·中性」 |
| 日线不因 seg&lt;11 变线段不足 | 上表 + 删除硬失败路径 |
| 周线参数独立 | `test_daily_vs_weekly_conf_thresholds` |
| timeframe 分离防同源冒充 | `test_daily_and_midline_timeframe_separated` |
| conf=low 旁注「段偏少」 | `test_theory_line_low_conf_annotation` |

### [PASS] 未乱切 build_segments

**证据**

- 本轮 diff **未**改 `build_segments` 函数体
- 仍用 `CHANLUN_MIN_STROKES_PER_SEGMENT`；分析管线调用方式未为凑段数而改算法
- 无「为凑 11 段乱切」行为

### [PASS] 业务逻辑与代码逻辑对应（对照计划 §2 表）

| 业务规则 | 代码落点 | 审查 |
|----------|----------|------|
| 消灭线段不足主状态 | `classify_structure` 删除硬失败分支 | PASS |
| 中枢拓扑定名 | zones 同向/重叠循环 + 2+ 直接趋势 | PASS |
| conf / evidence | `_structure_confidence` + base.evidence；analysis 透传 | PASS |
| 日/周门槛 | `config` 常量 + `timeframe=` | PASS |
| 中线/短线引用分离 | report 理论只读 `chanlun_midline`；短线读 fusion | PASS |
| 包装层 unwrap | `format_chanlun_theory_line` → `unwrap_chan` | PASS |
| 展示段偏少 | conf=low → `{主名}(段偏少)` | PASS |

---

## 3. 跑测记录

```bash
cd /Users/like/Documents/Opencode/Trader3.0
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_chan_core.py \
  02-共享模块-shared/tests/test_chan_midline.py -q
```

```text
102 passed in 0.07s
```

```bash
rg "线段不足" 02-共享模块-shared/trader_shared/chan_core.py
```

```text
# 仅 docstring / 历史兼容分支，无主路径 return
```

---

## 4. 业务 → 代码映射抽检（§1.3）

| 条件 | 期望主状态 | 实现 |
|------|------------|------|
| strokes &lt; 3 | 无结构 | `_ok("无结构")` |
| 0 中枢 + 单边启发式 | 单边上涨/下跌 | `_detect_unilateral` |
| 0 中枢 + 有线段 | 盘整（弱） | `_ok("盘整")` |
| 0 中枢 + 无线段 | 无结构 | `_ok("无结构")` |
| 1 中枢 | 盘整 | 先拓扑循环再 `len==1` 返回盘整 |
| 2+ 同向不重叠 | 上涨/下跌趋势 | 直接 `_ok(zones_trend)` |
| 2+ 重叠/混乱 | 盘整 | 末尾 `_ok("盘整")` |

与计划 §1.2–1.4 **一致**。

---

## 5. 问题列表

### P0（阻塞）

无。

### P1（非阻塞建议）

1. **report_core 理论源缺少自动化回归**  
   当前靠静态读码确认理论行只读 `chanlun_midline`。建议补 1 条轻量单测：mock `r["chanlun_midline"]` vs fusion 日线结构不同时，输出行只含 midline 文案。  
   影响：防未来回归交叉引用；**不挡本次合并**。

2. **历史缓存「线段不足」兼容分支无专测**  
   `format_chanlun_theory_line` 对 `st.startswith("线段不足")` → 「结构未成型」无独立 assert。建议一行单测锁兼容语义。  
   影响：极低。

### 备注（非问题）

- 单边涨跌走 **trend** conf 门槛：计划表只写「上涨/下跌趋势」，把单边并入 trend 类合理，不违背「段数不改主名」。
- conf 仅在 `format_chanlun_theory_line` 对 **low** 旁注「段偏少」；mid/high 无旁注，符合计划「可选旁注」。

---

## 6. 改动范围复核（本轮 uncommitted / 相关文件）

| 文件 | 角色 | 审查结论 |
|------|------|----------|
| `trader_shared/chan_core.py` | classify / conf / strategy / theory line | 符合计划；无 build_segments 乱切 |
| `trader_shared/config.py` | 日周 8 常量 | 与计划默认值一致 |
| `tests/test_chan_core.py` | 结构/ conf / 流水线 | 覆盖 §3 核心 |
| `tests/test_chan_midline.py` | 中线 timeframe / 展示 | 覆盖双源与展示 |
| `report_core.py` | 理论只读 midline | 静态 PASS（本轮 diff 未强制要求改 report） |

---

## 7. 结论与后续

**判定：通过。**

Implementer 交付满足计划 §1–§3；可合并。可选跟进 P1 两条测试加固。人工抽检建议（计划 §5）：实盘华工等样本看「理论：缠论 …」与「短线专家 缠论：…」在结构不同时是否仍分离展示——属运营抽检，非代码阻塞。

审查人未修改业务代码；未 force push。
