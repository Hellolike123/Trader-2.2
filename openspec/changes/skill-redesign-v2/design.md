## Context

当前三个 skill 的 SKILL.md 指令是"跑脚本，原样转发，不许改"。AI 只是转发器，没有用到智能。用户需要 AI 能解读数据、给建议、回答追问。

参考 Google 的 5 种 Agent 技能设计模式（Tool Wrapper / Generator / Reviewer / Inversion / Pipeline），将 skill 从"script-output"升级为"AI analyst"。

## Goals / Non-Goals

**Goals:**
- 三个 skill 新增 `--output json` 模式，输出结构化数据
- 三个 SKILL.md 重写为 AI 解读指南
- 防幻觉机制：每个建议必须有数据支撑
- 保持现有 Markdown 输出不变

**Non-Goals:**
- 不改 SOUL.md（Hermes 框架人格层）
- 不重新设计 JSON schema（直接用现有 report/review dict 字段）
- 不改业务逻辑（输出内容不变）
- 不接入利弗莫尔 skill（单独设计）

## Decisions

### Decision 1: JSON 输出 — 直接序列化现有 report dict

**选择**: 将 `build_report()` 返回的 report dict 原样 JSON 序列化输出。

**原因**:
- report dict 已有 63 个字段，完整覆盖所有分析维度
- 不需要重新设计 schema，不会漏字段
- AI 学一次格式就能用

**实现**: `final_report.py` 已有 `--output json` 参数（line 1363），当前输出 `{"full_markdown": ..., "report": ..., "signal": ...}`。改为直接输出 report dict 的 JSON。

**补全缺失字段**: render_markdown() 中有几个动态生成的字段需要补进 report dict：
- `one_liner`: 由 `one_sentence()` 函数生成
- `t0_ref`: 由 levels 计算的 T0 参考价位（low_buy/high_sell）
- `macd_status`: 从 momentum_core 传入

### Decision 2: SKILL.md 结构 — 遵循 Google 5 模式

每个 SKILL.md 包含以下段落，对应 Google 的 5 个模式：

```
1. 我是谁（Tool Wrapper）
   职责边界、什么时候用这个 skill

2. 怎么调命令（Tool Wrapper）
   命令格式、参数说明

3. 怎么读数据（Generator）
   JSON 字段含义表、关键字段解释

4. 工作流程（Pipeline）
   Step 1: 拿数据 → Step 2: 解读 → Step 3: 给建议
   每步有明确的关卡检查

5. 解读框架（Generator）
   什么评分算好/差、信号矛盾怎么处理、市场环境如何影响判断

6. 什么时候先问用户（Inversion）
   模糊查询时先澄清，明确查询直接执行

7. 防幻觉规则（Reviewer）
   回答前必须自检的清单
```

### Decision 3: Pipeline — 三步走，每步有检查

**trader skill pipeline:**
```
Step 1: 拿数据
  调 final_report.py --output json
  检查: data_status 是否 full/partial/degraded
  关卡: degraded → 提示"数据不完整，分析可能不准"

Step 2: 解读数据
  读 scores → 总体评分
  读 signals → 信号方向
  读 fusion.action → 系统建议
  读 warnings → 风险
  检查: 信号是否矛盾（direction 不一致）
  关卡: 矛盾 → 说明矛盾在哪，建议等待

Step 3: 给建议
  基于 Step 2 解读
  检查: 每个建议是否有数据支撑
  关卡: 无支撑 → 改为"数据不足，无法给建议"
```

**t0 skill pipeline:**
```
Step 1: 拿数据
  调 t0 script --target <NAME> --once --output json
  检查: data_status 是否 live/stale
  关卡: stale → 提示"非交易时段，数据可能过期"

Step 2: 判断状态
  读 buy.status/sell.status → 当前该做什么
  读 big_orders → 有无大单异动
  关卡: 有大单 → 重点提示

Step 3: 给操作建议
  基于 Step 2 判断
  检查: 建议是否引用了具体价位
  关卡: 无价位 → 不给操作建议，只报状态
```

