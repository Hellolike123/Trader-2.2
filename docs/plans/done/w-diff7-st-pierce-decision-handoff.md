# W-DIFF-7 深刺穿收回与 ST — 产品裁决 Handoff

> **状态**: done（2026-08-02；文档裁决已写入法源；known-gaps 未修行已清空）  
> **背景**: known-gaps 唯一剩余项；用户口令继续自主收口。  
> **裁决（钉死，对齐原典 spring/测试 + 现码）**:

---

## 1. 产品裁决

1. **破位**（Phase A failed）：仅当 `low < sc_low×(1−MAX_PIERCE)` **且** `close < sc_low`（structure-anchor §3.1；G-K1 已对齐）。  
2. **深刺穿但收盘收回**（`close ≥ sc_low`）：**不算**破位。  
3. **广义 ST**：在未 failed 前提下，若该棒（或候选棒）满足既有 ST 条件（回测 SC 区 + 缩量等），**允许**认 ST——**不**因「曾刺穿过 floor」单独否决。  
   - 理由：原典 spring/二次测试允许刺穿支撑后收回；`MAX_PIERCE` 与 `close` 共同定义**失败**，不是「禁止深测」。  
4. **本 PR 不改** ST 检测阈值/公式；只把裁决写入法源，并从 known-gaps **移除**「未修」。

---

## 2. 必须（文档）

| ID | 必须 |
|----|------|
| D-7a | `wyckoff-structure-anchor-handoff.md` §3.1 或紧接：补一句「刺穿超限但 close 收回 → 不 failed；仍可走 ST 检测」 |
| D-7b | `wyckoff-tr-maturity-l0l3-handoff.md` §1.3/刺穿相关：同上，禁写成「超刺穿一律否 ST」 |
| D-7c | `known-gaps.md`：删除 W-DIFF-7 未修行；移入「已声明取舍」 |
| D-7d | `BUSINESS.md` §2.2 已知未修：去掉 W-DIFF-7；可一句指向取舍 |
| D-7e | `git mv known-gaps-close-handoff.md` → `done/`（已合 #47） |

## 3. 禁止

改 ST 检测代码（本裁决确认现码合法）；改 fusion/出手；重开四区。

## 4. 双 Agent

写：只改文档 + mv + push。  
查：确认 known-gaps 无未修代码项；裁决与 §3.1 不矛盾。
