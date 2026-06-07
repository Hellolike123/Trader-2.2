# Round 3 修复 - review P0 NameError + 5 P1 准确性 bug

## 目标
修复 1 个 P0 阻塞 bug + 4 个 P1 准确性 bug，让 review 主流程恢复、T0 胜率回测拿到真实数据、缓存键一致。

## 修复清单

### 1. P0 - review_core.py NameError
- 文件：`01-功能包-packages/review/scripts/review_core.py:543-562`
- 问题：`selected_date` 赋值在使用之后 → UnboundLocalError，所有 review 命令崩溃
- 修复：把赋值上移到 try 块前

### 2. P1 - time_part 误杀 T0 盘中信号
- 文件：`01-功能包-packages/trader/scripts/run_analysis.py:910` + 2 副本
- 问题：`time_part >= "15:00"` 误杀盘中 T0 信号
- 修复：只对 `review_result` 生效

### 3. P1 - T0 卖方向与白名单
- 文件：`01-功能包-packages/t0/scripts/t0_core.py:135` + `01-功能包-packages/trader/scripts/run_analysis.py:907`
- 问题：T0 卖方向 "neutral" + 白名单不含 `high_sell_triggered`
- 修复：改方向为 `bearish_lean` + 加白名单

### 4. P1 - tick_cache 跨日缓存键错位
- 文件：`01-功能包-packages/t0/scripts/t0_run.py:101`
- 问题：`save_tick_cache` 漏传 `trade_date` → 跨日缓存键错位
- 修复：补 `trade_date=quote.get("trade_date")`

### 5. P1 - review_render 死代码
- 文件：`01-功能包-packages/review/scripts/review_render.py:246,260`
- 问题：`review_label` 死代码，午间复盘仍输出"盘后复盘"违反合同
- 修复：用 `session_label` 替换硬编码

## 验收标准
- 现有 90+67+28 测试全通过
- 4 个新回归测试：build_review 不抛异常、T0 盘中时间入桶、T0 卖方向正确、tick_cache 跨日不丢
- 手动验证 review/t0 主流程可用

## 范围之外
- P2/P3 6 项单独立项跟踪
- 先前的 8 个准确性 bug（阶段状态隔离等）也单独立项

## 预估
5-7 行代码 + 4 个测试
