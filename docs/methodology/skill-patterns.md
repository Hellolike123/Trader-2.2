# Skill 设计方法论 — Google ADK 5 模式

> **来源**：Google Cloud Tech, "5 Agent Skill Design Patterns Every ADK Developer Should Know" (2026-03-18)
> **作者**：Shubham Saboo, Lavi Nigam
> **核心价值**：不是"怎么写 prompt"，而是"用什么结构组织 SKILL.md 才能让 Agent 稳定执行"

---

## 5 种模式概览

| 模式 | 一句话 | 核心目录 |
|------|--------|----------|
| Tool Wrapper | 让 Agent 调某个工具/API 时像专家 | `references/` |
| Generator | 让 Agent 每次输出结构一致 | `assets/` + `references/` |
| Reviewer | 让 Agent 按检查清单评分 | `references/` |
| Inversion | 让 Agent 先提问再行动 | SKILL.md（纯指令） |
| Pipeline | 让 Agent 按步骤走完不能跳 | `scripts/` + SKILL.md |

---

## 模式 1：Tool Wrapper（工具包装器）

### 定义
把外部工具/API/框架的约定和最佳实践封装成 Skill。Agent 只在处理相关技术时才加载这些知识，不被无关知识污染上下文。

### 结构
```
skill-name/
├── SKILL.md           ← 监听关键词 + 加载 references/ 的指令
└── references/
    └── conventions.md ← 工具的具体约定（API 参数、最佳实践、反模式）
```

### SKILL.md 核心写法
```markdown
---
name: api-expert
description: FastAPI development best practices. Use when building, reviewing,
  or debugging FastAPI applications, REST APIs, or Pydantic models.
---

## Core Conventions
Load 'references/conventions.md' for the complete list.

## When Reviewing Code
1. Load the conventions reference
2. Check the user's code against each convention
3. For each violation, cite the specific rule and suggest the fix

## When Writing Code
1. Load the conventions reference
2. Follow every convention exactly
```

### 关键原则
- `description` 必须精确描述触发场景（Use when: ...）
- 规则放 `references/`，指令放 SKILL.md——分离"是什么"和"怎么做"
- 不要把所有规则塞进 SKILL.md，用 `Load 'references/...'` 按需加载

### 本项目示例
- `coros-data-fetch`：包装 `coros_api` Python 模块 + 双人格系统
- `trader-indicator-enhancement`：包装 Trader 的 Plugin 架构
- `karpathy-engineering-guidelines`：注入工程执行准则

---

## 模式 2：Generator（生成器）

### 定义
Agent 作为"模板填充器"——不重新设计输出结构，而是填入数据。确保每次输出格式完全一致。

### 结构
```
skill-name/
├── SKILL.md           ← 「Fill this template. Do not change structure.」
├── assets/
│   └── template.html  ← 输出模板（HTML/JSON/Markdown 等）
└── references/
    └── style-guide.md ← 风格/语气规则
```

### SKILL.md 核心写法
```markdown
## Output Rules
1. Load 'assets/report-template.html'
2. Fill the template with the user's data
3. Do NOT change the template structure, sections, or CSS
4. Load 'references/style-guide.md' for tone and formatting
```

### 关键原则
- **模板必须在 `assets/` 中显式存在**——不能让 Agent "心里记得"模板长什么样
- 指令必须说「Do NOT change structure」——Agent 天然倾向于"优化"
- 考虑加 section checklist（要求 Agent 输出前逐项打勾）

### 本项目示例
- `cycling-training-report`：深色主题 HTML 报告（模板应在 `assets/`）
- `drawio`：draw.io 图生成

---

## 模式 3：Reviewer（审查器）

### 定义
Agent 按检查清单对输出逐项评分，生成按严重程度分组的审查报告。

### 结构
```
skill-name/
├── SKILL.md           ← 审查协议（怎么审）
└── references/
    └── checklist.md   ← 检查清单（审什么）
```

### SKILL.md 核心写法
```markdown
## Review Protocol
1. Load 'references/checklist.md'
2. For each item in the checklist, determine: PASS / WARN / FAIL
3. Group findings by severity: 🔴 Critical / 🟠 Warning / 🟡 Info
4. For each FAIL, cite the specific rule and suggest the fix

## Output Format
### 🔴 Critical (must fix)
- [item] — [violation] → [fix]
### 🟠 Warning (should fix)
### 🟡 Info (consider)
```

### 关键原则
- **检查清单必须可执行**：说「检查是否存在 `print()` 调用」而不说「检查代码质量」
- 把"审什么"和"怎么审"分开：检查清单独立文件，协议在 SKILL.md
- 替换 `references/checklist.md` 即可用同一 Skill 做不同审查

### 本项目示例
- `review`（复盘的五层评分分析 — 目前检查清单散落在 SKILL.md，应独立）
- `google-skill-patterns`（审查 Skill 是否符合 5 模式）

---

## 模式 4：Inversion（反转/门控）

