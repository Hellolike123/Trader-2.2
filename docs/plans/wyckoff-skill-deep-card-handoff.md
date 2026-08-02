# 威科夫 Skill 详析卡 — Agent Handoff

> **状态**: 规格冻结（用户 2026-08-01 对话确认；明日再调参）  
> **产品法源**:  
> - 原典盘点 `docs/audit/wyckoff-original-concept-inventory.md`  
> - 箱体/量度门禁 `docs/plans/wyckoff-tr-maturity-l0l3-handoff.md`  
> - View 契约 `docs/designs/wyckoff-state-view.md`  
> - P&F `docs/plans/wyckoff-pnf-handoff.md`  
> **协作**: 写 Agent 实现；查 Agent 对照本文 + 原典盘点查幻觉/漏项；父 Agent 修完再 PR  

---

## 0. 本迭代范围

### 0.1 做

1. **单票默认输出「详析卡」**（学术展开、日线+周线分维），入口仍 `final_wyckoff.py --target`。  
2. **短卡保留**：`--brief` 走现有 `render_wyckoff_card` 薄卡（兼容）。  
3. **只渲染、不改检测**：全部结构/事件/成熟度/量度来自 `wyckoff_analysis` → `to_wyckoff_state_view` / 既有 chain 辅助；**禁止**手写事件、假箱沿、假 SC、假量度。  
4. **L0–L3 展示门禁**（与 maturity handoff 一致，硬禁止）：  
   - L0 / `box_display_mode=none` / `tr_seed_source=percentile` → **禁止**上屏「箱体/雏形上下沿」当作区间；可写「无成熟箱/无雏形」；分位种子数不得进故事链关键价。  
   - L1 → 可写「雏形 下沿/上沿（待 ST）」  
   - L2/L3 → 可写「箱体 下沿/上沿」  
   - 量度目标 **仅 L3 / measure_allowed**；否则「未达 L3，暂不测算」  
5. **事件灯**：● 亮 / ○ 未亮；一行一灯；缩写后必须带中文释义；亮灯须带引擎事件价（有则）。  
6. **故事链**：`现在 / 若变好 / 若变坏 / ⭐ 盯 / 入池 / 说明`；原典缩写保留+释义；价格只许来自批准源（见 §2.3）。  
   - Phase A failed 时，「若变好」与「⭐ 盯」不得写下一灯推进；文案收口见 `wyckoff-failed-chain-copy-handoff.md` §2.3。
7. **`🔔 变化`**：相对上次同票快照的新亮/仍亮/熄灭；首次无快照写「首次记录，暂无对比」。  
8. **入池软建议**三档：`建议入池` / `暂不建议入池` / `建议复核出池`（规则见 §2.5）；**禁止**买卖仓位指令。  
9. 同步 `01-功能包-packages/wyckoff/references/output-template.md` + pytest。  

### 0.2 本迭代不做（明日可调 / 另开）

- `filter --event LPS` 池内过滤器（合同可先占位，**本迭代可不实现 CLI**）。  
- 全市场扫描；TdxMCP 新 Provider。  
- 改 SC/ST/LPS 检测阈值（用户明日再调）。  
- 改 fusion / trader 门禁 / 池分道。  
- 在详析里手工补「有低点就算 SC」。  
- **检测下一轮备忘**（SC 结构搜索宇宙、南网破位后仍亮 SC+AR 雏形收口）：见 [`wyckoff-detect-tuning-next.md`](wyckoff-detect-tuning-next.md)。

---

## 1. 面板骨架（必须）

```text
威科夫详析 — {名}（{码}）｜日线+周线

📊 现况
  现价 x｜周线{偏多|偏空|中性} · {主灯或无主灯}｜日线{…} · {主灯或无灯}｜测算{已给出|均未达 L3}

🔔 变化
  首次记录，暂无对比
  或：新亮：…｜仍亮：…｜熄灭：…

🧭 中线（周线 · 入池看这里）
  一句话：{summary 压缩 / bias + 主灯含义}
  区间：{按 L0–L3 门禁}
  失效：{invalidation_hint；L0 无箱时勿把分位沿当失效箱沿冒充——若 hint 含 TR 沿但 box_display_mode=none，改写为「暂无明确箱体失效价」或保留 hint 但区间行已声明不当箱}
  入池：{三档之一 + 短因}

  灯
  ● {CODE}（{中文}）{价?}
  ○ {CODE}（{中文}）未亮
  （无任何亮灯时：○ 其他主灯未亮 或 列出吸筹/派发相关未亮集，见 §2.4）

⚡ 短线（日线 · 盯触发看这里）
  一句话：…
  区间：…
  失效：…

  灯
  （格式同中线；吸筹链五灯 SC/AR/ST/LPS/SOS 建议日线默认列出）

🔮 故事链（以日线推进；周线作背景）

  现在
  …

  若变好
  …

  若变坏
  …

  ⭐ 盯
  …

  入池：…（可与中线入池同结论，允许重复一句总判）
  说明：本卡不下单；买卖看 trader 门禁；分道仍听 trader

💬 综述
  1～3 句，只复述已上屏事实，禁止新价/新事件
```

