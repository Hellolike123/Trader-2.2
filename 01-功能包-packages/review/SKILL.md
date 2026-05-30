# Review — 盘后复盘 + 仓位轮动 + 信号统计

## 职责
- 五层打分复盘（个股盘后分析）
- 仓位轮动（2-3 只票资金分配）
- 信号统计分析（信号准确率追踪）

## 命令映射
- `review script --target <NAME>` → 单票复盘
- `review script --all` → 全池复盘
- `review script --targets A B` → 仓位轮动
- `review script --tracking` → 信号统计分析

## Hermes 触发词
- 「复盘南网科技」→ review --target 南网科技
- 「复盘全部」→ review --all
- 「轮动中国铝业和南网科技」→ portfolio --targets A B
- 「信号追踪」→ tracking
