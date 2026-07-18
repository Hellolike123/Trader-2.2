# 缠论买卖点 / 消费面修复记录（2026-07-16）

> 背景：审计发现二类买前置一类实现自锁、一类趋势判定偏松、区间套未进 fusion。  
> 权威规则同步：`02-共享模块-shared/trader_shared/formulas.md` §6 / §6.1。

## 改动文件

| 文件 | 内容 |
|------|------|
| `chan_structure.py` | `_strict_*_trend_zones`、`_historical_type1_*_ok`；一/二类买卖重写 |
| `fusion_core.py` | `_chan_to_signal` 对 `lower_confirmed` / `nesting_confirmed` 降权 |
| `tests/test_chan_core.py` | 一类 2 中枢、二类历史前置、0 中枢=无结构、merge 开关 patch 几何模块 |
| `tests/test_fusion_core.py` | 区间套未确认降权 |
| `formulas.md` / `AGENTS.md` | 契约与消费面 |

## 不变量（后续 Agent 勿破坏）

1. 一类与二类**不得**要求同帧 `buy_points`/`sell_points` 互为前提。  
2. 趋势中枢判定与 `classify_structure` 一致：严格不重叠。  
3. 区间套未确认 → fusion 置信度必须下降（展示与决策一致）。  
4. 行为变更刷新 `test_chan_core` 买卖点测例 + formulas §6。

## 自测

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest \
  02-共享模块-shared/tests/test_chan_core.py \
  02-共享模块-shared/tests/test_chanlun_correctness.py \
  02-共享模块-shared/tests/test_fusion_core.py -k "chan or 一类 or 二类 or nesting" \
  -q
```
