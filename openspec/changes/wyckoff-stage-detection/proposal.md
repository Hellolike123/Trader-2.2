## Why

当前四阶段判定是纯 MA 驱动的简化版，缺少量价关系维度。讨论结果 #16 要求以威科夫市场周期理论为核心判定四阶段，#17 要求四层防护机制规避单点故障。

## What Changes

- 四阶段判定改为威科夫量价关系为核心（缩量横盘=蓄势，放量上涨=主升，放量不涨=派发，放量下跌=衰退）
- MA 结构作为辅助维度（多头/空头/收敛）
- ATR 波动作为辅助维度（上升/下降/走平）
- MA250 从阶段判定改为独立提醒层
- 四层防护：多日确认、置信度评分、缠论+动量交叉验证、阶段锁定期

## Impact

- 修改文件：`trader_shared/stage_positioning.py`
- 下游影响：run_analysis.py、portfolio_core.py、final_pool.py（调用 assess_stage 的地方）
