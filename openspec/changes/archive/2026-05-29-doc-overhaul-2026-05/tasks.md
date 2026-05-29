# Doc Overhaul — 任务清单

- [x] 1. 编写 `specs/trend-filter/spec.md` — 250日线趋势过滤规格
- [x] 2. 编写 `specs/exit-strategy/spec.md` — ATR移动止损 + 假跌破 + 分阶段退出规格
- [x] 3. 编写 `specs/fusion-layer-sync/spec.md` — 融合层文档同步差异清单
- [x] 4. 更新 `docs/designs/decision-fusion-layer.md`
  - [x] 4a. 更新 merge_decisions 签名（4→8参数）
  - [x] 4b. 修正 FUSION_LOG_ONLY 默认值（true→false）
  - [x] 4c. 更新输出示例（action 字符串 + 多行格式）
  - [x] 4d. 添加 hmm_regime 到输出字段
  - [x] 4e. 新增 FUSION_STATUS_MAP + 覆盖机制 Section
  - [x] 4f. 新增 Scenario Priority Filter Section
  - [x] 4g. 简要提及贝叶斯融合和 Veto 机制
- [x] 5. 更新 `docs/trader-refactor-plan.md`
  - [x] 5a. 添加动态移动止损 Section
  - [x] 5b. 标注 --atr/--no-atr 为未实现（文件中不存在该 flag，无需标注）
- [x] 6. 更新 `docs/phase2-improvement-plan.md`
  - [x] 6a. C-13 标记为 [RESOLVED] 并说明修复方案
  - [x] 6b. 确认其他 issue 的修复状态（其他 issue 需单独确认，不在本次范围）
- [x] 7. 编写 `specs/agents-sync/spec.md` — AGENTS 同步规格
- [x] 8. 更新 `AGENTS.md`
  - [x] 8a. 添加 250日线趋势过滤描述
  - [x] 8b. 添加 ATR 移动止损 + 假跌破 + 分阶段退出描述
  - [x] 8c. 添加 status_layers() 描述
  - [x] 8d. 添加融合覆盖机制描述
  - [x] 8e. 更新决策流程图
- [x] 9. 更新 `AGENTS_DEEP.md`
  - [x] 9a. 更新 Section 2.3 状态机（STATUS_SCORE 完整列表）
  - [x] 9b. 更新 Section 5.1 核心函数（status_for→status_layers）
  - [x] 9c. 更新 merge_decisions 签名
  - [x] 9d. 更新 Section 5.6.2 添加 HMM 参数
  - [x] 9e. 重绘 Section 8 数据流图
- [x] 10. 最终审查 — 逐文档确认与代码一致

---

## 执行顺序

```
Phase 1 (并行): Task 1, 2, 3
Phase 2 (并行): Task 4, 5, 6
Phase 3 (串行): Task 7 → 8 → 9
Phase 4: Task 10
```
