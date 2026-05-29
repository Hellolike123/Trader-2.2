# Doc Overhaul — 设计

> 决策日期：2026-05-29

---

## 文档体系关系图

```
AGENTS.md (快速参考，给 Agent 用)
  │
  ├── 决策流程概览
  ├── 关键配置项速查
  └── 链接 → AGENTS_DEEP.md

AGENTS_DEEP.md (深度参考，给 Agent 用)
  │
  ├── 状态机详解 ──────→ decision_core.py (status_layers)
  ├── 数据流图 ────────→ 实际代码调用链
  ├── 函数签名 ────────→ config.py, fusion_core.py
  └── 引用 ───────────→ docs/designs/*.md

docs/designs/decision-fusion-layer.md (融合层设计)
  │
  ├── 架构设计
  ├── 信号加权 + 冲突检测
  └── 输出格式规格

docs/trader-refactor-plan.md (ATR 体系)
  │
  ├── ATR 计算方式
  ├── 移动止损机制
  └── 止损策略演进

docs/phase2-improvement-plan.md (审计记录)
  │
  ├── 已发现的问题 (C-1..C-13, S-1..S-N)
  └── 修复状态标记
```

---

## 设计决策

### D1: 新增文档放在 specs/ 下，不混入现有文档

250日线过滤和退出策略是独立的功能模块，有自己的规格。放在 `specs/` 下而不是塞进 `trader-refactor-plan.md`，原因是：
- trader-refactor-plan.md 是历史设计文档，描述的是"当时想怎么做"
- specs/ 描述的是"现在实际是什么"
- 两者定位不同，混在一起会造成混淆

### D2: 更新现有文档而非废弃重写

`decision-fusion-layer.md` 和 `trader-refactor-plan.md` 有历史价值（记录了设计演进），直接废弃会丢失上下文。选择在原文档上更新，用"最后更新"标记和变更说明来标识修改。

### D3: AGENTS 文件分层更新

- `AGENTS.md`：只添加行为级描述（"250日线下方一票否决"），不放实现细节
- `AGENTS_DEEP.md`：更新函数签名、状态列表、数据流图等技术细节

### D4: phase2 用注释标记而非删除

已修复的 issue（如 C-13）不删除，而是在段落开头加 `[RESOLVED]` 标记并说明修复方式。保留审计记录的价值。

---

## 执行顺序

```
1. specs/trend-filter/spec.md        ← 独立，无依赖
2. specs/exit-strategy/spec.md       ← 独立，无依赖
3. specs/fusion-layer-sync/spec.md   ← 需要读代码确认最新签名
4. docs/designs/decision-fusion-layer.md  ← 依赖 #3 的确认结果
5. docs/trader-refactor-plan.md      ← 依赖 #2 的 spec
6. docs/phase2-improvement-plan.md   ← 依赖 #1 的 spec
7. specs/agents-sync/spec.md         ← 依赖 #1-6 全部完成
8. AGENTS.md + AGENTS_DEEP.md        ← 依赖 #7
```

1-2 可以并行，3-6 可以并行，7-8 串行。
