# Output Template — t0（策略 v2.1）

> **This is the absolute truth for valid output.** Never generate output format from memory.  
> 产品法源：`docs/t0-strategy-v2.md` — 结构参考卡 · 人决策 · 不做机械可执行指令。

## Structure Card Output

Markdown from `render_markdown()` — `final_t0.py` without `--monitor`.

Must start with `🎯`:

```text
🎯 {name}（{symbol}）{current_price}（{change_pct}）
  → {conclusion}

📌 结构
位置：{vwap_rel}（VWAP {vwap}） · 今日 {low}-{high} · {box_pos}
量能：量比{x}（放量/缩量/平量）
空间：振幅 {amp}%（{space_lbl}）{fee_hint}
{no_position_line}
当前：观望 ｜ 止损参考：{stop}
低吸：{buy_display}
高抛：{sell_display}
{buy_tp_line}
{sell_tp_line}

📋 若做正T（人勾选）
  · …（仅有底仓时）

🔗 参考
  评分 {score}/100 · 仅供结构参考，不构成执行指令
  {lights_line}
  看法失效：{failure_conditions}

💰 {capital_line}

{account_section}
```

### Conclusion（一句话，位置叙事优先）

由 `_build_conclusion()` 生成。评分**不进**结论主语（评分只在 `🔗 参考`）。

| 元素 | 示例 |
|------|------|
| vs VWAP | 价在VWAP上 / 价在VWAP下 / 价近VWAP / VWAP不足 |
| 今日箱位 | 靠近今日高区 / 低区 / 中轴 |
| 量 | 量放 / 量缩 / 量平 / 量不足 |
| 数据烂 | 数据不足，仅现价 |
| 关注区 | 近低吸关注区 / 近高抛关注区（若到价） |
| 持仓 | 无底仓（无持仓时） |
| 收尾 | 宜观察 · 人决策 |

禁止结论出现：`可低吸` / `可加仓` / `可执行` / `三重共振买` / `轻仓试探`（作为系统指令）。

内部状态枚举：价到关注区用 `到价关注`（`SIDE_ZONE_HIT`）；旧值 `可执行` 读入时归一化，不得出现在 markdown。

### 结构区（四块必出）

1. **位置**：VWAP 相对 + 今日高低 + 箱位；不足写「VWAP不足 / 今日高低不足」
2. **量能**：量比 + 放/缩/平；不足写「量能不足」
3. **空间**：振幅；有仓可附「费后盖住门槛 / 可能盖不住费用」（纪律提醒）
4. **关注价**：低吸/高抛/止损参考；价到写 `关注 a～b（参考）`

假结构治理：低吸价区与高抛价区同时 ≈ 现价时，写「暂无有效关注价（结构数据不足）」，禁止 `低吸：价区X` + `高抛：价区X` 且 X=现价。

无底仓：必须有一行 `持仓：无底仓 · 仅结构参考，不做 T 召唤`。

### 做人清单（有底仓）

- 标题固定 `📋 若做正T（人勾选）`
- 只列条件，不勾选、不下令；须含「是否动手由人决定」
- 无底仓：整块不出现

### 参考区

- 标题 `🔗 参考`。
- 五条件评分可展示，必须含：`仅供结构参考，不构成执行指令`
- **禁止**：`三重共振 → 可执行` 等交易许可叙事。

### 看法失效

- 前缀：`看法失效：`（非「止损必须卖」指令）。

### 账户区

- 仅有底仓（`total_shares > 0`）时显示，标题 `📉 持仓纪律`。
- 无底仓：禁止降本/做 T 模式块。
- 费后空间：用「够门槛/不够门槛（纪律提醒）」。

### VWAP / 数据长度

- VWAP 只用今日 bar；距现价 ±20% 内才写入位置句。
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
