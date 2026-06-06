# Round 2 修复 - 三个 P1 bug

## 目标
修复三轮审计新发现的三个 P1 bug。

## 修复项

### 1. 融合层冲突消解静默归零动量
- 文件：`02-共享模块-shared/trader_shared/fusion_core.py:416-424`
- 问题：强结构信号 + 反向动量时，动量方向直接设为 0，`disagreement_for_action=0`，掩盖风险信号
- 修复：改为衰减 `direction × 0.3` 而非归零，保留风险信号

### 2. import 路径错误导致配置不生效
- 文件：`02-共享模块-shared/trader_shared/decision_core.py:305`
- 问题：`from config import PULLBACK_CONFIRM_DAYS, EXIT_PHASED_ENABLED` 路径错误，永远走 except 用硬编码默认值
- 修复：改为 `from trader_shared.config import`

### 3. 阶段锁定按调用次数递减而非交易日
- 文件：`02-共享模块-shared/trader_shared/stage_positioning.py:340-365`
- 问题：注释说"锁定5天"，代码用 `pending_count` 计数调用次数，一天多次分析会缩短锁定
- 修复：使用交易日期（`state["pending_date"]`）判断是否跨日

## 验收标准
- 现有测试全部通过
- 每个修复补充对应的单元测试
