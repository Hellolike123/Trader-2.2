# 缠论线段第二类破坏 & 中枢合并合同对齐

> **status**: active
> **日期**: 2026-08-07
> **发现人**: Mavis（mvs_7e6d9488b80b478fa4dcd0fc018c3140）
> **复核**: Codex（2026-08-07）
> **实施**: P0 + P1 已落地（2026-08-07，Codex）；P1 选方案 A（回交集 + 合法护栏）
> **对照法源**: `02-共享模块-shared/trader_shared/formulas.md`
>   - §1.2 双侧严格分型（A-2）
>   - §3.1–§3.5b 线段（特征序列三分型、起终点、未完成段纠偏）
>   - §4.1–§4.3 中枢（连续 3 段重叠、合并取交集、拓扑）
>   - §11A 0 中枢 → 无结构 / 单边启发式
> **代码锚点**:
> - `02-共享模块-shared/trader_shared/chan_geometry.py:684` `build_segments`
> - `02-共享模块-shared/trader_shared/chan_geometry.py:775` Bug R 注释与实现
> - `02-共享模块-shared/trader_shared/chan_geometry.py:1095` `_merge_zones` / Bug S
> - `02-共享模块-shared/trader_shared/chan_core.py:122` 段中枢→笔中枢 fallback
> - `02-共享模块-shared/trader_shared/chan_structure.py:109` `classify_structure`

---

## 0. 30 秒摘要

本轮只做**合同对齐型**修复，不改缠论定义。

1. **P0 — Bug R（代码 vs 注释不一致，真 bug）**：`build_segments` 注释写「向上段被破坏 = 向下笔 `low` 跌破段起点 `low`」，实现却是 `char_h < seg_pivot_low`（整根 high 掉到起点下方）。向下段对称同样错位。修代码对齐注释，并把第二类破坏正式写入 `formulas.md` §3（当前合同里只字未提）。
2. **P1 — 中枢合并（代码 vs `formulas.md` §4.2 不一致）**：`formulas.md` §4.2 写合并取**交集**（`zh_top=min`、`zh_bottom=max`），`_merge_zones` Bug S 实际取**并集**。并集是为修工行链式塌缩而引入的，不能盲回。需先在 A/B/C 三个合同方案里选一个，再改码 + 加工行/窄震荡双向 fixture。
3. **非 bug，仅记录**：「9 笔完美交替只切 1 段」是 `formulas.md` §3.1 的正确输出（特征序列 4 根向下笔高低点同步抬高，形不成双侧底分型）。若产品要更敏感的切段，**必须先改 §3.1 合同**再改码，不得当 bugfix 偷渡。
4. **因果校正**：段数 < 3 时 `chan_core` 会 fallback 到笔中枢；0 中枢走单边启发式是 §11A 设计。「段不切 → 必判单边」不成立。真实影响面是：段级中枢拓扑、`_higher_level_trend`（需 ≥3 段）、线段展示。

---

## 1. P0 — Bug R：第二类破坏实现与注释不一致

### 1.1 现状

`chan_geometry.py:775-780` 注释：

```
缠论原典：特征序列元素突破线段起点极值即线段破坏（与三分型 OR 并存）。
  - 向下段：特征序列（向上笔）的 high 突破段起点 high → 破坏
  - 向上段：特征序列（向下笔）的 low 跌破段起点 low → 破坏
```

实现却写成「整根脱离」：

```python
# 向上段（chan_geometry.py:851）
if ... and char_h < seg_pivot_low:   # 应为 char_l < seg_pivot_low

# 向下段（chan_geometry.py:941）
if ... and char_l > seg_pivot_high:  # 应为 char_h > seg_pivot_high
```

`char_h < seg_pivot_low` 要求向下笔**整根 high** 都在段起点 low 之下，等于价格已经回到起点以下极深位置，远严于「突破」。这种位置 A-2 多半早已触发（若特征序列够长），导致 Bug R 分支几乎是死代码。

