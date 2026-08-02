# 威科夫 Phase 失效文案统一 — Agent Handoff

> **状态**: impl_done（现行展示合同；Phase 失效人话 SSOT 已合入）  
> 法源对齐：`docs/plans/wyckoff-detail-slim-b-handoff.md`（B 卡骨架）；`docs/plans/done/wyckoff-failed-chain-copy-handoff.md`（失败态禁健康推进）；`docs/plans/wyckoff-structure-anchor-handoff.md` §3（failed → L0）  
> 实现锚点：`wyckoff_render.py`（`render_wyckoff_slim` / `render_wyckoff_detail` / `render_wyckoff_card` / `_story_block`）；链短句 `wyckoff_chain.format_wyckoff_chain_plain`（仅展示词）  
> 产品裁决：只改**人话展示**；不改 Phase A failed 判定、L0–L3、fusion、出手、池分道。  
> 续篇（已合入）：报告光杆 `format_wyckoff_*_light` failed 见 `done/wyckoff-report-fail-copy-leak-handoff.md`（R-F*）。

---

## 1. 产品裁决

### 1.1 做

1. 默认 B 卡日线失败态统一句式：  
   - 无新强势：`Phase A 失效｜须重新寻底`  
   - 有 SOS：`Phase A 失效 · 破后强势｜本波 SOS 强`  
   - 有 LPS 无 SOS：`Phase A 失效｜本波 LPS 修复`
2. 日线本波主句可附旧 SC 对照价：`｜旧SC {价}（仅对照）`；**禁止**「废锚 / 已废 / 作废」。
3. 有效阶段**不写「有效」**；阶段名与中文释义用中间点：  
   - `Phase A · 止跌开场`  
   - `Phase B · 建因横盘`  
   - `Phase C · 试盘`  
   （D/E 本迭代可不强改，有现成 phase 展示则尽量同构：`Phase D · 强度确认` / `Phase E · 离开区间`）
4. 推演「现在」日线句与总览/本波主句同语义（失效｜须重新寻底 或 失效 · 破后强势｜本波 SOS 强）。
5. 「若变坏」周线少用「作废」→ 可用 `雏形不成立` / `结构不成立`。
6. **`--full` / `--brief` 人话与默认 B 同源**（骨架可不同，失败语义同句式）：  
   - 禁面板可见：`Phase A 失败`、`Phase A 已失效`、`旧故事作废`、`待新寻底`（作主句）、`废锚` / `（已废）`  
   - `--full` 故事链「若变好」failed：`Phase A 失效｜须重新寻底`（可续「出现新 SC」）；链短句 `威：SC（Phase A 失效）`（去掉「已」）  
   - `--brief`：阶段/链/事件/一句 中 failed 可见面改写为「失效」语义；可用 render 层映射，**不必**改 core 内部 `fail_reason` 字段存储  
7. 同步文档：本文、slim-b 对照样、`output-template.md`（含 `--full`/`--brief` 示例）、`agent-quickstart.md`、相关 pytest。

### 1.2 不做

1. 不改 `phase_a_status=failed` / `tr_maturity=L0` 判定。  
2. 不改检测阈值、fusion、decision_view、池分道。  
3. 不恢复健康「还差 AR / 链可推进」。  
4. 不发明 B/C「失效」引擎态（文案合同可先写；无判定则不硬编失败）。  
5. 不把 `--full`/`--brief` 骨架改成默认 B 卡（只对齐失败人话）。  
6. 不改 `wyckoff_core` / `wyckoff_events` 内部调试字段原文（除非该字符串直接进面板且无法在 render 映射）。

---

## 2. 对照样（默认 B 卡）

### 2.1 A 失效 · 无新强势（南网类 · 用户锁定样例）

```text
南网科技（688248）｜现价 41.90
周线：偏多｜SC后反弹，雏形 37.80～43.85（待 ST）｜慎做
日线本波：Phase A 失效｜须重新寻底
入池：暂不建议入池（早期结构，尚无 ST/LPS）

🧭 周线 · 大阶段
  SC后反弹偏多，雏形 37.80～43.85（待 ST）｜未达 L3
  灯
  ● SC（卖力高潮）37.80
  ● AR（自动反弹）41.52
  ○ ST（二次测试）
  ○ LPS（最后支撑点）
  ○ SOS（强势信号）

⚡ 日线 · 本波
  Phase A 失效｜须重新寻底｜旧SC 41.02（仅对照）
  灯
  ● SC（卖力高潮）41.02
  ○ AR（自动反弹）
  ○ ST（二次测试）
  ○ LPS（最后支撑点）
  ○ SOS（强势信号）

🔮 推演
  现在
    周线：SC→AR，待 ST（二次测试）
    日线：Phase A 失效｜须重新寻底
    周线量度：未达 L3，暂不测算
    日线量度：未达 L3，暂不测算
```

### 2.2 A 失效 · 破后强势（SOS）

