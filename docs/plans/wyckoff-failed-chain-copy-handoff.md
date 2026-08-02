# Phase A 失败态链文案收口 — Agent Handoff

> 状态：规格冻结（用户 2026-08-02 确认；Agent1 只写 handoff，不改代码）  
> 法源对齐：`docs/plans/wyckoff-structure-anchor-handoff.md` §3.2 / S-A5（failed → L0，禁健康推进叙事）  
> 法源对齐：`docs/plans/wyckoff-skill-deep-card-handoff.md` §0.1 / §1 / §2.1（详析故事链只渲染，不改检测）  
> 实现锚点：`02-共享模块-shared/trader_shared/wyckoff_chain.py::format_wyckoff_chain_plain`；`02-共享模块-shared/trader_shared/wyckoff_render.py::_story_block`  
> 交叉：默认 B / `--full` / `--brief` 失败人话用词（`Phase A 失效`、去掉「已失效」）以 `docs/plans/wyckoff-phase-fail-copy-handoff.md` 为准；本文只管禁健康「还差 / 链可推进」，不恢复旧底已废词。展示短句若与本文旧例「已失效」冲突，以 phase-fail-copy 为准。

---

## 1. 状态 / 范围

### 1.1 做

1. 收口 Phase A 失败态的吸筹链短句：当 `phase_a_status == "failed"` 或 `phase_a_range.status == "failed"` 时，`chain_plain` 不得继续输出「还差X」。
2. 收口详析卡故事链「若变好」：失败态不得写「若出现 AR…链可推进」或「还差X」，改为失效后的重新观察语气。
3. 保留事件灯事实：`sc_signal=True` 仍可上屏为亮灯；失败态只影响链/故事链 copy，不熄灯。
4. 短卡与详析共用同一 `chain_plain` 失败态规则，避免一个收口、一个仍误导。
5. 补测并同步相关输出文档示例。

### 1.2 不做

1. 不改 `wyckoff_events.py` / phase 机 / `wyckoff_core.py` 的检测阈值和事件判定。
2. 不改 `phase_a_status` / `tr_maturity` / `box_display_mode` 的既有计算合同；失败态来源以结构锚点 handoff 为准。
3. 不改 fusion / decision_view / trader 出手 / 池分道 / 入池规则。
4. 不在 render 层补 SC、补 AR、重算 ST，或手工把失败结构写回健康推进。

---

## 2. 产品裁决

### 2.1 失败态识别

任一来源表明失败即按失败态 copy：

```text
phase_a_status == "failed"
或
phase_a_range.status == "failed"
```

若两个字段同时存在但不一致，copy 层按更保守的失败态处理；字段一致性问题由结构锚点 S-A5 / 相关测试另行卡住。

渲染拼装：`daily_raw` / `daily_view` **任一** failed 即收口；`_display_chain_plain` 须把失败态写入用于 `format_wyckoff_chain_plain` 的 src，禁止「view=failed、raw 仍 established」时优先 raw 而漏出「还差」。

### 2.2 `chain_plain` 短句规则

失败态时，`format_wyckoff_chain_plain` 仍可展示已经亮过的吸筹链事实，但必须停止健康推进暗示。

短句规则：

```text
有已亮链：威：{已亮链}（Phase A 失效）
无已亮链：威：结构失效
```

南网科技这类 `sc_signal=True`、`phase_a_status=failed`、`tr_maturity=L0` 的对照，应输出：

```text
威：SC（Phase A 失效）
```

禁止：

```text
威：SC，还差AR
威：SC→AR，还差Spring确认
威：SC→AR→ST，链待推进
```

说明：

1. `{已亮链}` 沿用现有显示名映射（如 `SC→AR→Spring确认→LPS→SOS`），不新增事件名。
2. 失败态短句不含「还差」「链可推进」「待补下一灯」等健康链推进语气。
3. 文案须微信安全：不用 `#` 标题、`**` 粗体、Markdown 表格；短句内并列只用全角符号或中文括号。

### 2.3 详析故事链「若变好」

失败态时，「若变好」不得基于 `first_missing_accum(events)` 写下一灯推进：

```text
禁止：若出现 AR（自动反弹）且站稳，链可推进
禁止：还差AR，出现后链可推进
```

失败态应改为重新观察语气，不假装旧 Phase A 仍健康：

```text
Phase A 失效｜须重新寻底；观察是否出现新的 SC（卖力高潮）
```

可选追加条件必须仍是观察语气：

```text
Phase A 失效｜须重新寻底；观察是否出现新的 SC（卖力高潮）；后续若有新 AR/ST，再按新结构评估
```

禁止把旧 SC 后的 AR / ST / LPS / SOS 写成可推进链；旧结构已 failed 时，下一步不是「还差下一灯」，而是「重新寻底 / 新 SC」。

### 2.4 灯逻辑不变

`sc_signal`、`ar_signal`、`secondary_test_sc_signal`、`active_events` 等事件灯仍按引擎事实展示。失败态 copy 不负责灭灯，也不得为了让文案顺眼修改事件旗。

---

## 3. 可改 / 勿改白名单

### 3.1 可改

1. `02-共享模块-shared/trader_shared/wyckoff_chain.py`
   - `format_wyckoff_chain_plain` 增加失败态 copy 分支。
   - 如需，可新增小型 helper 判断 `phase_a_status` / `phase_a_range.status`。
2. `02-共享模块-shared/trader_shared/wyckoff_render.py`
   - `_story_block` 在失败态时改写「若变好」。
   - 确保短卡 / 详析取到的 chain 文案一致。
3. `02-共享模块-shared/tests/test_wyckoff_skill_render.py`
   - 增加失败态详析故事链断言。
