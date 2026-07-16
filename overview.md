# Trader3.0 项目知识沉淀 — 交付摘要

> 生成时间: 2026-07-14；文档再同步: 2026-07-16（代码标杆：周线 260 / wave_label / regime 很差 / 融合权重）
> 基于: trader_shared 代码 + 活文档（AGENT / BUSINESS / AGENTS）

---

## 一、已交付文档

| 文档 | 位置 | 行数 | 读者 |
|------|------|------|------|
| **AGENT.md** | `/AGENT.md` | ~280 | AI Agent（最高规范） |
| **ARCHITECTURE.md** | `/ARCHITECTURE.md` | ~230 | 开发者 / Agent |
| **BUSINESS.md** | `/BUSINESS.md` | ~190 | 开发者 / 业务 |
| **README.md** | `/README.md` | ~65 | 所有人 |

## 二、文档引用关系

```
README.md (项目入口)
  ├── AGENT.md ← 任何 AI Agent 进入项目后的第一份读物
  │   ├── ARCHITECTURE.md ← 架构细节
  │   ├── BUSINESS.md ← 业务规则
  │   ├── docs/ci-gate.md ← CI 门禁
  │   ├── docs/designs/ ← 设计文档（P0/P1/P3）
  │   └── docs/output-redux-plan.md ← 报告模板规范
  │
  └── ARCHITECTURE.md
      └── docs/ADR-*.md ← 架构决策记录
```

## 三、项目健康检查摘要

### 全部通过
- ✅ 无向上依赖（ADR-001 收编完成）
- ✅ 无循环导入
- ✅ 领域-展示层正确分离（ADR-003b）
- ✅ 展示型插件不进融合评分
- ✅ box_detect 正确隔离
- ✅ fusion_core print 已修复
- ✅ data_provider env 写入已修复
- ✅ wyckoff phase 持久化已修复

### 已知技术债（非阻塞）
- 🟡 self_calibration.py 有 ~10 个 print() 在生产路径
- 🟡 wyckoff_core + wyckoff_phase 有 ~100 行重复配置 fallback
- 🟡 report_renderer/ 子包是 thin re-export（实现在 report_core.py）
- 🟡 `03-输出校验-contracts/` 空目录可清理

### 2026-07-16 文档对齐（已完成）
- ✅ `WEEKLY_LOOKBACK_BARS=260` 写入 AGENTS/BUSINESS/ARCHITECTURE
- ✅ wave_label「笔数不足」契约与代码一致
- ✅ regime=很差 → 空仓侧（非字面暂不碰）写入 AGENT/BUSINESS
- ✅ 融合权重正常 0.30/0.45/0.25 与 yaml 一致
- ✅ user-guide 示例切到双轨模板

### 2026-07-17
- ✅ 日频缓存（筹码/资金流/大盘/板块/日周K）+ 性能 profile
- ✅ 威科夫 A 档出口 `WyckoffStateView`（`wyckoff_view.py` + `docs/designs/wyckoff-state-view.md`）

## 四、后续建议

1. **清理技术债**：self_calibration print → logger、wyckoff 配置去重、空目录清理
2. **Skill 副本**：打包后 Hermes 技能包与仓库文档定期 diff
3. **CI 增强**：考虑加入 `golden_diff_gate.py check --replicas` 到 pre-push hook

## 五、AI Agent 如何使用这些文档

新 Agent 进入项目的标准流程：
1. 读 `AGENT.md` → 理解架构、规范、工作流
2. 读 `ARCHITECTURE.md` → 理解模块职责、依赖关系
3. 读 `BUSINESS.md` → 理解业务规则、计算规则
4. 按需读 `docs/designs/` → 理解具体设计决策
5. 开始开发
