# Trader 面板去掉「阶段：」行 — Agent Handoff

> 状态：规格冻结（用户 2026-08-02 确认：有威科夫定阶段则面板「阶段：」不需要）  
> 法源对齐：`BUSINESS.md` §2.0 / §2.2 / §4.0 / §5.1；`docs/designs/resonance-and-orchestration.md`（背景岗读周线威科夫 / `midline_stage`）  
> 实现锚点：`02-共享模块-shared/trader_shared/report_renderer/short_midline.py`

---

## 1. 产品裁决

### 1.1 做

1. **面板不再输出** `阶段：…` 行（中线区扫读改以 `威科夫：` 为阶段细读入口）。
2. **字段保留**：`midline_stage` / `conclusion.stage_line` / `midline_verdict.stage` 继续由周线威科夫短词写入；共振背景岗、池/门禁逻辑**零改语义**。
3. 原挂在「阶段：」行后的偏多/偏空短因（若有）**并入 `定论：`**（` · 偏空（…）` / ` · 偏多（…）`）；无定论时单独写 `定论：{偏多|偏空}（短因）`。禁止新开独立 `看法：` 行。
4. 亮点/风险：
   - **禁止**刷「中线阶段无阶段」；
   - 仅当 `stage_line` 为真实阶段词（吸筹/主升/主跌/派发…，非「无阶段」）才可写「中线阶段{词}」；
   - 无阶段且偏空：风险可用「中线偏空」或定论/威科夫已有语义，不重复「无阶段」。
5. 同步 `output-template.md`、`BUSINESS.md` §5.1、golden / baseline、相关断言；`output-style-guide.md` / `anti-hallucination.md` / `ai-guide.md` 中「面板阶段：」表述改为「字段 midline_stage，面板不单独成行」。

### 1.2 不做

1. 不改 `synthesize_midline_verdict` 的 stage 算法与词表。
2. 不改 `resonance._eval_background` 对 `无阶段` 的 fail-closed。
3. 不改 fusion / decision_view / chan_discipline / 池分道。
4. 不把日线 `major_stage` 写回任何中线展示行。
5. 不嵌威科夫/缠论 skill 详卡；不改详卡引用脚注（本迭代不做脚注）。

---

## 2. 中线区骨架（改后）

```text
🧭 中线
  定论：…（可选；可含 · 偏多/偏空（短因））
  威科夫：…          ← 周线；含阶段槽 · [箱体] · 事件 · 含义
  量度目标：…        ← 仅 L3
  缠论：…
  …
```

**禁止**再出现独立行 `阶段：…`。

---

## 3. 验收表

| ID | 必须 | 测 |
|----|------|-----|
| S-R1 | markdown 无 `阶段：` 行（允许正文他处「中线阶段吸筹」类亮点/风险，但不得「阶段：」标签行） | golden + contract |
| S-R2 | `midline_stage` / `stage_line` 仍写入；phase=none → `无阶段` | 现有 conclusion / stage_field 测 |
| S-R3 | 共振：`无阶段` 背景岗仍 fail-closed | `test_stage_field_discipline` |
| S-R4 | 禁止 `阶段：蓄势偏强`（日线冒充）仍成立 | mid_short_sources / key_prices |
| S-R5 | 有偏空短因时进入定论或单独定论行，不丢信息 | render 测或 golden |

---

## 4. 可改 / 勿改

**可改**

- `report_renderer/short_midline.py`
- `trader/references/output-template.md`、`output-style-guide.md`、`anti-hallucination.md`、`ai-guide.md`
- `BUSINESS.md` §5.1（及 §4.0 用途列：面板不再映射「阶段：」行）
- `AGENTS_DEEP.md` 微信满分骨架中的 `阶段：` 示例行
- golden / `fixtures/report_render_baseline.txt` / 相关 pytest 断言

**勿改**

- `conclusion_block.synthesize_midline_verdict` 算法
- `resonance.py` 背景岗逻辑
- `wyckoff_core` / `chan_core` 检测
- fusion / decision_view / 池分道
