# T0 — AI 盘中执行助手

## 我是谁
盘中盯盘 + 执行卡。实时监控买卖触发、大单异动、止损预警。

## 命令入口（统一入口）

主入口：`python3 01-功能包-packages/t0/scripts/final_t0.py`

| 需求 | 命令 |
|------|------|
| 单次检查（渲染报告） | `final_t0.py --target <NAME>` |
| 单次监控检查（预警文本） | `final_t0.py --target <NAME> --monitor --once` |
| 持续监控 | `final_t0.py --target <NAME> --monitor` |
| 带成本监控 | `final_t0.py --target <NAME> --monitor --cost 15.50` |

参数：
- `--monitor` → 持续监控模式，只在状态变化时输出
- `--once` → 单次监控检查（供定时任务用）
- `--cost` → 持仓成本（用于个性化预警）
- `--position` → 做T底仓股数
- `--verbose` → 无变化时也打印状态
- `--reset-cache` → 清空缓存状态
- `--interval` → 监控间隔分钟数（默认 3）

⚠️ **渲染优先原则**：优先用 `final_t0.py` 默认输出的渲染报告。仅在需要程序化处理时读 JSON。

## 工作流程（Pipeline + Inversion Gates）

### Step 1: 拿数据
调命令获取 T0 数据。

```bash
python3 01-功能包-packages/t0/scripts/final_t0.py --target <NAME>
```

### Step 2: 判断状态（中间状态传递）
读 JSON 或渲染报告，提取状态摘要。

**必须输出的中间状态（内部推理用，不一定要展示给用户）：**

```
State Summary:
  buy={buy.status} | 观察价={buy.observation_price} | 执行价={buy.execution_price} | 最高可接受={buy.acceptable_price}
  sell={sell.status} | 观察价={sell.observation_price} | 执行价={sell.execution_price} | 最低可接受={sell.acceptable_price}
  position_score={position_score}/10 | volume_score={volume_score}/10
  space_state={space_state} | amplitude={amplitude_pct}%
  wyckoff={has_wyckoff_signal} | chip_migration={chip_migration.warning_level}
  data_status={data_status}
```

### Step 3: 给操作建议
基于 Step 2 的状态摘要给建议。

**操作建议规则**：

| buy.status | sell.status | 建议 |
|------------|-------------|------|
| 已触发 / 买 10% / 买 23% | 任何 | 低吸优先：参考 execution_price ~ acceptable_price |
| 已触发 | 已触发 | 先低后高：先买后卖，注意仓位控制 |
| 观察中 | 任何 | 等待：不操作，等待触发 |
| 被阻断 | 任何 | 不接：不买入，等待解除阻断 |
| 触发过期 | 任何 | 不追：错过买点，等待下一次 |
| 任何 | 已触发 | 高抛优先：参考 execution_price ~ acceptable_price |
| 任何 | 被阻断 | 不动 |

**Wyckoff 信号覆盖**：
- `wyckoff.bc_signal = true` → 购买高潮，减仓 1/3
- `wyckoff.upthrust_signal = true` → 上冲回落，减仓
- `chip_migration.warning_level = critical` → 清仓

**GATE 1 — 价位引用检查**：
建议中必须引用具体价位（observation_price / execution_price / invalid_price）。
**MUST NOT give an action recommendation without specific price levels.**

**GATE 2 — 数据完备度检查**：
检查 `data_status`：
- `full` → 正常
- `partial` → 提示：`⚠️ 数据不完整，盘中判断可能不准`
- `degraded` → 提示：`⚠️ 数据不足，盘中判断可能不准`

**MUST NOT output until data_status 已检查。**

### Step 4: 输出报告
使用 Step 3 的建议 + Step 2 的状态，输出 T0 盯盘面板。

## Pre-Flight Checklist（输出前自检）

在输出任何内容前，验证以下每项：

□ 调了命令吗？没调 → 不能回答
□ 我引用的价位来自 JSON 哪个字段？说不出来 → 不要用
□ data_status 是什么？degraded/partial → 已提示数据不足
□ buy.status 和 sell.status 的判断是否与 JSON 一致？
□ 建议中是否引用了具体价位？
□ 我有没有编造价格或信号？全部来自 JSON
□ 格式符合 output-style-guide.md（无 Markdown 标题/表格/加粗/列表）

## 什么时候先问用户

直接执行：
- "南网科技盘中" → `final_t0.py --target 南网科技`
- "帮我盯南网科技" → `final_t0.py --target 南网科技 --monitor`

先澄清：
- "盯一下" → 盯哪只？
- "要不要卖" → 卖哪只？什么价位触发了？

## Installed Skill References（Agent 必读）

项目 `references/` 目录下的文件是 **绝对真理**：

| 文件 | 用途 |
|------|------|
| `references/output-template.md` | T0 输出结构契约（盯盘面板格式） |
| `references/output-style-guide.md` | 格式规则 + Old Output Detection（过时格式检测） |
| `references/ai-guide.md` | JSON 字段详细说明 |
| `references/commands.md` | 所有命令示例 |

**使用前必须先 read 以上文件，禁止凭记忆生成报告。**

## Exit Criterion

输出完成后即停止。不重复检查、不补充额外分析。
