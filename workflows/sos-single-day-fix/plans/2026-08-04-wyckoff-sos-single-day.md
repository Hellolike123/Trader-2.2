# Plan — Wyckoff SOS 单日爆发型分支

| 项 | 值 |
|----|-----|
| status | **pending_human_approval** |
| date | 2026-08-04（对齐 WorkBuddy 交接日；实现日以 commit 为准） |
| tier | Medium（SOP §1.1） |
| task-dir | `workflows/sos-single-day-fix/` |
| 外部交接 | `/Users/like/Documents/Workbuddy/Docs/wyckoff-sos-修复交接说明.md` |
| 仓内法源（实现前落） | `docs/plans/wyckoff-sos-single-day-handoff.md`（Phase 0） |
| 产品/原典 | `docs/audit/wyckoff-original-concept-inventory.md` §三 SOS；AGENTS.md 威科夫改码表 |

---

## 1. Objective

在**不破坏**现有「连续爬坡型 SOS（≥4/5 阳）」的前提下，为 `_detect_sos` 增加 **OR** 分支：识别「单日放量大阳 + 收盘站上 TR 上沿」的 **单日爆发型 SOS**，修复南网科技类漏判，并让 BU / 事件簇 / JAC 背景链路可自然衔接。

### Out of scope（禁止）

- 改 fusion / `decision_view` / 出手 / 池分道 / major_stage
- 改 JAC 自身公式（仅期望 SOS 亮后 JAC 背景门打开）
- 软确认 ST、抬 tr_maturity、改 P&F
- 在 skill 解压目录或 `01-功能包-packages/*/scripts/` 正文复制引擎
- 无 TR 时用「大阳+放量」宽松兜底当默认（易与 UT/游资一字混淆）—— **v1 不做无 TR 兜底**
- 把 SOS 变成开仓指令叙事

---

## 2. Current-state evidence

| 事实 | 证据 |
|------|------|
| SOS 仅连续窗 | `wyckoff_events._detect_sos`：≥4/5 阳否则 early return |
| TR 上沿未参与 SOS | 同函数只用 `tr_ctx["tr_baseline_volume"]` |
| 主路径调用 | `wyckoff_core`：`sos = _detect_sos(bars, tr_ctx=event_tr_ctx)` |
| 簇扫描 | `_scan_last_event(scan, _detect_sos, tr_ctx, window=15)` |
| BU 回扫 | `_detect_backup` 近 12 根调 `_detect_sos(sub, tr_ctx=)` |
| JAC 依赖 SOS 背景 | `_detect_jump_across_creek`：`near_ctx = sos\|bu\|markup` |
| 测例缺口 | `tests/test_wyckoff_core.py` import 了 `_detect_sos`，无单日爆发边界矩阵 |
| 交接路径错误 | WorkBuddy 文写改 packages 内 trader_shared；本仓真相在 `02-共享模块-shared/trader_shared/` |

根因定性：**覆盖缺口**（实现把 SOS 窄化为 multi-bar thrust），非行情缺 bar。

---

## 3. Design

### 3.1 选用方案

**A（采用）— 双形态 OR**

1. **Climb（既有）**：保持现逻辑与阈值不动。  
2. **Thrust / 单日爆发（新增）**：仅当 climb **未**命中时评估（或 climb 失败 early-return 前先不 return，改为走完 climb 再试 thrust——实现上推荐：

```text
climb = _try_sos_climb(...)
if climb["sos_signal"]:
    return climb
return _try_sos_thrust(..., tr_ctx)   # 新
```

**Thrust 合同（v1）— 全部 AND：**

