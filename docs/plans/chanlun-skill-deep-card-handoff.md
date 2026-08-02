# 缠论专项结构卡 — Agent Handoff

> **status**: active（Agent1 方案已锁；实现待 Agent2）  
> **日期**: 2026-08-02  
> **开工备忘**: [`chanlun-skill-playbook.md`](./chanlun-skill-playbook.md)（须先读）  
> **产品法源**: `BUSINESS.md` §2.0 / §2.1；算法权威 `02-共享模块-shared/trader_shared/formulas.md` §2–§6  
> **读者**: Agent2 写码 / Agent3 查验 / Agent4 复审  
> **方法复用**: 仅复用「手递 + 四 Agent」做法；**禁止**把威科夫 SC/箱体/Phase A/L0–L3 语义硬套进缠论

---

## 0. 30 秒摘要

1. **要做**：独立缠论 Skill 结构卡（学术展开：笔/段/中枢/一二三买/笔方向），薄包装 + 引擎在 `trader_shared`。  
2. **验收主轴**（用户四点，缺一不算过）：取数对｜期限对｜一二三买只跟引擎｜笔向上向下与引擎一致。  
3. **不是**：威科夫换皮；不是出手总司令；不得覆盖周线威科夫中线阶段。  
4. **顺序**：本 handoff 锁定合同 → 写码+测 → 查验 → PASS 后复审 → PR。

---

## 1. 与 Trader / 威科夫的分工

| | Trader 短中线报告 | 威科夫 Skill | **缠论专项（本文）** |
|--|-------------------|--------------|----------------------|
| 角色 | 出手 / 门禁 / 多岗共振 | 中线状态结构卡 | 缠论结构学术卡 |
| 中线阶段定论 | **周线威科夫** | 同左 | **不得**覆盖；可展示周线缠论结构副读 |
| 短线扳机 | 日线缠论买卖点 + 纪律 | 不负责 | 展开笔/段/中枢/买卖点依据 |
| 禁止 | — | 下单词 | 下单词；手补买卖点；日线冒充中线 |

法源对齐：`BUSINESS.md` §2.0（中线状态=威科夫周线；短线交易=缠论日线）。

---

## 2. 四关心点合同（不可删）

### 2.1 取数合同（关心点 1）

| 项 | 合同 |
|----|------|
| 入口 | Skill/`chanlun_run` 与 Trader 共用 `load_market_snapshot`（或现行 SSOT `light_data` / `data_provider`）；**禁止**另开一套裸拉 CSV 当生产主路径 |
| 复权 | 日/周（及若用的 30m）须**同一前复权**口径；禁止未复权与前复权混拼 |
| 日线回看 | 默认 `LOOKBACK_DAYS=370`（`config.py`） |
| 周线回看 | 默认 `WEEKLY_LOOKBACK_BARS=260` |
| 最小成笔 | `CHANLUN_MIN_BARS=20`；不足 → 诚实报不足，**禁止**静默换成另一周期冒充 |
| 时序 | OHLCV 按时间升序；symbol/市场与用户标的一致 |
| 失败诚实 | 缺数 / 错周期 / 根数不够 → 面板明确「数据不足 / 周线不足 / 日线不足」类文案；**禁止**空结果装成「无买卖点·结构完美」 |

**透出字段（分析层或 meta，面板可核）**：

```text
data_bars_daily: int | None
data_bars_weekly: int | None
data_bars_lower: int | None          # 若跑 30m；否则 None
adjust_mode: "qfq" | str            # 实际使用的复权
data_ok: bool
data_note: str                      # 人话：不足/错标的/取数失败原因
```

### 2.2 期限合同（关心点 2）

| 块 | 默认 K | 不足时 | 禁止 |
|----|--------|--------|------|
| **短线块** | **日 K**（`chanlun_strategy` / `timeframe=daily`） | 日线 &lt; `CHANLUN_MIN_BARS` → `insufficient`，不编结构 | 用周线笔冒充短线扳机 |
| **中线缠论块**（结构副读） | **周 K**（`chanlun_strategy_midline`） | 周不足且日够 → `timeframe=daily_fallback`，展示**必须**标注「（日线）」 | fallback 结果参与中线阶段/定论；fallback 笔段进中线关键价主路径 |
| **区间套**（可选确认） | 日线 + 30m（`TRADER_CHAN_NESTING` 默认开） | 下级缺失/过短 → 原样返回日线结果，零副作用（见 `chan_nesting`） | 把 30m 笔方向写成日线笔方向 |

铁律（`BUSINESS.md` §2.1）：

- 中线「现在什么阶段」**只听周线威科夫**；缠论中线行只做结构副读。  
- `daily_fallback` **允许**结构展示，**禁止**当中线裁定。  
- 面板必须能区分：`weekly` / `daily` / `daily_fallback` / `insufficient`。

### 2.3 买卖点合同（关心点 3）

权威：`formulas.md` §6；检测：`chan_structure.detect_buy_points` / `detect_sell_points`。

