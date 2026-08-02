# 威科夫详析默认 B·中剪 — Agent Handoff

> 状态：规格冻结（用户 2026-08-02 确认；Agent1 只写 handoff，不改代码）  
> 本文 SSOT：威科夫 `--target` 默认输出改为 B·中剪瘦身卡；旧完整详析保留到 `--full`。  
> 法源对齐：`docs/plans/wyckoff-skill-deep-card-handoff.md`（旧完整详析合同，需改为 `--full`）；`docs/plans/wyckoff-failed-chain-copy-handoff.md` §2.3（失败态不得健康推进）；`docs/plans/wyckoff-tr-maturity-l0l3-handoff.md`（L0-L3 / 箱体与量度门禁）。  
> 实现锚点：`02-共享模块-shared/trader_shared/wyckoff_render.py`；`02-共享模块-shared/trader_shared/wyckoff_run.py`；skill shim `01-功能包-packages/wyckoff/scripts/final_wyckoff.py` 只保持薄入口。
> 实现勘误（Agent2）：failed 短句采用“旧链停止推进”，避免默认 slim 卡出现裸 `还差 AR` 字样；下一盯仍固定“重新寻底／新 SC”。

---

## 1. 产品裁决 / CLI 行为

### 1.1 CLI 三档

1. `python3 scripts/final_wyckoff.py --target <NAME>`  
   默认输出 **B·中剪瘦身卡**，本文为唯一骨架合同。
2. `python3 scripts/final_wyckoff.py --target <NAME> --full`  
   输出旧完整详析，沿用现 `render_wyckoff_detail` 的完整骨架；`wyckoff-skill-deep-card-handoff.md` 改为 `--full` 合同。
3. `python3 scripts/final_wyckoff.py --target <NAME> --brief`  
   仍输出最短卡，沿用现 `render_wyckoff_card`。

优先级：`--brief` 与 `--full` 不应同时使用；如实现层需要兜底，CLI 应报参数冲突，不默默选一档。

### 1.2 做

1. 把默认 `--target` 从旧完整详析改为 B·中剪瘦身卡。
2. 保留顶栏一行摘要：现价 + 周摘要 + 日摘要 + 入池判断。
3. 保留中线 / 短线双块，且每块只有短句 + 灯。
4. 保留区间与 L0-L3 门禁表达：L1 才能写雏形，L2/L3 才能写箱体，量度仅 L3。
5. 保留失败态 copy：日线 Phase A failed 时，不写旧链健康推进；下一盯写重新寻底 / 新 SC。
6. 保留竖排灯：一行一灯，与现行一致。
7. `🔔 变化` 默认折叠：无新亮 / 熄灭时整块省略；有变化时保留一行短句。
8. 底部不再重复入池长文；在 `⭐ 盯` 下固定一行短提示：`本卡不下单；出手/分道看 trader`。
9. 同步输出文档、快路径文档、旧完整详析 handoff 指针与测试。

### 1.3 不做

1. 不改 SC / AR / ST / LPS / SOS 等检测阈值。
2. 不改 `phase_a_status`、`tr_maturity`、`box_display_mode` 的计算语义。
3. 不改 fusion、decision_view、trader 出手、池分道、mistery_gate。
4. 不在 render 层补事件、补假箱体、补假量度。
5. 不把旧完整详析删除；只迁移为 `--full`。
6. 不把灯改成横排；禁止 `● SC｜● AR` 这种横排灯。

---

## 2. B·中剪骨架（默认 `--target`）

默认输出必须贴近下列骨架。事实数字只来自引擎字段；下例数字仅为南网科技对照样，不得硬编码。

```text
威科夫 — {名}（{码}）｜日+周
现价 {price}｜周{bias}·{weekly_main}｜日{bias}·{daily_main}｜{pool_hint}

🧭 中线
  {weekly_short_sentence}
  灯
  ● {CODE}（{中文}）{price?}
  ○ {下一盯：... 或 CODE（中文）下一盯}

⚡ 短线
  {daily_short_sentence}
  灯
  ● {CODE}（{中文}）{price?}
  ○ 下一盯：{next_watch}

🔔 变化
  新亮：...；熄灭：...

🔮 推演
  现在
  {日线短状态}｜{周线短状态}

  若变好
  {一行}

  若变坏
  {一行}

  ⭐ 盯
  {一行}
  本卡不下单；出手/分道看 trader
```

`🔔 变化` 只有存在新亮或熄灭时出现；仅“仍亮”或无变化时整块省略。若首次记录且无变化事实，也省略，避免默认卡被撑长。

`🔮 推演` **必须保留**（用户确认：B 卡不能缺推演故事）。排版与中线/短线一致：标题下两格缩进；标签与正文分行、段间空行。失败态遵守 failed-chain-copy（禁「还差AR / 链可推进」）。

