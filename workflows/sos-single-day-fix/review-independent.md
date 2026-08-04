# Independent Review — Wyckoff SOS epic (A+B+C/G)

| 项 | 值 |
|----|-----|
| mode | SOP independent review（只读；本会话相对实现有上下文，**非跨厂商 fresh session** — 降级 ladder L3，Medium 允许） |
| 法源 | `docs/plans/wyckoff-sos-single-day-handoff.md` + `docs/plans/wyckoff-sos-epic-bcg-handoff.md` |
| 外部 | WorkBuddy `wyckoff-sos-修复交接说明.md` Bug A/B/C/G |
| 实证 | 南网 diag + `final_wyckoff`：日线 ●SOS 45.50；TR fallback；假 SOS 63 已灭 |
| 日期 | review 随会话 |

---

## VERDICT: **PASS with docs delta**（建议合入；先补 handoff M4 一句）

无阻断级代码缺陷。有 2 条 **文档合同漂移** 须补丁 handoff（非回滚实现）。1 条 suggested。

---

## 对照清单

### Bug A — SOS thrust（`wyckoff-sos-single-day-handoff`）

| ID | 合同 | 结论 | 证据 |
|----|------|------|------|
| M1 | climb 不变 | ✅ | `_try_sos_climb` 仍 ≥4/5 + 抬高 + 均量×1.2 + ≥2% |
| M2 | climb 后 OR thrust | ✅ | `_detect_sos_at_tip` |
| M3 | 阳线 ∧ close>creek ∧ 涨≥5% ∧ 量比 round≥1.8；creek=ar_high\|tr_upper | ✅ | `_try_sos_thrust` + `_sos_thrust_creek`；南网 creek=43、+8.6%、量比1.9 |
| M4 | baseline 优先 tr_baseline 否则前窗均量 | ⚠️ **实现已进化** | thrust 现用 **溪内 tip 前中位数**（`_sos_thrust_baseline_vol`）；climb 仍旧。handoff M4 未写溪内中位 → **须改文档** |
| M5 | sos_kind climb\|thrust\|None | ✅ | core 透传 `sos_kind` |
| M6 | pytest 边界 | ✅ | TestDetectSosThrust / NanwangLike / SosScFloor；用户曾 137+1 vol 边界，测例已修待确认 138 |
| M7 | 只改 shared | ✅ | events/core/config/tests/docs |
| P1 | 无上沿不 thrust | ✅* | 无 creek（ar_high 与 tr_upper 皆无）不 thrust；*仅 ar_high 可 thrust（有意，优于死板 tr_upper） |
| P2 | 不降 4/5 | ✅ | |
| P3–P6 | 不改 fusion/池/指令 | ✅ | 未触 |
| A1–A7 | 验收表 | ✅ | 构造+南网 A1；箱内/涨幅/量比/climb/BU 有测 |
| 回扫 | SC 后 + lookback | ✅ | `min_tip_idx` + SC→今≤120；簇/BU tip-only=1 |
| 假 SOS 63 | SC 地板 | ✅ | 周线曾亮 63 → 已灭 |

### Bug B — TR fallback

| ID | 合同 | 结论 | 证据 |
|----|------|------|------|
| M-B1 | 主 grow 优先 | ✅ | primary 命中即 return |
| M-B2 | fallback 短横盘 | ✅ | `FALLBACK_MIN_WIDTH=10`；南网 TR width=11 fallback |
| M-B3 | amp/折返/分位 | ✅ | `_tr_build_from_slice` |
| P2 | 不全局降 MIN_WIDTH | ✅ | |
| B1 南网 | TR 非 None | ✅ | diag `tr_fallback=True` upper/lower 合理 |

### Bug C — 簇污染

| ID | 合同 | 结论 | 证据 |
|----|------|------|------|
| M-C1 | SC 后才认派发/吸筹事件 | ✅ | `_detect_event_cluster` 滤 idx≤sc |
| M-C2 | SOW/确认事件 fresh | ✅ | `fresh_floor`；测 `test_stale_sow_not_fresh_enough` |
| 测 | SC 重置旧 UT→SOW | ✅ | `test_sc_resets_pre_sc_distribution` |

### Bug G — phase_a failed

| ID | 合同 | 结论 | 证据 |
|----|------|------|------|
| M-G1 | failed → 四簇 False | ✅ | `wyckoff_core` 在 refine 后闸；测 monkeypatch |

### 南网产品验收（外部交接 §9.1 子集）

| 项 | 结论 |
|----|------|
| TR 非空 | ✅ fallback |
| 日线 SOS● ≈45.50 | ✅ |
| 周线 SOS | ○（可接受；周 K 非 thrust 日） |
| 假 63 不亮 | ✅ |
| dist 误确认 | 未在面板暴露；C 测覆盖 |
| F/D/E | ❌ 明确 **out of scope** 本 epic |

---

## BLOCKING

1. **无代码阻断项。**  
2. **文档（合入前建议 5 分钟补丁）**：`wyckoff-sos-single-day-handoff.md` **M4** 改为：  
   - climb：tr_baseline 或前窗均量  
   - thrust：溪内（close≤creek）tip 前中位数；不足 3 根再 fallback robust/tr_baseline  
   并在 §0 摘要写明「溪 = ar_high 优先」。

---

## SUGGESTED（非阻断）

1. pytest 全量请再跑一次确认 vol_boundary 修后 **0 failed**（上次 1 failed 测例侧）。  
2. Reviewer 独立性：本 review 同实现会话；正式 PR 可用 codex 只读再扫一眼。  
3. 后续 epic：F（SC 失效文案）、D 周线、E volume 单位 — 勿混本 PR。  
4. `sos_reason` 文案仍写「TR上沿」即使 creek 来自 ar_high — 可改「溪/上沿」减少误解。

---

## EVIDENCE

- 代码：`wyckoff_events.py` SOS/TR/cluster；`wyckoff_core.py` sos 回扫 + phase_a 闸簇；`config.py` 常量  
- 测：`TestDetectSosThrust` / `TestNanwangLikeThrust` / `TestSosScFloor` / `TestTradingRangeFallbackBugB` / `TestEventClusterBugCG`  
- 实证：`workflows/sos-single-day-fix/evidence/nanwang-sos-pass.md`；用户 diag `main_detect_sos True`；面板 ●SOS 45.50  

---

## NEXT

1. 写 Agent：补 handoff M4 文档漂移（可选改 reason 文案）  
2. 用户：`pytest test_wyckoff_core -q` 确认全绿  
3. 用户批准后 commit/PR（SOP 不自动推）