微信红线：无 `#` / `**` / `|...|` 表 / `---` / `*/-` 列表符。

### 1.1 Emoji

| 块 | 标题 |
|----|------|
| 现况 | `📊 现况` |
| 变化 | `🔔 变化` |
| 中线 | `🧭 中线（周线 · 入池看这里）` |
| 短线 | `⚡ 短线（日线 · 盯触发看这里）` |
| 故事链 | `🔮 故事链（以日线推进；周线作背景）` |
| 盯 | `⭐ 盯`（故事链内） |
| 综述 | `💬 综述` |

---

## 2. 字段与算法来源（禁止自编）

### 2.1 唯一计算入口

```text
load_market_snapshot → wyckoff_analysis(daily|weekly)
  → to_wyckoff_state_view
  → format_wyckoff_chain_plain / wyckoff_chain 事件提取（日线链）
  → format_wyckoff_event_light（可选主灯摘要）
  → 本迭代 render_wyckoff_detail（纯展示）
```

**禁止**：在 render 层重新检测 SC/AR/ST；禁止用行情 min(low) 冒充 SC；禁止用 L0 分位 `tr_lower/tr_upper` 当箱沿。

### 2.2 缩写释义表（上屏必须带括号）

| CODE | 中文 |
|------|------|
| SC | 卖力高潮 |
| AR | 自动反弹 |
| ST | 二次测试 |
| Spring | 弹簧确认 |
| LPS | 最后支撑点 |
| SOS | 强势信号 |
| PS | 初步止跌 |
| BC | 买力高潮 |
| ARE | 自动回落 |
| SOW | 弱势信号 |
| LPSY | 最后供应点 |
| UT / UTAD | 上冲 / 派发后上冲 |
| BU | 回调买入 |
| JAC | 跳溪 |
| SV | 止跌量 |
| PSY | 初步供应 |
| Markup | 主升 |
| Markdown | 主跌 |
| TR | 交易区间 |

（与 `format_wyckoff_event_light` / 原典盘点对齐；未知 code 原样+「事件」）

### 2.3 故事链可用价格源（白名单）

1. `event_detail[*].price` / 各 `*_price` 灯价  
2. L1 雏形沿：Phase A `sc_low` / `ar_high`（且 `box_display_mode=proto`）  
3. L2/L3 箱沿：view.tr 或 phase_a 边界（且 `box_display_mode=box`）  
4. `invalidation_hint` 中引擎已写出的价（展示时可引用）  
5. **明确标注非箱沿**的旁注：仅当需要对照时，可用「近端低点对照：{min low in lookback}（行情低点，非威科夫箱沿）」——**可选**；不得写入「区间：」主行  

**禁止**：L0 percentile `tr_lower/tr_upper`；臆造「约 xx」；把 trader 止损/生命线写进威科夫「区间」主行（故事链「若变坏」若引用 trader 价必须标注来源且本迭代**可不引用**——详析卡以威科夫字段自洽为准，缺则写「暂无明确失效价」）。

### 2.4 灯列表

- 日线默认展示吸筹链：`SC, AR, ST, LPS, SOS`（ST 含 `secondary_test_sc_signal` 或 Spring 确认类灯的映射按 chain 模块既有语义；**以 `extract_accum_events` / active_events + 信号字段为准**）。  
- 日线另追加：**引擎已亮**的非五灯（PS / Spring / BU / JAC / SV / 派发侧等，来自 active_events 或信号字段）一行一灯，避免 W-D10「引擎有、面板永远不提」；**不**为未亮概念编造整表 ○。  
- 周线：以 `active_events` 亮灯为主；未亮可 `○ 其他主灯未亮`。  
- 亮：`● CODE（中文）价`；未亮：`○ CODE（中文）未亮`。  
- **不得**因「价格合适」手工点亮。

### 2.5 入池三档（只读结构，规则写死）