| 条件 | 合同值 | 理由 |
|------|--------|------|
| `tr_ctx` 与 `tr_upper` 可用 | 必须 | 无上沿不做 thrust（防无箱乱亮） |
| 末日阳线 | `close > open` | 强势 K |
| 收盘站上 TR 上沿 | `close > tr_upper` | 原典离开 TR；防箱内大阳 |
| 单日涨幅（开→收） | `>= WYCKOFF_SOS_THRUST_MIN_GAIN` **默认 0.05** | 对齐交接 5%；可配置 |
| 量比 | `vol / baseline >= WYCKOFF_SOS_THRUST_VOL_RATIO` **默认 1.8** | baseline 优先 `tr_baseline_volume`，否则前窗均量 |
| 派发背景抑制 | 若 `bc_signal` 或 `upthrust_signal` 已在 **同一分析层** 为真且 thrust 仅靠末日大阳 | **v1 简化**：thrust **不**读其他检测器布尔（避免循环依赖）；改为：若 `tr_ctx` 显式带 `suppress_sos_thrust=True` 则否。主路径默认不设。UT 假突破由「须收盘站上且次日确认」不在 v1 做；靠 close>tr_upper + 高量阈降误报。派发区上冲回落形态由 UT 灯表达，不在本分支抢戏。 |

**输出字段（不增键，兼容）：**

```text
sos_signal: bool
sos_reason: str   # 含「单日爆发型」或既有「强势突破，n/5 阳…」
sos_price: float | None   # 末日 close
```

可选调试（**非必须**，若加须在 handoff 写明）：

```text
sos_kind: "climb" | "thrust" | None
```

**建议 v1 加 `sos_kind`**：簇/BU/报告零消费也可，便于测例与面板日后区分；若要最小 diff 可只写在 `sos_reason` 前缀。  
**计划裁定：v1 增加 `sos_kind`，分析层透传；渲染可不展示。**

### 3.2 拒绝的方案

| 方案 | 拒绝理由 |
|------|----------|
| B. 把 4/5 再降到 3/5 | 仍非「站上 TR」语义；箱内震荡阳线误报升 |
| C. 只改 JAC 不认 SOS | JAC 合同是跳溪专名灯且依赖 SOS 背景；会绕开积累确认/BU |
| D. 无 TR 涨幅+量比兜底（交接 4.1 宽松支） | v1 误报面过大；有 TR 才是 SOS 离开 TR 的原典锚 |
| E. 直接改 WorkBuddy skill 解压树 | 覆盖安装即丢；违反 AGENTS 引擎唯一真相 |

### 3.3 常量（`config.py`）

```python
WYCKOFF_SOS_THRUST_MIN_GAIN: float = 0.05      # 单日开收涨幅
WYCKOFF_SOS_THRUST_VOL_RATIO: float = 1.8      # vs baseline
# 不引入 ENABLE 开关 unless 需要紧急回滚；回滚 = git revert / 阈值调极高
```

`wyckoff_events` try-import 与 fallback 默认同步。

---

## 4. Affected surfaces

| 路径 | 动作 |
|------|------|
| `docs/plans/wyckoff-sos-single-day-handoff.md` | **新建**正式 handoff（Phase 0） |
| `02-共享模块-shared/trader_shared/config.py` | 增 thrust 常量 |
| `02-共享模块-shared/trader_shared/wyckoff_events.py` | `_detect_sos` 重构为 climb OR thrust；docstring |
| `02-共享模块-shared/tests/test_wyckoff_core.py` | 边界测例（先写后码） |
| `docs/audit/wyckoff-original-concept-inventory.md` | SOS 行补「climb+thrust」一句（Phase 收尾） |
| **禁止** | fusion_* / decision_* / pool / short_midline 主结构 / packages 引擎正文 |

BU/簇/core **无逻辑改动**（行为随 SOS 真值变化 → 回归测覆盖）。

---

## 5. Phases（测先于码）

### Phase 0 — 法源 handoff（sole-writer，文档）

- 将本 plan §3 合同写入 `docs/plans/wyckoff-sos-single-day-handoff.md`（字段、必须/禁止、验收表、可改白名单）。
- **STATUS gate**：文档存在且无 TBD。

### Phase 1 — 红灯测例（sole-writer，只加测）

在 `test_wyckoff_core.py` 增加 `TestDetectSosThrust`（构造 bars，**不**打外网）：

