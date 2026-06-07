# Review JSON 字段说明

## 核心字段（AI 必读）

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `quote.close` | float | 收盘价（注意：字段名是 close 而非 current_price） | 14.29 |
| `quote.open` | float | 开盘价 | 14.10 |
| `quote.high` | float | 最高价 | 14.50 |
| `quote.low` | float | 最低价 | 13.80 |
| `quote.pre_close` | float | 昨收 | 14.00 |
| `quote.change_pct` | float | 涨跌幅 % | 2.07 |
| `quote.volume` | float | 成交量（股） | 5000000 |
| `quote.amount` | float | 成交额（元） | 70000000 |
| `quote.turnover_rate` | float | 换手率 % | 1.5 |
| `cost` | float | 持仓成本 | 13.50 |
| `pnl_pct` | float | 浮盈浮亏 % | 5.85 |
| `conclusion_text` | str | 复盘结论（由 review_single._compute_display 注入） | "弱修复观察，还不能按反转处理" |
| `one_liner_text` | str | 一句话总结（由 review_single._compute_display 注入） | "防守观察，等确认" |
| `summary.state` | str | 综合状态：转强确认 / 短线止跌修复 / 弱修复观察 | "短线止跌修复" |
| `summary.score` | int | 总分 0-100 | 52 |
| `summary.key_pressure` | float | 关键压力位 | 14.80 |
| `summary.key_support` | float | 关键支撑位 | 13.50 |
| `summary.first_support` | float | 第一防线 | 13.90 |
| `summary.action` | str | 总结性动作建议 | "放量站稳关键压力才考虑加仓；否则继续观察。" |
| `session` | str | 复盘时段 | "close" / "midday" |

## 五层评分

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `theory.scores.structure` | int | 结构分 0-100 | 65 |
| `theory.scores.volume` | int | 量价分 0-100 | 45 |
| `theory.scores.chip` | int | 筹码分 0-100 | 50 |
| `theory.scores.momentum` | int | 动能分 0-100 | 50 |
| `theory.scores.total` | int | 加权总分 0-100（结构×0.32+量价×0.28+筹码×0.18+动能×0.22） | 52 |

## 理论分析字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `theory.state` | str | 结论状态：转强确认/短线止跌修复/弱修复观察 | "弱修复观察" |
| `theory.chanlun` | str | 缠论分析文本 | "回调段。有底背驰，止跌信号增强。" |
| `theory.wyckoff` | str | 威科夫分析文本 | "Spring 吸筹信号：..." |
| `theory.chip` | str | 筹码说明 | "13.50 是你的成本压力区" |
| `theory.fund` | str | 资金行为评估 | "资金行为证据不足" |
| `theory.momentum` | str | 动能评估文本 | "Neutral，动能评分50/100" |
| `theory.supports` | list[str] | 看多信号（5条） | ["结构：两次接近位置止跌", "量价：收盘修复，但分时确认不足"] |
| `theory.blocks` | list[str] | 看空信号（5条） | ["缠论：还没突破...", "量价：持续性还要等明天验证"] |
| `theory.double_low` | bool | 是否双低点 | true |
| `theory.afternoon_shrink` | bool | 午后是否缩量 | true |
| `theory.momentum_raw.rsi` | dict | RSI 原始数据（含 last/...） | {"last": 45.2} |
| `theory.momentum_raw.adx` | dict | ADX 原始数据（含 value/strong_trend） | {"value": 18.3, "strong_trend": false} |
| `theory.momentum_raw.macd` | dict | MACD 原始数据 | {...} |

## 价位于支撑/压力列表

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `levels.support` | list[dict] | 支撑列表，每个含 price/label | [{"price": 14.29, "label": "今日收盘价，守住偏强"}] |
| `levels.pressure` | list[dict] | 压力列表，每个含 price/label | [{"price": 14.50, "label": "今日高点，明日第一关"}] |
| `levels.key_support` | float | 关键支撑（support[2]或support[1]的 price） | 13.50 |
| `levels.key_pressure` | float | 关键压力（pressure[1]或pressure[0]的 price） | 14.80 |
| `levels.first_support` | float | 第一防线（support[1].price） | 13.90 |
| `levels.today_high` | float | 今日最高 | 14.50 |
| `levels.today_low` | float | 今日最低 | 13.80 |
| `levels.previous_low` | float | 前日最低 | 13.75 |
| `levels.recent_high` | float | 近20日最高 | 15.20 |
| `levels.recent_low` | float | 近20日最低 | 13.50 |
| `levels.ma.ma5` | float | 5日均线 | 14.20 |
| `levels.ma.ma10` | float | 10日均线 | 14.10 |
| `levels.ma.ma20` | float | 20日均线 | 14.00 |
| `levels.chip_zone.low` | float | 成交密集区下沿 | 13.80 |
| `levels.chip_zone.high` | float | 成交密集区上沿 | 14.30 |

## 大单字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `big_order.events` | list[dict] | 大单事件列表，每个含 time/side/hands/amount_wan/close/meaning/focus_label/near_focus | [{"time": "14:35", "side": "主动买入", "amount_wan": 4178, "hands": 6939}] |
| `big_order.events[].time` | str | 事件时间（分钟级） | "14:35" |
| `big_order.events[].side` | str | 方向 | "主动买入" / "主动卖出" |
| `big_order.events[].hands` | float | 手数 | 6939 |
| `big_order.events[].amount_wan` | float | 金额（万元） | 4178 |
| `big_order.events[].meaning` | str | 含义 | "偏试盘" |
| `big_order.events[].near_focus` | bool | 是否靠近关注价 | true |
| `big_order.events[].focus_label` | str | 贴近的关注区标签 | "关注区" |
| `big_order.summary` | str | 全天回溯总结 | "全天回溯到 5 次大单事件..." |
| `big_order.direction_summary` | str | 大单方向 | "买方更强" / "卖方更强" / "买卖接近" |
| `big_order.total_hands` | float | 总手数 | 15000 |
| `big_order.total_amount_wan` | float | 总金额（万元） | 12500 |
| `big_order.validation.verdict` | str | 走势验证结论 | "有效" / "背离" / "数据不足" |
| `big_order.validation.reason` | str | 验证理由 | "大单方向与价格方向一致" |

