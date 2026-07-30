# Output Contract — trader (pool)

> **This is the absolute truth for valid output.** Never generate output format from memory.

Common rules: no markdown tables in rank/show/plan outputs; use indented alignment; no `##/###` headings.

评分：`total_score` = 缠+威+筹+动（入池门槛 + 同档弱决胜，**作战表不展示总分榜**）；池排序主轴是 **状态 → 共振档 → 可碰性（买点未过期/盈亏比）→ 分数**。`fusion_score` 仅仪表，不进总分、不进排序。

## rank output

```text
选股池  ｜  大盘{环境}，{建议}

🥇  ⭐ {name}  {status}  {price}  {atr_text}
    买  {buy_low}-{buy_high} 止跌确认  ｜  仓位 {cap}%  ｜  止损 {stop}
...

👉 首选{name}。...
📊 信号回测
  {name}    {sig_text}    {verify_status}
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
状态：{status}
触发：{price}
防守：{price}
下一步：盘后可说"生成明日作战表"。
```

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
池内 {n}/{limit}｜明日可盯 {k}｜观察 {o}｜过期待刷 {s}｜淘汰 {t}

明日只盯
🥇 {name} · {status} · {共振白话}
  现价{p}｜计划买点{p}｜防守{p}｜仓1→3成
  动作：放量站上计划买点 {p} 才考虑
  注意：盈亏比 {r}R 偏弱 · 宁可不追   ← 仅盈亏比低于门槛时

过期待刷（{s}只，计划买点与现价差太远）
  {name}  现价{p}｜计划买点{p}｜已涨过约{n}% · 需重算   ← 或「买点还高约n%」
  其余跑：final_pool.py refresh 重算买点                 ← 仅 s>3

说明：字段 `trigger` 对人话统一称「计划买点」；禁止再写难懂的「偏离±xx%」。

结构短板                         ← 仅执行/观察且买点未过期、确有短板才出；全正常则整段省略
  {name}  还差缠论 · 赔率偏弱
  {name}  缠偏弱

池内警示                         ← 有待补/拒绝/淘汰才出
  {name}：{reason}

仓位纪律 执行首次1成 确认加至3成 单票风险1R 总仓位≤5成
{one_sentence}
```

禁止：整段「交易指导」（已并入动作行）；「评分参考/总分榜」`总xx 缠x 威x…`；「缺结构（缺：结构）」叠词；过期票写进结构短板（已有过期待刷）；淘汰原因写进结构短板（已有池内警示）。

## analyze output

```text
入池建议
结果：通过/观察/拒绝  理由：...
触发：{price}  防守：{price}
📊 ATR入池检查  建议首仓：≤{cap}%
```
