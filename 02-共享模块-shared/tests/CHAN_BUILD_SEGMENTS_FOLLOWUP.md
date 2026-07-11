# build_segments 改进与测试文档（A 缠论合规 + B 健壮性/性能）

- 核心文件：`02-共享模块-shared/trader_shared/chan_core.py`
  - 函数：`build_segments`、`_valid_strokes`（新增）、`_merge_char_element`（改为模块级）
- 测试文件：`02-共享模块-shared/tests/test_chan_core.py`
  - 既有类 `TestBuildSegments`（7 例，全绿）
  - 新增类 `TestBuildSegmentsFollowups`（11 例）

> 运行（在 `02-共享模块-shared` 下）：
> ```bash
> cd 02-共享模块-shared && PYTHONPATH=".:$PYTHONPATH" python -m pytest tests/test_chan_core.py -v
> ```

---

## A-2 双侧分型（缠论合规）

**标准依据**：`/Users/like/.agents/skills/algo-doctor/references/formulas.md` 1.2 分型，
与本仓库 `find_fractions` 的双侧判定一致（底分型 = middle 整体低于左右、顶分型 = middle 整体高于左右）。

**改动**：`build_segments` 中两段终结判定由「仅比单侧」升级为「双侧」：

- 向上段终结（向下笔特征序列底分型）：
  - 旧：`mid["low"] < left["low"] and mid["low"] < right["low"]`
  - 新：追加 `and mid["high"] < left["high"] and mid["high"] < right["high"]`
    （middle 整体低于左右：**mid.low 三者最低 且 mid.high 三者最低**）
- 向下段终结（向上笔特征序列顶分型）：
  - 旧：`mid["high"] > left["high"] and mid["high"] > right["high"]`
  - 新：追加 `and mid["low"] > left["low"] and mid["low"] > right["low"]`
    （middle 整体高于左右：**mid.high 三者最高 且 mid.low 三者最高**）

> 说明：任务初稿措辞为「mid.high 最高」式双侧，但经验证（含包含处理）若 middle 同时取
> 最高 high 与最低 low，会**必然触发包含合并**而被吞掉、永远无法形成 3 元素三分型，
> 导致线段永不终结、特性失效。因此采用与 `find_fractions`/formulas.md 1.2 一致且可终止的
> 正确双侧定义（middle 整体在单侧之外）。这一修正使「单侧假分型（仅 low 达标、high 不达标）
> 被包含处理吸收而不终结，真正的双侧分型才终结」，符合 A-2「拒绝单侧假分型」的意图，且使
> `TestBuildSegments` 既有两例（单侧 fixture）在改为标准双侧 fixture 后仍然绿。

**不变量/收益**：线段终结更严格，减少包含处理诱发的假终结；段数不增（只会因假终结被拒而
略减或持平），属于缠论合规层面的改善。

---

## B-01 NaN/Inf 防护（健壮性）

- 新增模块级辅助 `_valid_strokes(strokes)`：过滤 `start_price`/`end_price` 为
  `None` 或非有限值（`math.isfinite` 判定 NaN/Inf）的笔，**仅过滤、不拷贝元素**；
  返回新列表（保留原 dict 引用）。
- `build_segments` 入口在 `if len(strokes) < min_strokes: return []` 之后、
  `seg_start` 判定之前插入：
  ```python
  strokes = _valid_strokes(strokes)
  if len(strokes) < min_strokes:
      return []
  ```
- **不变量**：对正常（全有限）笔序列，过滤为空操作，段输出逐字节不变。
- **收益**：坏数据（缺失价格、除零、异常来源）不会令 `build_segments` 崩溃，也不会输出含
  NaN/Inf 的段；全非有限列表直接返回 `[]`。

---

## P-02 特征序列非合并分支原地追加（性能）

- `_merge_char_element` 由 `build_segments` 内的嵌套函数提升为**模块级**函数
  （便于单测），签名变为 `(seq, new_h, new_l, char_direction) -> (seq, char_direction)`。
- 非合并分支由 `return seq + [{"high": new_h, "low": new_l}]`（O(n) 拷贝整条序列）
  改为 `seq.append({"high": new_h, "low": new_l}); return seq`（O(1) 原地）。
- 合并分支（`seq[-1] = merged`）本就原地，未改。
- **收益**：特征序列每追加一个元素从 O(n) 降为 O(1)，长序列下累计显著减少拷贝开销；
  输出与旧逻辑逐字节一致（性质测试锁定）。

---

