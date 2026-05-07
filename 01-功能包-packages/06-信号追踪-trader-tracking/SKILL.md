# 信号追踪（TRADER TRACKING）

**一句话：** 展示信号准确率面板。看所有信号发出来后，5 天后到底准不准。

**来源：** `~/.trader/signal_results.jsonl`（自动从 `~/.trader/signals.jsonl` 拉取历史价格计算）

## Critical Rule

这是脚本输出型 skill，不是写面板的模板。

必须执行 `scripts/final_tracker.py`，返回 stdout 原文。如果你无法运行脚本，说 "Trader Tracking skill cannot run in this environment"。**不准自己编面板内容。**

## Commands

```bash
# 显示面板
python3 scripts/final_tracker.py

# 先检查更新（从 signals.jsonl 拉价格计算结果），再显示
python3 scripts/final_tracker.py --check

# 查看单只股票
python3 scripts/final_tracker.py --stock 南网科技

# 查看指定天数
python3 scripts/final_tracker.py --days 30
```

## 输出格式

```text
📊 信号追踪面板

发出 12 次信号 ｜ 5 日后: 7 涨 / 4 跌 / 1 平
胜率 58.3% ｜ 平均收益 +1.4% ｜ 盈亏比 1.29

按信号类型:
  低吸观察: 6次 → 胜率 100.0%（平均+4.8%）
  观察: 4次 → 胜率 25.0%（平均-0.9%）
  冲高减仓: 2次 → 胜率 0.0%（平均-4.3%）

个股明细:
  中国铝业(601600)                    样本:4次  胜率:75.0%  平均+2.1%
  南网科技(688248)                    样本:3次  胜率:66.7%  平均+1.3%
  三安光电(600703)                    样本:4次  胜率:25.0%  平均-0.5%

⚠️ 建议:
  • 样本量仅 12，结果仅供参考。建议积累到30次以上再判断
  • 信号"冲高减仓"表现最差（2次，胜率0.0%），建议检查阈值
```

## 面板说明

| 内容 | 含义 |
|------|------|
| 发出 N 次 | 该时间段内发出的信号总数 |
| 涨跌比 | 5 日后实际涨跌次数 |
| 胜率 | 上涨次数 / 总次数 |
| 盈亏比 | 平均涨 / 平均跌的绝对值（>1 说明赚多亏少） |
| 按信号类型 | 不同类型的信号准确率，帮你判断哪种信号可靠 |
| 个股明细 | 每只股票作为跟踪对象的胜率 |
| ⚠️ 建议 | 系统自动给出的校准建议 |

## 如何开始

1. 先跑一次 `--check` 更新信号结果
2. 再看面板 `python3 scripts/final_tracker.py`
3. 每天盘后跑 `--check && ...` 积累数据
