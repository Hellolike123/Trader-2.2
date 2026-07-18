# build_report 流水线拆分（行为冻结）

> **分支**：`refactor/build-report-pipeline`  
> **原则**：只搬家/抽函数，不改加权、不改出手语义；每步跑门禁  
> **法源**：`docs/designs/resonance-and-orchestration.md` 阶段 5

## 目标

`build_report` 变成短总管：按序调用阶段函数；业务在 `report_pipeline`（及既有 cores）。

## 已完成

| 块 | 函数 | 状态 |
|----|------|------|
| 卡→共振→策略→决策 | `attach_analysis_decision_stack` | ✅ main |
| 买点盖生命周期 | `apply_buy_point_lifecycle` | ✅ 本分支 |

## 建议续拆顺序（由边界清晰 → 难）

1. **discipline + conclusion 组装尾段**（门控后写 report 字段）  
2. **key_prices / mid_key_prices / weekly_frame**  
3. **stage_pack / position_state / suggested_pct**  
4. **structure / chip**  
5. **plugins + fusion**（注意 pre_cards）  
6. **load snapshot + risk_flags + live_bar**（最前）

每抽一块：`bash scripts/run-gate-tests.sh` 绿再 commit。

## 不做

- 改 fusion 公式、改决策铁律  
- 与 T0/池接线混在同一 PR  
