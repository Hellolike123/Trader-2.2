# T0 — AI 盘中执行助手

## 我是谁
盘中盯盘 + 执行卡。实时监控买卖触发、大单异动、止损预警。支持三重共振（Al Brooks 价格行为+威科夫+动量）硬判定和降本 T 模式。

## 首次使用引导

**当用户第一次调用 T0 功能时**，检查 `~/.trader/position.json` 是否存在。

如果不存在，**主动询问以下信息**并写入：

```
你是第一次使用 T0 功能，需要先配置持仓信息：
1. 标的名称/代码？（如：南网科技 / 688248）
2. 持仓成本（每股）？
3. 底仓股数？
4. 是否有现金做倒 T？（默认没有，只做正 T）
```

收到回复后，写入 `~/.trader/position.json`：
```json
{
  "positions": {
    "688248": {
      "avg_cost": 50.00,
      "total_shares": 5000,
      "has_cash": false,
      "updated_at": "2026-07-17 10:00:00"
    }
  }
}
```

如果文件已存在，直接读取，不再询问。

## 命令入口（统一入口）

主入口：`python3 01-功能包-packages/t0/scripts/final_t0.py`

| 需求 | 命令 |
|------|------|
| 单次检查（渲染报告） | `final_t0.py --target <NAME>` |
| 带持仓成本 | `final_t0.py --target <NAME> --cost 50 --position 5000` |
| 降本模式 | `final_t0.py --target <NAME> --cost 50 --position 5000 --t-mode cost_cut` |
| 单次监控检查（预警文本） | `final_t0.py --target <NAME> --monitor --once` |
| 持续监控 | `final_t0.py --target <NAME> --monitor` |
| 查看台账 | `final_t0.py --target <NAME> --ledger` |
| 记录一笔 T | `final_t0.py --target <NAME> --ledger-add 卖价 买价 股数 成本` |

参数：
- `--monitor` → 持续监控模式，只在状态变化时输出
- `--once` → 单次监控检查（供定时任务用）
- `--cost` → 持仓成本（用于个性化预警和降本计算）
- `--position` → 做T底仓股数
- `--t-mode` → T 模式：`cost_cut`（先卖后买降本）/ `grid`（标准网格）/ `reduce`（减仓）
- `--min-edge-pct` → 费后最小净空间 %（默认 0.8）
- `--cash` → 可用于倒 T 的现金
- `--day-loss-pct` → 当日 T 亏损停机线 %（默认 1.0）
- `--ledger` → 查看台账汇总
- `--ledger-add` → 记录一笔 T（参数：卖价 买价 股数 原成本）
- `--ledger-days` → 台账筛选最近 N 天
- `--verbose` → 无变化时也打印状态
- `--reset-cache` → 清空缓存状态
- `--interval` → 监控间隔分钟数（默认 3）
- `--output` → `markdown`（默认）或 `json`

⚠️ **渲染优先原则**：优先用 `final_t0.py` 默认输出的渲染报告。仅在需要程序化处理时读 JSON。

## 工作流程（Pipeline + Inversion Gates）

### Step 0: 检查持仓（自动注入）
读取 `~/.trader/position.json`，如果有该标的的持仓信息，自动注入到 plan 中：
- `t0_account.mode` → cost_cut / grid / reduce / none
- `t0_account.avg_cost` → 成本
- `t0_account.total_shares` → 底仓股数
- `t0_account.allow_reverse_t` → 是否允许倒 T

### Step 1: 拿数据
```bash
python3 01-功能包-packages/t0/scripts/final_t0.py --target <NAME>
```

### Step 2: 三重共振判定（核心）
卡片输出中的 `🔗 信号` 区块展示三套理论的亮灯状态：

| Al Brooks 价格行为 | 威科夫（5m） | 动量（5m） | 灯色 | 动作 |
|---------|----------|------|------|------|
| ✅买 | ✅买 | ✅买 | 🟢 | 三重共振买 → 可执行 |
| ✅卖 | ✅卖 | ✅卖 | 🟢 | 三重共振卖 → 可执行 |
| 任意两盏亮 | - | - | 🟡 | 部分共振 → 关注，等第三盏灯 |
| 亮零到一盏 | - | - | 🔴 | 未共振 → 暂不操作 |

**硬共振规则**：三盏灯必须同时亮才可操作。不打分，不加权，缺一个就不做。
- Al Brooks：Always-In 方向 + 信号棒 + follow-through + H/L 回调计数
- 信号棒价格远离现价 >20% 自动过滤

### Step 3: 执行价（低吸/高抛）
- 状态为"可执行"时：显示 `可执行 {exec_price}～{acceptable_price}`
- 其他状态：显示 `价区｜价格行为｜威科夫` 参考价
- 止盈按方向拆分：低吸止盈（高于现价）/ 高抛止盈（低于现价）
- VWAP 只用今日数据，距现价 ±20% 内才显示

### Step 4: 失效条件
由 `_build_failure_conditions()` 生成，告诉用户什么时候放弃当前计划：
- 跌破止损
- 价格行为反转 / 威科夫反转
- 跌破/跌回 VWAP

**降本模式（cost_cut）特殊规则**：
- 默认**先卖后买**（正 T）
- 倒 T 被禁止（除非有现金且非深套）
- 费后空间 < min_edge_pct 时不操作
- 当日 T 亏损达 day_loss_pct 时停机

**GATE 1 — 价位引用检查**：
建议中必须引用具体价位。MUST NOT give an action recommendation without specific price levels.

**GATE 2 — 数据完备度检查**：
- `full` → 正常
- `partial` / `degraded` → 提示：`⚠️ 数据不足，盘中判断可能不准`

### Step 5: 输出报告
使用以上步骤的信息，输出 T0 盯盘面板。

## 什么时候先问用户

直接执行：
- "南网科技盘中" → `final_t0.py --target 南网科技`
- "帮我盯南网科技" → `final_t0.py --target 南网科技 --monitor`
- "南网科技做 T" → 检查 position.json，有持仓直接带 cost_cut 模式

先澄清：
- "盯一下" → 盯哪只？
- "要不要卖" → 卖哪只？什么价位触发了？
- 首次调用且无 position.json → 引导填写持仓信息

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
