## 1. 清理利弗莫尔框架

- [ ] 1.1 删除 `trader_shared/livermore_rules.yml`
- [ ] 1.2 清理 `modifier_rule_engine.py` 中的 `apply_livermore_scale()` 函数
- [ ] 1.3 清理 `portfolio_core.py` 中的 `livermore_tier` 计算
- [ ] 1.4 清理 `portfolio_run.py` 中的 `livermore_score` fallback
- [ ] 1.5 保留 `apply_score_modifiers`（非利弗莫尔功能）

## 2. 四阶段仓位管理

- [ ] 2.1 在 `stage_positioning.py` 中添加仓位规则常量（蓄势30%/主升80%/派发30%/衰退0%）
- [ ] 2.2 在 `run_analysis.py` 的决策输出中使用阶段仓位上限
- [ ] 2.3 实现硬规则：持仓亏损时禁止加仓

## 3. 选股池精简

- [ ] 3.1 合并 `show` + `list` 为 `list`（池子概览）
- [ ] 3.2 合并 `rank` + `plan` 为 `plan`（作战表）
- [ ] 3.3 更新 `final_pool.py` 的 argparse 命令映射

## 4. 选股池显示阶段信息

- [ ] 4.1 在 `list` 输出中每只票显示大阶段+短期动能
- [ ] 4.2 在 `plan` 输出中按阶段排序（主升期优先，蓄势期其次）

## 5. 入池规则挂钩四阶段

- [ ] 5.1 实现阶段筛选：衰退期直接拒绝
- [ ] 5.2 实现评分门槛：蓄势≥70观察/≥80执行，主升≥60执行，派发≥70观察
- [ ] 5.3 实现风控检查：现价跌破止损→拒绝
- [ ] 5.4 实现出池规则：阶段跌到衰退→自动淘汰提醒

## 6. 入池流程优化

- [ ] 6.1 在 trader 输出末尾显示「当前池 4/10，回复 1 入池」
- [ ] 6.2 实现回复 1 自动入池逻辑（阶段+评分检查→入池/拒绝）
