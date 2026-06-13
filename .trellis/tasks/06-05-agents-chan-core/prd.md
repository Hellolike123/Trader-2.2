# 更新 AGENTS 文档：补充 chan_core 修复记录

## Goal

补充 AGENTS.md 和 AGENTS_DEEP.md 中关于 chan_core.py 的修复记录，使文档与实际代码保持一致。

## What I already know

提交 `3ff332a` 包含 4 项修复：

1. **chan_core**: 新增 `_check_macd_for_2nd_buy()` — 二类买需 MACD 底背驰/止跌确认
2. **chan_core**: 空头排列过滤 — 最近5收盘价低于 MA5/10/20 则拒绝二类买
3. **chan_core**: MA 计算 bug — 从同窗口改为跨窗口比较
4. **decision_core**: 承接存在阈值 — `below_ma_count >= 1` 改为 `>= 3`
5. **fusion_core**: 二类买 confidence 从 0.6 降至 0.4

## Requirements

- 更新 AGENTS_DEEP.md 的 chan_core 章节（5.2）
- 更新 AGENTS_DEEP.md 的 fusion_core 章节（5.5）中的 confidence 值
- 更新 AGENTS.md 如有相关描述

## Acceptance Criteria

- [ ] AGENTS_DEEP.md 记录 `_check_macd_for_2nd_buy()` 函数
- [ ] AGENTS_DEEP.md 记录空头排列过滤逻辑
- [ ] AGENTS_DEEP.md 记录 MA 计算修复
- [ ] AGENTS_DEEP.md 记录承接存在阈值变更
- [ ] AGENTS_DEEP.md 更新二类买 confidence 为 0.4

## Out of Scope

- 不修改代码文件
- 不更新 output-template.md（输出模板不受影响）

## Technical Notes

- 文档路径：`AGENTS.md`、`AGENTS_DEEP.md`
- 相关代码：`chan_core.py`、`fusion_core.py`、`decision_core.py`
