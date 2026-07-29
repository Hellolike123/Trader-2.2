# Output Template — t0（策略 v2.1 · 微信短卡）

> **This is the absolute truth for valid output.** Never generate output format from memory.  
> 产品法源：`docs/t0-strategy-v2.md`。微信红线见 AGENTS「微信红线」。

## Structure Card Output

```text
🎯 {名}（{码}）{现价}（{涨跌%}）
→ {短结论}

📌 盘面
今日{低}-{高}｜振幅x%｜平量｜VWAPx.xx
无底仓 · 不做T召唤

📌 买卖价
低吸 {buy}｜止损 {stop}｜高抛 {sell}
ATR {atr}（{pct}%）
计划 亏a/xA 赚b/yA → RR1:z 够用
费后约n% 够费用
现价 亏c 赚d → RR1:e 可看

失效：破{stop}
```

有底仓时在买卖价后可接 `📋 若做正T（人勾选）` / `📉 持仓纪律`。

### 微信排版规则（本卡）

- 禁止 `#` / `**` / `---` / `|表格` / `>` / `*-` 列表
- 用全角 `｜` 分隔同列数字，不用 Markdown 表格
- 结论一行短写：`VWAP上 · 近高区 · 无底仓 · 人决策`
- 买卖价块优先；评分默认不占屏（有分才一行 `参考分`）
- 不写「还差 x% 约 N 根 5m」距离噪音
- 标题代码可去掉 `.SH/.SZ` 后缀省宽度

### Conclusion

位置叙事短词；评分不进结论。禁止：`可低吸` / `可执行` / `三重共振买`。

内部状态：`到价关注`（旧 `可执行` 归一化）。

### 买卖价

必须含关键字：`低吸` / `止损` / `高抛`（契约校验）。  
RR 与 ATR 倍数用短写：`亏0.57/0.1A`、`RR1:2.9`。

## Monitor Alert Output

结构提醒话术；禁止做T指令/可执行。