| 类型 | 引擎判定摘要（不得在 render 重写） | 正式 / 观察 |
|------|-----------------------------------|-------------|
| 一类买/卖 | ≥2 严格不重叠同向中枢 + 离开段背驰 + 末两同向笔新低/高 + MACD 面积减弱 | 正式（conf=3） |
| 类一买/卖 | 单中枢盘整背驰等降级 | 观察（不进强扳机叙事） |
| 二类买/卖 | 回抽不破前低/高 + **时间轴历史一类**（禁止同帧互为前提） | 正式 |
| 类二买/卖 | 历史一类不齐或力度未齐 | 观察 |
| 三类买/卖 | 离开中枢后回抽不入（末 3 笔内）；离开幅度 ≤15% 等引擎条件 | 正式 |

**字段来源表（只读引擎）**：

| 面板槽 | 来源 | 禁止 |
|--------|------|------|
| 买点类型 | `buy_points[].type`（如 `一类买`/`二类买`/`三类买`/`类一买`…） | render 手补「接近一买」「像二买」 |
| 卖点类型 | `sell_points[].type` | 同上 |
| 价 | `buy_points[].price` / `sell_points[].price` | 用现价或均线冒充信号价 |
| 依据 | `divergence_kind` / `force_source` / `anchor_*` / 关联笔 end_index | 盘感文案当依据 |
| 汇总串 | `buy_point_text`（引擎已拼） | 改写类型名 |
| 未触发 | 诚实「未形成」/「无」 | 「马上就是一买」「潜在三买」暗示 |
| 生命周期 | 若接 `buy_point_lifecycle`：失败 `signal_id` **不得**当新开 | 接旧 failed id |

**展示分层**：正式一/二/三类可进主槽；类一/类二须标观察档或不进强信号槽（与 BUSINESS「执行优先认正式」一致）。  
**禁止下单词**：`宜买` / `可执行` / `可低吸` / `该买了` / `三重共振买` 等（对齐威科夫 Skill 硬停，缠论同禁）。

### 2.4 笔方向合同（关心点 4）

权威：`formulas.md` §2；几何：`chan_geometry.build_strokes`。

| 项 | 合同 |
|----|------|
| 当前笔方向 | `strokes[-1]["direction"]` ∈ {`up`,`down`} → 面板「向上笔」/「向下笔」 |
| 笔数 | `strokes_count` == `len(strokes)`（与引擎一致；裁悬空后的序列） |
| 最近序列 | 最近 N 笔（建议 N=5，不足则全量）方向序列与 `strokes` 一致 |
| 交替 | 引擎强制交替；面板不得显示同向连续两笔为「当前结构」而不加说明 |
| 禁止 | 用均线斜率 /「看起来像」判方向；把**线段**方向当成**笔**方向；合并/裁笔后仍显示旧向 |

**建议透出（便于测与核对）**：

```text
stroke_count: int
current_stroke_direction: "up" | "down" | ""   # ""=无笔
recent_stroke_directions: list["up"|"down"]    # 最近 N 笔，时间升序
```

可由 `chanlun_run` / 薄 view 从 `strokes` 派生，**禁止**在 render 里重算分型成笔。

---

## 3. 输出骨架合同（微信红线）

与 `_common/agent-rules.md` 一致：禁 `#` / `---` / `**` / `|` 表格 / `>` / `*-` 列表。并列用全角 `｜`。

建议骨架（Agent2 落地后写入 `01-功能包-packages/chanlun/references/output-template.md`，与 render 同源）：

```text
缠论 — {名}（{码}）｜短中线结构卡
现价 {价}
取数：日{n}根｜周{m}根｜复权前复权｜{data_note或齐}
⏱ 短线（日）：结构 {structure_type}｜笔 {n}｜当前笔 {向上|向下}｜近笔 {↑↓…}
   中枢 {zones_count}｜段 {segments_count}｜买点 {正式类型或未形成}｜卖点 {…}
⏱ 中线副读（周|日线fallback）：…；fallback 须带「（日线）」
💬 一句：{summary，无下单词}
```

数据不足时首屏即诚实不足，不得假装完整结构。

---

## 4. 验收表（C-D* · 必须有测）

