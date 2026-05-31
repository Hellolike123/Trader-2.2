# Trader JSON 字段说明

## 核心字段（AI 必读）

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `current` | float | 当前价格 | 14.29 |
| `change_pct` | float | 今日涨跌幅 % | 1.5 |
| `name` | str | 股票名称 | 南网科技 |
| `symbol` | str | 股票代码 | 688248.SH |
| `major_stage` | str | 大阶段 | 蓄势/主升/派发/衰退 |
| `short_term_momentum` | str | 短期动能 | 走强/修复/震荡/转弱 |
| `stage_action` | str | 阶段操作建议 | 试探买/持有/减仓/不碰 |
| `confidence` | int | 阶段置信度 0-100 | 65 |
| `theory_status` | str | 体系结论 | 突破确认/等转强/低吸观察/暂不碰/防守观察 |
| `base_status` | str | 基础状态（结构位置） | 低位修复/确认观察/中性整理 |
| `one_liner` | str | 一句话总结 | "蓄势期，不动手。等放量站稳 10.50 再说。" |

## 价位字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `support` | float | 支撑位 | 13.50 |
| `confirm` | float | 确认位（站稳才加仓） | 14.80 |
| `stop` | float | 止损位 | 13.20 |
| `resistance` | float | 阻力位 | 15.00 |
| `low_zone` | str | 低吸区间 | "13.50-13.64元" |
| `t0_ref.low_buy` | float | T0 低吸参考价 | 13.50 |
| `t0_ref.high_sell` | float | T0 高抛参考价 | 14.80 |
| `t0_ref.stop` | float | T0 止损参考价 | 13.20 |

## 融合层字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `fusion.action` | str | 融合层建议 | 半仓试 (多方主导) |
| `fusion.confidence` | float | 融合置信度 0-1 | 0.65 |
| `fusion.weighted_score` | float | 加权分 -1~+1 | 0.35 |
| `fusion.regime` | str | 大盘环境 | 正常/偏弱/很差 |
| `fusion.main_force_env` | str | 主力行为阶段 | accumulation/markup/unknown |

## 仓位字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `position_info.stage_position_pct` | int | 阶段仓位上限 % | 70 |
| `position_info.suggested_pct` | int | 建议仓位 % | 30 |
| `position_info.hard_rule_blocked` | bool | 硬规则阻止 | false |
| `position_info.hard_rule_reason` | str | 阻止原因 | "持仓亏损，禁止加仓" |

## MA 和 ATR 字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `ma.ma5` | float | 5 日均线 | 14.20 |
| `ma.ma10` | float | 10 日均线 | 14.10 |
| `ma.ma20` | float | 20 日均线 | 14.00 |
| `atr14` | float | 14 日 ATR | 0.35 |
| `atr_ratio` | float | ATR 占比 | 0.025 |
| `atr_level` | str | 波动率级别 | 波动正常 |

## 信号字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `fusion.signals_detail.chan.direction` | int | 缠论方向 1/-1/0 | 1 |
| `fusion.signals_detail.chan.reason` | str | 缠论原因 | 缠论一类买 (底背驰) |
| `fusion.signals_detail.momentum.direction` | int | 动量方向 | 1 |
| `fusion.signals_detail.momentum.score` | int | 动量评分 0-100 | 72 |
| `fusion.signals_detail.wyckoff.direction` | int | 威科夫方向 | 1 |
| `fusion.signals_detail.wyckoff.spring_signal` | bool | 弹簧信号 | true |

## 主力行为字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `main_force.stage` | str | 主力阶段 | accumulation/testing/markup/distribution/markdown/unknown |
| `main_force.confidence` | float | 置信度 0-1 | 0.6 |
| `main_force.cum_flow_5d_wan` | float | 5 日累计净流入（万元） | 3200 |
| `main_force.flow_price_relation` | str | 价资关系 | 价跌资入 |

## 数据状态字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `data_status` | str | 数据状态 | full/partial/degraded |
| `warnings` | list | 风险警告 | ["250日线下方"] |
| `gap.condition` | str | 开盘缺口 | normal/gap_up/gap_down |
