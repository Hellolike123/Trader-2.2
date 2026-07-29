> **已归档（2026-07-29）**：历史计划/摘要，勿按本文施工。现行法源见 `AGENTS.md` + `docs/designs/resonance-and-orchestration.md`。

# Gemini 建议实现规格文档

## P0-1：Spring 改 ATR 动态比例

### 规格要求
1. config.py 新增 `WYCKOFF_SPRING_ATR_MULTIPLE = 0.5`
2. `_detect_spring()` 中 `breach_level = support * WYCKOFF_SPRING_RECLAIM_RATIO` 改为 ATR 动态计算
3. 优先用 ATR，ATR 不可用时 fallback 到原固定比例
4. ATR 数据来自 bar 上的 `atr14` 字段（已由 `_compute_atr_fields()` 计算）

### 实现清单
- [ ] config.py: 新增常量
- [ ] wyckoff_core.py: import 新常量
- [ ] wyckoff_core.py: `_detect_spring()` 改用 ATR 计算 breach_level
- [ ] 测试: 单元测试覆盖 ATR 可用和不可用两种情况
- [ ] 验证: 真实数据跑 Spring 检测

## P0-2：假跌破硬性熔断

### 规格要求
1. config.py 新增 `HARD_STOP_SINGLE_DAY_DROP = -0.07`（单日跌幅超 7%）
2. `decision_core.py` 的 `status_layers()` 中，假跌破确认之前先检查单日跌幅
3. `change <= -7%` 直接返回"风险回避"，跳过假跌破逻辑

### 实现清单
- [ ] config.py: 新增常量
- [ ] decision_core.py: import 新常量
- [ ] decision_core.py: `status_layers()` 在假跌破逻辑前加硬性熔断检查
- [ ] 测试: 单元测试覆盖熔断触发和未触发情况
- [ ] 验证: 真实数据验证

## P0-3：T+1 隔离锁

### 规格要求
1. `stage_positioning.py` 的 `evaluate_position_state()` 新增 `last_add_date` 参数
2. 回踩加仓路径中检查 `last_add_date == today`
3. 当天已加仓则返回"持仓观察（T+1冷却）"

### 实现清单
- [ ] stage_positioning.py: `evaluate_position_state()` 新增参数
- [ ] stage_positioning.py: 回踩加仓路径加 T+1 检查
- [ ] 调用方传入 `last_add_date`
- [ ] 测试: 单元测试覆盖 T+1 冷却情况
- [ ] 验证: 真实数据验证

## P0-4：多周期支撑压力阶梯展示

### 规格要求
1. structure_core.py 新增 `find_key_levels(bars)` 函数
2. 在 300 根数据里找三个周期的关键位：
   - 短线（10日）：最近 10 日的高低点
   - 中线（60日）：最近 60 日的重要支撑/压力（至少 2 次触及未破）
   - 长线（120日）：最近 120 日的重要支撑/压力
3. 输出 dict：`{"short_support", "mid_support", "long_support", "short_resist", "mid_resist", "long_resist"}`
4. run_analysis.py 调用并写入 levels
5. 报告渲染为价格阶梯（从低到高）

### 实现清单
- [ ] structure_core.py: 新增 `find_key_levels()` 函数
- [ ] run_analysis.py: 调用并写入 levels
- [ ] run_analysis.py: 报告渲染为价格阶梯
- [ ] 测试: 单元测试覆盖边界条件
- [ ] 验证: 真实数据验证阶梯展示

## P0-5：长线压力位动态动作

### 规格要求
1. run_analysis.py 渲染时，长线压力位的动作由系统动态决定
2. 依据信号：`weighted_score`、成交量、缠论趋势标签
3. 逻辑：
   - `weighted_score >= 0.25` 且放量 → "持有关注（趋势强）"
   - `weighted_score >= 0.1` → "减仓 20%"
   - 否则 → "减仓 50%（趋势弱）"
4. 其他压力位动作固定（短线卖 20%，中线减 30%）

### 实现清单
- [ ] run_analysis.py: 长线压力位动态动作逻辑
- [ ] 测试: 覆盖三种情况（强/中/弱）
- [ ] 验证: 真实数据验证

## P0-6：止损分层展示

### 规格要求
1. 报告「📌 如果你有持仓」区块分短线止损和中线止损
2. 短线止损 = 短线支撑下方
3. 中线止损 = 长线支撑下方

### 实现清单
- [ ] run_analysis.py: 持仓区块分层展示
- [ ] 验证: 真实数据验证

## P0-7：亮点与风险距离百分比量化

### 规格要求
1. 亮点：描述当前价距离最近支撑的百分比
2. 风险：描述当前价距离最近压力的百分比

### 实现清单
- [ ] run_analysis.py: 亮点与风险用距离百分比
- [ ] 验证: 真实数据验证

## 向后兼容检查

- [ ] 不删除任何现有返回字段
- [ ] 新增字段写入 levels 中间层
- [ ] 测试覆盖边界条件（空/最少/正常输入）
