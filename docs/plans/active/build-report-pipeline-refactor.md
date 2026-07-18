# build_report 流水线拆分（行为冻结）

> **分支**：`refactor/build-report-pipeline`  
> **原则**：只搬家/抽函数，不改加权、不改出手语义；每步跑门禁  
> **法源**：`docs/designs/resonance-and-orchestration.md` 阶段 5

## 目标

`build_report` 变成短总管：按序调用阶段函数；业务在 `report_pipeline`（及既有 cores）。

## 已完成

| 块 | 函数 | 状态 |
|----|------|------|
| 卡→共振→策略→决策 | `attach_analysis_decision_stack` | ✅ |
| 买点盖生命周期 | `apply_buy_point_lifecycle` | ✅ |
| 关键价+周框+纪律+结论+上两者 | `attach_short_midline_and_decision` | ✅ 大门禁 354 绿 |

`report_builder.py` 自 ~1800 行降至 ~1400 行；尾部短中线整段已出总管。

## 可选续拆（非阻塞）

1. **stage_pack**（持仓/仓位/exit_plan/suggested_pct_context）— 注意与 `sync_report_with_data` 循环 import，宜 lazy import  
2. **structure / chip**  
3. **plugins + fusion**  
4. **load snapshot + risk_flags**  

每抽一块：`bash scripts/run-gate-tests.sh` 绿再 commit。

## 不做

- 改 fusion 公式、改决策铁律  
- 与 T0/池接线混在同一 PR  
