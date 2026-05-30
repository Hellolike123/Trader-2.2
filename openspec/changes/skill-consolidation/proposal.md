## Why

当前 6 个 skill 存在骨架重复（6 套 SKILL.md/HERMES.md/commands.md）、紧耦合（pool 直接 import trader 的 run_analysis）、边界模糊（pool 和 trader 都有 run_analysis.py）、80% 提交跨 skill 等问题。合并为 3 个 skill 可消除重复、降低维护成本、统一用户体验。

同时引入四阶段定位模型（大阶段+短期动能嵌套）、250日线提醒不屏蔽、仓位跟着大阶段走等核心设计改进。

## What Changes

- 6 个 skill 合并为 3 个：trader（分析+选票）、t0（盯盘）、review（复盘+仓位+追踪）
- 从 trader 中移除扩展数据（股东/机构/解禁/题材），省 7 秒
- 实现四阶段定位逻辑（蓄势/主升/派发/衰退 × 走强/修复/震荡/转弱）
- 250日线一票否决改为提醒不屏蔽
- 仓位跟着大阶段走（ATR 变成阶段内微调工具）
- 信号统计分析重新设计（纯数字，不给建议）
- 分析模块并行化（chanlun/wyckoff/momentum 并行）
- 重写 pack_all.py 支持新结构
- 统一输出格式规范（微信端格式红线）

## Capabilities

### New Capabilities
- `stage-positioning`: 四阶段定位模型（大阶段+短期动能嵌套组合决策）
- `signal-stats`: 信号统计分析（说买→涨了吗？说卖→跌了吗？纯数字）

### Modified Capabilities
- `trader`: 从 6 合 3 后的 trader skill，合并 pool 功能，移除扩展数据，新增四阶段定位
- `t0`: 从 t0-trader 独立出来，职责变薄（只看+只响）
- `review`: 合并 review-trader + trader-portfolio + trader-tracking

## Impact

- 修改目录：`01-功能包-packages/` 下 6 个目录合并为 3 个
- 修改文件：run_analysis.py、final_pool.py、final_review.py、portfolio_core.py、signal_tracker.py、pack_all.py、各 SKILL.md/commands.md/output-contract.md
- 新增文件：3 个新 skill 目录结构
- 删除文件：旧的 6 个 skill 目录
- 依赖：无新依赖
- 向后兼容：trader.py CLI 路由保持不变
