# 中短线双轨对齐计划（理论已双源 → 看法/价位/报告闭环）

> **status**: done / **superseded（布局）**  
> **superseded 注（2026-08-02）**：独立面板「阶段：」行已由 [`../trader-drop-stage-line-handoff.md`](../trader-drop-stage-line-handoff.md) 废除；中线阶段细读改走「威科夫：」；字段 `midline_stage` 仍保留。下文凡写「阶段：与看法：并列」仅作历史，**勿按本文恢复「阶段：」行**。  
> 状态（历史）：规格冻结（B1A / B2A / B3C / B4A 已拍板，见 §0.3）  

> 日期：2026-07-10  
> 协作：双 Agent（Implementer 改 / Reviewer 审）  
> 规格真相源：现行面板以 `BUSINESS.md` §5.1 + drop-stage / declutter 为准；本文仅历史  
> 前置：`docs/short-midline-report-and-gate-plan.md` 已落地门控/短中线骨架；本计划纠正「中线挂羊头」并补中线关键价闭环  
> 布局覆盖声明：本计划 §0.1 覆盖前置文档 §1.1 布局，以及 §1.2/§1.5/§4.3 中「中线看法=major_stage」口径；门控 H 规则、亏赚句式、微信红线仍继承前置

---

## 0. 背景与诊断（已对齐用户）

### 0.1 用户冻结观感（南网/华工样例）

报告拆成两块，价简 + 半句解释。  
**B3C 已冻结：** 中线块内 **`阶段：` 与 `看法：` 并列**——阶段最能服务中线叙事，但不得与周线看法揉成一句。

```text
分析报告 — {名}（{码}）｜短中线

现价 …
  动能 … ｜ 大盘 …
  MA5 ｜ MA20 ｜ MA250
  （量比/换手可选）
  （meta 可不重复阶段；阶段主展示在 🧭 内）

🧭 中线
  阶段：{major_stage}         ← 主力四阶段（门控/入池/轮动语义；中线区块主展示）
  看法：…                    ← 仅周线缠+威合成；禁止四阶段词冒充看法
  威科夫：…                  ← wyckoff_midline
  缠论：…                    ← chanlun_midline

  关键价（中线）
    生命线 X（破则中线转弱）
    回踩区 A-B（到了才谈低吸）
    压力 X（靠近只减不加）
    目标 X（波段上看）
    （无 🌟；B2A）

⚡ 短线
  看法：…
  缠论：…                    ← 日线 fusion 专家
  动能：…
  裁定：…
  出手：…                    ← 门控 + 短线价；中线价不得单独喊买

  关键价（短线）
    止损 X（破则今日计划作废）
    买点区 A-B（回这里再谈买）
    🌟 现价 …
    卖点区 A-B（冲到减/高抛）

  {买} 买：亏约 … / 赚约 …（远看 …）
  {现价} 追：… → 不追|可考虑

说明：…                      ← 仅中短冲突时
📌 本周只做：…
T0：…
（无独立 🗺 空间参考整节；B2A）
```

微信红线不变（无 `#` / `---` / `**` / 表格 / `>` / `*-` 列表）。

### 0.3 预审决策台账

| 编号 | 议题 | 状态 | 冻结口径 |
|------|------|------|----------|
| **B3C** | 阶段放哪 | **已冻结** | 见下 §0.3.1 |
| **B1A** | 周线威多+缠空看法合成 | **已冻结** | 见下 §0.3.2 |
| **B2A** | 🌟 双写与 🗺 去留 | **已冻结** | 见下 §0.3.3 |
| **B4A** | 生命线回退链 | **已冻结** | 见下 §0.3.4 |

#### 0.3.1 B3C（已冻结）— 中线：`阶段：` + `看法：` 并列

**动机：** 四阶段最适合表达中线仓位/故事语言；挂羊头的根因是「阶段 + 看法揉成一句中线：蓄势·可跟踪」，不是「阶段不该出现在中线」。

| 行 | 数据源 | 纪律 |
|----|--------|------|
| `阶段：` | `major_stage`（算法不改；继续喂门控/入池/轮动） | 只输出阶段标签；不写周线结构句 |
| `看法：` / `conclusion.midline` | 周线 `chanlun_midline` + `wyckoff_midline` 合成 | **禁止**出现：蓄势、主升、派发、衰退 |
| ⚡ 短线块 | 不出现四阶段主标签 | 阶段不进短线「看法/出手」主句 |