### 2.1 南网科技定稿样（验收对照）

```text
威科夫 — 南网科技（688248）｜日+周
现价 41.90｜周偏多·AR｜日偏空·PhaseAFail｜暂不建议入池（无 ST/LPS）

🧭 中线
  SC后反弹偏多，雏形 37.80～43.85（待 ST）｜未达 L3
  灯
  ● SC（卖力高潮）37.80
  ● AR（自动反弹）41.52
  ○ ST（二次测试）下一盯

⚡ 短线
  Phase A 已失效（SC 41.02 后破位未收）｜无箱｜勿按还差 AR 推进
  灯
  ● SC（卖力高潮）41.02
  ○ 下一盯：重新寻底／新 SC（卖力高潮）

🔮 推演
  现在
  日线 SC（Phase A 已失效）｜周线 SC→AR，待ST

  若变好
  日线重新寻底并出现新 SC（卖力高潮）；周线出 ST（二次测试）确认雏形

  若变坏
  日线继续破位走弱则旧链彻底作废；周线失守 37.80 一带则雏形作废

  ⭐ 盯
  日线等新 SC；周线看能否出 ST（二次测试）确认结构
  本卡不下单；出手/分道看 trader
```

---

## 3. 块级规则

### 3.1 顶栏一行摘要

格式：

```text
现价 {price}｜周{bias}·{weekly_main}｜日{bias}·{daily_main}｜{pool_hint}
```

规则：

1. `weekly_main` / `daily_main` 用短 token，不写长 summary。
2. 失败态日线可写 `PhaseAFail`，不写成“还差 AR”。
3. 入池只给短结论：`建议入池` / `暂不建议入池（短因）` / `结构偏空，暂不建议入池`。
4. 顶栏不得出现买卖、仓位、低吸、可执行等 trader 出手词。

### 3.2 中线 / 短线一句话

一句话必须由结构字段拼短句，不直接塞引擎长 summary 后截断。

拼法建议：

```text
{bias语气} + {主事件/失败态} + {区间成熟度/门禁}
```

示例：

```text
SC后反弹偏多，雏形 37.80～43.85（待 ST）｜未达 L3
Phase A 已失效（SC 41.02 后破位未收）｜无箱｜勿按还差 AR 推进
```

硬要求：

1. 每块一句话原则上一行；不得输出综述腔长段。
2. 区间表达遵守 L0-L3：
   - L0 / `box_display_mode=none`：写 `无箱` / `无成熟箱`，不得展示分位上下沿为箱体或雏形。
   - L1：可写 `雏形 {lower}～{upper}（待 ST）`。
   - L2 / L3：可写 `箱体 {lower}～{upper}`。
   - 未达 L3：写 `未达 L3`；不得给量度目标。
3. 失败态必须使用 `failed-chain-copy` 语义：旧 Phase A failed 时，不得写“还差 AR / 链可推进”。

### 3.3 `🔔 变化`

默认折叠：

1. 无新亮、无熄灭：整块省略。
2. 仅仍亮：整块省略。
3. 有新亮或熄灭：出现一行短句。

格式示例：

```text
🔔 变化
  新亮：周 AR（自动反弹）；熄灭：日 ST（二次测试）
```

禁止恢复旧详析里的“首次记录，暂无对比”默认块，除非 `--full`。

### 3.4 `🔮 推演` + `⭐ 盯`

短推演块必须出现在默认 B 卡（补回用户需要的故事推演，但保持一行一段）。

规则：

1. 固定四段：`现在` / `若变好` / `若变坏` / `⭐ 盯`；标签与正文分行，段间空行；正文两格缩进。
2. 失败态日线「若变好」写重新寻底 / 新 SC，不得写「若出现 AR…链可推进」或「还差」。
3. 「若变坏」可引用周线批准下沿（L1+），L0 不得拿分位沿冒充。
4. 不恢复旧 `--full` 标题 `🔮 故事链（以日线推进；周线作背景）`。
5. 盯段末固定：`本卡不下单；出手/分道看 trader`；不写底部重复入池长文。

---

## 4. 灯规则（默认 B·中剪）

### 4.1 竖排硬规则

1. 灯必须竖排，一行一灯。
2. 禁止横排灯：`● SC｜● AR`、`● SC / ● AR`、`SC、AR 已亮` 均不合格。
3. 缩写必须带中文括号：`SC（卖力高潮）`、`AR（自动反弹）`、`ST（二次测试）`。
4. 亮灯格式：`● CODE（中文）{价?}`。
5. 空心灯格式：`○ CODE（中文）下一盯` 或 `○ 下一盯：{观察项}`。

