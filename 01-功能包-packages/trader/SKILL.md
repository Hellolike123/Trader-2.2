# Trader — 单票分析 + 选股池全生命周期管理

## 职责
- 单票分析（缠论/威科夫/动量/筹码/ATR 综合研判）
- 选股池管理（入池/出池/作战表/多票对比）
- 四阶段定位（蓄势/主升/派发/衰退 × 走强/修复/震荡/转弱）

## 命令映射
- `trader script --target <NAME>` → 单票分析
- `trader script add --target <NAME>` → 入池
- `trader script plan` → 明日作战表
- `trader script list` → 池子概览
- `trader script compare --targets A B C` → 多票对比
- `trader script remove --target <NAME>` → 移除出池

## Hermes 触发词
- 「分析南网科技」→ trader --target 南网科技
- 「南网科技入池」→ trader add --target 南网科技
- 「明日作战表」→ trader plan
- 「看看池子」→ trader list
- 「对比南网科技和中国铝业」→ trader compare --targets A B
