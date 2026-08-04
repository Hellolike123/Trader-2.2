# 缠论笔几何后续 — 结构叙事 / 短笔副作用 Handoff

> **状态**: **landed_on_main**（2026-08-04；几何语义 + S-1 合同测 + golden 基线 **已在 `main`**；无需再开几何 PR）  
> **main 等价链**（验收用这组 SHA）: `39222f3` → `a72c987` → `46084ee` → `682dbce` → `1c47814` → `6616ea1`  
> **历史 feature 枝**（仅考古）: `cursor/chanlun-stroke-geom-nangwang` @ `dc3fcb1`（枝上 6 SHA **不是** main 祖先；关键文件与 main **内容对等**）  
> **法源**: `formulas.md` §2–§3 / §6；`chanlun-skill-slim-b-handoff.md` §2.4；`done/chanlun-cd-followup-handoff.md` C-D4e；`BUSINESS.md` §2.0  
> **方法**: 挖 Agent（只读）→ 查 Agent（只读对照）→ 父 Agent 只加测 + 刷新基线，**不改几何语义**

---

## 0. 一句话

笔价断层层（§2.1a–c / §3.4–3.5b）经双 Agent 排查已收口并 **已落入 main**；本轮补了 S-1 合同测（破极值短笔须参与中枢）与 golden/等价闸基线刷新，门禁绿。叙事（N-*）与其余短笔副作用（S-2/S-3）无硬证据，**不授权改生产语义**。

---

## 1. 已合入 main（6 commit · 验收 SHA）

| Commit（main） | 内容 | 枝上对应（非 ancestor，仅对照） |
|----------------|------|--------------------------------|
| `39222f3` | 笔衔接延伸 + 护栏；段端点跟方向；破极值可短笔 | `13c2163` |
| `a72c987` | 短笔可跟更深底；段排除共用转折远端 | `018ae4a` |
| `46084ee` | 未完成唯一段与净走势拧句 → 纠偏方向 | `75df01d` |
| `682dbce` | 形成中下行回到高点 → 并回上段或省略 | `d6f23cf` |
| `1c47814` | **S-1 合同测**：破极值短笔须参与中枢（`test_extreme_breaking_short_stroke_feeds_pivot`） | `2a7b166` |
| `6616ea1` | **刷新基线**：几何/渲染等价闸 golden | `dc3fcb1` |

**验收注意**：

- 不要用 `git merge-base --is-ancestor 13c2163 main` 判「是否合入」——枝 SHA 与 main SHA 不同。  
- 应用 main 表内 SHA，或 `git diff main dc3fcb1 -- chan_geometry.py …`（关键文件应为空 diff）。

测锚：`test_chan_core` / `test_chanlun_stroke_stall` / `test_chanlun_correctness`（合计约 191 passed）/ 门禁 `run-gate-tests.sh`（698 passed, 4 skipped）。

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

**总判**：**几何已在 main，无需再开几何 PR**；语义无再改项。门禁 `698 passed, 4 skipped`。

---

## 4. 接手 Agent 待办

1. ~~查 Agent 复验~~ → **已完成**（见 §8 / §9）。  
2. ~~开几何 PR~~ → **取消**：main 已含等价 6 连；勿再以 feature 枝 6 SHA 开重复 PR。  
   - **勿**混威科夫 PR #58（`fix/wyckoff-b-card-spring-st-gh` 已另开）。  
3. **可选后续**（非本轮，均需**新 handoff** 授权）：  
   - S-2 快照测  
   - S-3 近笔截断（render only）  
   - N-3 实盘拧句巡检  
4. **文档维护**（可随时）：若发现仍有文案写「未 push / 用 13c2163 验 main」，改指向 §1 main SHA 表。

---

## 5. 可改 / 勿改

| 可改（后续 handoff 授权） | 勿改 |
|---------------------------|------|
| `chanlun_render.py` 人话（近笔截断/推演） | fusion / decision_view / 池分道 |
| 补 S-2 前后对照测 | `CHANLUN_MIN_BARS_PER_STROKE` 全局放宽 |
| `formulas.md` 同步 | 与威科夫 #58 混 PR；重复合几何枝 |

---

## 6. 分支关系

| 枝 | 用途 |
|----|------|
| `main`（含 `39222f3…6616ea1`） | **生产真相**：笔/段几何 + S-1 测 + 基线 |
| `cursor/chanlun-stroke-geom-nangwang` @ `dc3fcb1` | 历史实现枝；内容已对等进 main；**勿再当未合入源** |
| `fix/wyckoff-b-card-spring-st` / `*-gh` | 威科夫展示；PR #58；**勿混** |

## 7. Git 备忘

```bash
# 验收是否在 main（用 main SHA，不要用 13c2163…）
git merge-base --is-ancestor 6616ea1 main && echo ok

# 或与历史枝尖内容对等
git diff main dc3fcb1 -- \
  02-共享模块-shared/trader_shared/chan_geometry.py \
  02-共享模块-shared/tests/test_chanlun_stroke_stall.py
# 期望：空

bash scripts/run-gate-tests.sh   # 698 passed, 4 skipped
python3 -m pytest \
  02-共享模块-shared/tests/test_chanlun_stroke_stall.py \
  02-共享模块-shared/tests/test_chan_core.py \
  02-共享模块-shared/tests/test_chanlun_correctness.py -q
```