### 定义
Agent 在生成任何输出前，必须先主导对话，向用户提出结构化问题收集信息。翻转「用户问 → Agent 答」为「用户问 → Agent 反问 → 用户答 → Agent 执行」。

### 结构
```
skill-name/
└── SKILL.md           ← 纯指令（无 references/，无 assets/）
```

### SKILL.md 核心写法
```markdown
## ⛔ PHASE GATE — DO NOT SKIP

You are in Phase 1: Information Gathering.
DO NOT start building until you have collected ALL of the following:

- [ ] What is the target stock code?
- [ ] What is the user's current position (cost, shares)?
- [ ] What specific question does the user want answered?

Check each item off before proceeding to Phase 2.

When all items are checked: "✅ Phase 1 complete. Proceeding to Phase 2."
```

### 关键原则
- 用 `⛔ STOP. DO NOT PROCEED until...` 而非 `MUST NOT`——语言越强硬，Agent 越遵守
- 每个阶段以 `✅ Phase N complete` 显式结账——给 Agent 一个"我完成了"的信号
- 阶段不超过 3 个（GPT-4 在 3-5 轮内遵守好，5-10 轮后注意力稀释）

### 本项目示例
- `trader` 的 GATE 1/2/3（数据完备度 → 信号矛盾 → 方向铁律）
- `review` 的检查门控

---

## 模式 5：Pipeline（流水线）

### 定义
强制 Agent 按步骤顺序执行工作流，步骤间有显式验证门槛。

### 结构
```
skill-name/
├── SKILL.md           ← 步骤定义 + 流转控制
├── scripts/           ← 每个步骤对应的脚本
└── references/        ← 每步的参考文档
```

### SKILL.md 核心写法
```markdown
## Pipeline Steps (execute in order — do NOT skip)

### Step 1: Fetch Data
```bash
python scripts/fetch.py --target <NAME>
```
✅ Step 1 complete when: output contains "data_status: full"

### Step 2: Analyze
```bash
python scripts/analyze.py --input step1_output.json
```
✅ Step 2 complete when: output contains "weighted_score"

### Step 3: Render
```bash
python scripts/render.py --input step2_output.json
```
✅ Step 3 complete when: output is valid Markdown

⛔ DO NOT proceed to the next step until the current step's completion condition is met.
```

### 关键原则
- **每个步骤必须有可验证的完成条件**（不是"Step 1 做完"而是"Step 1 的输出包含 `data_status: full`"）
- 步骤间依赖必须显式（Step 2 的输入是 Step 1 的输出文件）
- 复杂 Pipeline 考虑用脚本而非 SKILL.md 控制流转（Google 文章指出 ADK 的 Pipeline 框架级支持最弱）

### 本项目示例
- `trader`：Step 1(拿数据) → Step 2(解读JSON) → Step 3(输出)
- `t0`：盘中盯盘 Pipeline
- `logo-generator`：Phase 1(信息收集) → Phase 2(生成)

---

## 混合模式

大多数生产级 Skill 是 2-3 种模式的混合。本项目最常见组合：

**Pipeline + Inversion + Generator**（trader / review / t0）：
```
Pipeline 定义步骤顺序
  ├── Step 1: Inversion 门控（数据完备才能进 Step 2）
  ├── Step 2: Inversion 门控（信号矛盾必须说明）
  └── Step 3: Generator 模板（按 output-template.md 填充）
```

**Tool Wrapper + Generator**（trader-indicator-enhancement）：
```
Tool Wrapper 提供 Plugin 架构知识
  └── Generator 产出标准化指标描述
```

---

## 设计决策树

编写新 Skill 时，用这个决策树确定模式：

```
需要调用外部工具/API？
├── 是 → 需要 Tool Wrapper
│   └── 输出格式必须一致？ → 加 Generator
└── 否
    ├── 需要先收集信息？ → Inversion
    ├── 多步骤且有依赖？ → Pipeline
    ├── 按清单审查？ → Reviewer
    └── 生成固定格式输出？ → Generator
```

---

## 常见反模式

| 反模式 | 表现 | 修正 |
|--------|------|------|
| **模糊 Generator** | 「生成一份报告」但没有模板 | 把模板放到 `assets/`，指令写「Fill this template」 |
| **软弱 Inversion** | 写「应该先检查」而非「⛔ STOP. DO NOT PROCEED」 | 用最强硬的否定句 |
| **无 checkpoint Pipeline** | Step 1/2/3 有顺序但没有完成条件 | 每步加 `✅ Step N complete when:` |
| **模板在脑子里** | 依赖 Agent "知道"报告结构 | 模板必须显式写在 `assets/` 或 `references/` 中 |
| **检查清单不可执行** | 「检查代码质量」 | 改为 「检查是否存在 print() 调用」「检查 import 是否来自 scripts/」 |

---

*此文档用于指导本项目的 Skill 设计与审查。任何新增或修改 Skill 时，应先参考本文档确定模式。*
