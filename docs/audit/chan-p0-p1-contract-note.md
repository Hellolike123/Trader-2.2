# Chanlun P0 / P1 合同附注

> 日期：2026-08-01  
> 目的：标明 P0/P1 代码与既有 BUSINESS / formulas 合同的对应关系；**不改写** `BUSINESS.md`。

---

## P0（A1–A5）— 实现既有 BUSINESS §2.0 / §2.1

P0 提交（`580147e` 及同族）把运行时对齐到已写明的合同，而非新开产品语义：

| 项 | 合同锚点 | 代码 realization |
|----|----------|------------------|
| 阶段 | BUSINESS §2.0/§2.1：`stage` = 周威科夫 | 中线阶段读周线威科夫，不日线冒充 |
| daily_fallback | 仅展示（日线回退标注） | 不抬升为中线主裁定 |
| C1 / 共振买点 | 正式一/二/三类 | fusion / 开仓清单只认正式档 |
| 类一 / 类二 | 观察档 | 不进强多/强空 / C1「买点信号」二档 |

法源仍以 `BUSINESS.md` 正文为准；本文件只作对照索引。

---

## P1 — 假趋势 demotion（formulas §9）

- §9.1：两中枢连接段须为**反向走势**。
- §9.2 / §9.4：同向不重叠但连接段非反向（夹同向小中枢）→ **降为盘整（假趋势）**。
- 输出：`structure_type=盘整`（可在 `structure_evidence` 注假趋势）；**禁止** `structure_type="假趋势"`。
- 实现：`chan_structure._connector_is_non_reverse` + `classify_structure` / `_strict_*_trend_zones`。
- §4.3 文案已与 §9 对齐；权威仍是 §9。
