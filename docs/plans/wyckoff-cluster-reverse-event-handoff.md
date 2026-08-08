# 威科夫簇确认后近端反向事件 — Agent Handoff

> **status**: impl_in_progress（2026-08-08）
> **日期**: 2026-08-08
> **承接**: `wyckoff-ghost-st-stale-sos-bare-d-handoff.md`（G2 只防过期 SOS，未定义「簇成立后再出反向事件」）
> **范围**: 派发确认（UT→SOW）后近端再出 SOS 的叙事/打分/展示一致性；**不改** fusion / decision_view / major_stage / 池分道公式

---

## 0. 问题

南网科技 688248 周线实盘（2026-08-07 缓存，137 根，last=08-07）：

| 现象 | 现状 | 误伤 |
|------|------|------|
| `distribution_confirmed=True` 与 `sos_signal=True` 并存 | 派发灯与强势灯同亮，叙事打架 | `infer_daily_short_wave` 按命中数量把周线短波侧判成 `accumulation · SOS 偏多` |
| `calculate_wyckoff_score` 同段双计 | SOS +15 与 派发确认 -15 对冲成中性 | 派发确认的看空信号被近端 SOS 抵消 |
| 近端 SOS 不失效 | `_detect_event_cluster` 只校验 UT→SOW 先后，无「SOW 成立后近端再出 SOS」规则 | 既亮派发灯又亮强势灯；`distribution_failed` 因 `sos_idx > sow_idx` 不满足（或 scan 内 SOS 不 fresh）覆盖不了 |

一句话：派发簇确认后，近端强势突破**不推翻派发叙事**；方向仍偏空（decision_view 不新开），但内部不得既亮派发灯又亮强势灯、分数不得互相抵消。

---

## 1. 必须行为

### 1.1 簇检测：派发确认后近端 SOS 降级（不翻案）

`_detect_event_cluster` 新增可选参数 `near_sos`（主分析 overlay 后的最终 SOS dict，含 `sos_age`）：

1. **反向不翻案**：当 `distribution_confirmed=True` 且近端再出 SOS（scan 内 `sos_idx > sow_idx` 且 fresh，或 `near_sos` 带 `sos_age <= WYCKOFF_CLUSTER_EVENT_FRESH_BARS`）→ `distribution_failed` **强制 False**；禁止 UT→SOW→SOS 被当成「假派发实为吸筹」。
2. **降级不消失**：`distribution_confirmed` 保持 `True`（派发叙事保留），新增 `cluster_contested=True`；`cluster_quality` 降一级（high→medium / medium→low / low→low），`cluster_confidence` 按降级后的档位重取。
3. `cluster_reason` 追加人话：`近端再出 SOS，派发簇降级（不推翻派发叙事）`。
4. 近端判定复用 `WYCKOFF_CLUSTER_EVENT_FRESH_BARS`（默认 10）；`near_sos` 缺 `sos_age` 视为非近端（不误伤旧调用）。

对称积累侧（accumulation_confirmed 后再出 SOW）**本 handoff 不改**，避免扩大合同面；复查 Agent 可另行评估。

### 1.2 打分：派发确认侧占叙事，抑反向 SOS 分

`_resolve_score_conflicts` 增加规则：

- `distribution_confirmed=True` 且 `distribution_failed=False` 时 → `suppress` 加入 `sos_signal`（近端 SOS 不得 +15 对冲派发确认 -15）。
- `distribution_failed=True`（UT→SOS 无 SOW，假派发实为吸筹）→ 不抑 SOS，维持既有看多叙事。

`calculate_wyckoff_score` 的 SOS 计分与 VSA 相关分支统一消费抑后布尔（`sos_on`），禁止用 raw `analysis["sos_signal"]` 再计一次。

### 1.4 阶段机消费：派发确认语境不得抬成积累 D/C

- `wyckoff_analysis` 喂给 `_detect_phase` 的 `signals_dict` 与打分同规则抑 `sos_signal`，并透出 `distribution_confirmed` / `distribution_failed` 两个簇标志；结果 dict 的 `sos_signal` 保持原值（审计/展示用）。
- `_detect_phase` 增加 `_dist_cluster` 守卫（`distribution_confirmed ∧ ¬distribution_failed`）：Spring+Test、Spring+SOS/LPS、Spring+TrendPullback、裸 Spring 这 4 个积累 D/C 分支一律 `and not _dist_cluster`；即使 `_scan` 从 bars 重新检出 SOS，也不得在派发确认语境跳成积累 D/C。
- `distribution_failed=True`（假派发实为吸筹）不受守卫影响，Spring+SOS 仍可进积累 D。

