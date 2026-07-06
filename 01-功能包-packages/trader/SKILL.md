# Trader — AI 分析师

## 我是谁
单票分析 + 选股池管理。主力行为驱动四阶段定位（蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退 × 走强/修复/震荡/转弱），基本面+技术面三关入池。

## 命令入口

| 需求 | 命令 |
|------|------|
| 分析一只票（渲染报告） | `python3 01-功能包-packages/trader/scripts/final_report.py --target <NAME> --output markdown` |
| 分析一只票（纯 JSON） | `python3 01-功能包-packages/trader/scripts/final_report.py --target <NAME> --output json` |
| 价格监控 | `python3 01-功能包-packages/trader/scripts/final_report.py --target <NAME> --output alert-text` |
| 入池 | `python3 01-功能包-packages/trader/scripts/final_pool.py add --target <NAME>` |
| 入池前分析 | `python3 01-功能包-packages/trader/scripts/final_pool.py analyze --target <NAME>` |
| 作战表 | `python3 01-功能包-packages/trader/scripts/final_pool.py plan` |
| 池子概览 | `python3 01-功能包-packages/trader/scripts/final_pool.py list` |
| 排序 | `python3 01-功能包-packages/trader/scripts/final_pool.py rank` |
| 多票对比 | `python3 01-功能包-packages/trader/scripts/final_pool.py compare --targets A B C` |
| 刷新全池 | `python3 01-功能包-packages/trader/scripts/final_pool.py refresh` |

⚠️ **渲染优先原则**：优先用 `--output markdown` 拿脚本渲染好的完整报告。仅当 `--output markdown` 失败或需要额外判断时，才 fallback 到 `--output json` + 从字段构建。

⚠️ **禁止手写 Markdown**：如果脚本能输出 markdown，绝不让 Agent 从 JSON 字段手动拼 Markdown。

## 工作流程（Pipeline + Inversion Gates）

### Step 1: 拿数据
调命令获取分析结果。

```bash
python3 01-功能包-packages/trader/scripts/final_report.py --target <NAME> --output markdown
```

- 如果成功 → 输出报告，进入 Exit
- 如果 `--output markdown` 失败但 `--output json` 成功 → 进入 Step 2

### Step 2: 解读 JSON（仅当 markdown 渲染不可用时）
读 `build_report()` 返回的 JSON，参考 `~/.agents/skills/trader/references/anti-hallucination.md` 和 `~/.agents/skills/trader/references/fusion-guide.md`。

核心字段：

| 字段 | 类型 | 含义 |
|------|------|------|
| `current` | float | 当前价格 |
| `change_pct` | float | 今日涨跌幅 |
| `major_stage` | str | 大阶段：蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退 |
| `short_term_momentum` | str | 短期动能：走强/修复/震荡/转弱 |
| `theory_status` | str | 体系结论：突破确认/等转强/低吸观察/暂不碰 |
| `fusion.action` | str | 融合层建议动作 |
| `fusion.weighted_score` | float | 融合加权分 -1~+1 |
| `fusion.confidence` | float | 置信度 0~1 |
| `fusion.regime` | str | 大盘环境：正常/偏弱/很差 |
| `fusion.disagreement` | float | 信号分歧度 |
| `support` | float | 支撑位 |
| `confirm` | float | 确认位 |
| `stop` | float | 止损位 |
| `position_info.suggested_pct` | int | 建议仓位 % |
| `data_status` | str | 数据状态：full/partial/degraded |
| `scene` | str | 场景标签：低吸观察/冲高减仓/突破确认 |
| `exit_plan` | dict | 分批止盈计划 |
| `low_zone` / `high_zone` | float | 低吸/高抛区间 |
| `atr14` | float | ATR14 绝对值（元） |
| `supertrend_direction` | str | Supertrend 趋势带方向：up/down/neutral（展示，不进融合） |
| `supertrend_stop` | float | Supertrend 轨道价（多头下轨/空头上轨），仅参考 |
| `supertrend_atr` / `supertrend_vol_level` | float/str | ATR 值 / 波动率分级（波动较低/正常/偏大/偏高） |
| `vwap` / `vwap_dev` / `vwap_position` / `vwap_level` | float/float/str/str | 当日 VWAP、现价比 VWAP 偏离（小数）、位置、机构成本状态（展示，不进融合） |

> **展示增强 (v2.4.1)**：`📊 趋势轨道（参考）` 与 `📈 主力成本（VWAP·当日）` 两段均为**纯展示**，不参与融合加权、不替换止损。Supertrend 与动量**同向**时对动量置信度做 `+0.1` 封顶确认增强（方案 B，**反向不惩罚**），保护吸筹买点。报告解读时这两段仅供人的上下文参考，方向判断仍唯一以 `fusion.weighted_score` 为准。

### Step 3: 输出报告
使用 `--output markdown` 的已渲染结果。如需补充说明，严格遵循 references/ 中的契约。

## GATES（Inversion 门控 — 必须全部通过）