对用户文案用 **`阶段：`**，不强调「日线阶段」（避免削弱中线语义）。  
实现注释可写：阶段模型输入特征以日线为主。

华工锚点：

```text
阶段：蓄势偏强
看法：盘整偏空 · 暂缓跟踪
```

禁止再出现：`中线：蓄势偏强 · 可跟踪`。

#### 0.3.2 B1A（已冻结）— 周线两源可编码合成 + 打架显式

定义（与 `format_chanlun_theory_line` 同源方向，禁止另写一套）：

- `chan_dir` ∈ `{+1, 0, -1}`：周线缠论看涨 / 中性 / 看跌  
- `wyck_bias` ∈ `{strong_bull, strong_bear, neutral}`：  
  - `strong_bull` := `spring_signal` or `sos_signal`  
  - `strong_bear` := `upthrust_signal` or `bc_signal` or `sow_signal`  
  - 多信号并存时：**strong_bear 优先于 strong_bull**  
  - 否则 `neutral`  
- `weekly_frame` 仅当非 `None` 参与；P0 常为 `None`

优先级（命中即停）：

1. `weekly_frame == "破坏"` → `中线框破坏 · 战略减/清倾向`  
2. `wyck_bias == strong_bear` → `中线慎跟 · 偏空信号`  
3. `chan_dir < 0` 且 `wyck_bias == strong_bull` → `中线信号打架 · 暂缓跟踪`  
4. `chan_dir < 0` → `盘整偏空 · 暂缓跟踪`（可用 `structure_type` 替换「盘整」主词，**不得**插入 major_stage）  
5. `chan_dir > 0` 且 `wyck_bias != strong_bear` → `上涨趋势未坏 · 可跟踪、不加仓`（结构含上涨用该主词，否则 `结构偏多 · 可跟踪、不加仓`）  
6. 否则 → `中线观察`

硬约束（叠加 B3C）：`conclusion.midline` 禁止四阶段词。

#### 0.3.3 B2A（已冻结）— 🌟 仅短线；删除 🗺

1. **🌟 现价**：仅在 ⚡ 短线关键价块输出一行；🧭 中线关键价**不**输出 🌟。  
2. **删除**独立「🗺 空间参考」整节（P0）。近端/波段支撑由中线生命线、回踩区承担；远端不单开地图（P1 再议）。  
3. 报告主分区固定：meta → 🧭 中线 → ⚡ 短线 →（可选说明）→ 📌 / T0 / 池。  
   不再用「🎯 结论」「🗳️ 日线三专家」作主标题。

#### 0.3.4 B4A（已冻结）— 生命线回退链

`life_line` 取值（第一个 `>0` 生效）：

1. `key_levels.mid_support`  
2. `stop_losses.stage_based.price`（或等价 `stage_based` 结构）  
3. `stop`（日线结构止损）  
4. 皆无 → `None`，**省略** `line_life` 行（不输出「数据不足」占位，除非实现另有统一缺省策略且单测写死）

说明：

- 回退到 `stop` 时，允许与短线止损同价；**标签必须仍是「生命线」vs「止损」**，语义不同。  
- `life_line > current`（价已在生命线下方）：P0 仍展示，**不**自动改写中线看法（看法只走 B1A 表）。  
- `notes` 可记 `source=daily_key_levels_proxy` 或实际命中的回退级（调试用，不进主报告括号说明书）。

### 0.2 引擎现状（实现前必须承认）

| 层 | 是否双轨 | 现状 |
|----|----------|------|
| 缠论/威科夫理论 | ✅ 已双源 | `chanlun_strategy`+`wyckoff_strategy`（日）与 `*_midline`（优先周 K）并行；字段 `chanlun_daily`/`wyckoff_daily` vs `chanlun_midline`/`wyckoff_midline` |
| 中线看法 | ❌ | `conclusion.midline` ← `_midline_view(major_stage, …)`，未读周线理论 |
| 中线关键价 | ❌ 无独立模块 | 样例用 `key_levels` 日 K 10/60/120 窗拼装展示；无 `mid_key_prices` |
| 短线看法/专家/出手/关键价 | ✅ 基本闭环 | fusion + `key_prices` + mistery_gate |
| `weekly_frame` | ❌ 占位 | `report["weekly_frame"]=None`（P1） |
| 动能 | 仅日线 | 无周线动能；中线块不强制动能行 |