---

## 8. 复验记录（2026-08-04，几何枝 @ 7e36685）

**挖 Agent 二轮**（只读：5 票实盘 + 开关探测）：

| ID | 复验证据 | 判 |
|----|----------|-----|
| S-2 | 5 票实盘（南网/华工/中际/曙光/中航）**零假买卖点**；中际「类一卖（观察）1416.88」为合法观察档，不冒充正式；合成 bars 开关 §2.1c 短笔 → 买卖点/中枢/结构**零差异**（未触发短笔形态处无影响） | ✅ 无假信号 |
| S-3 | 近笔序列 `↑↓↑↓↑` 5 票均**稳定**（笔数 23/34/36/34/29），无笔碎噪声爆表；中枢 1~9、段 1~3 均正常 | ✅ 无噪声问题 |
| N-1 | 周/日口径复验：华工/曙光/中际/中航 周「高点已离开·向下未成笔」与日「向下笔」一致；**南网**周「低点已离开·向上未成笔」vs 日「拉升段·向上笔」——诊断确认**非 bug**：周线末笔 down 75.0→37.8，现价 45.5 高于终点 20.4% → `down_left`（低点已离开·向上未成笔）正确；日线「拉升段·向上笔」是本波笔，属**正常多级别叠加** | ✅ 无真洞 |

**总判**：S-2 / S-3 / N-1 **均无真洞**，不授权改几何语义。门禁复验 `run-gate-tests.sh` 698 passed（geom 枝），几何专项 191 passed。

---

## 9. SOP 三轮复验（2026-08-04，`main` @ `56360a7`）

> 方法：SOP dig → check（只读）。Orca/外部 worker 提权未过时，父会话串行等价执行。  
> 产物：`.tmp/chanlun-sop-recheck/{dig,check,parent_synthesis}_report.md`（本地，可不入库）

| 检查 | 结果 |
|------|------|
| handoff 枝 SHA `13c2163…dc3fcb1` 是否 main 祖先 | ❌ 否（预期：枝 hash） |
| main 等价链 `39222f3…6616ea1` 是否 HEAD 祖先 | ✅ 是 |
| `git diff HEAD dc3fcb1` 关键几何/测文件 | ✅ 空（内容对等） |
| S-1 `test_extreme_breaking_short_stroke_feeds_pivot` | ✅ passed |
| 缠论专项 stall+core+correctness | ✅ 191 passed |
| 门禁（本轮前已跑） | ✅ 698 passed, 4 skipped |
| S-1…S-3 / N-1…N-4 真洞 | ✅ **无新真洞** |

**总判**：与 §3/§8 一致——**无新 bug；几何已在 main；S-2/S-3 观察项需新 handoff 才可动**。本文 §0/§1/§4/§6/§7 已按本轮纠正「未 push / 用错 SHA 验收」的文档噪音。

---

## 10. 五票 smoke 复跑（2026-08-04 · 离线缓存）

> **通道**：沙箱无外网 DNS；`final_chanlun` 全链路拉行情失败（数据不足兜底）。  
> **改用** `~/.trader/cache/daily` 日线 → `chanlun_analysis` + `build_chanlun_view` + `_collect_points`（引擎/分层真相；非 UI 全链路）。  
> **产物**：`.tmp/chanlun-sop-recheck/smoke5/summary.json`

| 票 | 代码 | 缓存截至 | 日笔数 / 近5 | 周笔数 / tip | 买卖点（引擎 type） | S-2 |
|----|------|----------|--------------|--------------|---------------------|-----|
| 南网科技 | 688248 | 2026-07-31 | 24 / ↑↓↑↓↑ | 3 / — | 日 类二卖 | ✅ 观察未进正式灯 |
| 华工科技 | 000988 | 2026-07-29 | 24 / ↓↑↓↑↓ | 19 / up_left | 日 类一买 | ✅ |
| 中际旭创 | 300308 | 2026-07-22 | 10 / ↓↑↓↑↓ | 13 / up_left | 周 **类一卖** @1416.88 | ✅ 与 §8 同价观察档 |
| 曙光数创 | — | 无本地日线缓存 | — | — | — | ⏭ 跳过 |
| 中航光电 | 002179 | 2026-07-30 | 50 / ↑↓↑↓↑ | 14 / up_left | 日 类二卖 | ✅ |

**S-2**：4/4 可跑票 **零假正式**（`类一*`/`类二*` 只进 observe；`formal_keys` 无泄漏）。  
**S-3**：近笔 `↑↓` 交替稳定；日笔数 10–50（中航缓存更长→笔更多，属样本窗差异，非碎笔爆表）。中枢/段均有输出。  
**N-1**：华工/中际/中航周线 `tip=up_left`（高点已离开语义源字段在）；与 §8 多级别叙事不冲突。  
**限制**：未重跑联网 `final_chanlun` 全卡；render slim 因 `chanlun_analysis` 成功体未带 `timeframe` 字段，view 层 `data_ok` 在本离线缝被标 false（生产 `build_chanlun_plan`/strategy 路径会写 timeframe——**不在本轮改几何**；若修缝另开 handoff）。

**总判**：离线 4 票支持 §8「S-2/S-3/N-1 无真洞」；不授权改 detect / min_bars / 截断。
