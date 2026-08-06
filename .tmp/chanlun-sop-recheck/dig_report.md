# 挖 Agent 报告 — 缠论笔几何后续（2026-08-04）

> 角色：scout / 只读  
> HEAD：`56360a7` on `main`（跟踪 `github/main`）  
> 法源：`docs/plans/chanlun-stroke-narrative-followup-handoff.md`；`formulas.md` §2–§3 / §6

## 0. 基线事实

| 项 | 证据 |
|----|------|
| handoff 6 SHA `13c2163…dc3fcb1` | 对象存在，但 **不是** `main`/`github/main`/`origin/main` 祖先 |
| 等价合入（main 上） | `39222f3` 笔衔接/破极值短笔 → `a72c987` 更深底 → `46084ee` 未完成段纠偏 → `682dbce` §3.5b 并回 → `1c47814` S-1 合同测 → `6616ea1` 刷新几何/渲染基线 |
| 内容对等 | `git diff HEAD dc3fcb1 -- chan_geometry.py chanlun_render.py chanlun_run.py test_chanlun_stroke_stall.py` **空** |
| 专项测 | `test_chanlun_stroke_stall` + `test_chan_core` + `test_chanlun_correctness` → **191 passed** |
| S-1 单测 | `test_extreme_breaking_short_stroke_feeds_pivot` **passed** |

> 注：handoff 写「几何枝 6 commit 在位」用的是 **feature 枝 hash**；main 上是 **另一组 hash、同内容**。复验应用 main 等价链，勿只 `merge-base --is-ancestor 13c2163`。

## 1. 分 ID 证据

### S-1 破极值短笔须参与中枢 — ✅ 合同锁
- **formulas** §2.1c：短距反向破上一笔起点极值可成笔  
- **代码** `chan_geometry._reverse_breaks_prior_extreme` + `build_strokes`：`dist_ok or _reverse_breaks_prior_extreme(...)`  
- **测** `test_chanlun_stroke_stall.test_extreme_breaking_short_stroke_feeds_pivot`：造短上笔 length<4 → `build_zones` 得 valid 中枢且 zh_top>zh_bottom  
- **对齐** §2.1c + §4（短笔不因 length 丢中枢）

### S-2 假买卖点 / signal_tier — ⚠️ 无真洞证据（保留观察）
- **detect** `chan_structure` 分正式一类 vs 类一/类二观察档（粘连离开不升格正式）  
- **render** `_OBSERVE_TYPE_PREFIXES` + `（观察）` 后缀；正式六灯与观察分列  
- **未发现** 把观察档写成正式一/二/三类的代码路径；无新假点硬复现  
- 初判：⚠️ 产品观察项，非本轮真洞

### S-3 近笔噪声 — ⚠️ 产品取舍
- `CHANLUN_MIN_BARS_PER_STROKE` 仍为默认 5；§2.1c 仅破极值破例  
- 无「全局放宽 min_bars」生产改动  
- 近笔截断属 render 议题，handoff 明确需新授权  
- 初判：⚠️ 不改笔规则

### N-1 跨级/叙事拧句 — ⚠️ 无新硬证据
- 本轮未跑 5 票联网 smoke（只读本地）  
- 段纠偏：`46084ee` / §3.5 未完成唯一段；几何内容与 `dc3fcb1` 对等  
- 初判：沿用 handoff 二轮「非 bug」；无新反证

### N-2 tip_leave（C-D4e）— ✅ 合同锁
- **handoff/C-D4e**：末笔 tip 高、现价反向离开 → 降级文案  
- **run** `chanlun_run`：`tip_leave = _stroke_tip_left_against(strokes, price)` 写入 view  
- **render** `_tip_leave_label`；正式买且无 tip_leave 才可盯（slim-b §2.4 表）  
- geom 枝未改 tip 计算语义；现码仍在

### N-3 推演拼句 — ⚠️ 无拧句硬证据
- 推演在 render；与 `dc3fcb1` render diff 空  
- 无新拧句样本

### N-4 并回后段/中枢 — ✅ 由基线锁定
- **代码** `chan_geometry._absorb_unfinished_down_at_high`（§3.5b）  
- **formulas** §3.5b  
- golden/等价闸经 `6616ea1` 刷新；内容对等 dc3fcb1

## 2. 挖 Agent 总判

- **无新真洞（❌）**  
- handoff「可合 PR / 几何无再改项」在 **main 等价链 + 内容对等 + 191 passed** 下成立  
- 唯一文档噪音：handoff §1/§7 用 feature 枝 SHA 验收会误报「不在 main」——应改注 main 等价 SHA 或写「内容对等 dc3fcb1」

DIG_DONE
