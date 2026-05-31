## ADDED Requirements

### Requirement: SKILL.md 包含 AI 解读指南
三个 skill 的 SKILL.md MUST 包含以下段落：我是谁、怎么调命令、怎么读数据、工作流程（Pipeline）、解读框架、什么时候先问用户（Inversion）、防幻觉规则（Reviewer）。

#### Scenario: trader SKILL.md 结构
- **WHEN** AI 加载 trader skill
- **THEN** SKILL.md 包含命令调用方式、JSON 字段含义表、三步 Pipeline（拿数据→解读→给建议）、解读框架（评分标准、信号矛盾处理）、澄清规则、防幻觉检查清单

#### Scenario: t0 SKILL.md 结构
- **WHEN** AI 加载 t0 skill
- **THEN** SKILL.md 包含命令调用方式、JSON 字段含义表、三步 Pipeline（拿数据→判断状态→给操作建议）、澄清规则、防幻觉检查清单

#### Scenario: review SKILL.md 结构
- **WHEN** AI 加载 review skill
- **THEN** SKILL.md 包含命令调用方式、JSON 字段含义表、三步 Pipeline（拿数据→分析走势→给明日策略）、澄清规则、防幻觉检查清单

### Requirement: SKILL.md 引用 JSON 而非 Markdown
SKILL.md MUST 指示 AI 通过 `--output json` 获取结构化数据，禁止从 Markdown 输出解析数据。

#### Scenario: AI 调用时使用 json 输出
- **WHEN** AI 按 SKILL.md 指令调用命令
- **THEN** 命令包含 --output json 参数

#### Scenario: SKILL.md 禁止读 Markdown 做判断
- **WHEN** AI 阅读 SKILL.md
- **THEN** 其中明确写"禁止从 Markdown 输出解析数据做判断"

### Requirement: references/ai-guide.md 包含完整字段表
每个 skill 的 references/ai-guide.md MUST 包含 JSON 字段的完整说明，包括字段名、类型、含义、示例值。

#### Scenario: trader ai-guide.md 字段表
- **WHEN** AI 需要查询某个 JSON 字段的含义
- **THEN** ai-guide.md 中有该字段的说明和示例值
