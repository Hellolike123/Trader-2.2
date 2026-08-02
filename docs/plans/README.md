# plans/ — Agent 法源入口

任意 Agent **先读本页**，再按开读顺序进母法源。勿在根目录堆一次性手递；勿把母法源塞进 `done/`。

## 三桶

| 桶 | 含义 | 放什么 |
|----|------|--------|
| **母法源（本目录根）** | 开发 / 验收必须读；文首 `mother_law` 或 `impl_done` +「现行」 | 下表清单 |
| **`done/`** | 已合入的一次性手递 / 历史计划 | MOVE 优先；慎 DELETE |
| **obsolete 杀开关** | **禁止再做**的方向 | 现仅 [`report-section-reorg-obsolete.md`](./report-section-reorg-obsolete.md)（报告四区） |

`active/` 目录**暂不用**；勿往里丢母法源（空目录占位即可）。

文首建议：`status: mother_law | impl_done | done | obsolete`。  
策略分层主计划见 [`../designs/strategy-roadmap-and-tests.md`](../designs/strategy-roadmap-and-tests.md)（属 designs，不算本目录琐碎 plan）。

---

## 开发开读顺序（30 秒定位）

### 威科夫

1. [`BUSINESS.md`](../../BUSINESS.md) §2.0 / §2.2  
2. [`wyckoff-structure-anchor-handoff.md`](./wyckoff-structure-anchor-handoff.md) — SC 宇宙 / 钉住 / 破位→L0  
3. [`wyckoff-tr-maturity-l0l3-handoff.md`](./wyckoff-tr-maturity-l0l3-handoff.md) — L0–L3 / 箱体·量度门  
4. [`wyckoff-detail-slim-b-handoff.md`](./wyckoff-detail-slim-b-handoff.md) — 默认 B 卡；[`wyckoff-phase-fail-copy-handoff.md`](./wyckoff-phase-fail-copy-handoff.md) — 失效人话  
5. 需要时：[`wyckoff-skill-deep-card-handoff.md`](./wyckoff-skill-deep-card-handoff.md)（`--full`）· [`wyckoff-pnf-handoff.md`](./wyckoff-pnf-handoff.md) · [`wyckoff-weekly-scan-windows-handoff.md`](./wyckoff-weekly-scan-windows-handoff.md)

### 缠论

1. [`BUSINESS.md`](../../BUSINESS.md) §2.0 / §2.1  
2. [`chanlun-skill-playbook.md`](./chanlun-skill-playbook.md) — 四关心点薄入口  
3. [`chanlun-skill-deep-card-handoff.md`](./chanlun-skill-deep-card-handoff.md) — C-D* 母本（`impl_done`；表内 ❌ 为历史快照）  
4. 算法：[`formulas.md`](../../02-共享模块-shared/trader_shared/formulas.md) §2–§6 / §4.1 / §9.1

### 交易员面板

1. [`BUSINESS.md`](../../BUSINESS.md) §4.0 / §5.1  
2. [`trader-drop-stage-line-handoff.md`](./trader-drop-stage-line-handoff.md) — 无独立「阶段：」行  
3. [`trader-panel-declutter-handoff.md`](./trader-panel-declutter-handoff.md) — 关闭态动词净化  
4. **禁止**：[`report-section-reorg-obsolete.md`](./report-section-reorg-obsolete.md)（勿重开四区）

### 产品 / 架构总入口

- 产品总契约：[`BUSINESS.md`](../../BUSINESS.md)  
- 算法：[`formulas.md`](../../02-共享模块-shared/trader_shared/formulas.md)  
- 架构（五层+编排）：[`../designs/resonance-and-orchestration.md`](../designs/resonance-and-orchestration.md)

---

## 母法源清单（根下保留）

文首统一为 `mother_law` 或 `impl_done` + 一句「现行」。**禁止删除**下列文件。

### 威科夫

| 文件 | 一句 |
|------|------|
| [`wyckoff-structure-anchor-handoff.md`](./wyckoff-structure-anchor-handoff.md) | SC 宇宙 / 钉住 / 破位→L0 |
| [`wyckoff-tr-maturity-l0l3-handoff.md`](./wyckoff-tr-maturity-l0l3-handoff.md) | L0–L3 / 箱体·量度门 |
| [`wyckoff-detail-slim-b-handoff.md`](./wyckoff-detail-slim-b-handoff.md) | 默认 B 卡骨架 |
| [`wyckoff-phase-fail-copy-handoff.md`](./wyckoff-phase-fail-copy-handoff.md) | Phase 失效人话 SSOT |
| [`wyckoff-skill-deep-card-handoff.md`](./wyckoff-skill-deep-card-handoff.md) | `--full` 详析 |
| [`wyckoff-pnf-handoff.md`](./wyckoff-pnf-handoff.md) | P&F 计数（量度授权听 L3） |
| [`wyckoff-weekly-scan-windows-handoff.md`](./wyckoff-weekly-scan-windows-handoff.md) | 周窗 S1/S3 |
| [`wyckoff-phase-a-range-handoff.md`](./wyckoff-phase-a-range-handoff.md) | **仅**种子史；**SC 窗以 structure-anchor 为准** |
| [`wyckoff-detect-tuning-next.md`](./wyckoff-detect-tuning-next.md) | 薄指针（勿当第二 SSOT） |
| [`wyckoff-rs-phase-handoff.md`](./wyckoff-rs-phase-handoff.md) | 池 RS |

### 交易员面板

| 文件 | 一句 |
|------|------|
| [`trader-panel-declutter-handoff.md`](./trader-panel-declutter-handoff.md) | 关闭态动词净化 |
| [`trader-drop-stage-line-handoff.md`](./trader-drop-stage-line-handoff.md) | 去掉面板「阶段：」行 |
| [`report-section-reorg-obsolete.md`](./report-section-reorg-obsolete.md) | **禁止**四区重组 |

### 缠论

| 文件 | 一句 |
|------|------|
| [`chanlun-skill-deep-card-handoff.md`](./chanlun-skill-deep-card-handoff.md) | 四关心点 + C-D* 母本（勿标 active） |
| [`chanlun-skill-playbook.md`](./chanlun-skill-playbook.md) | 薄入口，链到 deep-card |

### 本轮清理手递

- [`docs-law-cleanup-handoff.md`](./docs-law-cleanup-handoff.md) — 文档三桶 / MOVE / 状态消歧（完成后可进 `done/`）

---

## 已知未修差异（诚实列表）

见 [`known-gaps.md`](./known-gaps.md)（与 `BUSINESS.md` §2.2 同源；**禁止**当大重构待办诱惑）。

---

## `done/` 提示

一次性已合入手递在 [`done/`](./done/)。链文案 / follow-up / range-diff / accuracy 等历史见该目录；母法源内用 `done/…` 相对路径或「见 done/…」指过去。  
例：`done/wyckoff-failed-chain-copy-handoff.md`、`done/range-diff-fixes-handoff.md`、`done/chanlun-cd-followup-handoff.md`、`done/wyckoff-phase-accuracy-handoff-2026-07-31.md`。
