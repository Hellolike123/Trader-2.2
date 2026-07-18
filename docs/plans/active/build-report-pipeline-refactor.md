# build_report 流水线拆分（行为冻结）— 工程债收口

> **分支**：`refactor/build-report-debt` → 合 main  
> **原则**：只搬家/抽函数 + 元数据标记；不改加权公式、不改出手铁律  
> **法源**：`docs/designs/resonance-and-orchestration.md`

## 已完成（工程债清单）

| 项 | 落点 | 状态 |
|----|------|------|
| 卡→共振→策略→决策 | `attach_analysis_decision_stack` | ✅ |
| 买点盖 | `apply_buy_point_lifecycle` | ✅ |
| 短中线整段 | `attach_short_midline_and_decision` | ✅ |
| stage_pack 持仓/仓位 | `attach_stage_position_pack` | ✅ |
| sync_report_with_data | `report_pipeline.sync_report_with_data`（builder re-export） | ✅ |
| 风险旗 / live_bar | `detect_risk_flags` / `build_live_bar_anchor` | ✅ |
| fusion 退居仪表（元数据） | `tag_fusion_as_instrument` → `product_role=instrument` | ✅ |
| decision 统一出口 | `report["decision"]` = `decision_view` 别名 | ✅ |
| 策略可读共振 | 阶段 2 context（已 main） | ✅ |

`report_builder` 主路径仍负责：snapshot 拉取、plugins、fusion 计算、structure/chip 拼装（计算热路径，抽函数收益低于耦合成本，保留在总管前半段）。

## 刻意不做（非工程债 / 产品债）

- 删除 fusion 计算路径（回测/兼容仍需要）  
- 默认策略包强制共振齐（会改匹配结果，需产品拍板）  
- T0/池/仓位接线（产品延伸，见法源 §5.1）  

## 验收

```bash
bash scripts/run-gate-tests.sh   # 354 passed
```
