# Output Template — t0

> **This is the absolute truth for valid output.** Never generate output format from memory.

## Execution Card Output

Markdown output from `render_markdown()` — used when `final_t0.py` is invoked without `--monitor`.

Must start with `🎯`:

```text
🎯 {name}（{symbol}）{current_price}（{change_pct}）
  → {conclusion}

📌 执行
低吸：{buy_display}
高抛：{sell_display}
{buy_tp_line}
{sell_tp_line}
VWAP {vwap}

🔗 信号
  价格行为 {ab_status}（{ab_detail}） ｜ 威科夫 {wyck_status}（{wyck_type}） ｜ 动量 {mom_status}
  失效：{failure_conditions}

💰 {capital_line}
  {tick_details}

{account_section}
```

### Conclusion（一句话结论）

由 `_build_conclusion()` 根据三重共振状态生成：

| 条件 | 结论 |
|------|------|
| 买状态=可执行 + 三重共振买 | 三重共振买 → 可低吸 |
| 卖状态=可执行 + 三重共振卖 | 三重共振卖 → 可高抛 |
| 买/卖状态=可执行 + 未共振 | 触发但未共振 → 等确认再操作 |
| ≥2 盏买灯 | 部分共振（买）→ 关注，等第三盏灯 |
| ≥2 盏卖灯 | 部分共振（卖）→ 关注，等第三盏灯 |
| 其他 | 暂不操作 |

### 执行价（低吸/高抛）

- 状态为"可执行"时：显示 `可执行 {exec_price}～{acceptable_price}`
- 其他状态：显示 `价区{zone}｜价格行为{ab}｜威科夫{wyck}`（参考价）
- 信号棒价格远离现价 >20% 自动过滤

### 止盈（按方向拆分）

- 低吸止盈：高于现价的止盈价，显示 `低吸止盈：{prices}`
- 高抛止盈：低于现价的止盈价，显示 `高抛止盈：{prices}`
- 有 risk_r > 0 且有 exit_items 时才显示

### 三重共振（信号区）

- Al Brooks 价格行为：Always-In 方向 + 信号棒 + follow-through + H/L 回调计数
- 威科夫：5m（Spring/UT/无供给/放量滞涨）
- 动量：5m（RSI/MACD/ADX）
- 信号棒价格远离现价 >20% 自动过滤

### 失效条件

由 `_build_failure_conditions()` 生成：
- 跌破止损
- 价格行为反转（当前买→转卖 / 当前卖→转买）
- 威科夫反转（当前买→转卖 / 当前卖→转买）
- 跌回/跌破 VWAP

### 条件显示规则

- `🎯 标题 + 结论` — 始终显示
- `📌 执行` — 始终显示（低吸/高抛/止盈/VWAP）
- `🔗 信号` — 始终显示（三重共振状态 + 失效条件）
- `💰 资金` — 有净流入数据时显示
- `降本模式` — 有持仓信息时显示（`--t-mode cost_cut`）

### VWAP

- 只用今日数据（`today_bars()` 过滤跨日 bar）
- 距现价 ±20% 内才显示

### 数据长度

- 日线：120 根（`t0_config.LOOKBACK_DAYS`）
- 15m：800 根
- 5m：800 根

## Monitor Alert Output

Appears only on state changes from `final_t0.py --monitor`:

```
{name} {低吸触发/高抛触发/止损退出} | 现价 xx.xx | {buysell} xx.xx 附近
```

Valid alert patterns: `低吸触发`, `高抛触发`, `止损退出`.
