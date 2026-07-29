# T0 — AI 盘中执行助手

## 我是谁
盘中 **结构参考卡**（策略 v2）。帮助人看清位置/量能/参考价/失效条件。  
**不做**机械信号下单指令；评分与灯色仅供参考。有持仓时可展示降本纪律与台账。  
法源：`docs/t0-strategy-v2.md`。

快路径：只读 `references/agent-quickstart.md` → 跑脚本 → 原样贴出 → 停。禁止预读全部 references；禁止默认 JSON。

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

### Step 2: 结构结论（核心 · 人决策）
主结论描述 **位置与强弱**，禁止「可低吸 / 可执行 / 三重共振买」指令句。  
模板见 `references/output-template.md`。

### Step 3: 参考价与评分（仪表）
- `📌 结构`：低吸/高抛 **关注价**（价到时写 `关注 a～b（参考）`；内部状态 `到价关注`，禁止 `可执行`）
- 无底仓：必须写「仅结构参考，不做 T 召唤」
- `🔗 参考`：五条件评分等，必须带「仅供结构参考，不构成执行指令」
- VWAP 只用今日数据，距现价 ±20% 内才显示

### Step 4: 看法失效
由 `_build_failure_conditions()` 生成：跌破止损参考 / 结构反转 / VWAP 等。  
语义是「看法何时作废」，不是系统强制下单。

**持仓纪律（展示，非自动单）**：
- 有持仓才展开降本/费后空间/倒 T 限制
- 费后空间、day_loss 为 **纪律提醒**，是否做 T 由人决定

**GATE 1 — 价位引用检查**：
结构描述须带具体价位或「暂无」。禁止空泛喊单。

**GATE 2 — 数据完备度检查**：
- `full` → 正常
- `partial` / `degraded` → 提示：`⚠️ 数据不足，盘中判断可能不准`

**GATE 3 — 指令句禁令（v2）**：
输出不得含：`可执行`（作主结论/价位标签）、`三重共振买/卖 →`、`可低吸`、`可加仓`、`做T指令`。

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

## 快路径与按需 references

首次使用只读 `references/agent-quickstart.md`。跑脚本拿渲染输出，原样贴出后停。

| 文件 | 何时读 |
|------|--------|
| `agent-quickstart.md` | 首次使用 |
| `output-template.md` / `output-style-guide.md` | 校验或怀疑格式不对 |
| `ai-guide.md` | 需要 JSON 字段时 |
| `commands.md` | 需要完整命令表 |

`references/` 仍是契约真理；**按需 read，禁止开工前批量读完。**

## Exit Criterion

输出完成后即停止。不重复检查、不补充额外分析。