### 1.2 复现

6 笔「先大涨再砸穿起点」：up 10→17，紧跟 down 笔跌破 10。按注释 / 原典应：up 段在跌破 10 时被第二类破坏闭合，再起 down 段。当前实现：up 段不闭合，最终整段被识别为 1 个 down 段 n=6，吞掉前段。

```bash
cd 02-共享模块-shared && python3 -c "
import sys; sys.path.insert(0, '.')
from trader_shared.chan_geometry import build_segments
strokes = [
  {'start_type':'bottom','start_index':0,'start_price':10.0,'end_type':'top','end_index':3,'end_price':17.0,'direction':'up','power_price':7.0,'length':3},
  {'start_type':'top','start_index':3,'start_price':17.0,'end_type':'bottom','end_index':6,'end_price':15.0,'direction':'down','power_price':2.0,'length':3},
  {'start_type':'bottom','start_index':6,'start_price':15.0,'end_type':'top','end_index':9,'end_price':16.5,'direction':'up','power_price':1.5,'length':3},
  {'start_type':'top','start_index':9,'start_price':16.5,'end_type':'bottom','end_index':12,'end_price':12.0,'direction':'down','power_price':4.5,'length':3},
  {'start_type':'bottom','start_index':12,'start_price':12.0,'end_type':'top','end_index':15,'end_price':13.0,'direction':'up','power_price':1.0,'length':3},
  {'start_type':'top','start_index':15,'start_price':13.0,'end_type':'bottom','end_index':18,'end_price':9.5,'direction':'down','power_price':3.5,'length':3},
]
for s in build_segments(strokes, min_strokes=3):
    print(s['direction'], s['start_price'], '->', s['end_price'], 'n=', s['strokes_count'])
"
```

### 1.3 修法（合同已在注释里，直接对齐）

- 向上段：`char_h < seg_pivot_low` → `char_l < seg_pivot_low`
- 向下段：`char_l > seg_pivot_high` → `char_h > seg_pivot_high`
- 保留护栏：`seg_len >= min_strokes and (len(strokes) - i) >= min_strokes`，避免单笔假突破过切。
- 复位逻辑（`seg_pivot_high/low`、`char_seq`、`char_direction`）不动。

### 1.4 文档同步

在 `formulas.md` §3 新增 **§3.6 第二类线段破坏**（目前合同里没有，只在代码注释里）：

- 与 §3.1 三分型终结 **OR 并存**。
- 向上段：特征序列（向下笔）`low` 跌破段起点 `low` → 段破坏。
- 向下段：特征序列（向上笔）`high` 突破段起点 `high` → 段破坏。
- 护栏：段内累计笔数 ≥ `min_strokes` 且剩余笔数 ≥ `min_strokes`，避免噪声。
- 段起点取段首笔极值（唯一，不随段内延伸更新）。

---

## 2. P1 — 中枢合并：交集 vs 并集，先定合同再改码

### 2.1 现状

`formulas.md` §4.2：

> 仅当两中枢**价格真正重叠**才合并为 consolidated pivot，取**交集**（`zh_top=min`，`zh_bottom=max`）。

`_merge_zones` Bug S（`chan_geometry.py:1152-1166`）实际取**并集**（`max(top)/min(bottom)`），注释理由是「交集链式合并塌缩成 0.04 元窄条（工行实测）」。

二者直接冲突。Bug Q 加了 `contiguous = (span[0] - last["_span_end"]) <= 2` 时间约束，但**没有消除链式合并**：时间相邻、价格两两重叠的滑动窗中枢仍会被串成长条，并集策略会把它们撑成一个宽幅巨中枢（窄震荡 5 笔案例：宽度从 ~0.5 元被撑到 1.15 元）。

### 2.2 这不是「直接回交集」就能修

盲回交集会重新引入工行 0.04 元塌缩，且可能让 `strict` 背驰的 b/c 笔解析失败（Bug S 注释明确点过）。需要在以下合同方案里**先选一个**，写进 §4.2，再改码：