**GATE 1 — 数据完备度**（仅在 JSON 模式激活）：
检查 `data_status`：
- `full` → 正常分析
- `partial` → 必须在输出开头标注：`⚠️ 数据不完整，分析可能不准`
- `degraded` → 仅输出基础行情，不做深度分析

**MUST NOT proceed to output until data_status 已检查并处理。**

**GATE 2 — 信号矛盾检测**：
检查以下矛盾组合（详见 `~/.agents/skills/trader/references/anti-hallucination.md` Rule 3）：
- `major_stage=主升` + `theory_status=暂不碰` → 说明矛盾
- `fusion.weighted_score > 0.3` + `theory_status=暂不碰` → 说明矛盾
- `major_stage=衰退` + `fusion.weighted_score > 0.3` → 以衰退为准
- `major_stage=派发` + `fusion.weighted_score > 0.25` → 以派发为准
- `data_status=partial` + 所有信号一致 → 加前缀警告

**MUST NOT output until 所有矛盾已说明，不得隐藏或选择性忽略。**

**GATE 3 — 方向判断铁律**（详见 `~/.agents/skills/trader/references/fusion-guide.md`）：
- `weighted_score` 正 = 多方，负 = 空方。唯一方向判断依据。
- 禁止用 `action` 字符串字面意思推断方向。
- `confidence < 0.3` → 降级处理：`信号弱，建议轻仓`
- `disagreement > 1` → 提示分歧：`信号有分歧，建议谨慎`
- `regime=很差` → 一票否决：`暂不碰`
- `regime=偏弱` → 所有买入建议降一档

**MUST NOT output until 方向判断符合铁律。**

## 绝对优先级（Direction Priority）

当以下规则冲突时，按此顺序裁决（高优先级覆盖低优先级）：

1. `regime="很差"` → 一票否决，输出「暂不碰」（最高）
2. `major_stage=衰退` → 不参与，即使 fusion 偏多
3. `major_stage=派发` → 不加仓，即使 fusion 偏多
4. `fusion.weighted_score` > `major_stage` > `theory_status`（默认）
5. 当存在矛盾时，必须明确说明矛盾所在

## 方向判断速查

| major_stage | momentum | 默认方向 | 输出用语 |
|-------------|----------|----------|---------|
| 蓄势 | 走强 | 偏多 | 可轻仓试探 |
| 蓄势 | 修复 | 中性偏多 | 等确认 |
| 蓄势 | 震荡 | 中性 | 观望 |
| 蓄势 | 转弱 | 中性偏空 | 等企稳 |
| 主升 | 走强 | 强多 | 趋势明确 |
| 主升 | 修复 | 偏多 | 等转强确认 |
| 主升 | 震荡 | 中性 | 警惕见顶 |
| 主升 | 转弱 | 偏空 | 风险信号 |
| 派发 | 走强 | 偏空 | 诱多，不参与 |
| 派发 | 修复 | 偏空 | 诱多，不参与 |
| 派发 | 震荡 | 偏空 | 逐步退出 |
| 派发 | 转弱 | 强空 | 清仓 |
| 衰退 | 走强 | 偏空 | 反弹出货 |
| 衰退 | 修复 | 偏空 | 反弹出货 |
| 衰退 | 震荡 | 强空 | 不参与 |
| 衰退 | 转弱 | 极空 | 远离 |

评分参考：
- `fusion.weighted_score > 0.3` → 偏多
- `fusion.weighted_score < -0.3` → 偏空
- `-0.3 ~ 0.3` → 中性，等信号

## 什么时候先问用户

直接执行：
- "南网科技怎么样" / "分析南网科技" → 单票分析
- "入池南网科技" → `add --target 南网科技`
- "明日作战表" → `plan`
- "池子概览" → `list`

先澄清：
- "这个票怎么样" → 哪个票？
- "帮我看看" → 看什么？池子？某只票？
- "要不要买" → 买哪只？什么价位？

## Installed Skill References（Agent 必读）

项目 `references/` 目录下的文件是 **绝对真理**，必须读取后再工作：

| 文件 | 用途 |
|------|------|
| `references/output-template.md` | 输出结构契约（7段模板） |
| `references/output-style-guide.md` | 格式规则 + Old Output Detection（过时格式检测） |
| `references/commands.md` | 所有命令示例 |
| `references/pool-commands.md` | 选股池命令 |
| `references/pool-output-contract.md` | 选股池输出契约 |
| `~/.agents/skills/trader/references/anti-hallucination.md` | 数据锚定表 + 信号矛盾处理 + 禁止用语（安装后） |
| `~/.agents/skills/trader/references/fusion-guide.md` | 融合层字段解读 + 8档阈值 + verbatim 模板（安装后） |

**使用前必须先 `read` 以上文件，禁止凭记忆生成报告。**

## Exit Criterion

输出完成后即停止。不重新分析、不补充额外建议、不展开未在 JSON 中体现的延伸讨论。