| 档 | 条件（满足第一条硬否决则暂不建议/复核） |
|----|----------------------------------------|
| **建议复核出池** | 周线 bias=bear 且存在派发侧主灯（ARE/BC/SOW/LPSY/UTAD 等，以 active_events/信号为准）且票已在池——**若无法知是否在池，详析仍可输出「建议复核出池」语义改写为「结构偏空，不宜新开仓位/新入池」**；本迭代简化：偏空+派发灯 → `暂不建议入池`（或文案 `结构偏空，暂不建议入池`） |
| **暂不建议入池** | 日线吸筹链未成型；或双线 L0；或仅早期 AR/无 ST 且无箱（L0/L1 无 LPS/SOS） |
| **建议入池** | 日线链已含 LPS 或 SOS（或 ST+AR+SC 且 L2+），且周线 bias ≠ bear |

查 Agent 验：不得出现「立即买入」。

### 2.6 `🔔 变化` 持久化

- 路径：`trader_paths` 新 key `wyckoff_light_snapshot` → `wyckoff_light_snapshot.json`  
- 结构：`{ "{code}": { "ts": ISO, "daily_events": [...], "weekly_events": [...], "daily_prices": {code: price}, "weekly_prices": {...} } }`  
- 每次详析渲染后更新该票；对比在更新前做。  

---

## 3. 可改 / 勿改

### 可改

- `trader_shared/wyckoff_render.py`（新增 `render_wyckoff_detail`；brief 保留）  
- `trader_shared/wyckoff_run.py`（CLI：默认 detail，`--brief`；拼装 plan 字段供 render）  
- `trader_shared/trader_paths.py`（注册 snapshot key）  
- `01-功能包-packages/wyckoff/references/output-template.md`  
- `01-功能包-packages/wyckoff/references/agent-quickstart.md`（一句：默认详析，`--brief` 短卡）  
- `02-共享模块-shared/tests/test_wyckoff_skill_render.py`（及必要新测）  
- 本 handoff  

### 勿改

- `wyckoff_events.py` / `wyckoff_phase.py` / `wyckoff_core.py` 检测阈值与判定语义  
- `fusion_*` / `decision_view` / 池分道 / `mistery_gate`  
- 用 render 层「补 SC」迁就肉眼低点  

---

## 4. 验收表

| ID | 必须 | 测/验 |
|----|------|-------|
| W-D1 | `--target` 默认详析含 现况/变化/中线/短线/故事链/综述 | 单测 fixture |
| W-D2 | `--brief` 仍为旧短卡骨架 | 单测 |
| W-D3 | L0 + percentile：详析「区间」不得出现分位上下沿数字当箱/雏形 | 单测（天奈类：有 tr_lower 但 maturity L0） |
| W-D4 | L1 写雏形；L2/L3 写箱体；量度仅 L3 | 单测 |
| W-D5 | 灯 ●/○ 一行一灯；缩写带中文；亮灯价来自 event_detail/信号价 | 单测 |
| W-D6 | 无「宜买/可低吸/可执行/该买了」 | 单测禁词 |
| W-D7 | 故事链价格不出现白名单外数字 | 单测或属性检查 |
| W-D8 | 变化：无快照→首次记录；有快照→新亮/熄灭可测 | 单测 tmp_path |
| W-D9 | 入池三档文案出现且无下单句 | 单测 |
| W-D10 | 查 Agent：对照原典盘点已实现概念——详析应能展示的（阶段/链/事件/TR成熟度/P&F闸）无「引擎有、面板永远不提」的静默黑洞；**未实现概念不得假装有** | 查清单 |
| W-D11 | 门禁相关 pytest 绿 | CI/本地 |

---

## 5. 双 Agent

| 角色 | 职责 |
|------|------|
| **写 Agent** | 只读本文 + L0–L3 handoff + view 契约；实现 detail 渲染与测；禁止改检测 |
| **查 Agent** | 对照本文 §0.1/§1/§2/§4 + 原典盘点；抓幻觉价、L0 冒充箱、漏块、买卖词；默认不改码 |

父 Agent：查完修完再 PR。

---

## 6. 用户已确认的产品裁决（防忘）

1. 详析比 trader 多视角卡更学术、只威科夫。  
2. 故事链：现在/若变好/若变坏；缩写+释义；不要「人话」标签。  
3. 中线 4 行版（一句话/区间/失效/入池）+ 灯块；短线灯格式同中线。  
4. 现况一行摘要，避免与中线重复抄区间。  
5. `🔔 变化` 防忘新亮灯；`⭐ 盯` 是未来待办。  
6. 入池：建议/暂不建议/复核（软），不下单。  
7. **L0 分位带禁止当箱沿**（天奈教训）。  
8. SC 等灯严格跟引擎；不因肉眼低点手工亮灯。  
9. 过滤器改期；明日再调检测参数。  
)
