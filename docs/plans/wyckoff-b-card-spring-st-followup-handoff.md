# 威科夫 B 卡 Spring/ST + 周线 failed 展示 — 续作 Handoff

> **状态**: ready_for_pr（2026-08-03；写/查双 Agent 审计后已落地 2 code commit + 文档同步；交付时 push/开 PR）  
> **分支**: `fix/wyckoff-b-card-spring-st`（基于 `main` @ `9db225b` 一带；缠论已另分支，勿混）  
> **法源**: `wyckoff-phase-a-range-handoff.md` §4.4.2（Spring Test ≠ 广义 ST）；`wyckoff-detail-slim-b-handoff.md` §4.4（灯释义）；`wyckoff-tr-maturity-l0l3-handoff.md` §0（字段分离）；`wyckoff-phase-fail-copy-handoff.md`（失效人话）；`wyckoff-structure-anchor-handoff.md` §3（failed→L0）  
> **审计依据**: 池内 9 票实盘 + [挖 Agent](f957f4db-4cbe-4826-bd2c-cc38de0560b5) / [查 Agent](063b4afb-b966-432c-9827-da6a2ccb6249) 双 Agent 闭环（2026-08-03）

---

## 0. 给接手 Agent 的一句话

**成熟度/L0–L3/假箱假量度合同已锁**；本轮只修 **B 卡展示语义**。分支上已有 2 commit，测绿；你主要做 **PR 验收、文档同步、可选 P2、勿动引擎**。

---

## 1. 已合入（本分支 2 commit）

| Commit | 内容 | 测 |
|--------|------|-----|
| `7453c16` | **P0-1**：B 卡 `ST（二次测试）` 只认 `secondary_test_sc_signal`；`spring_test`/`st_*` 另灯 `Spring（弹簧确认）`；同步 `_accum_lit_set` / `_SLIM_SIGNAL_KEYS` / 推演「Spring 确认｜待 SC」 | `test_p0_spring_confirm_not_labeled_as_st_secondary_test` + W-DIFF-7 / ST无AR→L1 边界测 |
| `fddf38f` | **P1-2 展示**：周线 `phase_a=failed` 且无真实派发灯时，总览/大阶段/推演写 `Phase A 失效｜须重新寻底`，禁止空「派发未确认」盖住；有 ARE 等派发灯仍走派发侧 | `test_p1_weekly_failed_not_blank_distribution` |

**本地验证（接手必跑）**：

```bash
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_wyckoff_skill_render.py \
  02-共享模块-shared/tests/test_wyckoff_structure_anchor.py \
  02-共享模块-shared/tests/test_wyckoff_tr_maturity.py -q
# 期望：81 passed（2026-08-03 绿）
```

**实盘 smoke（禾望 603063）**：

```bash
python3 01-功能包-packages/wyckoff/scripts/final_wyckoff.py --target 603063
# 期望：○ ST（二次测试）；● Spring（弹簧确认）；日线本波「Spring 确认」；推演「Spring（弹簧确认），待 SC（卖力高潮）」
```

---

## 2. 双 Agent 审计结论（勿重开算法）

### 2.1 合同级 ✅（九票池）

- 无假箱体 / 无 L3 以下假量度 / 破位→L0 / 南网 688248 对照样合规  
- S-A*/S-P*/M-R* 查 Agent 全 ✅（见当轮查 Agent 报告）

### 2.2 已修 ❌

| ID | 问题 | 状态 |
|----|------|------|
| P0-1 | Spring 确认误标「ST（二次测试）」（禾望 603063） | **已修** commit `7453c16` |
| P1-2 | 周线 failed+bear 空灯 →「派发未确认」盖住失效（赣锋/天齐/恩捷类） | **已修** commit `fddf38f` |

### 2.3 仍 ⚠️（可选后续；**禁止**当 P0 放宽门禁）

| ID | 问题 | 建议 |
|----|------|------|
| P2-1 | BC 面板中文「购买高潮」vs slim-b 样例「买力高潮」 | 仅文案统一；改 `wyckoff_render._EVENT_CN` 或 slim-b 对照样二选一 |
| P2-2 | 标题偶发 `603063（603063）` 名=码 | 数据/取名层；非 wyckoff_render 主责 |
| P2-3 | L0 时 `cause_effect.note` 仍可有 P&F 算式（面板不贴量度） | 可选净化 note；勿改 L3 门禁 |
| P1-3 | 事件检测仍用局部窗极值（Spring/SOW/UT 等） | **inventory 已声明取舍**；箱体/量度路径已 L0–L3 收口；另开 handoff 才动检测 |
| P1-4 | `wyckoff_chain` ST 槽=「Spring确认」 vs B 卡 ST=「二次测试」 | **有意分离**；B 卡已另灯 Spring；链槽勿改除非 phase-a §4.4.2 修订 |
| — | 文案别名 Ice/跳溪/破冰（孟洪涛映射） | 用户 **明确不做** C 线；勿提交 `docs/audit/wyckoff-meng-alias-map.md` 除非单开文档 PR |

---

## 3. 接手 Agent 待办（按优先级）

### 必做（交付）

1. **查 Agent 复验**（只读）：对照本文 §1 + 法源，重跑 §1 命令；池内抽 3 票（603063 / 688248 / 002460）跑 `final_wyckoff.py`，列 ✅/❌。  
2. **开 PR**（若用户要求 push）：  
   - 标题示例：`fix(wyckoff): B 卡 Spring/ST 分离 + 周线 failed 失效文案`  
   - PR 必填：法源链接（本文 + phase-a §4.4.2 + fail-copy）；对照清单；pytest 结果；双 Agent 或等价自检表  
   - **勿**把缠论改动、`docs/audit/wyckoff-meng-alias-map.md` 混进同一 PR  