### 1.3 View：簇确认定侧，先定侧再顺侧取灯

`infer_daily_short_wave`：

1. `distribution_confirmed`（且无 accumulation_confirmed）→ 短波侧直接定为 `distribution`；`accumulation_confirmed` 对称定为 `accumulation`；不再用「命中数量」让 SOS/SC/AR 数量把派发侧翻成吸筹。
2. 侧内主灯仍按既有链优先级（派发：UTAD > LPSY > SOW > UT > BC > ARE）；该侧无事件灯时，簇本身作为主事件：`DistConfirm`（偏空）／`AccumConfirm`（偏多）。

`resolve_wyckoff_primary`：

- `_side == "distribution"` 且无 UTAD/LPSY/SOW/UT/BC/ARE 事件灯 → 返回 `DistConfirmed`（派发确认）偏空，不再落进 JAC/SOS 偏多分支；`_side == "accumulation"` 对称返回 `AccumConfirmed`。
- `_midline_meaning` 增加 `DistConfirmed → 先防守`、`AccumConfirmed → 仍看回踩站不站稳`。

---

## 2. 字段

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `cluster_contested` | bool | False | 派发确认后近端再出 SOS → True；纯展示/降级标记，不进 fusion |
| `sos_age` | int / None | None | `_detect_sos` 新增透传：0=末日 tip，>0=回扫命中距末日根数；仅审计/近端判定用 |

---

## 3. 可改文件

- `02-共享模块-shared/trader_shared/wyckoff_events.py` — `_detect_event_cluster` + `_detect_sos`（sos_age）
- `02-共享模块-shared/trader_shared/wyckoff_core.py` — 簇调用时机/near_sos 注入、`_resolve_score_conflicts`、`calculate_wyckoff_score`、`resolve_wyckoff_primary`、`_midline_meaning`、结果透出
- `02-共享模块-shared/trader_shared/wyckoff_phase.py` — `_detect_phase` 的 `_dist_cluster` 守卫
- `02-共享模块-shared/trader_shared/wyckoff_view.py` — `infer_daily_short_wave`、`format_daily_short_wave_line` 的簇灯位
- `02-共享模块-shared/tests/test_wyckoff_tr.py` / `test_wyckoff_core.py` / `test_wyckoff_state_view.py`
- 本 handoff + `BUSINESS.md` 日线威科夫节（先定侧再取灯的簇优先级说明）

---

## 4. 验收

| # | 测 |
|---|-----|
| A | UT→SOW 成立后近端 SOS（near_sos age=0）→ `distribution_confirmed=True`、`distribution_failed=False`、`cluster_contested=True`、质量降级、reason 含降级 |
| B | 同场景 SOS age > fresh → 不 contested |
| C | scan 内 `sow_idx < sos_idx` 且 fresh → 也不得 `distribution_failed=True` |
| D | 打分：`distribution_confirmed + sos_signal` → raw 只含派发确认 -15，无 SOS +15，signals 含互斥抑制 |
| E | 打分：`distribution_failed + sos_signal` → SOS +15 与派发失败 +20 仍计（回归） |
| F | View：`distribution_confirmed + sos_signal`（无其他事件灯）→ side=distribution、code=DistConfirm、偏空 |
| G | View：`distribution_confirmed + sos + bc + are` → side=distribution（簇定侧胜过数量）、主灯 BC |
| H | `resolve_wyckoff_primary` 同 F → code=DistConfirmed、direction=-1 |
| I | phase：`distribution_confirmed + spring + sos`（_scan 钉死 False）→ 不进 accumulation_d/c；`distribution_failed=True` 回归仍进 accumulation_d |

```bash
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_wyckoff_tr.py \
  02-共享模块-shared/tests/test_wyckoff_core.py \
  02-共享模块-shared/tests/test_wyckoff_state_view.py -q --tb=short
```

---

## 5. 禁止

- 改 fusion / decision_view / major_stage / 池分道公式
- 把 UT→SOW→近端 SOS 判成 `distribution_failed`（假派发实为吸筹）
- 让近端 SOS 把短波侧/中线灯翻成偏多
- 给 `cluster_contested` 接入出手/共振背景岗
- 把 merge 挪到 decision_view 后
