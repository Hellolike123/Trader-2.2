# Output Contract — trader-pool

> **This is the absolute truth for valid output.** Never generate output from memory.

Common rules: no markdown tables in rank/show/plan outputs; use indented alignment; no `##/###` headings.

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
选股池盘后分析 — {date}
明日优先级  🥇 {name}（{status}）  触发{price}  防守{price}  仓位{percent}
评分总览  {name}  总分{s}  缠{n}/45 威{n}/30 筹{n}/25
仓位纪律 执行首次1成 确认加至3成 单票风险1R 总仓位≤5成
{one_sentence}
```

## analyze output

```text
入池建议
结果：通过/观察/拒绝  理由：...
触发：{price}  防守：{price}
📊 ATR入池检查  建议首仓：≤{cap}%
```
