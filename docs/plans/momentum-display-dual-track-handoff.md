# 动能在强弱展示上双轨 — Agent Handoff

> **status**: done
> **日期**: 2026-08-08
> **产品法源**: `BUSINESS.md` §4.0 / §5.1；`01-功能包-packages/trader/references/output-template.md`
> **目标**: 不换 `short_term_momentum` 引擎语义，只把面板展示改成“位置 + 综合强弱 + 买卖盘”三件事分开，让用户不用猜。

## 0. 30 秒摘要

1. `short_term_momentum` 仍是 EXPMA 短期动能，词表 `走强/修复/震荡/转弱` 不变，门控/池/信号字段不变。
2. 顶栏原 `动能 {short_term_momentum}` 改标 `位置 {short_term_momentum}`，表示价格相对 EXPMA 的位置状态。
3. 短线 `动能：` 行先给综合动量结论：`偏强/中性/偏弱`，再给原始 reason。
4. 短线 `资金：` 行在有依据时先给 `买盘占优/卖盘占优`，再给原资金短扫读。
5. 禁止改 `momentum_core`、fusion cards、decision_view、mistery_gate、选股池、关键价、动作/仓位。

## 1. 目标展示

禾望 603063 期望形态（数值来自已跑真实报告）：

```text
量能：量比1.1 平量 ｜ 调整19天 ｜ 位置 修复 ｜ ATR14 2.04

动能：中性 · MACD柱为正(偏多)、ADX强趋势(下跌)
资金：卖盘占优 · 5日净出2.75亿 · 连5日净出 · 价资看不出 · 主力0/10撤离
```

Golden 600000 期望形态：

```text
量能：量比1.0 平量 ｜ 换手2.1% ｜ 调整3天 ｜ 位置 震荡 ｜ ATR14 0.50

动能：偏弱 · MACD死叉+RSI下降(偏空)、多指标共振(强烈看空)
```

## 2. 必须项

- 顶栏 `量能：` 行的 EXPMA 词标签改为 `位置`；字段仍读 `short_term_momentum`。
- 短线 `动能：` 行：
  - 从 `fusion.signals_detail.momentum` 的 `direction` 派生总词：`1/bullish → 偏强`，`-1/bearish → 偏弱`，`0/neutral → 中性`。
  - 无 direction、reason 含“数据不足”时不硬加总词。
  - `中性 + 动量中性` 只显示 `动能：中性`，避免重复；其余为 `动能：{总词} · {reason}`。
- 短线 `资金：` 行：
  - 优先按 `big_order_direction/big_order_summary` 判 `买盘占优/卖盘占优`。
  - 无大单依据时按 `fund_features.cum_flow_5d_wan`（`|x|>=100` 万）或 `cum_flow_10d_wan`（`|x|>=3000` 万）符号判。
  - 无依据时不加买卖盘词，保持原资金行。
- 同步测试、golden、fixtures、output-template、BUSINESS、AGENTS_DEEP、output-style-guide、user-guide、agent-rules。

## 3. 禁止项

- 禁止改 `short_term_momentum` 计算/词表/字段语义。
- 禁止改 `momentum_core`、`fusion_card_signals`、`mistery_gate`、decision/池/信号逻辑。
- 禁止新增独立 `强弱：` 行；本次只做顶栏标签和现有两行文案。
- 禁止改任何价格、止损、买点、仓位、动作。

## 4. 可改文件

- `02-共享模块-shared/trader_shared/report_renderer/short_midline.py`
- `02-共享模块-shared/tests/test_report_optimization.py`
- `02-共享模块-shared/tests/test_sector_concept_index_map.py`
- `02-共享模块-shared/tests/golden/600000.render.md`
- `02-共享模块-shared/tests/fixtures/report_render_baseline.txt`
- `01-功能包-packages/trader/references/output-template.md`
- `01-功能包-packages/trader/references/output-style-guide.md`
- `01-功能包-packages/trader/references/agent-rules.md`
- `01-功能包-packages/_common/agent-rules.md`
- `01-功能包-packages/t0/references/agent-rules.md`
- `01-功能包-packages/review/references/agent-rules.md`
- `01-功能包-packages/wyckoff/references/agent-rules.md`
- `01-功能包-packages/daily_briefing/references/agent-rules.md`
- `01-功能包-packages/chanlun/references/agent-rules.md`
- `docs/guide/user-guide.md`
- `BUSINESS.md`
- `AGENTS_DEEP.md`
- `AGENTS.md`
- `ARCHITECTURE.md`
- 本 handoff 文件

## 5. 验收表

- `python3 scripts/golden_diff_gate.py capture` 后 `check` 通过。
- `python3 -m pytest 02-共享模块-shared/tests/test_report_optimization.py 02-共享模块-shared/tests/test_sector_concept_index_map.py 02-共享模块-shared/tests/test_golden_diff_gate.py -q` 通过。
- 顶栏不再出现 `动能 震荡/动能 修复` 旧标签；出现 `位置 震荡/位置 修复`。
- 短线 `动能：` 先有 `偏强/中性/偏弱`（有 direction 时），reason 不丢关键信号。
- `资金：` 有净额/主力/大单依据时可读作 `卖盘占优 · …` 或 `买盘占优 · …`。
- 字段断言：`short_term_momentum` 仍为 `走强/修复/震荡/转弱`。

## 6. 落地记录（2026-08-08）

- `render_short_midline` 已实现：顶栏 `量能：` 改 `位置 {short_term_momentum}`；短线 `动能：` 按 `direction` 派生 `偏强/中性/偏弱`；`资金：` 按大单/显著净额前置 `买盘占优/卖盘占优`。
- 未改 `momentum_core`、`fusion_card_signals`、decision/池/信号/价格/仓位逻辑。
- `golden_diff_gate check`、指定 pytest、`scripts/run-gate-tests.sh` 均通过。