**本计划目标：** 让报告「中线块 / 短线块」各自对应清晰数据源；理论沿用已有双源；**阶段落在中线块、看法接周线理论、价位独立字段**；禁止「中线：{stage}·{看法}」揉句挂羊头。

---

## 1. 目标与非目标

### 1.1 目标（P0）

1. **中线块并列两行（B3C）：** `阶段：` ← `major_stage`（门控/入池/轮动不改算法）；`看法：`/`conclusion.midline` ← 周线缠+威合成，**禁止四阶段词**。
2. **中线关键价**正式产出 `mid_key_prices`（第一期仍可用日 K `key_levels`+MA20，但是**独立字段 + 独立渲染块**，解释句式固定）。
3. **短线块**沿用 `key_prices` + 日线专家 + 出手；与中线块在 `report_core.render_short_midline` 中物理分区；短线不主打四阶段标签。
4. **冲突说明**仅在中短叙事冲突时输出固定短句。
5. 单测 + 南网/华工级契约测（字段源不交叉；禁止 `中线：蓄势` 揉句）。
6. 双 Agent：Implementer 按清单改；Reviewer **持本规格**对照验收，不只看代码品味。

### 1.2 非目标（本轮不做）

- 不重写缠/威/动能算法内核。
- 不把 fusion 主周期改成周线；fusion 仍服务短线/日线裁定。
- 不改 T0 主逻辑（报告末行提示可顺带对齐文案）。
- 不强制 P1：周线笔端点生命线、`weekly_frame` 完好|紧张|破坏、周线动能。
- 不改选股池 rank/plan 全量 UI（字段可先写入 report 供后用）。
- 不删除旧字段（向后兼容：`conclusion.midline` 语义变更须在测试与 output-template 写明）。

---

## 2. 数据契约（字段 → 报告行）

### 2.1 双轨对照（实现后必须成立）

| 报告行 | 唯一数据源 | 禁止来源 |
|--------|------------|----------|
| 🧭 `阶段：` | `major_stage` | 不得与看法揉成「中线：{stage} · …」一句 |
| 🧭 `看法：` / `conclusion.midline` | 周线理论合成 | `major_stage` 映射；文案禁：蓄势/主升/派发/衰退 |
| 🧭 威科夫 | `wyckoff_midline` | `wyckoff_daily` / fusion.wyckoff |
| 🧭 缠论 | `chanlun_midline` | fusion.chan 日线结构/顶背驰 |
| 🧭 关键价 | `mid_key_prices.*` | 不得与短线 stop/买点混标签 |
| ⚡ 看法 | `conclusion.shortline` | 周线结构类型；四阶段主标签 |
| ⚡ 专家缠/动 | `fusion.signals_detail` 日线 | `chanlun_midline` |
| ⚡ 裁定 | `conclusion.daily_ruling` / `daily_ruling` | — |
| ⚡ 出手 | `conclusion.execution` + reason | 中线目标/生命线单独驱动买 |
| ⚡ 关键价+亏赚 | `key_prices.*` | mid 生命线充当短线止损 |

### 2.2 `mid_key_prices` 字段（新建）

```python
{
  "life_line": float | None,       # 生命线
  "pullback_low": float | None,    # 回踩区下沿
  "pullback_high": float | None,   # 回踩区上沿
  "resist": float | None,          # 主压力（一个）
  "target": float | None,          # 波段目标
  "current": float | None,         # 可选回填
  # 展示句（可选预渲染，render 也可本地拼）
  "line_life": "生命线 46.88（破则中线转弱）",
  "line_pullback": "回踩区 54.15-56.72（到了才谈低吸）",
  "line_resist": "压力 69.67（靠近只减不加）",
  "line_target": "目标 75.00（波段上看）",
  "notes": str,
}
```

**P0 取值规则（笨而稳，写死）：**

| 字段 | 来源 |
|------|------|
| life_line | **B4A**：`mid_support` → `stop_losses.stage_based.price` → `stop` → None（省略行） |
| pullback_low | `key_levels.short_support` |
| pullback_high | `max(pullback_low, ma20)`（ma20 缺失则 = pullback_low 或留单点） |
| resist | `key_levels.mid_resist`（一个主压力；勿并芯片说明） |
| target | `key_levels.long_resist`；若与 resist 同价，render 可合并为 `压力/目标 X` 一行 |