## P-01 段高/段低增量维护（性能，与旧 O(n) 重算字节级一致）

- 新增 `run_high`/`run_low`，在外循环推进时增量维护「当前未闭合段 = strokes[seg_start..i-1]」
  的极值：
  - 循环前用 `strokes[seg_start]` 初始化；
  - 每次迭代末尾把当前笔 `i` 的高/低并入 `run`（未触发终结时）；
  - 触发终结时，闭合段直接采用 `run_high`/`run_low`，再把 `run` 重置为新段起点
    （并纳入触发笔 `i`，因其属于新段），随后 `continue`；
  - 尾部收尾直接采用 `run`。
- 去掉原每次终结/收尾的 `max(max(ss...)...)` / `min(min(ss...)...)` O(n) 重算。
- **不变量（被性质测试锁死）**：任一输出段的 `high == max(max(s.start,s.end) for s in 构成笔)`、
  `low == min(min(s.start,s.end) for s in 构成笔)`，与「原 O(n) 重算逻辑逐字复刻」的暴力参考
  实现（`TestBuildSegmentsFollowups._brute_force_segments`）在
  `段数 / direction / high / low / start_price / end_price / start_index / end_index /
  strokes_count` 上**完全一致**（浮点 max/min 对集合顺序无关，故字节级一致）。

---

## 新增用例清单（`TestBuildSegmentsFollowups`，11 例）与预期

| 用例 | 验证点 | 预期 |
|------|--------|------|
| `test_a2_unilateral_fake_bottom_does_not_terminate` | 单侧假底分型（mid.low 最低但 high 不最低→被包含合并） | `len==1` |
| `test_a2_bilateral_bottom_terminates` | 标准双侧底分型（mid.low 最低 且 mid.high 最低） | `len>=2`, `up` 后 `down` |
| `test_a2_unilateral_fake_top_does_not_terminate` | 单侧假顶分型（mid.high 最高但 low 不最高→被包含合并） | `len==1` |
| `test_a2_bilateral_top_terminates` | 标准双侧顶分型（mid.high 最高 且 mid.low 最高） | `len>=2`, `down` 后 `up` |
| `test_a2_bilateral_fewer_segments_than_unilateral_for_same_swing` | 同一摆动：单侧被拒后段数 < 双侧 | 断言不等式成立 |
| `test_b01_valid_strokes_filters_non_finite` | `_valid_strokes` 过滤 NaN/Inf/None，保留有限笔，不改原列表 | 仅 4 笔保留，且均有限 |
| `test_b01_all_non_finite_returns_empty` | 全非有限笔 | `build_segments==[]` 且 `_valid_strokes==[]` |
| `test_b01_nan_inf_does_not_crash_and_filters` | 含 NaN/Inf 的序列：过滤后正常产出、无 NaN/Inf 输出 | `len>=1`，输出全有限 |
| `test_p01_matches_brute_force_reference` | 多组结构化序列（多段/单边/震荡/含包含）与暴力 O(n) 参考字节级一致 | `actual == expect` |
| `test_p01_each_segment_high_low_is_constituent_extremes` | 每段 high/low 等于构成笔极值；start/end_price 与方向公式一致 | 全部相等 |
| `test_p02_merge_non_contain_is_inplace` | `_merge_char_element` 非合并原地 append、合并原地改 `seq[-1]` | `out is seq`，值正确 |

---

## 实测：5 只票段数 before/after（只读，腾讯行情 qfq 日线，401 条）

| 代码 | before（单侧旧逻辑） | after（A-2 双侧 + relax） | 备注 |
|------|------|------|------|
| 688248 | 0 | 2 | `relax_overlap=True` 取消三笔严格重叠门槛，从首笔起段；A-2 双侧分型过滤了 1 个假终结（旧逻辑单侧 1 个），净增 2 段 |
| 000988 | 1 | 2 | relax 后增加 1 段（盘整股原被三笔重叠门槛遮蔽） |
| 600519 | 1 | 1 | 持平 |
| 300750 | 1 | 1 | 持平 |
| 601318 | 1 | 1 | 持平 |

- 无崩溃：5 只票均正常跑通 `chanlun_analysis` / `build_segments`。
- 688248 从 0 段恢复到 2 段：`relax_overlap=True`（默认）取消三笔严格重叠门槛后，单边上涨股可正常从首笔起段并产出进行中段；A-2 双侧分型进一步减少假终结，改善段质量。
- A-2 更严格使段数「不增加」：盘整/重叠型标的（600519/300750/601318）段数持平，符合预期改善方向。
