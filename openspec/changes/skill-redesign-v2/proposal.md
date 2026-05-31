## Why

当前三个 skill（trader/t0/review）采用"script-output"模式——AI 只管跑脚本原样转发输出，不解读、不建议、不推理。这导致：

1. AI 的智能完全浪费，只是转发器
2. 用户看到输出后追问"为什么"，AI 无法基于数据解释
3. 多票对比、操作建议等需要 AI 判断的场景无法支持
4. 输出格式是 Markdown（给人看的），AI 要从文本里猜字段含义，容易出错产生幻觉

需要将 skill 从"脚本转发器"升级为"AI 分析师"——AI 拿结构化数据做解读、给建议、回答追问。

## What Changes

### 输出格式升级
- 三个 skill 新增 `--output json` 模式，输出完整结构化 JSON（直接使用现有 report/review dict 的字段，不重新设计 schema）
- 保留现有 Markdown 输出作为人类可读格式
- AI 优先消费 JSON，避免从 Markdown 解析出错

### SKILL.md 重写
- 三个 skill 的 SKILL.md 从"原样转发"改为"AI 解读指南"
- 遵循 Google 5 种 Agent 技能设计模式：
  - **Tool Wrapper**：教 AI 怎么调命令、怎么读 JSON 字段
  - **Generator**：JSON schema + 输出格式模板
  - **Pipeline**：多步骤工作流（拿数据→解读→给建议）
  - **Inversion**：模糊查询时先澄清
  - **Reviewer**：防幻觉检查清单

### HERMES.md 输出规则更新
- 三个 skill 的 HERMES.md 需要更新输出规则
- 当前规则："脚本输出即最终格式，不要修改"（纯转发模式）
- 改为：双模式——给人看时原样转发，给 AI 用时读 JSON 做解读
- HERMES.md 不是 Hermes 框架的人格（那是 SOUL.md），是 skill 自己的配置，可以安全修改

## Capabilities

### New Capabilities
- `trader-json-output`: trader skill 的 --output json 模式
- `t0-json-output`: t0 skill 的 --output json 模式
- `review-json-output`: review skill 的 --output json 模式
- `skill-ai-guide`: 三个 SKILL.md 的 AI 解读指南

### Modified Capabilities
（无 spec 级别的行为变更，输出内容不变，新增 JSON 输出格式）

## Impact

- 修改文件：`final_report.py`（trader JSON 输出）、`t0_core.py`（t0 JSON 输出）、`review_render.py`（review JSON 输出）
- 重写文件：三个 SKILL.md + 三个 HERMES.md（输出规则更新）
- 新增文件：三个 `references/ai-guide.md`（AI 解读详细指南）
- 无新增依赖
- 现有 Markdown 输出不变
- 用户看到的输出格式不变（不加 --output json 时行为完全一样）
