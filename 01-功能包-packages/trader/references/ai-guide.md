# Trader JSON 字段说明

## 核心字段（AI 必读）

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `current` | float | 当前价格 | 14.29 |
| `change_pct` | float | 今日涨跌幅 % | 1.5 |
| `name` | str | 股票名称 | 南网科技 |
| `symbol` | str | 股票代码 | 688248.SH |
| `major_stage` | str | 大阶段 | 蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退 |
| `short_term_momentum` | str | 短期动能 | 走强/修复/震荡/转弱 |
| `stage_action` | str | 阶段操作建议 | 试探买/持有/减仓/不碰 |
| `confidence` | int | 阶段置信度 0-100 | 65 |
| `theory_status` | str | 体系结论 | 突破确认/等转强/低吸观察/暂不碰/防守观察 |
| `base_status` | str | 基础状态（结构位置） | 低位修复/确认观察/中性整理 |
| `one_liner` | str | 一句话总结 | "蓄势期，不动手。等放量站稳 10.50 再说。" |
| `scene` | str | 当前场景标签 | 低吸观察/冲高减仓/突破确认/防守观察/等转强 |
| `state_label` | str | 状态摘要（兼容层） | 体系转强确认/未确认转强/承接存在/修复观察 |
| `fusion_override_used` | bool | 融合层是否覆盖了基础决策 | true |

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

## 持仓与盈亏字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `has_position` | bool | 是否持有该股 | true |
| `cost_price` | float | 持仓成本价 | 60.00 |
| `pnl_pct` | float | 盈亏比例 % | 2.5 |
| `pnl_text` | str | 盈亏描述文本 | "盈 +2.5%" |
| `position_info.stage_position_pct` | int | 阶段仓位上限 % | 70 |
| `position_info.suggested_pct` | int | 建议仓位 % | 30 |
| `position_info.hard_rule_blocked` | bool | 硬规则阻止 | false |
| `position_info.hard_rule_reason` | str | 阻止原因 | "持仓亏损，禁止加仓" |
| `position_state.state` | str | 仓位状态机状态 | 回踩加仓/阻力位分歧/空仓 |
| `position_state.action` | str | 仓位状态机动作 | 加仓/持有/减仓 |
| `position_state.position_pct` | int | 状态机建议仓位 % | 10 |
| `position_state.stop_price` | float | 状态机止损价 | 55.57 |
| `stage_stop.stage` | str | 阶段止损类型 | ma20/expma20/range_low |
| `stage_stop.price` | float | 阶段止损价 | 56.00 |

## 止盈止损字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `stop` | float | 硬止损位 | 13.20 |
| `trailing_stop` | float | 移动止损（只紧不松） | 14.50 |
| `take` | float | 第一止盈位 | 15.50 |
| `exit_plan.exit_plan` | list | 分批止盈列表 | [{"price":14.80,"ratio":0.33,"reason":"阻力位"}] |
| `exit_plan.stage_exit` | str | 阶段转换清仓条件 | 派发 |
| `exit_plan.wyckoff_signals` | dict | 威科夫信号（bc_signal/utad_signal等） | {} |

## 融合层字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `fusion.action` | str | 融合层建议 | 半仓试 (多方主导) |
| `fusion.confidence` | float | 融合置信度 0-1 | 0.65 |
| `fusion.weighted_score` | float | 加权分仪表 -1~+1（出手听 decision_view） | 0.35 |
| `fusion.regime` | str | 大盘环境 | 正常/偏弱/很差 |
| `fusion.main_force_env` | str | 主力行为阶段 | accumulation/markup/unknown |
| `fusion.hmm_regime` | str | HMM大势前瞻 | bull/bear/range |
| `fusion.disagreement` | float | 多信号分歧度 | 1.5 |
| `fusion.weights_used.chan` | float | 缠论权重 | 0.35 |
| `fusion.weights_used.momentum` | float | 动量权重 | 0.25 |
| `fusion.weights_used.wyckoff` | float | 威科夫权重 | 0.40 |

## MA 和 ATR 字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `ma.ma5` | float | 5 日均线 | 14.20 |
| `ma.ma10` | float | 10 日均线 | 14.10 |
| `ma.ma20` | float | 20 日均线 | 14.00 |
| `atr14` | float | 14 日 ATR | 0.35 |
| `atr_ratio` | float | ATR 占比 | 0.025 |
| `atr_level` | str | 波动率级别 | 波动正常 |
| `atr_cap` | int | ATR建议仓位上限 % | 10 |