4. `02-共享模块-shared/tests/test_wyckoff_tr_maturity.py` 或 `02-共享模块-shared/tests/test_wyckoff_structure_anchor.py`
   - 可复用失败态 fixture，断言 copy 不含健康推进语气。
5. `01-功能包-packages/wyckoff/references/output-template.md`
   - 若示例包含链或故事链，需要更新失败态示例。
6. 相关 handoff 文档
   - 本文。
   - `docs/plans/wyckoff-skill-deep-card-handoff.md`。
   - `docs/plans/wyckoff-structure-anchor-handoff.md`。

### 3.2 勿改

1. `02-共享模块-shared/trader_shared/wyckoff_events.py` 的 SC / AR / ST / phase 检测阈值。
2. `02-共享模块-shared/trader_shared/wyckoff_core.py` 的失败态判定，除非另有结构锚点 handoff 明确授权。
3. `02-共享模块-shared/trader_shared/wyckoff_phase.py` 的阶段机语义。
4. fusion / decision_view / 池分道 / trader 出手 / mistery_gate。
5. 用 render 层重算或改写灯：失败态 copy 只能解释已有字段。

---

## 4. 验收表 C-F*

| ID | 必须 | 测 / 验 |
|----|------|---------|
| C-F1 | `chain_plain` 失败态无「还差」 | 输入含 `sc_signal=True` 且 `phase_a_status="failed"` 或 `phase_a_range.status="failed"`；断言输出为 `威：SC（Phase A 失效）`，且不含「还差」 |
| C-F2 | `chain_plain` 失败态保留已亮事实 | 输入含 SC+AR 等已亮灯且 failed；断言已亮链仍展示，但后缀为 `（Phase A 失效）`，不追加下一灯 |
| C-F3 | 无已亮链但 failed 时不写健康链 | 输入无吸筹链事件但 failed；断言输出 `威：结构失效`，不写「吸筹链未成型，还差…」 |
| C-F4 | 详析故事链「若变好」失败态不写推进 | `_story_block` / `render_wyckoff_detail` fixture：failed + SC 亮；断言「若变好」含「Phase A 失效」和「重新寻底」或「新的 SC」，不含「链可推进」/「还差」 |
| C-F5 | 灯逻辑不变 | 同一 fixture 断言灯区仍可显示 `● SC（卖力高潮）`；失败态 copy 不把 `sc_signal` 改 False |
| C-F6 | 短卡吃到 `chain_plain` | `render_wyckoff_card` 或短卡路径使用 failed fixture；断言链行不含「还差」，含失败态短句 |
| C-F7 | 详析现况 / 现在吃到 `chain_plain` | `render_wyckoff_detail` 的「现在」行使用同一失败态链短句，避免详析仍出现「威：SC，还差AR」 |
| C-F8 | 不改检测阈值 / phase 判定 | diff 审查：不得改 `wyckoff_events.py` 检测阈值；不得为通过 copy 测而修改 `phase_a_status` 来源 |
| C-F9 | 文档同步完成 | 本 handoff 已落；`wyckoff-skill-deep-card-handoff.md` 增补裁决或指向本文；`wyckoff-structure-anchor-handoff.md` S-A5 增文案收口指针或短勘误；`output-template.md` 如含链/故事链示例则同步 |
| C-F10 | 相关 pytest 绿 | 至少跑 `test_wyckoff_skill_render.py`；若复用结构 fixture，再跑 `test_wyckoff_tr_maturity.py` 或 `test_wyckoff_structure_anchor.py` |

---

## 5. 必须同步的文档清单

1. `docs/plans/wyckoff-failed-chain-copy-handoff.md`
   - 本 handoff，作为失败态链 copy 的 SSOT。
2. `docs/plans/wyckoff-skill-deep-card-handoff.md`
   - 在故事链裁决处增补：failed 时「若变好」不得写下一灯推进；可直接链到本文 §2.3。
3. `docs/plans/wyckoff-structure-anchor-handoff.md`
   - 在 S-A5 或 §3.2 文案合同处增一行指针：failed→L0 时链文案也必须收口到本文，不得保留「还差下一灯」。
4. `01-功能包-packages/wyckoff/references/output-template.md`
   - 若短卡链示例或详析故事链示例覆盖失败态，示例须使用 `威：SC（Phase A 失效）` 或本文同款规则（用词见 phase-fail-copy）。
5. 测例位置
   - 主测：`02-共享模块-shared/tests/test_wyckoff_skill_render.py`。
   - 可复用结构失败 fixture：`02-共享模块-shared/tests/test_wyckoff_tr_maturity.py` 或 `02-共享模块-shared/tests/test_wyckoff_structure_anchor.py`。

---

## 6. 双 Agent 写 / 查职责

### 6.1 写 Agent

1. 只读本文 + `wyckoff-structure-anchor-handoff.md` S-A5 + `wyckoff-skill-deep-card-handoff.md` 故事链合同。
2. 只改 §3.1 白名单文件，实现 C-F1…C-F10。
3. 不改检测阈值、不灭灯、不改 fusion / 出手 / 池分道。
4. 提交时列出失败态 copy 前后示例与 pytest 结果。

### 6.2 查 Agent

1. 对照本文 §2 / §4 逐项验收，优先抓三类问题：
   - failed 仍出现「还差」或「链可推进」。
   - 为了 copy 收口误改灯或检测阈值。
   - 短卡与详析不一致。
2. 查 diff 是否触碰勿改文件；若触碰，要求写 Agent 给出法源授权，否则退回。
3. 跑 C-F10 指定 pytest；失败则列明对应 C-F ID。

父 Agent：查 Agent PASS 后再进入 PR / 合并流程。
