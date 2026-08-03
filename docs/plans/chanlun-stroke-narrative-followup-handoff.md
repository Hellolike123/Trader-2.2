# 缠论笔几何后续 — 结构叙事 / 短笔副作用 Handoff

> **状态**: impl_done（2026-08-04；笔几何 4 commit + S-1 合同测 + golden 基线刷新，**未 push / 未开 PR**）  
> **分支**: `cursor/chanlun-stroke-geom-nangwang` @ `dc3fcb1`  
> **法源**: `formulas.md` §2–§3 / §6；`chanlun-skill-slim-b-handoff.md` §2.4；`done/chanlun-cd-followup-handoff.md` C-D4e；`BUSINESS.md` §2.0  
> **方法**: 挖 Agent（只读）→ 查 Agent（只读对照）→ 父 Agent 只加测 + 刷新基线，**不改几何语义**

---

## 0. 一句话

笔价断层层（§2.1a–c / §3.4–3.5b）经双 Agent 排查已收口；本轮**只补 S-1 合同测**（破极值短笔须参与中枢），并把几何变化导致的 golden/等价闸基线刷新，门禁绿。叙事（N-*）与其余短笔副作用（S-2/S-3）无硬证据，**不授权改生产语义**。

---

## 1. 已合入（相对 main，6 commit）

| Commit | 内容 |
|--------|------|
| `13c2163` | 笔衔接延伸 + 护栏；段端点跟方向；破极值可短笔 |
| `018ae4a` | 短笔可跟更深底；段排除共用转折远端 |
| `75df01d` | 未完成唯一段与净走势拧句 → 纠偏方向 |
| `d6f23cf` | 形成中下行回到高点 → 并回上段或省略 |
| `2a7b166` | **S-1 合同测**：破极值短笔须参与中枢（`test_extreme_breaking_short_stroke_feeds_pivot`） |
| `dc3fcb1` | **刷新基线**：chan_split / report / golden 600000 + `_render_eq_capture.py` 改走统一测试 seam |

测锚：`test_chan_core` / `test_chanlun_stroke_stall`（8 passed）/ `test_chanlun_correctness` / 门禁 `run-gate-tests.sh`（698 passed, 4 skipped）。

---

## 2. 挖 Agent 结论（只读，2026-08-03/04）

| ID | 证据 | 初判 |
|----|------|------|
| N-1 | 5 票 `final_chanlun` smoke（南网/华工/中际/曙光/中航）结构正常；4 票有数据、1 票数据不足兜底（非崩） | ⚠️ 待二次查 |
| N-2 | C-D4e `tip_leave` 展示合同在 render；geom 枝未碰 tip_leave 计算 | ✅ 合同已锁 |
| N-3 | 推演拼句在 render/core，geom 枝未动 | ⚠️ 无证据 |
| N-4 | §3.5b 并回改段端点；补测未发现中枢假合并 | ⚠️ 已由门禁 golden 覆盖 |
| S-1 | **本轮已补测**：破极值短笔长度 <5 不丢，须参与 build_zones，`zh_top>zh_bottom` | ✅ 已修 |
| S-2 | 无假买卖点/`signal_tier` 乱跳的实盘证据 | ⚠️ 待样 |
| S-3 | 短笔密度→近笔噪声属产品取舍；未达禁止项 | ⚠️ 不改笔规则 |

---

## 3. 查 Agent 结论（对照 formulas §2.1a–c / §3.4–3.5b、slim-b §2.4、C-D4e）

| ID | 查判 | 说明 |
|----|------|------|
| N-1 | ✅ | 5 票 smoke 无拧句；面板字段与结构一致 |
| N-2 | ✅ | tip_leave 合同未破坏 |
| N-3 | ✅ | 推演无拧句证据；render 未动 |
| N-4 | ✅ | 并回后段/中枢由 golden 基线锁定，门禁绿 |
| S-1 | ✅ | 新测绿（`test_extreme_breaking_short_stroke_feeds_pivot`） |
| S-2 | ⚠️ | 保留观察；无假点证据不改 detect |
| S-3 | ⚠️ | 产品取舍；近笔噪声可另开 render 截断（须新 handoff） |

**总判**：**可合 PR（若用户要求 push）**；几何语义无再改项。门禁 `698 passed, 4 skipped`。

---

## 4. 接手 Agent 待办

1. **查 Agent 复验**（只读）：重跑 `run-gate-tests.sh`（绿）+ `test_chanlun_stroke_stall.py`（8 passed）+ 5 票 smoke。  
2. **开 PR**（若用户要求 push）：标题如 `fix(chanlun): 笔/段几何修正 + 破极值短笔合同测`；PR 必填法源链接（本文 + formulas §2–3）、对照清单、门禁结果。  
   - **勿**混威科夫 PR #58（`fix/wyckoff-b-card-spring-st-gh` 已另开）。  
3. **可选后续**（非本轮）：S-2 快照测、S-3 近笔截断、N-3 实盘拧句巡检——均需新 handoff 授权。

---

## 5. 可改 / 勿改

| 可改（后续 handoff 授权） | 勿改 |
|---------------------------|------|
| `chanlun_render.py` 人话（近笔截断/推演） | fusion / decision_view / 池分道 |
| 补 S-2 前后对照测 | `CHANLUN_MIN_BARS_PER_STROKE` 全局放宽 |
| `formulas.md` 同步 | 与威科夫 #58 混 PR |

---

## 6. 分支关系

| 枝 | 用途 |
|----|------|
| `cursor/chanlun-stroke-geom-nangwang` | **本枝**：笔/段几何 6 commit（含测+基线） |
| `fix/wyckoff-b-card-spring-st` / `*-gh` | 威科夫展示；PR #58；**勿混** |

## 7. Git 备忘

```bash
git log main..HEAD --oneline   # 应见 6 commit（13c2163…dc3fcb1）
bash scripts/run-gate-tests.sh # 698 passed, 4 skipped
# push 另请示（此前未推远程）
```

---

## 8. 复验记录（2026-08-04，几何枝 @ 7e36685）

**挖 Agent 二轮**（只读：5 票实盘 + 开关探测）：

| ID | 复验证据 | 判 |
|----|----------|-----|
| S-2 | 5 票实盘（南网/华工/中际/曙光/中航）**零假买卖点**；中际「类一卖（观察）1416.88」为合法观察档，不冒充正式；合成 bars 开关 §2.1c 短笔 → 买卖点/中枢/结构**零差异**（未触发短笔形态处无影响） | ✅ 无假信号 |
| S-3 | 近笔序列 `↑↓↑↓↑` 5 票均**稳定**（笔数 23/34/36/34/29），无笔碎噪声爆表；中枢 1~9、段 1~3 均正常 | ✅ 无噪声问题 |
| N-1 | 周/日口径复验：华工/曙光/中际/中航 周「高点已离开·向下未成笔」与日「向下笔」一致；**南网**周「低点已离开·向上未成笔」vs 日「拉升段·向上笔」**跨级口径略有差异**（周线 tip_leave 基于周线数据，日线笔已推进；属多级差异非拧句 bug，记录待用户裁决） | ⚠️ 南网一条 |

**总判**：S-2 / S-3 **无真洞**，不授权改几何语义；南网跨级口径为已知多级差异，可选后续。门禁复验 `run-gate-tests.sh` 698 passed（geom 枝），几何专项 191 passed。