## EXPMA 字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `expma10` | float | EXPMA(10) 值 | 14.20 |
| `expma12` | float | EXPMA(12) 值 | 14.15 |
| `expma20` | float | EXPMA(20) 值 | 14.00 |
| `expma50` | float | EXPMA(50) 值 | 13.80 |
| `expma_trend` | str | EXPMA排列趋势 | 多头排列/空头排列/交叉震荡/短期偏多/短期偏空 |

## MACD 字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `macd_status.histogram` | float | MACD柱状线 | 0.05 |
| `macd_status.golden_cross` | bool | 是否金叉 | true |
| `macd_status.death_cross` | bool | 是否死叉 | false |
| `macd_status.positive` | bool | MACD是否为正 | true |

## 阶段定位字段（6 阶段 + 4 动能）

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `major_stage` | str | 大阶段 | 蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退 |
| `major_reason` | str | 阶段判定原因 | "主力:主力行为不明｜量价兜底:蓄势" |
| `short_term_momentum` | str | 短期动能 | 走强/修复/震荡/转弱 |
| `momentum_reason` | str | 动能判定原因 | "MACD转正，量价修复" |
| `stage_action` | str | 阶段操作建议 | 试探买/持有/减仓/不碰 |
| `max_position_pct` | int | 阶段最大仓位 % | 30 |
| `stage_label` | str | 阶段标签摘要 | "蓄势期修复" |
| `protection_notes` | list | 保护性说明 | ["年线下方注意趋势风险"] |
| `stop_losses` | dict | 各维度止损价 | {"ma20": 14.00} |

## 量价与筹码字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `volume_ratio` | float | 量比 | 0.75 |
| `volume_vacuum.vacuum_warning` | bool | 量能真空预警 | false |
| `volume_vacuum.warning_text` | str | 真空区说明 | "当前价位于量能稀疏区" |
| `chip_support` | float | 筹码支撑价 | 57.88 |
| `chip_resistance` | float | 筹码压力价 | 60.46 |
| `chip_peaks` | list | 筹码峰列表 | [{"price":57.88,"share_of_total":5.91,"support_level":"支撑"}] |
| `chip_current_pct` | float | 现价以上筹码占比 % | 67.3 |
| `chip_mid_price` | float | 筹码中位数价格 | 60.29 |
| `chip_migration.warning_level` | str | 搬家警告级别 | none/warning/critical |
| `chip_migration.warning_text` | str | 搬家描述文本 | "底部筹码减少，顶部筹码增加" |
| `chip_migration.has_history` | bool | 是否有历史对比 | true |

## 其他字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `gap.condition` | str | 开盘缺口状态 | normal/gap_up/gap_down |
| `gap.gap_pct` | float | 缺口幅度 % | 1.2 |
| `time_window` | str | 时间窗口提示 | "临近财报发布" |
| `fib_retrace` | dict | 斐波那契回调位 | {"0.382": 58.00, "0.500": 57.00, "0.618": 56.00} |
| `wyckoff` | dict | 威科夫完整分析结果（spring/bc/sos/phase 等） | `{"spring_signal":true,"phase_label":"..."}`；报告文案见 `format_wyckoff_oneline()` |
| `market_env.level` | str | 大盘环境等级 | 正常/偏弱/很差 |
| `market_env.hmm_regime_en` | str | HMM 大势（英文） | bull/bear/range |

## 信号字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `fusion.signals_detail.chan.direction` | int | 缠论方向 1/-1/0 | 1 |
| `fusion.signals_detail.chan.reason` | str | 缠论原因 | 缠论一类买 (底背驰) |
| `fusion.signals_detail.momentum.direction` | int | 动量方向 | 1 |
| `fusion.signals_detail.momentum.score` | int | 动量评分 0-100 | 72 |
| `fusion.signals_detail.wyckoff.direction` | int | 威科夫方向 | 1 |
| `fusion.signals_detail.wyckoff.spring_signal` | bool | 弹簧信号 | true |

> 注：主力行为阶段可通过 `fusion.main_force_env` 获取（见融合层字段），详细主力资金数据仅由渲染层消费，不在 JSON 输出中暴露。

## 数据状态字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `data_status` | str | 数据状态 | full/partial/degraded |
| `missing_sources` | list | 缺失数据源 | ["fund_flow"] |
| `source_errors` | dict | 数据源错误详情 | {"mootdx": "timeout"}