| ID | 关心点 | 用例 | 期望 |
|----|--------|------|------|
| **C-D1a** | 取数 | 日线根数 &lt; `CHANLUN_MIN_BARS` | `data_ok=False` 或短线 `insufficient`；面板明示不足；**不**输出伪造买卖点 |
| **C-D1b** | 取数 | 取数失败 / 空 bars | 诚实失败文案；不静默换错标的或错周期 |
| **C-D1c** | 取数 | 正常前复权日+周夹具 | `adjust_mode` 一致；升序；`data_bars_*` 与输入一致 |
| **C-D2a** | 期限 | 周 K 充足 | 中线副读 `timeframe=weekly`；无「（日线）」误标 |
| **C-D2b** | 期限 | 周不足、日够 | `timeframe=daily_fallback`；面板含「（日线）」；**不**写入中线阶段定论槽 |
| **C-D2c** | 期限 | 短线块 | 仅日线（+可选 30m 确认字段）；禁止周线笔出现在短线「当前笔」 |
| **C-D3a** | 买卖点 | 引擎 `buy_points=[{type:一类买,…}]` | 面板只出现引擎类型/价；与 `buy_point_text` 一致 |
| **C-D3b** | 买卖点 | 引擎无买点 | 「未形成」/「无」；**禁止**「接近一买」「潜在二买」 |
| **C-D3c** | 买卖点 | render 输入被掏空 buy_points | 不得手补任何一/二/三类 |
| **C-D3d** | 买卖点 | 文案扫描 | 面板不含下单词（宜买/可执行/可低吸/该买了…） |
| **C-D4a** | 笔方向 | 合成夹具末笔 `direction=up` | 面板当前笔=向上；`stroke_count` 匹配 |
| **C-D4b** | 笔方向 | 合成夹具末笔 `direction=down` | 面板当前笔=向下 |
| **C-D4c** | 笔方向 | 近 N 笔序列 | 面板近笔序列与 `strokes[*].direction` 一致 |
| **C-D5** | 输出 | 渲染样例 | 无微信违禁符；与 output-template 同源 |
| **C-D6** | 边界 | 回归 | 相关 pytest 绿；**勿改** fusion 出手语义、威科夫中线定论、池分道 |

查验口令：对照本表 + playbook §0 四关心点逐项 ✅/❌；抓假买卖点与笔反向。

---

## 5. 实现切分与白名单（四 Agent）

```text
Agent1 方案（本会话）: playbook + 本文；C-D* 锁死
Agent2 写码:
  - 新建 01-功能包-packages/chanlun/（SKILL / quickstart / output-template / shim）
  - trader_shared/chanlun_run.py + chanlun_render.py（引擎编排与面板；不复制 chan_core）
  - tests：C-D1…C-D6（合成夹具优先）
Agent3 查验: 对照本文 C-D* + 四关心点；跑测；列 ❌
Agent4 复审: Agent3 PASS 后独立再过一遍
```

**可改**：

- 新建：`01-功能包-packages/chanlun/**`
- 新建：`02-共享模块-shared/trader_shared/chanlun_run.py`、`chanlun_render.py`（命名以落地为准，须在 PR 点名）
- 新建/改：`02-共享模块-shared/tests/test_chanlun_skill_*.py`（或等价）
- 文档：本文、playbook、必要时 `AGENTS.md` Skill 速查一行、`BUSINESS.md` 仅增加「专项卡入口」交叉引用（**不改** §2.0 岗位语义）

**可薄改（仅当透出字段缺口）**：

- `chan_core` / 策略包装：只加**派生只读字段**（如 `current_stroke_direction`），禁止改买卖点/成笔判定公式

**勿改**：

- `fusion_core` / 出手 / `decision_view` 语义  
- 威科夫中线定论与 L0–L3 箱体量度  
- 池分道 / `classify.py`  
- `formulas.md` 买卖点定义（除非另开算法 handoff）  
- 在 Skill 包内复制一整份 `chan_core` 引擎

包形态对齐威科夫：`final_chanlun.py` → `trader_shared.chanlun_run.main`；包内 `chanlun_*.py` 为 identity shim。

建议命令（落地后）：

```bash
python3 01-功能包-packages/chanlun/scripts/final_chanlun.py --target <NAME>
```

自测（Agent2 补齐路径后）：

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest 02-共享模块-shared/tests/test_chanlun_skill_card.py -q
```

---

## 6. 硬禁止（查验否决项）

1. 把威科夫 SC/箱体/Phase A/L0–L3 **原样抄**成缠论「期限/成熟度」  
2. render **手补**一买/二买/三买或「接近×买」  
3. 用均线或盘感判笔方向  
4. 专项卡覆盖威科夫中线阶段，或直接给仓位/下单指令  
5. 日线笔写入中线关键价主路径；`daily_fallback` 不标注「（日线）」  
6. 无本 handoff 授权的大改 / 发明出手逻辑  
7. 缺数时静默用错周期数据

---

## 7. DoD

- [ ] `chanlun` Skill 包可跑，stdout 结构卡符合 §3  
- [ ] C-D1a…C-D6 测例绿（或表中每条有对应用例）  
- [ ] 四关心点在真票或夹具上可人工核对：取数根数、期限标签、买卖点仅引擎、笔方向一致  
- [ ] 微信红线扫描通过  
- [ ] 未改 fusion / 威科夫中线定论 / 池分道  
- [ ] PR 含：法源链接、C-D* 对照清单、Agent3/4 结论、pytest 结果

---

## 8. 一句话

> 缠论专项用自己的笔/段/中枢/买卖点；用户死盯取数、期限、一二三买、笔上下。方法走手递+四 Agent；语义禁止威科夫化。先锁本文再写码。
