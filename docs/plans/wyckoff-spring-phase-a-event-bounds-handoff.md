# Spring 认 Phase A 雏形下沿（事件用）— Handoff

> **status**: impl_done（2026-03-22；南网 tip 原因从「非交易区间」→「未刺穿支撑」）  
> **日期**: 2026-03-22  
> **触发**: 南网科技 Spring 客观存在，tip 报「非交易区间（振幅过大）」；`phase_a` 已 established（sc_low/ar_high）但未进 Spring 的 `tr_lower`  
> **法源**: 原典 TR = SC/ST lows + AR high；L0–L3 仍禁止 L1 量度/成熟箱展示

## 必须

1. `phase_a` 有 `sc_low`（forming/established）时，为 **事件检测** 注入 `tr_lower=sc_low`（有 `ar_high` 则 `tr_upper`），**不**写 `phase_a_seed`、**不**抬 L2/L3 展示。  
2. 在 `_build_phase_a_range` 之后 **重判** Spring / ST / spring_test（对标 SOS 二次重判）。  
3. 禁止用分位 TR 假箱冒充；仅用 phase_a 钉的 SC/AR 价。

## 禁止

- 改 fusion/出手；L1 面板写成熟「箱体 lo-hi」量度

## 验收

- 南网：有 sc_low 时 Spring 不再仅因「非交易区间」整段灭灯（若价量满足刺穿收回则可亮）  
- L1 仍 `box_display_mode=proto` / 待 ST  
