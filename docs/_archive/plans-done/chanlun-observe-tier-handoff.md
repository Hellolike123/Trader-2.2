# 缠论类一/类二观察档展示 — Agent Handoff

> **状态**: done（2026-08-02；写/查双 Agent PASS）  
> **轨道**: 与「真池/样本干跑」并行的缠论下一刀（用户口令：1 与 2 分开、双 Agent、同时做）  
> **母法源**: `../chanlun-skill-deep-card-handoff.md` §2.3「展示分层」；`../chanlun-skill-playbook.md` §0 关心点 3  
> **产品裁决**: **只改展示分层文案**；不改买卖点检测、不改 fusion/出手/威科夫定论/池分道。

---

## 1. 背景

干跑可见中线副读：`买点：类二买 346.16`（宁德/上证类）。  
合同要求：正式一/二/三类可进主槽；**类一/类二须标观察档**（或不进强信号槽）。当前专项卡未标「观察」。

---

## 2. 必须（O-T1…O-T6）

| ID | 必须 |
|----|------|
| O-T1 | 缠论专项卡（`chanlun_render`）买/卖点行：类型为 `类一买/卖`、`类二买/卖` 时，可见面带 **观察** 标注（推荐：`类二买（观察）{价}`；多点并列同规则） |
| O-T2 | 正式 `一类/二类/三类` 买卖 **不**加「观察」 |
| O-T3 | 未形成仍写「未形成」；禁止「接近一买」等手补 |
| O-T4 | 不下单词：宜买/可执行/可低吸/该买了 |
| O-T5 | pytest：类二/类一夹具 → 面板含「观察」；正式一类夹具 → 无「（观察）」误标 |
| O-T6 | 同步 `01-功能包-packages/chanlun/references/output-template.md` 一句说明观察档 |

可选（有余力且同 PR）：Trader 短线灯 `format_chanlun_short_light` 对类一/类二短名旁同样带观察语义（若已有短名「类二买」露出），**不得**改 fusion 计分。

---

## 3. 禁止

1. 不改 `detect_buy_points` / `detect_sell_points` 判定。  
2. 不改 fusion weighted_score / decision_view / 池分道。  
3. 不把类二升格成正式二类叙事。  
4. 不覆盖周线威科夫中线阶段。  
5. 不重开报告四区。

---

## 4. 可改 / 勿改

| 可改 | 勿改 |
|------|------|
| `chanlun_render.py`（`_fmt_points` 或等价） | `chan_structure` 检测核心 |
| 相关 pytest（skill_render / chanlun tests） | fusion / 出手 |
| `chanlun/.../output-template.md`；本 handoff | 威科夫引擎 |
| 可选：`chan_core.format_chanlun_*_light` 仅展示词 | 池分道 |

---

## 5. 验收

| ID | 项 |
|----|-----|
| M-O1 | 类二买 fixture 面板含「观察」 |
| M-O2 | 一类买 fixture 无「（观察）」 |
| M-O3 | 相关测绿；门禁绿（可不扩 TESTS 数组） |
| M-O4 | diff 无 fusion/出手/分道 |

---

## 6. 双 Agent

- **写 Agent**：按 O-T* 落地 + 测 + commit/push（分支 `cursor/chanlun-observe-tier-514d`）。  
- **查 Agent**：对照本文 + deep-card §2.3；列 must-fix。