解释句式**固定**，禁止堆数据来源括号。

**同价策略：** 同一数值可在中/短两套以不同角色出现，但「主展示角色」不重复三次（例如 69.67 作中线压力后，短线卖点仍用近端 short_sell，不把 69.67 再当短卖主角）。

### 2.3 中线看法合成（替换 `_midline_view` 主路径）

输入：

- `chanlun_midline`（`structure_type` / direction 或 `format_chanlun_theory_line` 可解析信息）
- `wyckoff_midline`（signal / phase / direction / summary）
- 可选：`weekly_frame`（P0 仍可为 None，预留）
- **`major_stage` 不进「看法：」主句**（只进 `阶段：` 行，见 B3C）

输出短句库：**以 §0.3.2 B1A 封闭表为准**（可编码，命中即停）。

硬约束（B3C + B1A）：

- `conclusion.midline` / 看法行 **禁止**子串：蓄势、主升、派发、衰退  
- 「可跟踪」**不等于**「现价可买」；加仓/买只由短线出手表达  
- 威多+缠空 → 必须走「中线信号打架 · 暂缓跟踪」，不得静默偏一侧  

华工验收：`阶段：蓄势偏强` + `看法：` 为暂缓/偏空/打架类；禁止 `中线：蓄势偏强 · 可跟踪`。  
南网验收：`阶段：蓄势` + `看法：` 可跟踪不加仓类；短线仍可不追。

### 2.4 冲突说明

仅当：

- 中线看法 ∈ 可跟踪/未坏 类，且 短线出手为不买/不追 / 裁定偏空  
  → `说明：中线还能看，现价别买`  
- 中线暂缓/偏空，且 短线也不追  
  → `说明：周线偏空，短线也不追`（或更短等价句）  
- 否则省略「说明」行

---

## 3. 模块与文件改造清单

| 优先级 | 文件 | 动作 |
|--------|------|------|
| P0 | `02-共享模块-shared/trader_shared/mid_key_prices.py` **新建** | `build_mid_key_prices(...)` 纯函数 |
| P0 | `02-共享模块-shared/trader_shared/conclusion_block.py` | 中线看法改周线驱动；`major_stage` 只服务「阶段：」展示与 gate，不进 `conclusion.midline`；冲突句更新 |
| P0 | `01-功能包-packages/trader/scripts/run_analysis.py` | 组装 `mid_key_prices`；`build_conclusion_block` 传入 chan/wyck mid；保留 major_stage 给 gate |
| P0 | `02-共享模块-shared/trader_shared/report_core.py` | `render_short_midline`：🧭 内 `阶段：`+`看法：`；中线关键价无 🌟；删 🗺；⚡ 唯一 🌟（B2A） |
| P0 | `01-功能包-packages/trader/references/output-template.md` + `output-style-guide.md` | 绝对输出契约与样例同步 |
| P0 | `02-共享模块-shared/tests/test_mid_key_prices.py` **新建** | 生命线/回踩/同价合并 |
| P0 | `02-共享模块-shared/tests/test_conclusion_block.py` 或扩展 | 中线看法不读 stage；华工/南网类 fixture |
| P0 | `02-共享模块-shared/tests/test_report_mid_short_sources.py` **新建** | mock 报告：理论行/中线价/短线专家字段源不交叉 |
| P1 | `weekly_frame` 小模块 | 真周 K 完好\|紧张\|破坏 → 看法/门控 |
| P1 | 周线笔端点替换 life_line/resist | 第二期价位 |
| P1 | Agents.md 短注 | 中线块=阶段(major_stage)+看法(周线理论)；禁止揉句 |
| P2 | rank/plan 展示双视角 | 另立项 |

**渲染入口：** 以 `report_core.render_short_midline`（`SHORT_MIDLINE_REPORT` 默认开）为准；改完后 grep 确认 `final_report` 不走旧「中线：{stage} · …」揉句路径。

**兼容：**  
- 保留 `key_prices` / `key_levels` / `major_stage` 字段名。  
- `conclusion.midline` **语义变更**为周线看法（不再是 stage 摘要）；阶段展示用 `major_stage` 字段本身，可在 conclusion 增加 `stage_line` 或由 render 直读 `major_stage`。  
- 测试/模板写死：禁止 `中线：蓄势` 类揉句。

---

