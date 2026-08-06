# 法源文档清理 — Agent 可读 + 去掉多余 — Handoff

> **状态**: done（2026-08-02；写/查双 Agent PASS）  
> **用户目标（两条）**:  
> 1) **任意 Agent** 读完知道按什么规则、在什么逻辑上开发（入口清晰、母法源不淹没）。  
> 2) **业务原点** 与代码对齐的合同要可见；已修的区间硬伤写进 BUSINESS；未修差异**显式列出**勿假装零差。  
> 3) 不必要的一次性手递 **挪到 `done/`**（优先 MOVE，慎 DELETE）。

---

## 1. 必须做

### 1.1 重写 `docs/plans/README.md`（Agent 入口）

三桶：

| 桶 | 含义 |
|----|------|
| **母法源（根目录保留）** | 开发/验收必须读 |
| **done/** | 已合入的一次性手递 / 历史 |
| **obsolete 杀开关** | 明确禁止再做的方向 |

母法源清单（根下保留，文首 status 统一为 `mother_law` 或 `impl_done` + 一句「现行」）：

**威科夫**

- `wyckoff-structure-anchor-handoff.md` — SC 宇宙 / 钉住 / 破位→L0  
- `wyckoff-tr-maturity-l0l3-handoff.md` — L0–L3 / 箱体·量度门  
- `wyckoff-detail-slim-b-handoff.md` — 默认 B 卡骨架  
- `wyckoff-phase-fail-copy-handoff.md` — Phase 失效人话 SSOT  
- `wyckoff-skill-deep-card-handoff.md` — `--full` 详析  
- `wyckoff-pnf-handoff.md` — P&F 计数（量度授权听 L3）  
- `wyckoff-weekly-scan-windows-handoff.md` — 周窗 S1/S3  
- `wyckoff-phase-a-range-handoff.md` — **仅**种子史；文首已勘误：**SC 窗以 structure-anchor 为准**  
- `wyckoff-detect-tuning-next.md` — 薄指针（勿当第二 SSOT）  
- `wyckoff-rs-phase-handoff.md` — 池 RS（若 BUSINESS 仍引）

**交易员面板**

- `trader-panel-declutter-handoff.md`  
- `trader-drop-stage-line-handoff.md`  
- `report-section-reorg-obsolete.md` — **禁止**四区重组

**缠论**

- `chanlun-skill-deep-card-handoff.md` — 四关心点 + C-D* 母本（status 改 `impl_done`，勿再标 active 诱重复开工）  
- `chanlun-skill-playbook.md` — 薄入口，链到 deep-card  

**产品总契约**：`BUSINESS.md`；算法：`formulas.md`；架构：`docs/designs/resonance-and-orchestration.md`。

README 须含「开发开读顺序」短表（威科夫 / 缠论 / 面板 各 3～5 链）。

### 1.2 MOVE 到 `docs/plans/done/`（一次性已合）

下列**整文件 git mv**（更新文首 `status: done` 若尚未）：

- `agents-rank-sanitize-handoff.md`  
- `chanlun-cd-followup-handoff.md`  
- `chanlun-observe-tier-handoff.md`  
- `ci-gate-python-portable-handoff.md`  
- `range-diff-fixes-handoff.md`  
- `skill-usage-guide-chanlun-handoff.md`  
- `smoke-pool-sample-audit-handoff.md`  
- `wyckoff-fail-copy-cleanup-handoff.md`  
- `wyckoff-failed-chain-copy-handoff.md`  
- `wyckoff-phase-label-fail-sanitize-handoff.md`  
- `wyckoff-report-fail-copy-leak-handoff.md`  
- `wyckoff-phase-accuracy-handoff-2026-07-31.md`  

MOVE 后若有链接断链：在母法源或 README 用相对路径指到 `done/`，或保留一句「见 done/…」。  
`AGENTS.md` / `BUSINESS.md` 若硬链旧路径 → 改到新路径或改指母法源。

### 1.3 状态与冲突消歧（根下母法源）

| 文件 | 动作 |
|------|------|
| `chanlun-skill-deep-card-handoff.md` | `active` → `impl_done`；文首注明 follow-up/observe 已合，C-D 表 ❌ 为历史快照 |
| `wyckoff-structure-anchor-handoff.md` | 文首标明 `impl_done` / 现行母法源 |
| `wyckoff-detail-slim-b` / `phase-fail-copy` / `weekly-scan` / `trader-*` | 规格冻结 → 加「已合入；现行展示/面板合同」 |
| `wyckoff-phase-a-range-handoff.md` | 文首勘误加粗：**禁止**按正文旧 CLIMAX=15 当 SC 窗；现行只读 structure-anchor |
| `done/mid-short-dual-track-plan.md` | 文首加 superseded：独立「阶段：」行已由 drop-stage 废除 |

### 1.4 `BUSINESS.md` 同步（Agent 可读 + 原点可见）

在威科夫 §2.2 附近补短段（勿开长文）：

1. forming 无 AR → 雏形只写「上沿未出」；**禁**分位 `tr_upper` 冒充（range-diff / maturity）。  
2. 破位冷启动排除 `sc_bar_idx ≤ fail_bar_idx`（structure-anchor）。  
3. 中枢 ZG/ZD 取 high/low 极值（formulas；已落地）。  
4. **已知未修差异**（诚实列表，勿装零差）：  
   - `report["wyckoff"]` 周不足可回退日线；面板 SSOT=`wyckoff_midline`/`wyckoff_daily`  
   - 破位：`close is None` 现码更严（与 structure-anchor「须 close」不完全一致）  
   - 背驰展示可 multi，一类扳机面积-only（formulas 取舍）  
   - `zones_count` 引擎 raw vs 卡 merged  

不在本 PR 改引擎（除非查 Agent 发现 MOVE 断链必修路径字符串）。

### 1.5 可选薄文件

- 新建 `docs/plans/known-gaps.md`（或 README 一节）= 上列已知未修；**禁止**写成待办诱惑大重构。  
- `active/` 空目录：README 写明「暂不用；勿往里丢母法源」。

---

## 2. 禁止

1. **删除**母法源（structure-anchor / tr-maturity / slim-b / phase-fail-copy / deep-card / pnf 等）。  
2. 删除 `report-section-reorg-obsolete.md`。  
3. 本 PR 不改 fusion / 出手 / 池分道 / 区间算法（已在 #45）。  
4. 不为「干净」把母法源塞进 done/ 导致 Agent 找不到。  
5. 不重开报告四区。

---

## 3. 验收

| ID | 项 |
|----|-----|
| D-1 | README 三桶 + 开读顺序；Agent 能 30 秒找到威科夫/缠论母法源 |
| D-2 | §1.2 列表文件已在 `done/`，根目录不再堆一次性手递 |
| D-3 | BUSINESS 含 range-diff 要点 + 已知未修列表 |
| D-4 | 母法源文首不再伪 `active` 诱重复开工（deep-card 等） |
| D-5 | `rg` 仓库内断链：关键路径指向 `done/` 或已改 |
| D-6 | 查 Agent：对照用户两条目标 ✅/❌；无 must-fix |

---

## 4. 双 Agent

- **写 Agent**：按 §1 执行 + commit/push（`cursor/docs-law-cleanup-514d`）。  
- **查 Agent**：扮演「新来的 Agent」——只读 README→母法源，判断能否开工；核对 MOVE/断链/禁止删除；对照两条用户目标。