- **方案 A（回到原典交集）**：合并取 `min(top)/max(bottom)`，保留 Bug Q 时间约束；额外加「链式合并深度上限」或「交集塌缩到 < ε 时拒绝合并」防工行 case。
- **方案 B（承认并集 = 中枢延伸语义）**：把 §4.2 改成并集，加上「合并成员数上限」或「合并后宽度 / 成员平均宽度」的硬上限，防窄震荡被撑成巨中枢。
- **方案 C（双轨）**：原始滑动窗用交集（保拓扑判断），另出一个字段记录并集震荡带（给背驰 b/c 锚定用）；`classify_structure` 只看交集轨。

本 handoff **不预设选哪个**。选方案的人需要：

1. 在 §4.2 写死选哪个、阈值多少。
2. 同时加工行（链式不塌缩）和窄震荡（不撑巨中枢）两个 fixture。
3. 明确 `classify_structure` 与 `detect_divergence` 分别读哪条轨（方案 C 才需要）。

在 §4.2 没改之前，**禁止改 `_merge_zones`**。

---

## 3. 非 bug — 「9 笔交替只切 1 段」是 §3.1 正确输出

原始 handoff 把这个列为严重 bug，与本仓法源冲突，记录在此防止后续 agent 误改。

9 笔 up-down-up-...-up，特征序列（向下笔）4 根：

| 向下笔 | high | low |
|--------|------|-----|
| 1 | 12.0 | 11.0 |
| 2 | 13.0 | 11.5 |
| 3 | 13.5 | 12.0 |
| 4 | 14.0 | 12.5 |

高低点同步抬高，**形不成 §3.1 / §1.2 要求的双侧底分型**。按现行合同，1 段 up 是正确输出，不是 bug。

若产品要更敏感的切段（例如「每 3 笔成段」或「2 根特征元素即判弱分型」），那是**修改缠论定义**：

1. 先改 `formulas.md` §3.1，写明新规则与开关（建议加 `CHAN_SEGMENT_SENSITIVITY` 之类显式配置，默认保留现行为）。
2. 标注对 `_higher_level_trend`（≥3 段）、段级中枢、买卖点、多级别区间套的连带影响。
3. 另开 handoff，不在本轮做。

在 §3.1 没改之前，**禁止**：

- 把 `len(char_seq) >= 3` 降到 `>= 2`。
- 加「每 3 笔硬切段」。
- 任何把这组 9 笔期望改成 ≥2 段的测试。

---

## 4. 影响面（写代码时要知道哪些下游会动）

- **段级中枢 / 一类买卖点**：`build_segments` 输出变了 → `build_zones(segments, level="segment")` 重叠关系会变；一类买/卖依赖严格不重叠同向中枢 + 反向连接段，Bug R 修复后可能多出/少掉一类信号，需要回归 `detect_buy_points` / `detect_sell_points`。
- **多级别趋势**：`_higher_level_trend` 需要 `len(segments) >= 3` 才给趋势。Bug R 修复后段数可能增加，周线趋势判定会变敏感——这是预期内，但要在测试里覆盖。
- **笔中枢 fallback**：`chan_core._chanlun_compute` 在段 < 3 或段中枢为空时回退笔中枢。不要因为段数变化就删 fallback。
- **`classify_structure`**：本轮不改主状态枚举；0 中枢走单边启发式是 §11A 设计，不要动。
- **未完成段纠偏（§3.5 / §3.5b）**：Bug R 修复后收尾时未完成段的翻转 / 并回上段逻辑要保持原样。

---

## 5. 验收

### 5.1 P0 Bug R

