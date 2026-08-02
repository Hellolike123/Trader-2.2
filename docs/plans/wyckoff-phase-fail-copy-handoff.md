# 威科夫 Phase 失效文案统一 — Agent Handoff

> 状态：实现中（写 Agent 按本文落地；查 Agent 对照 §1–§4）  
> 法源对齐：`docs/plans/wyckoff-detail-slim-b-handoff.md`（B 卡骨架）；`docs/plans/wyckoff-failed-chain-copy-handoff.md`（失败态禁健康推进）；`docs/plans/wyckoff-structure-anchor-handoff.md` §3（failed → L0）  
> 实现锚点：`02-共享模块-shared/trader_shared/wyckoff_render.py`（`render_wyckoff_slim` 及 `_slim_daily_*`）  
> 产品裁决：只改**人话展示**；不改 Phase A failed 判定、L0–L3、fusion、出手、池分道。

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
6. 同步文档：本文、`wyckoff-detail-slim-b-handoff.md` 对照样、`output-template.md`、`agent-quickstart.md`（若提及旧底已废）、相关 pytest。

### 1.2 不做

1. 不改 `phase_a_status=failed` / `tr_maturity=L0` 判定。  
2. 不改检测阈值、fusion、decision_view、池分道。  
3. 不恢复健康「还差 AR / 链可推进」。  
4. 不发明 B/C「失效」引擎态（文案合同可先写；无判定则不硬编失败）。  
5. 不改 `--full` 详析骨架（若详析仍有旧词，本迭代以默认 B 卡为准；详析可顺手替换同义词但非必须）。

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

---

## 5. 可改 / 勿改

### 5.1 可改

1. `02-共享模块-shared/trader_shared/wyckoff_render.py`  
2. `02-共享模块-shared/tests/test_wyckoff_skill_render.py`  
3. `docs/plans/wyckoff-phase-fail-copy-handoff.md`（本文）  
4. `docs/plans/wyckoff-detail-slim-b-handoff.md`（对照样与 S-B9/S-B18 文案同步）  
5. `01-功能包-packages/wyckoff/references/output-template.md`  
6. `01-功能包-packages/wyckoff/references/agent-quickstart.md`（若含旧词）  
7. 必要时 `docs/plans/wyckoff-failed-chain-copy-handoff.md` 交叉引用一句（勿改判定）

### 5.2 勿改

1. `wyckoff_core.py` / 事件检测阈值  
2. fusion / decision_view / 池分道 / trader 出手  
3. Skill shim 正文复制引擎  

---

## 6. 双 Agent

| 角色 | 职责 |
|------|------|
| **写 Agent** | 只读本文 + slim-b / failed-chain-copy → 改白名单 → 测 P-C* → 同步文档 |
| **查 Agent** | 对照本文 §1–§4 逐项 ✅/❌；抓残留「已废/废锚/failed」；默认不改码 |

父 Agent：查完修完再开/更新 PR。
