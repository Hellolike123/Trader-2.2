# 缠论 C-D Follow-up — Agent Handoff（并行四路）

> **status**: done  
> **日期**: 2026-08-02  
> **前置**: P0 已合 `main`（#27）；法源母本 [`chanlun-skill-deep-card-handoff.md`](../chanlun-skill-deep-card-handoff.md) §7.2 / §10  
> **本 PR 目标**: 清掉查表剩余 ❌（C-D1a–c / C-D2b / C-D3* / C-D4a–c / C-D5）  
> **方法**: 手递 + 多 Agent **同时**写码 → 查 Agent 对照 → 修 → PR  
> **禁止**: 威科夫 SC/箱体硬套；改 fusion 出手语义；改池分道；Skill 包复制引擎

---

## 0. 30 秒

P0 已修笔链/指数。本轮三刀并行：

1. **Buy** — 禁 fusion/render 手补买卖点（C-D3）  
2. **Data** — 不足/失败诚实 + fallback 面板「（日线）」不被盖掉（C-D1a–c / C-D2b）  
3. **Skill** — 薄缠论结构卡，透出笔方向/笔数/买卖点（C-D4a–c / C-D5）

---

## 1. 并行切分

| Agent | 验收 ID | 可改白名单 | 勿改 |
|-------|---------|------------|------|
| **Agent-Buy** | C-D3a–d | `chan_core.py`（`format_chanlun_short_light` 禁 fusion 手补）、相关 tests；必要时 `short_midline.py` 只去掉依赖手补的展示 | fusion 计分公式；出手 |
| **Agent-Data** | C-D1a/b/c、C-D2b | `chan_core`/`chanlun_strategy*` 不足字段；中线渲染路径保证 `daily_fallback`→「（日线）」进最终面板；tests | 威科夫；强改全市场复权源（可诚实标 `adjust_mode`） |
| **Agent-Skill** | C-D4a–c、C-D5 | 新建 `trader_shared/chanlun_run.py` + `chanlun_render.py`；`01-功能包-packages/chanlun/**`（shim+quickstart+output-template）；tests | 复制 `chan_core`；下单词 |
| **Agent-Check** | 全表 | **只查不改**；列 ❌ | — |

父 Agent：合并冲突、跑测、开/更新 PR。

---

## 2. 合同要点（不可删）

### 2.1 Buy（C-D3）

- 面板买卖点 **只**来自引擎 `buy_points`/`sell_points`（或 `buy_point_text` 同源）。  
- **禁止** `format_chanlun_short_light`（及同类）在 `buy_points` 空时从 `fusion_chan.reason` 解析出「一买」。  
- 无点：诚实「暂无买卖点」/「未形成」；禁「接近一买」。  
- 禁下单词测：宜买/可执行/可低吸/该买了。  
- 短名「一买」可保留作灯标，但不得无引擎点时出现；有点时可带价（或专项卡带价）。

### 2.2 Data（C-D1 / C-D2b）

- 日线 `< CHANLUN_MIN_BARS` → `timeframe=insufficient`（或 `data_ok=False`）+ 人话不足；**禁止**装成正常「暂无买卖点 · 中性」而无不足提示。  
- 空/失败 bars：同上，诚实失败。  
- 透出或可核：`data_bars_daily/weekly`、`adjust_mode`（允许标 `mixed`/`unknown`，禁止假称已统一）。  
- `daily_fallback`：最终中线缠论行（含 wave 路径）须含「（日线）」或等价标注，不得被盖掉。

### 2.3 Skill（C-D4 / C-D5）

- 命令：`python3 01-功能包-packages/chanlun/scripts/final_chanlun.py --target <NAME>`  
- 包形态对齐威科夫：shim → `trader_shared.chanlun_run.main`。  
- 面板须可核：取数根数、短线日/中线周（含 fallback 标注）、买卖点仅引擎、**当前笔方向 + 笔数 + 近笔序列**。  
- 微信红线；无下单词；不覆盖威科夫中线阶段。

---

## 3. 测例（必须有）

| ID | 测 |
|----|----|
| C-D3b/c | 引擎 buy_points=[] + fusion reason 含「一类买」→ 短线灯 **无**「一买」 |
| C-D3b/c/d | 污染 `wave_label_mid` + fusion reason → 中线缠论行与 ✅ 亮点 **无**一类买/可低吸 |
| C-D3d | render 样例无下单词 |
| C-D1a | bars 根数不足 → insufficient + 不足文案 |
| C-D2b | midline daily_fallback → 最终字符串含「日线」 |
| C-D4a/b | 夹具末笔 up/down → 卡文案方向一致 |
| C-D4e | Skill：末向上笔 tip 高、现价反向离开 ≥15% → 卡文案「高点已离开·向下未成笔」，禁「当前笔 向上笔／走势 拉升段」 |
| C-D5 | Skill stdout 无 `#`/`**`/`\|` 表格 |

---

## 4. DoD

- [x] Agent-Buy/Data/Skill 各自落地并测绿  
- [x] Agent-Check 首轮抓到 cards.py + short_midline 异常兜底漏网 → 父 Agent 已修  
- [x] Agent-Check 二～四轮抓漏（亮点 fusion / 假背驰 / Trader tip-leave / 有卖点跳过清洗 / 相反背驰）→ 父 Agent 已修  
- [x] Agent-Check 五轮全表复审：**通过，可以合 PR #29**  
- [x] 未改 fusion 出手 / 威科夫定论 / 池分道  
- [x] PR 含法源、对照清单、查结论、pytest（69 passed：report_optimization / skill_render / cards_p0 / wave_label_stroke_tip）

---

## 5. 一句话

> 三路并行清 C-D 余债：禁手补买点、不足诚实、专项卡透笔；**查完再合**（先修面板污染 + Skill tip-leave）。
