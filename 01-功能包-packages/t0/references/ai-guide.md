# T0 报告怎么用（交易员用法，handoff §6）

T0 卡是**盘中结构参考卡**，不是下单指令。基调（看正T/看反T/观望）来自**日线威科夫阶段**（handoff §1），日内箱位只做时机微调。

1. **开盘前**看基调（正T/反T/观望）定方向——日线派发→反T为主，积累→正T为主，无明确阶段→按日内箱位
2. **挂预警**在低吸/止损/高抛三个价位，不用盯盘
3. **到价后自己看量价**确认出手——报告给"在哪等"，"买不买"是人确认
4. **不等盯盘推送**——盯盘是闹钟，报告是作战地图；闹钟没响按地图走
5. **14:50 前平掉 T 仓**（铁律）

**出手信号（handoff §2，任一 + 顺日线方向即可，不要求同时）**：
- VWAP 回归：偏离均价线 >1.5% + 缩量 → 做回归
- 前高/前低突破：放量突破前高 + 顺日线 → 跟突破；缩量到前高 + 逆日线 → 假突破反向
- 开盘价失守/收复：开盘 30 分钟后站稳开盘价上方(顺多)→低吸；下方(顺空)→高抛
- Al Brooks 信号棒：高质量信号棒（strong + score≥0.8）+ 顺日线 → 出手

**风控（handoff §5）**：单笔止损 = 日内 5m ATR 的 0.5 倍；日内总亏损 1% 警告、2% 停手；单日单方向不反手；14:50 平 T 仓。

**选股前置（handoff §4）**：日均振幅 <3% / 日均成交额 <3 亿 / 当日涨跌停 / 无底仓 → 今日宜不做。

---

# T0 JSON 字段说明

## 核心字段（AI 必读）

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `current_price` | float | 当前价格 | 14.29 |
| `current_change_pct` | float | 今日涨跌幅 % | 1.5 |
| `today_action` | str | 今日结构文案（v2，人决策） | 价近低吸关注区 · 人决策 / 价近高抛关注区 · 人决策 / 双侧关注区皆近 · 人决策 / 等待，结构观察 · 人决策 |
| `data_status` | str | 数据状态 | full/partial/degraded |
| `name` | str | 股票名称 | 南网科技 |
| `symbol` | str | 股票代码 | 688248.SH |
| `max_move` | str | 建议仓位（`position_size` 认 v2 today_action + 旧枚举） | 底仓的 10%-20%/底仓的 20%-30%/不动 |
| `position_score` | int | 多空位置评分 1-10 | 5 |
| `volume_score` | int | 量价评分 1-10 | 6 |
| `resonance` | dict | T0 **结构评分卡**（分数/灯）；**不是**单票报告的 `pullback_probe` / `attach_resonance`；schema **不在**此 dict 内 | `{"score":60,"buy_green":false,"sell_red":false,…}` |
| `resonance_schema` | str | **plan 顶层**固定 `t0_structure_score_v1`（与报告侧共振命名隔离；勿读 `resonance.schema`） | t0_structure_score_v1 |
| `structure_ref` | dict\|null | 结构参考摘要（可选）；供人读，不构成下单指令 | `{"vwap":14.25,"bias":"偏强"}` |
| `amplitude_pct` | float | 日内振幅 | 0.025 |
| `space_state` | str | 振幅状态 | too_small/normal/good |
| `vwap` | float | VWAP | 14.25 |
| `volume_ratio` | float | 量比 | 1.5 |
| `buy_display_status` | str | 低吸显示状态 | 到价关注/未触发/已错过/被阻断/数据不足（旧「可执行」已废弃，读入归一化为到价关注） |
| `sell_display_status` | str | 高抛显示状态 | 到价关注/未触发/已错过/被阻断/数据不足 |
| `atr_info.atr14` | float | ATR | 0.35 |
| `atr_info.atr_ratio` | float | ATR 占比 | 0.025 |
| `atr_info.level` | str | 波动率级别 | 波动正常/波幅偏高 |
| `ict_signal.summary` | str | ICT信号摘要 | ICT执行辅助未启用。 |
| `ict_signal.buy_confirmed` | bool | ICT买入确认 | true/false |
| `ict_signal.sell_confirmed` | bool | ICT卖出确认 | true/false |
| `wyckoff` | dict | 威科夫分析结果 | 包含BC/UTAD/SOW信号字段 |
| `exit_plan.exit_plan` | list | 分批止盈计划 | [{"price":14.80,"ratio":0.33,"reason":"阻力位"}] |
| `chip_migration` | dict | 筹码搬家 | {"migration_pct":5,"warning_level":"none","has_history":true} |

## 低吸字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `buy.status` | str | 低吸状态 | 已触发/观察中/未进入候选区/被阻断/数据不足/触发过期/熔断中/数据异常/趋势下行暂不低吸 |
| `buy.observation_price` | float | 低吸观察价 | 13.50 |
| `buy.execution_price` | float | 低吸执行价 | 13.40 |
| `buy.acceptable_price` | float | 最高可接受价 | 13.80 |
| `buy.invalid_price` | float | 低吸止损价 | 13.20 |
| `buy.trigger_price` | float | 触发价 | 13.35 |
| `buy.trigger_time` | str | 触发时间 | 14:05 |
| `buy.matched_count` | int | 触发信号数 | 3 |
| `buy.reasons` | list | 触发原因 | ["5m不再创新低", "MACD绿柱缩短"] |
| `buy.blocked_reasons` | list | 阻断原因 | ["放量跌破主支撑"] |
| `buy.observation_valid` | bool | 观察价是否有效 | true/false |
| `buy.observation_reason` | str | 无效原因 | 盘中数据不足 |

## 高抛字段

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `sell.status` | str | 高抛状态 | 已触发/观察中/未进入候选区/被阻断/数据不足/触发过期/熔断中/数据异常/趋势下行暂不高抛 |
| `sell.observation_price` | float | 高抛观察价 | 14.80 |
| `sell.execution_price` | float | 高抛执行价 | 14.90 |
| `sell.acceptable_price` | float | 最低可接受价 | 14.50 |
| `sell.invalid_price` | float | 高抛失效价 | 15.10 |
| `sell.trigger_price` | float | 触发价 | 14.75 |
| `sell.trigger_time` | str | 触发时间 | 14:05 |
| `sell.matched_count` | int | 触发信号数 | 3 |
| `sell.reasons` | list | 触发原因 | ["MACD红柱缩短", "RSI高位拐头"] |
| `sell.blocked_reasons` | list | 阻断原因 | ["最近5m持续创新高"] |
| `sell.observation_valid` | bool | 观察价是否有效 | true/false |
| `sell.observation_reason` | str | 无效原因 | 高抛观察位距离现价太近 |
