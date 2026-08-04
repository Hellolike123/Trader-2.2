# Agent 建议落地计划 — sync 脚本 + 渲染防御 check + 盯盘 prompt 刷新

- 日期: 2026-08-04
- 法源: 另一 Agent 建议（改造执行/架构/数据/流程四块）；用户批准其中 3 项低风险落地
- 读者: 写 Agent（实现 + commit）/ 查 Agent（独立对照 ✅/❌，默认不改码，列必须再改）
- 双 Agent 闭环后：父 Agent 修完 commit（**默认不 push**，沿用项目约定）

## 0. 范围（只做这 3 项）

| # | 改动 | 类型 | 理由 |
|---|------|------|------|
| 1 | `scripts/sync_skill_engines.sh`（新增） | 运维脚本 | 根治「仓库引擎 → skill 安装位副本漂移」（本轮曾手工回灌 6 副本且首轮漏 3 个） |
| 2 | `wyckoff_render.py` 渲染前防御 check | 防御性告警 | accum_confirmed ∧ phase_a failed 并存 → warning（不改输出；G 修复已防并存，此为兜底） |
| 3 | `automation-1784136710106` prompt 价位刷新 | 自动化配置 | 关键价位 46.88/50.66 为 6 月旧值；08-03 放量突破后当前结构 = TR 41.5~44.5、突破 45.50（08-04 收 47.12） |

## 1. 明确不做（防扩散）

- **#5 volume 统一为「股」**：与实测冲突（全源日线=手，amount 交叉验证 + 腾讯实时抓取已证）；FDE 轮周线 ×100 回退属合同裁决，单独开轮。
- #1（golden 基线）/ #2（依赖顺序）/ #4（锚点校验层）/ #6（主源写死）：已落地或等价物存在（四票测试 + 南网标本端到端 + tr_ctx.sc_anchor 统一注入），不重复做。
- 不改检测器逻辑、阶段权重、fusion/出手/池、周线路径。

## 2. 改动清单

### 改动 1 — scripts/sync_skill_engines.sh（新增，可执行）

- **源**：`02-共享模块-shared/trader_shared/*.py`（仓库规范）
- **目标**：`{~/.workbuddy/skills, ~/.hermes/skills}/{trader,t0,wyckoff,review}/scripts/trader_shared/`
- **同步规则**：仅同步**目标已存在**的 .py（不新增文件，避免污染 skill 特有结构）；逐个 diff，不一致才复制；复制后复 diff 校验
- **模式**：默认 sync；`--check` 只 diff 报告不改写（exit 1 = 有漂移）
- **输出**：每文件 ✓/✗ 明细 + 汇总（8 安装位一致 → exit 0）；幂等（重复跑无副作用）
- **验收**：① 跑 `sync` 后 8 安装位 × 全部 engine .py diff 全空；② 跑 `--check` exit 0；③ 修改仓库文件后 `--check` exit 1、`sync` 后恢复 0
- 禁止：不用 `rm` 清理目标目录；不碰 skill 包内非 trader_shared 文件；不写临时文件到仓库

### 改动 2 — wyckoff_render.py 渲染前防御 check（修改）

- **位置**：渲染主入口（渲染循环/单卡渲染函数开头，构造输出前）
- **逻辑**：`result.get("accumulation_confirmed")` 为真 且 `(result.get("phase_a_range") or {}).get("status") == "failed"` → `_logger.warning("[wyckoff] 矛盾字段: accumulation_confirmed=True 与 phase_a_status=failed 并存 ...")`
- **铁律**：只告警，**不修改渲染输出**（golden 无漂移）；`_logger` 用现有 logger（同文件既有用法）
- **测试**（tests/test_wyckoff_skill_render.py 或就近）：① 构造矛盾结果 → caplog 断言 warning 文案；② 正常结果（accum=False 或 phase_a 非 failed）→ 不告警；③ 渲染输出与无 check 时一致（不因告警改输出）
- 验收：新增测试过；`test_wyckoff_*.py` 全量过；门禁全绿；golden check 无漂移

### 改动 3 — automation-1784136710106 prompt 刷新（automation_update）

- 现状 prompt：关键价位 46.88（06-11 低点）/ 50.66（MA250），路径 A/B/C 按旧结构
- 新价位（以 08-03 突破后结构为准）：
  - 突破确认位 **45.50**（08-03 放量突破收盘，回踩不破 = 吸筹推进）
  - TR 上沿 **44.5**（07-21~07-31 横盘上沿，回踩支撑）
  - TR 下沿 **41.5**（横盘下沿，收盘破位 = 结构转弱）
  - 上方压力 **50.66**（MA250，保留）
- 路径判定更新：A 吸筹推进（回踩 44.5~45.5 不破 + 放量再上）；B 破位转弱（收盘 <41.5）；C 区间震荡（41.5~45.5 缩量横盘）
- 保留：tdx MCP 取数方式、威科夫三大定律框架、`非投资建议` 声明
- 验收：`automation_update view` 确认 prompt 含新价位且不含旧关键位描述

## 3. 提交

- 改动 1+2（代码）一个 commit；改动 3 为配置更新（不入 git，automation_update 直接生效）
- commit message 附本计划法源 + 对照项编号
- **不 push**

## 4. 双 Agent 分工

- **写 Agent**：只读本计划 + 代码锚点 → 实现 1/2/3 + 测试 → commit
- **查 Agent**：独立对照本计划逐项 ✅/❌（不改码），列「必须再改」清单；重点核对：sync 脚本规则/幂等、render check 不改输出、prompt 价位与 08-03 后结构一致、commit 内容
- **父 Agent**：查完修完 → commit 汇总 → 收尾
