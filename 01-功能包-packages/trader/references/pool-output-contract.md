# Output Contract — trader (pool)

> **This is the absolute truth for valid output.** Never generate output format from memory.

Common rules: no markdown tables in rank/show/plan outputs; use indented alignment; no `##/###` headings.

池定位：用户自选名单 + 短线策略分道（可盯/等齐/先别碰/计划过时）。  
排序：`lane` → 共振档 → **威科夫吸筹链** → **周线 RS** → 可碰性（盈亏比）→ `total_score` 弱决胜（与 `sort_items_unified` / AGENTS.md 一致）。  
`total_score`（缠+威+筹+动）仅诊断附录；`fusion_score` 仅仪表。  
对外用词：**买点有效** / **买点失效**；计划价漂太远称**计划过时**。  
威科夫链文案（同道近因）：`威：SC→AR→ST→LPS，还差SOS`；全齐写满链；禁止「事件 n/5」、S级/星级。

## rank output

池日报「大盘{环境}」用宽基 `INDEX_CODE`（中证1000）；与单票报告顶栏（环境/概念/量能，板块真实指数对照、不写正常/偏弱）不同，见 `BUSINESS.md` §3.4。

```text
选股日报 — {date}  ｜  大盘{环境}，{建议}

🥇  {name}  {price}  {atr_text}
    {分道｜共振｜买点有效/失效｜近因}
    买  {buy_low}-{buy_high} 止跌确认  ｜  仓位 {cap}%  ｜  止损 {stop}
...
```

## show output

```text
选股池  {count}/{POOL_LIMIT}  执行{e}  观察{o}  淘汰{t}
  {name}  {status}  评分{score}  触发{price}  防守{price}
```

## add output

```text
已加入选股池
当前容量：{n}/{POOL_LIMIT}
分道：{lane_zh}
近因：{lane_reason}
计划买点：{price}
防守：{price}
下一步：盘后可说"生成明日作战表"。
```

容量满才拒；结构差票仍入库，分道标「先别碰」。

## add-pending output

```text
已加入待确认池：{name}
现价：{price}
入池建议：{admit_result}
评分：{total_score}
```

## plan output

```text
选股池作战表 — {date}
池内 {n}/{limit}｜可盯 {k}｜等齐 {w}｜先别碰 {a}｜计划过时 {s}

明日只盯
🥇 {name} · 可盯 · {共振} · {买点有效} · 威：SC→AR→ST→LPS，还差SOS
  现价{p}｜计划买点{p}｜防守{p}｜仓1→3成
  动作：放量站上计划买点 {p} 才考虑
  注意：盈亏比 {r}R 偏弱 · 宁可不追   ← 仅盈亏比低于门槛时

等齐（{w}只）
  {name}  {近因}

先别碰（{a}只）
  {name}  {近因}

计划过时（{s}只，计划买点与现价差太远）
  {name}  现价{p}｜计划买点{p}｜已涨过约{n}% · 需重算
  其余跑：final_pool.py refresh 重算买点                 ← 仅 s>3

评分参考（缠/威/筹/动 · 不决定盯谁）
  {name}  总{s}  缠{n} 威{n} 筹{n} 动{n}  {lane_zh}

池内警示                         ← 先别碰/淘汰/结构诊断才出
  {name}：{reason}

仓位纪律 执行首次1成 确认加至3成 单票风险1R 总仓位≤5成
{one_sentence}
```

禁止：整段「交易指导」；「执行」当注意力主语言（用分道）；「盖未过期」jargon；「事件 4/5」分数式链文案。

## analyze output

```text
入池建议
结果：可入库
理由：{lane_reason}
建议状态：{lane_zh}
计划买点：{price}  防守：{price}
下一步：如确认，请说“加入选股池”
📊 ATR入池检查  建议首仓：≤{cap}%
```
