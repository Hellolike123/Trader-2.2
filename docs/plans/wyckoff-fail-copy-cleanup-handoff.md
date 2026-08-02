# 威科夫失效文案残留清扫 + 选股器快路径 — Agent Handoff

> 状态：规格冻结（用户 2026-08-02：额度收尾；双 Agent；**一定不要出 bug**）  
> 法源对齐：`docs/plans/wyckoff-phase-fail-copy-handoff.md`（P-C*）；`docs/plans/wyckoff-detail-slim-b-handoff.md` S-B25（禁幕类隐喻）；`01-功能包-packages/trader/references/pool-commands.md`（选股池命令）  
> 实现锚点：`wyckoff_render.py`；`wyckoff`/`trader` `agent-quickstart.md`；测例  
> 产品裁决：**只清展示残留 + 文档快路径**；不改判定、不改报告四区、不造日线假雏形。

---

## 1. 做

### 1.1 残留文案清扫（render 层）

在 `wyckoff_render.py` 中，凡仍可能拼进面板或 helper 返回值的失败/幕类旧词，对齐 phase-fail-copy：

| 禁止（面板/helper 产出） | 改用 |
|--------------------------|------|
| `待新寻底`（作主语义） | `须重新寻底` |
| `雏形作废` / `结构作废` / `旧链保持作废` / `旧故事作废` | `雏形不成立` / `结构不成立` / `Phase A 失效` |
| `旧Phase A已破` | `Phase A 失效` |
| `换幕` / `当前幕` / `上一幕` / `吸筹幕`（默认 B 及相关 helper） | 直述：`破后强势` / `Phase A 失效` / `旧SC（仅对照）`（S-B25） |

说明：

1. 默认 B 生产路径已基本合规；重点清 **未走主路径但仍存活的 helper**（如 `_slim_structure_sentence` / `_slim_chain_token` / `_slim_story_lines` / `_format_slim_lights` / `_slim_prev_act_lines`），避免日后误接回主路径漏词。  
2. 优先**改词**；若确认某函数全仓零引用，允许删除，但须 grep 证明且不扩大 diff。  
3. **禁止**改 `wyckoff_core` / `wyckoff_events` 内部 `fail_reason` 存储串（面板已有 `_panel_fail_copy` 映射）。

### 1.2 回归测（防回退）

在 `test_wyckoff_skill_render.py` 增加（或扩展）测例：

- 对 failed / failed+SOS fixture，分别跑 `render_wyckoff_slim` / `render_wyckoff_detail` / `render_wyckoff_card`  
- 断言面板**不得**含：`旧底已废`、`废锚`、`Phase A failed`、`（已废）`、`待新寻底`、`Phase A 已失效`、`Phase A 失败`、`旧故事作废`、`换幕`、`当前幕`、`上一幕`、`吸筹幕`  
- 默认 B failed 仍须含：`Phase A 失效｜须重新寻底`

### 1.3 选股器快路径文档（只文档）

在下列文件各加一小节「当选股器用」命令表（不改池逻辑）：

1. `01-功能包-packages/wyckoff/references/agent-quickstart.md`  
2. `01-功能包-packages/trader/references/agent-quickstart.md`  

推荐流程（cwd 说明保留仓库根/包内两种写法之一，与现文件一致）：

```text
验票（结构）→ wyckoff --target
入池 → final_pool.py add --target
刷新 → final_pool.py refresh
排序 → final_pool.py rank  与/或  wyckoff rank
明日盯 → final_pool.py plan
```

写明：wyckoff 入池行为软建议；出手/分道仍听 trader。

---

## 2. 不做

1. 不实现报告四区重组（价格状态/理论/关键价/出手）。  
2. 不改 SC/AR/ST 检测、failed→L0 判定、L0–L3 量度门禁语义。  
3. 不给日线 L0 造假雏形/分位箱。  
4. 不改 fusion / decision_view / 池分道 / trader 出手。  
5. 不改 `--full`/`--brief` 骨架（仅人话残留）。  

---

## 3. 验收 C-L*

| ID | 必须 | 测 |
|----|------|-----|
| C-L1 | failed 三档面板无 §1.1 禁用词表 | pytest |
| C-L2 | 默认 B failed 仍为 `Phase A 失效｜须重新寻底` | pytest |
| C-L3 | helper/死路径若保留，产出不含幕类词与「待新寻底/作废」主语义 | grep + 测或单测 helper |
| C-L4 | wyckoff + trader agent-quickstart 含选股器命令流 | 文件断言或人工 |
| C-L5 | diff 不碰 core 判定 / fusion / 池分道 / short_midline 四区 | diff |
| C-L6 | `test_wyckoff_skill_render.py` + `test_pool_wyckoff_rank.py` 绿 | pytest |
| C-L7 | 门禁或至少上述 pytest 绿；南网实跑默认 B 关键可读 | 实跑 |

---

## 4. 可改 / 勿改

### 4.1 可改

1. `02-共享模块-shared/trader_shared/wyckoff_render.py`  
2. `02-共享模块-shared/tests/test_wyckoff_skill_render.py`  
3. `01-功能包-packages/wyckoff/references/agent-quickstart.md`  
4. `01-功能包-packages/trader/references/agent-quickstart.md`  
5. 本文；必要时 `wyckoff-phase-fail-copy-handoff.md` 加一句「残留清扫见本文」

### 4.2 勿改

1. `wyckoff_core.py` / `wyckoff_events.py` / `wyckoff_phase.py` 判定  
2. `short_midline.py` 与报告四区  
3. fusion / decision_view / classify / pool_cmds 业务逻辑  
4. Skill shim 复制引擎  

---

## 5. 双 Agent

| 角色 | 职责 |
|------|------|
| **写 Agent** | 只读本文 + phase-fail-copy → 小步改白名单 → 测 C-L* → commit/push |
| **查 Agent** | 对照本文逐项；抓禁用词回潮、误改判定、测红；**默认不改码** |

父 Agent：查完有 ❌ 再修；修完更新 PR。优先稳，不扩 scope。
