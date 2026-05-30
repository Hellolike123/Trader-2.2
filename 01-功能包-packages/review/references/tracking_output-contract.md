# Output Contract — trader-tracking

> **This is the absolute truth for valid output.** Never generate output from memory.

Valid output starts with: `📊 信号追踪面板`

Must include:
- `发出 N 次信号 ｜ 5 日后: X 涨 / X 跌 / X 平`
- `胜率 X% ｜ 平均收益 +/-X% ｜ 盈亏比 X.XX`
- `按信号类型:` with per-type stats
- `个股明细:` with per-stock stats
- `⚠️ 建议:` with calibration advice

Panel meanings (for reference only, not output content):

| 内容 | 含义 |
|------|------|
| 发出 N 次 | 该时间段内发出的信号总数 |
| 涨跌比 | 5 日后实际涨跌次数 |
| 胜率 | 上涨次数 / 总次数 |
| 盈亏比 | 平均涨 / 平均跌的绝对值 |
| 按信号类型 | 不同类型的信号准确率 |
| 个股明细 | 每只股票的胜率 |
| ⚠️ 建议 | 系统自动校准建议 |