**review skill pipeline:**
```
Step 1: 拿数据
  调 review script --target <NAME> --output json
  检查: 数据完整性

Step 2: 分析走势
  读 theory.scores → 五层评分
  读 big_order → 主力态度
  读 theory.supports/blocks → 信号方向
  关卡: 评分低 + 看空信号多 → 提示风险

Step 3: 给明日策略
  基于 Step 2 分析
  检查: 策略是否引用了关键价位
  关卡: 无价位 → 不给策略，只报数据
```

### Decision 4: 防幻觉规则 — 三个 skill 共享

```markdown
## 防幻觉检查清单（每次回答前必须自检）

□ 我调了命令吗？
  没调 → 不能回答，先调命令

□ 我读的是 JSON 还是 Markdown？
  Markdown → 切换到 JSON

□ 我引用的数字来自 JSON 哪个字段？
  说不出来 → 不要用这个数字

□ 我的建议有数据支撑吗？
  "建议买入" → 评分多少？信号是什么？价位在哪？
  说不出来 → 改为"数据不足，无法给建议"

□ 数据状态是什么？
  partial → 提示数据不完整
  degraded → 提示数据可能不准

□ 有没有 warnings？
  有 → 必须在回答中提及

□ 我有没有编造任何内容？
  价格、评分、信号、建议 — 全部来自 JSON？
  有一个不是 → 删掉
```

### Decision 5: Inversion — 澄清规则

```
直接回答（不问）：
├─ "南网科技怎么样" → 明确是 trader
├─ "南网科技止损位多少" → 明确问价位
├─ "复盘南网科技" → 明确是 review
├─ "帮我盯南网科技" → 明确是 t0
└─ "明天作战表" → 明确是 trader plan

需要澄清（先问）：
├─ "这个票怎么样" → 哪个票？
├─ "帮我看看" → 看什么？池子？某只票？
├─ "要不要买" → 买哪只？什么价位？
└─ "最近怎么样" → 最近什么？大盘？持仓？池子？

规则：
├─ 用户说的能直接映射到命令参数 → 直接执行
├─ 有歧义 → 先问
└─ 宁可多问一句，不要猜错
```

### Decision 6: HERMES.md — 输出规则从"纯转发"改为"双模式"

**选择**: 修改三个 skill 的 HERMES.md，更新输出规则。

**原因**: 当前 HERMES.md 写死"脚本输出即最终格式，不要修改"，会阻止 AI 做任何解读。必须放开这个限制。

**当前规则** (三个 HERMES.md 相同):
```
脚本输出的文本是最终格式，不要修改任何内容
不要添加脚本输出以外的解释、建议或总结
```

**改为**:
```
双模式输出：
- 给人看时：脚本输出即最终格式，不要修改（保持原样）
- 给 AI 用时：读 JSON 输出，基于数据做解读和建议
- 解读时每个建议必须引用 JSON 中的具体字段
- 禁止从 Markdown 输出解析数据做判断
```

**影响范围**: `~/.hermes/skills/trader/HERMES.md`、`~/.hermes/skills/t0/HERMES.md`、`~/.hermes/skills/review/HERMES.md`

## Risks / Trade-offs

**[JSON 输出体积]** report dict 有 63 个字段，JSON 可能较大。
→ 缓解: AI 只需要读关键字段，不需要全部解析。可以在 SKILL.md 中标注"核心字段"和"可选字段"。

**[SKILL.md 长度]** 三个 SKILL.md 的 AI 指南可能较长，占用 context。
→ 缓解: 将详细字段表放在 references/ai-guide.md，SKILL.md 只放核心流程和规则。

**[AI 不遵循指令]** AI 可能仍然跳过 JSON 直接读 Markdown。
→ 缓解: SKILL.md 中明确写"必须先调 --output json，禁止读 Markdown 做判断"。

**[现有输出不变]** Markdown 输出保持原样，但 AI 不再消费它。
→ 缓解: Markdown 仍然输出给人看，AI 只读 JSON，两层分离互不影响。
