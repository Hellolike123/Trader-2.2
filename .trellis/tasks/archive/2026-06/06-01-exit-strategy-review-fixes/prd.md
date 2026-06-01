# 退出策略系统复查问题修复

## 中等问题（需要修复）

### 问题1：衰退期状态机逻辑
- **文件**：stage_positioning.py 第1250行
- **问题**：衰退期直接返回"空仓"，但有持仓时应该先清仓
- **修复**：检查 has_position，有持仓时返回"退出再买"状态（清仓动作）

### 问题2：exit_reentry 条件来源不明
- **文件**：stage_positioning.py 第1260行
- **问题**：conditions.get("exit_reentry", False) 没看到赋值逻辑
- **修复**：确认这个条件在哪里设置，或者移除这个检查

### 问题3：派发期止损用 MA20 而不是 EXPMA(20)
- **文件**：stage_positioning.py 第1035行
- **问题**：PRD 要求派发期用 EXPMA(20) 上方，当前用 MA20
- **修复**：改为 EXPMA(20)，需要传入 expma20 参数

### 问题4：时间止损没检查持仓
- **文件**：stage_positioning.py 第1075行
- **问题**：衰退期直接返回"清仓"，但没检查是否有持仓
- **修复**：加 has_position 检查，空仓时不触发清仓

### 问题5：compute_exit_plan 第三笔无触发价
- **文件**：stage_positioning.py 第871行
- **问题**：第三笔 price=None，用户不知道什么时候触发
- **修复**：添加触发条件描述（"阶段转派发"）

### 问题6：输出段落顺序不符合 PRD
- **文件**：run_analysis.py 第1050行
- **问题**：🎯 今日行动 在 📍 决策 之后，PRD 要求放最前面
- **修复**：调整输出顺序：🎯 今日行动 → 📍 决策 → 🔔 信号提醒 → ❗ 关键价位

### 问题7：_get_cost_from_signals 性能问题
- **文件**：run_analysis.py 第625行
- **问题**：读取整个 signals.jsonl，文件大时性能差
- **修复**：只读最近100条，或加缓存

### 问题8：check_time_stop 硬编码
- **文件**：stage_positioning.py 第1075行
- **问题**：蓄势期30天、主升期15天是硬编码魔法数字
- **修复**：提取为常量 ACCUMULATION_DAYS_LIMIT = 30, MARKUP_DAYS_LIMIT = 15

## 轻微问题（有空再修）

### 问题9：_calc_reentry_score 注释不完整
- **文件**：stage_positioning.py 第1457行
- **问题**：只注释了3个条件，第4个"阶段没变坏"没注释
- **修复**：补充完整注释

### 问题10：compute_stage_stop 参数名不直观
- **文件**：stage_positioning.py 第1035行
- **问题**：atr_pct 参数名不直观，建议改为 atr_ratio
- **修复**：重命名参数

## 验证

```bash
python3 -m pytest 02-共享模块-shared/tests/
python3 -m pytest 01-功能包-packages/trader/tests/
python3 01-功能包-packages/trader/scripts/final_report.py --target 南网科技
```
