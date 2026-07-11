# PRD — 缠论增量引擎 ChanlunEngine

## 目标
将 `chanlun_analysis()` 从「无状态纯函数」重构为「有状态增量引擎 `ChanlunEngine`」，实现状态持久化、实时 T0 续算、模块化独立。完整规格见 `.mimocode/plans/1783685709154-silent-wolf.md`（第六节为原方案，第七节为主 agent 实测后的修订，以第七节为准）。

## 范围（Phase 1，本任务）
- 抽取共享内部函数 `_chanlun_compute(cleaned, current, ...)`，`chanlun_analysis` 改为委托它（字节级向后兼容）
- 新增 `ChanlunEngine`：有状态、`update_bar`（append / 当前 bar replace）、`get_analysis`（全参数透传 + 缓存 higher_trend）、`save` / `load`
- 持久化状态含 MACD EMA 状态（`_ema12/_ema26/_dea`）、inclusion run 起点、higher_trend 缓存、最后 bar 身份
- `config.py` 新增 `CHANLUN_STATE_DIR`
- 测试：原计划 7 组 + 第七节修订（全字段一致性为主门、修正语义等价、性能降级为参考）

## 不在本任务（Phase 2 opt-in）
T0 盯盘 / realtime_tracker 接入、cache warm 预建。批量调用方零改动。

## 验收门槛（优先级）
1. **正确性**：增量结果 ≡ 批量结果（完整 22 字段 dict，归一后相等）—— 主门
2. **接口兼容**：`chanlun_analysis` 签名/输出不变；所有下游 `unwrap_chan` 消费方不受影响
3. **持久化**：save/load 后状态一致（含 MACD EMA，numpy 类型归一）
4. **性能**：增量每 tick 不慢于批量重算（参考性，非硬门槛）

## 核心约束（来自评审第七节）
- **复用纯函数，禁止重实现**：增量引擎只维护 `self.cleaned` 等中间序列，下游全部走 `_chanlun_compute`，一致性由构造保证
- MACD 须维护 EMA 状态（7.4）；包含处理须覆盖级联 inclusion run（7.3）；get_analysis 须透传全参数（7.7）
- 测试 1 用同一 `weekly_bars` 比对，避免 higher_trend 抖动造成 diff
