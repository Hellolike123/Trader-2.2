# 交易系统准确性 & 正确性修复

## 目标
修复交易系统中的准确性和正确性问题，只修 P0 + P1，不改功能逻辑，不加新特性。

## P0 修复（4 项）

### 1. 阶段状态按股票隔离
- 文件：`02-共享模块-shared/trader_shared/stage_positioning.py`
- 改动：`_save_stage_state()` / `_load_stage_state()` 加 `symbol` 维度，存储格式从 `dict` 改为 `dict[symbol, dict]`
- 验证：连续分析两只票，确认第二只的状态不会覆盖第一只

### 2. 衰退阶段止损兜底
- 文件：`stage_positioning.py` → `compute_stop_losses()`
- 改动：衰退阶段 `stage_stop` 从 `0.0` 改为 `current_price`（立即退出），确保 `final_stop` 不会是 0
- 验证：构造衰退阶段输入，确认 `final_stop > 0`

### 3. 评分 gap 逻辑修正
- 文件：`02-共享模块-shared/trader_shared/decision_core.py` → `score_for()`
- 改动：当 `current >= confirm` 时，跳过 gap 扣分（不再对已突破的票扣分）
- 验证：输入一个已突破确认位的 case，确认分数不被扣

### 4. 池子停牌检测
- 文件：`01-功能包-packages/trader/scripts/final_pool.py`
- 改动：在 `cmd_plan` / `cmd_list` 中检查 `data_freshness`，交易时间内如果 `data_freshness == "stale"` 则标记为"疑似停牌"
- 验证：用过期缓存数据模拟，确认输出中有停牌提示

## P1 修复（5 项）

### 5. 威科夫 BC 扫描扩展
- 文件：`02-共享模块-shared/trader_shared/wyckoff_core.py` → `_detect_buying_climax()`
- 改动：从只看 `bars[-1]` 扩展到扫描 `bars[-5:]`，任一满足 BC 条件即触发
- 验证：构造 3 天前出现 BC 的数据，确认能检测到

### 6. HMM 结果缓存
- 文件：`02-共享模块-shared/trader_shared/hmm_regime.py` + `market_env.py`
- 改动：在 `detect_regime()` 层加内存缓存，同一交易日内相同输入不重复计算；缓存 key 用 `(data_hash, date)` 组合
- 验证：连续调用两次，第二次耗时应 < 10ms

### 7. 跳空缺口处理
- 文件：`stage_positioning.py` → `_assess_volume_price()`
- 改动：当单日涨跌幅 > 7% 时，从 5 日涨幅计算中剔除该日（或用 ATR 归一化），避免单日缺口主导阶段判定
- 验证：构造涨停后横盘 4 天的 case，确认不会被误判为"主升"

### 8. 新股置信度打折
- 文件：`stage_positioning.py` → `evaluate_stage()`
- 改动：当 `len(bars) < 60` 时，置信度乘以 `len(bars) / 60` 的折扣系数，输出加"新股数据不足"警告
- 验证：输入 30 天数据，确认置信度 ≤ 50%

### 9. 信号 ID 碰撞修复
- 文件：`02-共享模块-shared/trader_shared/signal_utils.py` → `normalize_signal_id()`
- 改动：当 `trigger_price = 0` 时，用 `"no_price"` 替代 `"0.00"` 参与 hash；加入 `source_skill` 字段
- 验证：两个不同信号但 price=0，确认生成不同 ID

## 附带清理

- `STATUS_SCORE` 去重：删除 `decision_core.py` 中的重复定义，统一用 `config.py`
- 死代码删除：移除 `light_data.py` 中重复的 Tencent fetch 重试

## 不改的内容

- 时间止损分级、移动止损放宽——这是功能变更，单独立项
- 评分 YAML 统一化——这是重构，不在 bugfix 范围
- 性能优化（线程池复用等）——单独立项

## 验收标准

- 现有测试全部通过
- 每个 P0 修复补充对应的单元测试
- 手动跑一次 `trader script --target <NAME>` 确认输出无异常