| 场景 | 期望 |
|------|------|
| 6 笔 up 10→17 后 down 笔跌破 10 | 2 段：先 up（在跌破 10 处闭合）+ down |
| 6 笔 down 对称（先大跌后反弹破起点高） | 2 段：先 down + up |
| 3 笔 up | 1 段 up（护栏 `seg_len >= min_strokes` 防过切） |
| 9 笔高低点同步抬高的震荡 | **1 段 up（不变，证明没乱切）** |
| 真单边 6 笔 up（无反向笔破起点） | 1 段 up |
| `formulas.md` §3.6 | 新增第二类破坏条款，文字与代码一致 |

### 5.2 P1 中枢合并

选定方案后才填。验收必须双向：

| 场景 | 期望 |
|------|------|
| 工行类链式相邻小中枢 | 不塌缩到 < ε 宽度（具体阈值由选定方案给） |
| 5 笔窄震荡（~0.5 元） | 不被撑成 1.15 元巨中枢（具体上限由选定方案给） |
| 纯 gap 中枢 | 不合并（§4.2 现行，不变） |
| `zh_top > zh_bottom` | 任意合并后合法，不出现非法中枢 |

### 5.3 不能改的（回归保护）

- 9 笔高低点同步抬高的完美交替 → 1 段 up（§3.1）。
- `classify_structure` 主状态枚举不变。
- 笔中枢 fallback 路径不变。
- 0 中枢 + 真单边笔 → `单边上涨/下跌`（§11A）。
- 0 中枢 + 非单边笔 → `无结构`。

---

## 6. 可改 / 勿改

### 可改（本轮 P0）
- `02-共享模块-shared/trader_shared/chan_geometry.py`
  - `build_segments` 内第二类破坏判定两处：`char_h`/`char_l` 与 `seg_pivot_low`/`seg_pivot_high` 对齐
- `02-共享模块-shared/trader_shared/formulas.md`
  - 新增 §3.6 第二类线段破坏

### 待合同决策后可改（P1）
- `formulas.md` §4.2 合并规则（先选定 A/B/C）
- `chan_geometry.py` `_merge_zones`（按选定方案）

### 勿改（除非新 handoff 显式授权）
- §3.1 三分型门槛（`len(char_seq) >= 3`、双侧严格）
- `classify_structure` 主状态枚举与单边启发式
- `chan_core` 的段中枢→笔中枢 fallback
- `_drop_leading_dangling_strokes`（先看 P0 修完效果）
- fusion / 出手 / 池分道 / 买卖点 / 背驰 / 多级别逻辑

---

## 7. 测试

1. **必加 pytest**（`02-共享模块-shared/tests/`）：
   - `chan_segments_2nd_break.py`：6 笔砸穿起点 up→up+down、对称 down→down+up、3 笔不切、真单边不切。
   - `chan_segments_no_overcut.py`：9 笔高低点同步抬高 → 仍 1 段 up（防回归成乱切）。
2. **P1 合同选定后**再加：
   - 工行链式不塌缩 fixture（取自 Bug S 注释的实测样本，需从 git 历史 / 实盘样本恢复）。
   - 窄震荡不撑巨中枢 fixture。
3. **回归**：
   - `scripts/run-gate-tests.sh` 通过。
   - `python3 -m pytest 02-共享模块-shared/tests/ -k chan` 全绿。
   - 若有覆盖 `build_segments` / `_merge_zones` 的 golden fixture，按新合同刷新并在 PR 里贴 diff。

---

## 8. 调查过程（备查）

Mavis 初版报告（2026-08-07）读了 `chan_core.py` / `chan_geometry.py` / `chan_structure.py`，跑了 4 组手工构造测试，识别出 Bug R 实现过严、中枢并集撑大、段数偏少三个现象。

Codex 复核（2026-08-07）对照 `formulas.md` 后修正：

- Bug R 是代码 vs 自家注释的直接不一致，P0 可修。
- 中枢并集 vs 交集是合同冲突，但不能盲回交集（工行 case），需要先选合同方案。
- 「9 笔交替只 1 段」是 §3.1 正确输出，不是 bug；要更敏感得先改合同。
- 「段不切 → 单边」不成立，笔中枢 fallback + §11A 兜住多数情况。