```text
日线本波：Phase A 失效 · 破后强势｜本波 SOS 强

⚡ 日线 · 本波
  Phase A 失效 · 破后强势｜本波 SOS 强｜旧SC {价}（仅对照）
  说明：●SC 是旧底事实，●SOS 是本波强势事实；不按 SC→SOS 顺序推进读。
```

### 2.3 有效阶段（不写「有效」）

```text
日线本波：Phase B · 建因横盘｜箱内吸筹中
日线本波：Phase C · 试盘｜试盘观察中
```

若引擎 phase 不足以区分 B/C，保持既有短句，**不得**假写 Phase B/C；有明确 phase/phase_label 时再套用。

---

## 3. 禁用词（默认 B 卡失败态）

| 禁止 | 改用 |
|------|------|
| `旧底已废` | `Phase A 失效` |
| `Phase A failed`（英文 failed） | `Phase A 失效` |
| `废锚参考` / `（已废）` | `旧SC {价}（仅对照）` |
| `待新寻底`（总览主句） | `须重新寻底` |
| `作废`（若变坏周线） | `雏形不成立` / `结构不成立` |

说明行「不按顺序推进读」保留。

---

## 4. 验收表 P-C*

| ID | 必须 | 测 |
|----|------|-----|
| P-C1 | failed 无强势：总览含 `Phase A 失效｜须重新寻底` | pytest fixture |
| P-C2 | failed 本波主句含 `旧SC` + `仅对照`；无废锚/已废/failed 英文 | pytest |
| P-C3 | failed+SOS：`Phase A 失效 · 破后强势｜本波 SOS 强`；说明行仍在 | pytest |
| P-C4 | failed+LPS：`Phase A 失效｜本波 LPS 修复` | pytest |
| P-C5 | 默认 B 失败路径无：`旧底已废` / `废锚` / `Phase A failed` / `（已废）` | pytest |
| P-C6 | 推演现在日线与总览同语义 | pytest |
| P-C7 | 文档对照样与 output-template 已同步 | 文件审查 |
| P-C8 | 勿改 failed 判定 / fusion / 出手 / 池分道 | diff 审查 |
| P-C9 | `test_wyckoff_skill_render.py` 绿 | pytest |
| P-C10 | `--full` failed fixture：故事链/综述可见面无 `Phase A 失败` / `Phase A 已失效` / `旧故事作废`；含 `Phase A 失效` 与重新寻底语义 | pytest `render_wyckoff_detail` |
| P-C11 | `--brief` failed fixture：阶段/链/事件/一句 无 `Phase A 失败`（作主展示）；链为 `Phase A 失效` 语义 | pytest `render_wyckoff_card` |
| P-C12 | `format_wyckoff_chain_plain` failed：`威：…（Phase A 失效）`（无「已失效」） | pytest |

### 2.4 `--full` / `--brief` 失败样（骨架保持，人话对齐）

`--full` 故事链片段：

```text
现在
威：SC（Phase A 失效）｜日线偏空｜周线背景偏多

若变好
Phase A 失效｜须重新寻底；观察是否出现新的 SC（卖力高潮）
```

`--brief` 片段：

```text
🧭 阶段：…（Phase A 失效…）｜偏向 …
📎 链：威：SC（Phase A 失效）
```

（阶段行若来自引擎 `phase_label` 含「失败」，render 层须映射为「失效」再上屏。）

---

## 5. 可改 / 勿改

### 5.1 可改

1. `02-共享模块-shared/trader_shared/wyckoff_render.py`（slim / detail / card / `_story_block`）  
2. `02-共享模块-shared/trader_shared/wyckoff_chain.py`（仅 `format_wyckoff_chain_plain` 等**展示短句**）  
3. `02-共享模块-shared/tests/test_wyckoff_skill_render.py`（及必要 chain 测）  
4. `docs/plans/wyckoff-phase-fail-copy-handoff.md`（本文）  
5. `docs/plans/wyckoff-detail-slim-b-handoff.md` / `wyckoff-skill-deep-card-handoff.md`（`--full` 文案交叉）  
6. `01-功能包-packages/wyckoff/references/output-template.md`  
7. `01-功能包-packages/wyckoff/references/agent-quickstart.md`  
8. 必要时 `docs/plans/done/wyckoff-failed-chain-copy-handoff.md` 交叉引用一句（勿改判定）

### 5.2 勿改

1. `wyckoff_core.py` / `wyckoff_events.py` 检测阈值与 failed 判定逻辑  
2. fusion / decision_view / 池分道 / trader 出手  
3. Skill shim 正文复制引擎  
4. 默认 B 卡骨架（已落地，勿回退）

---

## 6. 双 Agent

| 角色 | 职责 |
|------|------|
| **写 Agent** | 只读本文 + slim-b / failed-chain-copy / deep-card → 改白名单 → 测 P-C1…P-C12 → 同步文档 |
| **查 Agent** | 对照本文 §1–§4；重点抓 `--full`/`--brief` 残留「失败/已失效」；默认不改码 |

父 Agent：查完修完再更新 PR #36（同分支续作）或开新 PR。