### 4.2 默认只列已亮 + 至多一个下一盯

1. 每个时间维度默认只列已亮事件灯。
2. 每块最多追加一个空心灯，表示下一盯。
3. 不再默认铺开 SC / AR / ST / LPS / SOS 五灯全表。
4. 亮灯价格只来自引擎事件价或 view 中批准价格源；没有价格就省略价格。
5. 不得为了让卡片完整而手工点亮或手工定价。

### 4.3 失败态日线下一盯

当日线 `phase_a_status == "failed"` 或 `phase_a_range.status == "failed"`：

```text
○ 下一盯：重新寻底／新 SC（卖力高潮）
```

禁止：

```text
○ AR（自动反弹）未亮
○ AR（自动反弹）下一盯
威：SC，还差 AR
若出现 AR，链可推进
```

失败态不灭已亮灯。若旧 SC 已亮，仍可显示：

```text
● SC（卖力高潮）41.02
○ 下一盯：重新寻底／新 SC（卖力高潮）
```

### 4.4 缩写释义表

默认 B 至少覆盖：

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

未知 code 可原样展示，但仍需带 `（事件）` 或既有映射中文，避免裸缩写。

---

## 5. 砍掉 / 保留清单

### 5.1 默认 B 必须砍掉

1. `📊 现况` 整块。
2. `🔔 变化` 的默认常驻块；无新亮 / 熄灭则省略。
3. 旧长标题 `🔮 故事链（以日线推进；周线作背景）` 及其空行分段长文（改由短 `🔮 推演` 承担）。
4. `💬 综述` 整块。
5. 底部入池重复结论与说明长文。
6. 日线健康推进式空心灯全表。

### 5.2 默认 B 必须保留

1. 顶栏一行摘要。
2. 中线 / 短线双块。
3. L0-L3 / 箱体 / 雏形 / 量度门禁。
4. Phase A failed 收口 copy。
5. 竖排灯，一行一灯。
6. 入池短判断，但仅作为结构入池提示，不变成交易指令。
7. **短推演** `🔮 推演`（现在／若变好／若变坏／盯）。

---

## 6. 可改 / 勿改白名单

### 6.1 可改

1. `02-共享模块-shared/trader_shared/wyckoff_render.py`
   - 新增或改造默认 B renderer。
   - 保留现 `render_wyckoff_detail` 给 `--full`。
   - 保留 `render_wyckoff_card` 给 `--brief`。
2. `02-共享模块-shared/trader_shared/wyckoff_run.py`
   - CLI 增加 `--full`，调整 `--target` 默认渲染选择。
   - 确保 `--brief` / `--full` 冲突处理。
3. `01-功能包-packages/wyckoff/references/output-template.md`
   - 默认 `--target` 示例改为 B·中剪。
   - 旧完整详析移到 `--full`。
   - `--brief` 仍为最短卡。
4. `01-功能包-packages/wyckoff/references/agent-quickstart.md`
   - 默认命令说明改为 B·中剪。
   - 增加 `--full` 旧完整详析命令。
   - 保留 `--brief` 最短卡。
5. `docs/plans/wyckoff-skill-deep-card-handoff.md`
   - 顶部标注旧完整详析不再是默认，改为 `--full` 合同。
   - 增加指针指向本文作为默认 B SSOT。
6. `02-共享模块-shared/tests/test_wyckoff_skill_render.py` 及必要快路径/CLI 测试。
7. 本文档。

### 6.2 勿改

1. `02-共享模块-shared/trader_shared/wyckoff_events.py` 检测阈值。
2. `02-共享模块-shared/trader_shared/wyckoff_core.py` 结构判定语义。
3. `02-共享模块-shared/trader_shared/wyckoff_phase.py` 阶段机语义。
4. fusion、decision_view、trader 出手、池分道、mistery_gate。
5. trader / review / t0 输出合同。
6. Skill 包内 shim 不得复制完整引擎。

---

## 7. 验收表 S-B*