## 4. 实施任务分解（双 Agent）

### 4.1 总流程

```text
Phase 0  规格冻结（本文档）—— 用户已口头认可样例
    │
    ▼
Phase 1  Reviewer 预审规格（可选但推荐）：完整性/可测性/有无歧义
    │
    ▼
Phase 2  Implementer 按 §4.2 切片实现 + 单测
    │
    ▼
Phase 3  Reviewer 持规格对照表验收（§5）+ 真票抽样
    │
    ├─ 有 ❌ → Implementer 返工 → 再审
    ▼
Phase 4  交付：对照表全 ✅ + pytest 绿 + 南网/华工人工读感过关
```

### 4.2 Agent A — Implementer（只改，对照规格）

**切片顺序（禁止一次巨型 PR 混无关重构）：**

| 切片 | 内容 | 完成定义 |
|------|------|----------|
| S1 | `build_mid_key_prices` + 单测 | 给定 key_levels/ma20/current 输出四价+固定句式 |
| S2 | `build_conclusion_block` 中线看法改周线驱动 + 冲突句 + 单测 | fixture：周线看跌+stage 蓄势偏强 → midline 暂缓；周线看涨 → 可跟踪不加仓 |
| S3 | `run_analysis.build_report` 接线 `mid_key_prices` + 传 mid 理论进 conclusion | report 含新字段；gate 仍吃 major_stage |
| S4 | `report_core.render_short_midline` 模板分区 | 输出含 🧭/⚡；无「中线：{蓄势}」；中短关键价分块 |
| S5 | output-template / style-guide 同步 | 与渲染一致 |
| S6 | 源隔离单测 + 本地真票（南网、华工）粘贴验收 | 见 §5.2 |

**Implementer 禁令：**

- 不得用 `major_stage` 写入「中线看法」主句。  
- 不得把 `chanlun_midline` 回退成 fusion 日线顶背驰（理论行已有此纪律，保持）。  
- 不得让中线 `life_line` 覆盖短线 `stop_sell` 展示语义。  
- 不得改 fusion 权重/算法「顺便优化」。  
- 不扩大 scope 到 weekly_frame 实装（除非切片明确升 P0）。

### 4.3 Agent B — Reviewer（只审，对照规格）

**输入必须包含：**

1. 本文档全文（唯一验收真理）  
2. Implementer 的 diff / 文件列表  
3. 相关单测结果  
4. 至少 2 只真票报告文本（建议：南网科技、华工科技）

**禁止：** 只凭「代码是否干净」「命名好不好」判过；**必须以 §2 对照表逐行勾选**。

**Review 产出模板：** 写入 `docs/audit/mid-short-dual-track-review.md`

```markdown
# 中短线双轨 Review

| 规格 ID | 要求摘要 | 结果 | 证据 |
|---------|----------|------|------|
| R1 | … | PASS/FAIL | 文件:行 / 报告摘录 |
…

## 阻断项（必须修）
## 非阻断建议
## 总判：APPROVE / REQUEST_CHANGES
```

---

## 5. 验收规格对照表（Reviewer 勾选）

| ID | 规格要求 | 验证方法 |
|----|----------|----------|
| R1 | 🧭 有独立 `阶段：{major_stage}`，且无「中线：{stage} · …」揉句 | 渲染快照 / 真票 |
| R2 | 中线看法不由 major_stage 驱动；midline 禁四阶段词 | 单测：stage=蓄势偏强 + 周线看跌 → 阶段仍蓄势偏强、看法暂缓类；midline 不匹配蓄势\|主升\|派发\|衰退 |
| R3 | 中线威科夫只读 wyckoff_midline | 单测 mock 日/周不同文案，输出仅含周 |
| R4 | 中线缠论只读 chanlun_midline | 同上 |
| R5 | 短线专家只读日线 fusion | mock 交叉，短线块无周线 structure_type 冒充 |
| R6 | 存在 mid_key_prices 且含 life/pullback/resist/target | 单测 + report 字段 |
| R7 | 中线关键价解释句式固定四类 | 字符串断言 |
| R8 | 短线 key_prices + 亏赚仍在 | 回归 test_key_prices / 真票 |
| R9 | 出手不由中线目标单独放行 | 逻辑审 + 南网现价不买 |
| R10 | 冲突说明条件触发/省略正确 | 单测 |
| R11 | 微信红线 | 渲染无禁用 markdown |
| R12 | 向后兼容：major_stage/key_prices/gate 仍在 | 字段存在性 |
| R13 | pytest 相关套件通过 | CI/本地命令 |
| R14 | 南网读感：中线可跟、短线不追 | 人工 |
| R15 | 华工：`阶段：蓄势偏强` + 看法暂缓/偏空类；全文无「中线：蓄势」揉句；短线不追 | 真票关键词 |

