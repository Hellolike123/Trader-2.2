## Context

当前 6 个 skill（trader/t0-trader/trader-pool/trader-portfolio/review-trader/trader-tracking）存在骨架重复、紧耦合、边界模糊等问题。`docs/skill-consolidation-plan.md` 已有完整的设计方案（6→3 合并、四阶段定位、输出格式规范等）。

## Goals / Non-Goals

**Goals:**
- 6 个 skill 合并为 3 个（trader/t0/review）
- 消除骨架重复（6 套 → 3 套 SKILL.md 等）
- 消除 pool 和 trader 之间的紧耦合
- 实现四阶段定位模型
- 从 trader 移除扩展数据（省 7 秒）
- 统一输出格式规范

**Non-Goals:**
- 不改变 trader_shared 包结构
- 不实现 funda skill（基本面分析，未来单独做）
- 不实现板块共振检测（暂缓）
- 不改变信号契约（Signal Contract v1 不变）

## Decisions

### 1. 目录结构：3 个新目录替代 6 个旧目录

```
01-功能包-packages/
  ├── trader/          ← 合并 01-单票分析-trader + 03-选股池-trader-pool
  ├── t0/              ← 02-盘中T0-t0-trader（变薄）
  └── review/          ← 合并 04-仓位轮动 + 05-盘后复盘 + 06-信号追踪
```

### 2. 四阶段定位模型

两层嵌套：
- 第一层：大阶段（蓄势/主升/派发/衰退）→ 基于 MA250/MA60/MA20 关系 + 价格位置
- 第二层：短期动能（走强/修复/震荡/转弱）→ 基于 MA5/MA10 + change_pct + position_ratio

组合决策矩阵输出仓位建议和操作方向。

### 3. 250日线一票否决改为提醒

原来：`_ma250_check()` 直接返回"暂不碰"，跳过所有分析
改为：250日线下方显示警告，但继续输出完整分析

### 4. 扩展数据从 trader 移除

`_enrich_snapshot` 调用（4 路外部 API，耗时 7 秒）从 trader 的 `run_analysis.py` 中移除。未来在 funda skill 中独立实现。

### 5. 分析模块并行化

`chanlun_strategy`、`wyckoff_strategy`、`momentum_strategy` 用 `ThreadPoolExecutor` 并行运行。

### 6. 仓位跟着大阶段走

- 蓄势期：0-30%
- 主升期：50-80%
- 派发期：0-30%
- 衰退期：0%

ATR 变成阶段范围内微调工具。

## Risks / Trade-offs

**[pool import 断裂]** trader-pool 的 run_analysis.py 直接 import trader 的 run_analysis
→ 缓解: 合并后同一 skill 内部调用，耦合自动消除

**[pack_all.py 重写]** 打包脚本硬编码了 6 个旧目录
→ 缓冲: 重写为支持 3 个新目录

**[信号统计分析数据不足]** 需要足够的 signals.jsonl 历史数据
→ 缓解: 先实现框架，数据不够时显示"数据不足"

**[四阶段判定精度]** MA 关系判定大阶段可能不够准确
→ 缓解: 先用简单规则，后续可接入 HMM 优化