3. **文档同步（小改）**：  
   - `wyckoff-detail-slim-b-handoff.md` §2.4 / §4.4：注明日线五灯 ST=广义 ST；Spring 确认可 **额外一行** `● Spring（弹簧确认）`（详析/B 卡一致）  
   - `wyckoff-phase-fail-copy-handoff.md`：补一句「周线 failed 无派发灯时总览须写 Phase A 失效（2026-08-03 已落地）」  
   - 若 golden / `output-template.md` 有 Spring/ST 样例行，刷新（仅当 CI 或门禁红）

### 可选（有余力）

4. **P2-1** BC「购买→买力」用词统一（1 行 `_EVENT_CN` + 1 测）。  
5. **周线 failed + 真实派发灯**（如 failed+ARE 无 BC）：确认 `_slim_weekly_sentence` 已写 `Phase A 失效…｜派发侧另察`；补 1 fixture 测。  
6. **`--full` / trader 光杆** failed 泄漏扫描：`grep -r "Phase A failed\|废锚" 02-共享模块-shared/trader_shared/` + `test_wyckoff_skill_render.py` 已有 P-C* 回归。

### 明确不做

- 改 `wyckoff_events` / `wyckoff_phase` 检测阈值、ST 公式、W-DIFF-7 裁决  
- 改 fusion / decision_view / 池分道 / `tr_maturity` 门禁  
- 凭 wyckoffnotes.com 等实盘站改 A 股检测  
- 把 stash `stash@{1}: chanlun-wip-temp` 内容合进本 PR（已过期，缠论已另提交）

---

## 4. 可改白名单

| 文件 | 可改 |
|------|------|
| `02-共享模块-shared/trader_shared/wyckoff_render.py` | ✅ 展示/灯/推演/快照 `build_light_snapshot_entry` |
| `02-共享模块-shared/tests/test_wyckoff_skill_render.py` | ✅ 渲染合同测 |
| `02-共享模块-shared/tests/test_wyckoff_structure_anchor.py` | ✅ 仅边界测（勿改检测） |
| `02-共享模块-shared/tests/test_wyckoff_tr_maturity.py` | ✅ 同上 |
| `docs/plans/wyckoff-detail-slim-b-handoff.md` | ✅ 同步灯说明 |
| `docs/plans/wyckoff-phase-fail-copy-handoff.md` | ✅ 补周线 failed 一句 |
| `01-功能包-packages/wyckoff/references/output-template.md` | ⚠️ 仅骨架/样例变时 |

| 文件 | 勿改 |
|------|------|
| `wyckoff_core.py` / `wyckoff_events.py` / `wyckoff_phase.py` | ❌ 除非新 handoff 授权 |
| `fusion_core.py` / `pool_cmds/classify.py` / `decision_*` | ❌ |
| `wyckoff_chain.py` 链 ST 槽语义 | ❌ 除非 phase-a 修订 |

---

## 5. 验收表（接手 PR 对照）

| ID | 必须 | 验法 |
|----|------|------|
| F-1 | 仅 `spring_test` 无 `secondary_test_sc` → 面板 **无** `● ST（二次测试）`，**有** `● Spring（弹簧确认）` | 603063 实盘或 `test_p0_*` |
| F-2 | `secondary_test_sc` → `● ST（二次测试）`；链槽仍不进广义 ST（`extract_accum_events` 无 ST） | `test_wd5_secondary_test_sc_*` |
| F-3 | 周线 failed、无 BC/ARE/SOW… → 总览含 `Phase A 失效｜须重新寻底`，**无**单独「派发未确认」 | `test_p1_*` + 002460 实盘 |
| F-4 | 周线 ARE 无 BC → 仍「派发未确认」，**不**接吸筹 SC | `test_sb19_*` |
| F-5 | L0–L3 / 量度 / 破位 → L0 回归不红 | §1 pytest 81 passed |
| F-6 | 无 fusion/出手/池分道 diff | `git diff main --stat` 仅白名单 |

---

## 6. Git 操作备忘

```bash
git checkout fix/wyckoff-b-card-spring-st
git log main..HEAD --oneline   # 应见 7453c16、fddf38f 两笔
# 用户要求 push 时：
git push -u origin fix/wyckoff-b-card-spring-st
gh pr create --base main --title "..." --body "..."
```

**未跟踪、勿默认 add**：`docs/audit/wyckoff-meng-alias-map.md`（映射表草稿，非本 PR 范围）。

---

## 7. 背景：旧审计 `wyckoff-review.md`（2026-07-15）

下列 **已修或已收口**，接手勿当 open P0 重开：

- LPSY 无派发背景互抵 → `_resolve_score_conflicts` + 门控  
- SC 窗=15 唯一宇宙 → structure-anchor 冷启动 90/39 + 钉住  
- 南网 SC+AR 假箱体+量度 → L0–L3  
- SCORE_MAX → 140  

**仍在（P1 原典差距，非本 PR）**：局部窗极值 vs TR 边界；Spring support lookback 松耦合。见 `docs/audit/wyckoff-original-concept-inventory.md` §五 ⚠️。

---

## 8. 写/查 Agent 口令（可复制）

**写 Agent**：

> 读 `docs/plans/wyckoff-b-card-spring-st-followup-handoff.md`；在分支 `fix/wyckoff-b-card-spring-st` 完成 §3 必做；禁止改 fusion/出手/检测；跑 §1 pytest；查 Agent 对照 §5 验收表。

**查 Agent**：

> 只读验收 `docs/plans/wyckoff-b-card-spring-st-followup-handoff.md` §5；重跑 §1 命令 + 603063/688248/002460 三票；列 ❌/⚠️；默认不改码。
