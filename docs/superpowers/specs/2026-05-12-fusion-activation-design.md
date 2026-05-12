# Fusion 激活：FUSION_LOG_ONLY 默认 false

**日期**: 2026-05-12

## 问题

`FUSION_LOG_ONLY=true` 导致融合 action = "日志模式..."，`build_signal()` 的 `_map_fusion_to_signal()` 无法匹配该值，融合层虽然代码已接入但实际不会生效。

## 变更

在 `fusion_core.py` 中将默认值从 `"true"` 改为 `"false"`。

## 风险

- 融合层决策会覆盖 scene 决策（本次修改的目标）
- 可通过环境变量 `FUSION_LOG_ONLY=true` 临时恢复旧行为

## 测试

- 融合层 62 测试全部通过
- build_signal 11 测试全部通过