### 5.2 真票命令

```bash
cd /path/to/Trader3.0
PYTHONPATH=02-共享模块-shared python3 01-功能包-packages/trader/scripts/final_report.py --target 南网科技
PYTHONPATH=02-共享模块-shared python3 01-功能包-packages/trader/scripts/final_report.py --target 华工科技

python3 -m pytest 02-共享模块-shared/tests/test_mid_key_prices.py \
  02-共享模块-shared/tests/test_conclusion_block.py \
  02-共享模块-shared/tests/test_key_prices.py \
  02-共享模块-shared/tests/test_report_mid_short_sources.py \
  02-共享模块-shared/tests/test_chan_midline.py -q
```

---

## 6. Prompt 模板（开双 Agent 时复制）

### 6.1 Implementer Prompt

```text
你是 Implementer。唯一规格：docs/mid-short-dual-track-plan.md
按 §4.2 切片 S1→S6 实现，禁止扩大 scope。
纪律：
- B3C：🧭 阶段：= major_stage；看法：= 周线 chan+wyck；禁止揉成「中线：{stage} · …」
- conclusion.midline 禁止四阶段词；major_stage 继续给 mistery_gate
- 新建 mid_key_prices（P0 用 key_levels+MA20），与 key_prices 分轨
- render_short_midline 拆 🧭 / ⚡；B1/B2/B4 以文档台账冻结为准
- 微信红线；不改 fusion 算法
每完成一切片跑对应单测。全部完成后列出改动文件 + 南网/华工报告摘要。
```

### 6.2 Reviewer Prompt

```text
你是 Reviewer。只读审查，不改代码（除非用户明确要求你改）。
唯一验收真理：docs/mid-short-dual-track-plan.md §2 与 §5（含 §0.3 B3C 及已冻结 B 项）。
对照 R1–R15 逐条 PASS/FAIL，写 docs/audit/mid-short-dual-track-review.md。
必须检查：阶段行与看法行分离；midline 无四阶段词；中线理论/价位 vs 短线专家源不交叉。
发现「中线：蓄势 · …」揉句或日线顶背驰进 🧭 缠论 → 直接 FAIL。
总判 APPROVE 或 REQUEST_CHANGES（阻断项写清楚）。
```

---

## 7. 风险与回滚

| 风险 | 缓解 |
|------|------|
| conclusion.midline 语义变更导致外部脚本当 stage 用 | grep 引用；模板/测试写明；可同时保留 `conclusion.midline_stage_legacy` 一版（非必须，优先改干净） |
| 回踩区过宽（华工 145–164） | P0 接受；notes 可记；P1 收窄 |
| resist==target | render 合并一行 |
| 双 render 路径 | 只保证 short_midline 路径；旧模板若仍开需文档说明 |
| Review 无规格 | 强制本文档路径进 Reviewer prompt |

回滚：恢复 `conclusion_block._midline_view` 与旧 `render_short_midline` 结论区；删除 `mid_key_prices` 组装即可降级展示（字段 optional）。

---

## 8. 完成定义（Definition of Done）

- [ ] §5 R1–R15 全部 PASS（Reviewer 签字 APPROVE）  
- [ ] 相关 pytest 绿  
- [ ] 南网/华工真票读感符合 §0.1  
- [ ] output-template 与实现一致  
- [ ] 无 fusion/门控算法无关大改  

---

## 9. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-10 | 初版：双轨诊断 + 用户冻结样例 + 双 Agent 流程 |
| 2026-07-10 | 预审后冻结 **B3C**：中线 `阶段：`+`看法：` 并列；阶段服务中线叙事，看法禁四阶段词 |
| 2026-07-10 | 用户拍板 **B1A**：周线两源合成 + 打架显式 |
| 2026-07-10 | 用户拍板 **B2A**：🌟 仅短线；删除 🗺 |
| 2026-07-10 | 用户拍板 **B4A**：生命线回退链；**规格冻结** 可开 Implementer |
