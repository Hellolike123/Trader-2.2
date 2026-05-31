## Why

第二轮扫描发现 19 个计算和数据 bug。最严重的是 `decision_core.py` 的假跌破判定用错了比较对象（`prev_close >= support` 应为 `prev_close >= hard_stop`），导致真跌破被误判为假跌破，止损机制失效。其他问题包括置信度不连续、权重归一化扭曲、筹码零换手不衰减、confirm_buffer 无下限等。

## What Changes

**严重（1 个）**
- `decision_core.py:316-322` — 假跌破判定从 `prev_close >= support` 改为 `prev_close >= hard_stop`

**中等（12 个）**
- `main_force.py:158` — 阶段平局增加显式优先级
- `fusion_core.py:180-200` — `_score_to_confidence` 40/41 分界处修复连续性
- `fusion_core.py:266-272` — 权重 clamp 后归一化逻辑修正
- `chip_distribution.py:118` — `turnover_rate=0` 时设置最低 decay
- `stage_positioning.py:302-315` — 置信度门限从 60 降到 50
- `stage_positioning.py:539-542` — 删除死代码 `elif is_locked`
- `stage_positioning.py:642` — 派发阶段止损改为 `MA20 * 0.98`
- `decision_core.py:473-485` — 未知状态返回合理默认分而非 0
- `decision_core.py:525-532` — ATR 止损缓冲随波动率调整
- `structure_core.py:208-332` — `confirm_buffer` 增加下限 clamp
- `structure_core.py:279` — HMM 混合改为真混合（向 HMM 值靠拢）
- `signal_utils.py:159-160` — 后缀纠错逻辑修正或文档修正

**低（6 个）**
- `main_force.py:201` — `_calc_price_change` 数据不足返回 None
- `fund_flow_data.py:139-154` — 连续流入/流出在 net_flow=0 时的处理
- `fund_flow_data.py:133-136` — `cum_5` 不足 5 天时标签修正
- `stage_positioning.py:86-87` — 确认量价阈值设计意图
- `decision_core.py:498-502` — score_for 路径选择文档化
- `decision_core.py:329-353` — 状态优先级顺序文档化

## Capabilities

### New Capabilities

（无，纯 bug 修复）

### Modified Capabilities

- `data-safety`: 假跌破判定修正
- `calc-safety`: 置信度连续性、权重归一化、confirm_buffer 下限

## Impact

受影响文件：
- `02-共享模块-shared/trader_shared/decision_core.py` — 假跌破 + 评分 + ATR
- `02-共享模块-shared/trader_shared/fusion_core.py` — 置信度 + 权重
- `02-共享模块-shared/trader_shared/structure_core.py` — confirm_buffer + HMM 混合
- `02-共享模块-shared/trader_shared/stage_positioning.py` — 置信度门限 + 死代码
- `02-共享模块-shared/trader_shared/chip_distribution.py` — 零换手衰减
- `02-共享模块-shared/trader_shared/main_force.py` — 平局优先级 + 价格变化
- `02-共享模块-shared/trader_shared/fund_flow_data.py` — 连续天数 + 标签
- `02-共享模块-shared/trader_shared/signal_utils.py` — 后缀纠错