## 筹码字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `chip_distribution.peaks` | list[dict] | 筹码峰列表，每个含 price/share_of_total/support_level | [{"price": 14.00, "share_of_total": 5.91, "support_level": "支撑"}] |
| `chip_distribution.peaks[].price` | float | 筹码峰价格 | 14.00 |
| `chip_distribution.peaks[].share_of_total` | float | 占比 % | 5.91 |
| `chip_distribution.peaks[].support_level` | str | 级别：支撑/强阻力/弱阻力 | "支撑" |
| `chip_distribution.total_volume` | float | 总衰减筹码量 | 500000 |
| `chip_distribution.current_pct` | float | 现价以上筹码占比 % | 67.3 |
| `chip_distribution.mid_price` | float | 中位数价格 | 14.20 |
| `chip_distribution.volume_above_pct` | float | 现价以上量占比 % | 67.3 |
| `chip_distribution.bin_width` | float | 价格箱宽 | 0.05 |
| `chip_distribution.effective_range` | tuple | 价格范围 (min, max) | (13.00, 15.00) |

## 筹码搬家字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `chip_migration.migration_pct` | float | 搬家比例 % | 15.0 |
| `chip_migration.warning_level` | str | 警告级别 | "none" / "warning" / "critical" |
| `chip_migration.warning_text` | str | 警告文本 | "底部筹码减少，顶部筹码增加" |
| `chip_migration.has_history` | bool | 是否有历史对比数据 | true |

## 分时日内字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `intraday.data_state` | str | 分时数据完整性 | "full" / "partial_close" / "partial" |
| `intraday.lines` | list[str] | 分时叙事文本 | ["09:30-10:00..."] |
| `intraday.volume_lines` | list[str] | 量能叙事文本 | ["上午 500万，占全天55%"] |
| `intraday.total_volume` | float | 总成交量 | 5000000 |
| `intraday.morning_volume` | float | 上午成交量 | 2800000 |
| `intraday.afternoon_volume` | float | 下午成交量 | 2200000 |
| `intraday.morning_ratio` | float | 上午占比 | 0.56 |
| `intraday.volume_state` | str | 量能状态 | "早盘放量、午后缩量" / "量能平稳" |
| `intraday.coverage_complete` | bool | 是否覆盖全天 | true |
| `intraday.tail_has_data` | bool | 尾盘是否有数据 | true |

## MACD 参数字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `macd_params.macd_line` | float | MACD 快线值 | 0.15 |
| `macd_params.dea` | float | DEA 慢线值 | 0.10 |
| `macd_params.histogram` | float | 柱状线值 | 0.05 |
| `macd_params.golden_cross` | bool | 是否金叉（近5日内） | true |
| `macd_params.death_cross` | bool | 是否死叉（近5日内） | false |

## 主力行为字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `main_force.stage` | str | 主力阶段 | accumulation/testing/markup/distribution/markdown/unknown |
| `main_force.confidence` | float | 置信度 0-1 | 0.6 |
| `main_force.cum_flow_5d_wan` | float | 5 日累计净流入（万元） | 3200 |
| `main_force.flow_price_relation` | str | 价资关系 | 价跌资入 |
| `main_force.consecutive_inflow_days` | int | 连续流入天数 | 3 |
| `main_force.consecutive_outflow_days` | int | 连续流出天数 | 0 |
| `main_force.daily_flow_5d` | list[float] | 近5日每日净流（万元） | [100, 200, -50, 300, 150] |

## ATR 字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `atr.atr14` | float | 14 日 ATR | 0.35 |
| `atr.atr7` | float | 7 日 ATR | 0.30 |
| `atr.atr_ratio` | float | ATR 占比 | 0.025 |
| `atr.level` | str | 波动率级别 | 波幅偏高 / 波动偏大 / 波动正常 / 波动较低 |
| `atr.suggested_cap_pct` | int | 建议仓位上限 % | 5 |
| `atr.available` | bool | ATR 数据是否可用 | true |

## 四阶段定位字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `stage_result.major_stage` | str | 四阶段：蓄势/主升/派发/衰退 | "蓄势" |
| `stage_result.momentum` | str | 短期动能：走强/修复/震荡/转弱 | "修复" |
| `stage_result.action` | str | 操作建议：试探买/加仓/持有/减仓/清仓/不碰 | "试探买" |
| `stage_result.stage_label` | str | 阶段标签 | "蓄势期修复" |
| `stage_result.confidence` | int | 置信度 0-100 | 65 |

## 其他字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `name` | str | 股票名称 | "南网科技" |
| `symbol` | str | 股票代码含后缀 | "688248.SH" |
| `date` | str | 复盘日期 | "2026-05-28" |
| `session` | str | 复盘时段 | "close" / "midday" |
| `contract` | str | 契约版本 | "review_trader_v1" |
| `mode` | str | 模式 | "single" |
| `data_time` | str | 数据时间 | "2026-05-28 15:00" |
| `wyckoff` | dict | 威科夫分析完整结果 | {...} |
| `historical_signals` | list | 历史信号（由 enrich_with_signal_backtrack 注入） | [...] |
