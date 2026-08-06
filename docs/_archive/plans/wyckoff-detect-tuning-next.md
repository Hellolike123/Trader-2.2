# 威科夫检测调参 — 续篇指针（非第二 SSOT）

> **状态**: mother_law / 指针页（2026-08-02；勿当第二 SSOT）  
> **用途**: 避免「搜索宇宙 / 钉住 / 破位收口」出现双份现行法源。  
> **详析卡备忘**: 原对话记下的「15 窗 / 南网破位」已冻结进 structure-anchor；本文不再重开算法。

---

## 已冻结（勿在此重开方案）

下列产品裁决已写入并冻结于：

**[`wyckoff-structure-anchor-handoff.md`](./wyckoff-structure-anchor-handoff.md)**

含：

1. 未失效 Phase A → 钉住 `[sc_bar_idx, 今]`，不设到期  
2. 冷启动：日线 90 / 周线 39  
3. 破位收口与钉住同包（`status=failed` → `tr_maturity=L0`）  
4. 中线周 / 短线日分轨  
5. 50/200 MA 不法源  
6. 旧「`CLIMAX_ANCHOR_BARS=15` = SC 唯一搜索宇宙」作废  

实现与验收只读该 handoff（S-A1…S-A8）。**本文不另写算法、不改默认值表。**  
满血持久化（Phase A 锚跨日小本本）见 **structure-anchor §8**（S-P1…S-P4）；勿在本文另起存盘方案。

---

## 历史文档

| 文档 | 角色 |
|------|------|
| `wyckoff-phase-a-range-handoff.md` | P1/P2 历史；文首已勘误「15=SC 窗」 |
| `wyckoff-tr-maturity-l0l3-handoff.md` | L0–L3 展示/量度；破位失败态以 structure-anchor 为准 |
| `wyckoff-skill-deep-card-handoff.md` | 详析卡渲染合同（PR #25）；不改检测阈值 |

---

## 若需后续调参

SC/ST **现行默认值**以 `config.py` + [`wyckoff-tr-maturity-l0l3-handoff.md`](./wyckoff-tr-maturity-l0l3-handoff.md) §4 为准。  
PR #55 已合入小步松参（样本对照见 [`done/wyckoff-ashare-box-sensitivity-handoff.md`](./done/wyckoff-ashare-box-sensitivity-handoff.md)）；本文不重抄数值表。

再调参须另开手递。任何新手递若触及 SC 搜索宇宙 / 钉住 / 破位，必须 **修订 structure-anchor** 或显式声明取代它——禁止在本文件堆第二套规则。