| ID | 必须 | 测 / 验 |
|----|------|---------|
| S-B1 | `--target <NAME>` 默认输出 B·中剪骨架 | CLI / render fixture 断言首行 `威科夫 — {名}（{码}）｜日+周`，无 `威科夫详析 —` |
| S-B2 | `--full` 输出旧完整详析 | CLI 断言仍含旧完整块：`📊 现况`、`🔮 故事链`、`💬 综述` |
| S-B3 | `--brief` 仍输出最短卡 | CLI / render fixture 断言走 `render_wyckoff_card` 骨架 |
| S-B4 | 默认 B 砍掉常驻长块 | 默认输出不含 `📊 现况`、旧 `🔮 故事链` 长标题、`💬 综述`，且无底部入池长说明；**须含**短 `🔮 推演` |
| S-B5 | `🔔 变化` 默认折叠 | 无新亮 / 熄灭 fixture 不出现 `🔔 变化`；有新亮或熄灭 fixture 出现一行短句 |
| S-B6 | 灯竖排一行一灯 | 默认输出不得含 `● SC｜● AR` 等横排灯；每个灯独占一行 |
| S-B7 | 灯只列已亮 + 至多一个下一盯 | 每块空心灯数量不超过 1；不默认铺开五灯未亮表 |
| S-B8 | 缩写必须带中文括号 | 所有事件灯匹配 `CODE（中文）`；不得裸写 `SC` / `AR` 灯 |
| S-B9 | 失败态日线不健康推进 | failed fixture 输出 `重新寻底／新 SC（卖力高潮）`，不含 `还差 AR` / `链可推进` / `○ AR（自动反弹）未亮` |
| S-B10 | 中线 / 短线一句话为短句 | 不直接输出长 summary；南网类 fixture 中线含雏形与未达 L3，短线含 failed / 无箱 / 勿推进 |
| S-B11 | L0-L3 门禁保留 | L0 不展示分位箱沿；L1 写雏形；L2/L3 写箱体；量度仅 L3 |
| S-B12 | 顶栏入池短判断保留且非出手 | 顶栏含 `建议入池` / `暂不建议入池` 等短判断；全卡无 `买入` / `低吸` / `可执行` / 仓位建议 |
| S-B13 | `⭐ 盯` 固定短提示 | 默认 B 推演块含缩进 `⭐ 盯` 段与 `本卡不下单；出手/分道看 trader`，且不再有说明长文 |
| S-B14 | 文档同步完成 | `output-template.md`、`agent-quickstart.md`、`wyckoff-skill-deep-card-handoff.md` 均标明默认 B、`--full` 旧完整、`--brief` 最短 |
| S-B15 | 勿改边界未触碰 | diff 审查不得改检测阈值、fusion、decision_view、池分道、trader 出手 |
| S-B16 | 相关测试绿 | 至少跑 `python3 -m pytest 02-共享模块-shared/tests/test_wyckoff_skill_render.py`；如 CLI 参数测试另建文件，也一并跑 |
| S-B17 | 短推演必出且失败态收口 | 默认 B 含 `🔮 推演` + `现在/若变好/若变坏`；failed fixture 推演无「还差」「链可推进」 |

---

## 8. 文档同步清单

写 Agent2 实现时必须同步：

1. `docs/plans/wyckoff-detail-slim-b-handoff.md`
   - 本文，默认 B·中剪 SSOT。
2. `01-功能包-packages/wyckoff/references/output-template.md`
   - 默认 `--target` 改为 B·中剪骨架。
   - 新增或调整 `--full` 旧完整详析示例。
   - 保留 `--brief` 最短卡示例。
3. `01-功能包-packages/wyckoff/references/agent-quickstart.md`
   - 默认命令说明：B·中剪。
   - 新增 `--full` 命令：旧完整详析。
   - `--brief` 说明改为最短卡。
4. `docs/plans/wyckoff-skill-deep-card-handoff.md`
   - 顶部状态改为“旧完整详析 / `--full` 合同”。
   - 加链接：默认 `--target` 以本文为准。
5. `docs/plans/wyckoff-failed-chain-copy-handoff.md`
   - 若实现触碰失败态下一盯示例，可增指针；不要求改检测语义。

---

## 9. 双 Agent 职责

### 9.1 Agent1（本文）

1. 只创建本文 handoff。
2. 不改实现代码、不改输出文档、不改测试。
3. 返回本文路径、验收 ID、默认 CLI 行为。

### 9.2 Agent2（写代码）

1. 只读本文 + `wyckoff-failed-chain-copy-handoff.md` + `wyckoff-tr-maturity-l0l3-handoff.md` + 旧完整详析 handoff。
2. 只改 §6.1 白名单文件。
3. 逐项实现 S-B1…S-B16。
4. 同步 §8 文档清单。
5. 跑 S-B16 指定测试并提交结果。

### 9.3 查 Agent

1. 对照 §2…§7 验收，逐项标 S-B ID。
2. 重点查四类回归：
   - 默认仍是旧完整详析。
   - 灯被改成横排或未亮全表。
   - failed 仍出现健康推进感。
   - 为了渲染改了检测阈值 / fusion / 池分道。
3. 若发现触碰 §6.2 勿改文件，要求 Agent2 给出法源授权；无授权则退回。
4. 跑相关 pytest；失败项必须映射到 S-B ID。

父 Agent：查 Agent PASS 后再进入 PR / 合并流程。
