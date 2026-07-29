# Output Template — t0（策略 v2）

> **This is the absolute truth for valid output.** Never generate output format from memory.  
> 产品法源：`docs/t0-strategy-v2.md` — 结构参考卡 · 人决策 · 不做机械可执行指令。

## Structure Card Output

Markdown from `render_markdown()` — `final_t0.py` without `--monitor`.

Must start with `🎯`:

```text
🎯 {name}（{symbol}）{current_price}（{change_pct}）
  → {conclusion}

📌 结构
当前：观望 ｜ 止损参考：{stop}
{no_position_line}
低吸：{buy_display}
高抛：{sell_display}
{buy_tp_line}
{sell_tp_line}
VWAP {vwap}

🔗 参考
  评分 {score}/100 · 仅供结构参考，不构成执行指令
  {lights_line}
  看法失效：{failure_conditions}

💰 {capital_line}

{account_section}
```

### Conclusion（一句话，结构态）

由 `_build_conclusion()` 生成，**只描述位置/强弱**，禁止买卖指令句。

| 元素 | 示例 |
|------|------|
| vs VWAP | 价在VWAP上 / 价在VWAP下 / 价近VWAP |
| 评分带 | 结构偏强(n) / 结构中性偏上(n) / 结构偏弱(n) |
| 关注区 | 近低吸关注区 / 近高抛关注区（若状态命中） |
| 持仓 | 无底仓（无持仓时） |
| 收尾 | 宜观察 · 人决策 |

禁止结论出现：`可低吸` / `可加仓` / `可执行` / `三重共振买` / `轻仓试探`（作为系统指令）。

### 结构区（原「执行」）

- 标题固定 `📌 结构`（不再用「📌 执行」作默认主标题）。
- 价到关注区：显示 `关注 a～b（参考）`，**禁止** `可执行 a～b`。
- 无底仓：必须有一行 `持仓：无底仓 · 仅结构参考，不做 T 召唤`。
- 止盈行若有：仍可写低吸止盈/高抛止盈价，语义为参考。

### 参考区（原「信号/三重共振」）

- 标题 `🔗 参考`。
- 五条件评分或旧理论灯均可展示，句末或独立行必须含：  
  `仅供结构参考，不构成执行指令`
- **禁止**：`三重共振 → 可执行` / `部分共振 → 等第三盏灯` 等交易许可叙事。

### 看法失效

- 前缀：`看法失效：`（非「止损必须卖」指令）。

### 账户区

- 仅有持仓/`t0_account` 时显示。
- 费后空间：用「够门槛/不够门槛（纪律提醒）」，不用「可做/不可做」当下单许可。

### VWAP / 数据长度

- VWAP 只用今日 bar；距现价 ±20% 内才显示。
- 日线 120；5m/15m 800。

## Monitor Alert Output

状态变化时推送；话术为 **结构提醒**，禁止「做T指令/可执行」。

```
🎯 {name} ({symbol}) ─ 盘中结构卡
🟢 结构提醒：【近低吸关注区】（参考 · 人决策）
...
  📥 关注区（参考）：a～b · 是否动手由人决定
```

Valid alert themes: 近低吸关注区 / 近高抛关注区 / 已远离 / 被阻断 / 看法失效。