| 用例 | 期望 |
|------|------|
| `test_thrust_sos_breakout_above_tr` | 铺 TR 基线 + 阴线洗 + 末日 +6% 放量 2× 收上 `tr_upper` → `sos_signal` True，`sos_kind=="thrust"`，reason 含单日爆发 |
| `test_thrust_blocked_inside_tr` | 同大阳但 close ≤ tr_upper → False |
| `test_thrust_blocked_low_gain` | 4.9% → False；5.1% → True（边界） |
| `test_thrust_blocked_low_vol` | 量比 1.7 → False |
| `test_climb_sos_still_works` | 5 根 4 阳爬坡旧路径仍 True，`sos_kind=="climb"` |
| `test_thrust_requires_tr_upper` | tr_ctx 无 upper → 不走 thrust（climb 也不满足时 False） |
| `test_backup_can_anchor_thrust_sos` | 可选：thrust SOS 后 2 根缩量回踩 → `bu_signal`（集成轻量） |

先跑 pytest：**期望 RED**。

### Phase 2 — 实现（sole-writer）

- 落地常量 + `_detect_sos` OR 分支 + `sos_kind`。
- 保持 climb 文案兼容；thrust reason 可读。
- 再跑 Phase 1 测例 → GREEN。
- 全量相关：`pytest 02-共享模块-shared/tests/test_wyckoff_core.py -q`  
- 可选门禁：`scripts/run-gate-tests.sh`（若环境允许）。

### Phase 3 — 独立 review（reviewer，只读）

对照 handoff 逐条 ✅/❌：禁止项、阈值、调用点副作用、测例是否真断言语义。  
返回 SOP 合同：`VERDICT / BLOCKING / SUGGESTED / EVIDENCE`。

### Phase 4 — 修复（若 NEEDS_CHANGES）→ re-review

sole-writer only。

### Phase 5 — 验证与终报（orchestrator）

- 记录命令与输出到 `workflows/sos-single-day-fix/evidence/`
- 可选实票冒烟：`python3 01-功能包-packages/wyckoff/scripts/final_wyckoff.py --target 南网科技`（非门禁；外网/行情失败不挡合入若单测绿）
- 终报：变更、测、残留风险、回滚（`git revert`）

### 不自动执行

- commit / push / PR / 打包 skill / 覆盖 `~/.workbuddy` — **另要人批**

---

## 6. Checks

| 类 | 内容 |
|----|------|
| 功能 | thrust/climb 矩阵；箱内不亮；无 TR 不 thrust |
| 集成 | BU 能锚 thrust；簇不因同 bar 乱序（既有 MIN_GAP） |
| 安全 | 无密钥；无网络写 |
| 回滚 | revert 单 commit；或把 `MIN_GAIN` 调到 0.99 应急（次选） |
| 并发 | 无共享可变全局 |

---

## 7. Signoff criteria

- [ ] handoff 已合入 docs/plans 且与实现一致  
- [ ] Phase 1 全绿 + test_wyckoff_core 无回归  
- [ ] reviewer VERDICT=PASS（或人书面接受 SUGGESTED-only）  
- [ ] 未改 fusion/出手/池  
- [ ] 人确认是否 commit/PR  

---

## 8. Human decisions required **now**

1. **批准本 plan？**（`plan approved` / `plan changes: ...`）  
2. **批准 roster？**（见 `01-roster-proposal.md`）  
3. **v1 是否同意：无 TR 不做 thrust 兜底？**（计划默认同意）  
4. **是否要 `sos_kind` 字段？**（计划默认要）  
5. **实现后是否开 PR？**（默认：验证绿后再问）

---

## 9. Rollback

1. `git revert <impl-sha>`  
2. 确认 `_detect_sos` 回到仅 climb；测例删除或 skip  
3. 无数据迁移  

---

**Orchestrator 状态：已写 plan，等待人类明确批准。未开始 Phase 0+ 代码/handoff 落库以外的业务实现。**  
（若你回复 `plan approved` + `roster ok`，sole-writer 从 Phase 0 起执行。）
