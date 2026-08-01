# Anti-Hallucination Rules

仅在 **markdown 失败、走 JSON 回退** 时使用。markdown 成功时不要读本文——直接原样贴脚本 stdout。

数据锚定、信号矛盾处理、禁止用语。

## 数据锚定表

所有数值必须来自 build_report() 返回的 JSON 字段，禁止凭空估算。

| 字段 | 来源 | 说明 |
|------|------|------|
| `current` | fetch_quote() | 实时报价 |
| `change_pct` | fetch_quote() | 今日涨跌幅 % |
| `ma5/10/20/30/250` | 日线 bars 计算 | 均线 |
| `atr14` | 日线 bars 计算 | ATR14（元）；面板并入量价行，写 `ATR14 x.xx（前/后/未复权）`，勿独立成行、勿写成 ATR15 |
| `support` / `resistance` | build_structure_context() | 结构支撑/压力位 |
| `confirm` / `stop` | build_structure_context() | 确认位/止损位 |
| `major_stage` | assess_stage() | 日线四阶段：蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退（**非**面板「阶段：」） |
| `short_term_momentum` | assess_stage() → momentum | EXPMA 动能：走强/修复/震荡/转弱 |
| `stage` | = short_term_momentum 别名 | 兼容旧读方；禁止当成 major_stage |
| `midline_stage` / `conclusion.stage_line` | 周线威科夫 | 面板「阶段：」短词；不足→无阶段 |
| `momentum` | 同 short_term_momentum（内部） | 走强/修复/震荡/转弱 |
| `fusion.weighted_score` | merge_decisions() | 融合加权分 -1~+1 |
| `fusion.confidence` | merge_decisions() | 置信度 0~1 |
| `fusion.action` | merge_decisions() | 融合层建议动作 |
| `fusion.regime` | merge_decisions() | 板块环境档（跟所属板块指数；面板 meta 不写）：正常/偏弱/很差 |
| `data_status` | load_market_snapshot() | full/partial/degraded |

## Rule 1: 数据缺失处理

当 `data_status=partial` 或某个值为 `None` / "数据不足" 时：
- 不得编造替代值
- 不得省略该字段（必须显示并标注"数据不足"）
- 融合层 confidence 上限降为 0.3

当 `data_status=degraded` 时：
- 仅输出基础行情（现价/涨跌幅/MA）
- 不做深度分析，不做买卖建议

## Rule 2: 信号矛盾检测（GATE 2）

以下矛盾组合必须在报告中明确说明，不得隐藏：

| 组合 | 处理 |
|------|------|
| `major_stage=主升` + `theory_status=暂不碰` | 说明矛盾：主升期但理论结论不支持 |
| `fusion.weighted_score > 0.3` + `theory_status=暂不碰` | 说明矛盾：融合偏多但理论偏空 |
| `major_stage=衰退` + `fusion.weighted_score > 0.3` | 以衰退为准（阶段优先于融合） |
| `major_stage=派发` + `fusion.weighted_score > 0.25` | 以派发为准（阶段优先于融合） |
| `data_status=partial` + 所有信号一致 | 加前缀警告：数据不全，一致性可能不可靠 |

## Rule 3: 禁止用语

| 禁止 | 原因 | 替代 |
|------|------|------|
| "建议买入/卖出" | 系统不做投资建议 | "当前位置建议观望/可轻仓试探" |
| "一定涨/跌" | 无确定性 | "偏多/偏空概率较高" |
| "目标价 XX" | 无精确预测 | "上方压力位 XX" |
| "胜率 XX%" | 无回测支撑时 | 不使用；有回测数据时注明数据来源 |
| 省略 data_status=partial 警告 | 隐瞒数据缺陷 | 必须在报告开头标注 |

## Rule 4: 方向判断铁律

出手依据：`decision_view`（共振∧策略∧纪律）。fusion 仪表参考：`fusion.weighted_score`（禁止当总司令）

- 正值 = 多方，负值 = 空方
- 禁止用 `action` 字符串字面意思推断方向（action 是融合层内部映射，可能因 veto 机制被覆盖）
- `confidence < 0.3` → 信号弱，轻仓
- `disagreement > 1` → 信号有分歧，谨慎
- `regime=很差` → 一票否决，暂不碰
- `regime=偏弱` → 所有买入建议降一档
