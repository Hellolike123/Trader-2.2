# WyckoffStateView 契约（A 档：定 View）

> **状态**：已落地类型 + 薄适配，**未**改检测逻辑 / fusion / 纪律。  
> **代码**：`trader_shared/wyckoff_view.py`  
> **schema_version**：`wyckoff_state_v1`

## 目的

统一「威科夫对外长什么样」，供：

- 中线报告人话（`summary_oneline`）
- 选股池/复盘打分（后续可迁）
- Agent / AI（只读状态，不自己扫 K）

**不做**：直接下单；替换 fusion 三评委；推倒 `wyckoff_events`。

## 数据流（现状）

```
wyckoff_analysis() 大 dict
        │
        ▼
to_wyckoff_state_view()   ← 纯映射 + format_wyckoff_oneline
        │
        ▼
WyckoffStateView
```

检测仍在 `wyckoff_events` / `wyckoff_phase`；View 只是出口说明书。

## 字段

| 字段 | 含义 |
|------|------|
| `schema_version` | 固定 `wyckoff_state_v1` |
| `symbol` / `timeframe` | 标的；`daily` \| `weekly` \| `insufficient` |
| `phase` / `phase_label` | 阶段机结果 |
| `confidence` | 0~1 启发式（非校准概率） |
| `premature.spring/upthrust` | 孤立信号 |
| `tr.*` | 交易区间上下沿/质量等 |
| `active_events` | 当前亮灯事件 id 列表 |
| `event_detail` | id → reason/price |
| `cause_effect.*` | P&F 因果目标（水平计数主路径；含 `pnf_method`/`pnf_columns`/`pnf_box_size`；见 `docs/plans/wyckoff-pnf-handoff.md`） |
| `bias` | `bull` \| `bear` \| `neutral`（弱暗示） |
| `invalidation_hint` | 结构失效提示文案 |
| `summary_oneline` | 与 `format_wyckoff_oneline` 同源 |
| `raw_available` | 是否有非空 analysis |

## 使用示例

```python
from trader_shared.wyckoff_core import wyckoff_analysis
from trader_shared.wyckoff_view import to_wyckoff_state_view

raw = wyckoff_analysis(bars, symbol="000988", timeframe="weekly", use_persisted_phase=False)
view = to_wyckoff_state_view(raw, symbol="000988", timeframe="weekly")
print(view["phase"], view["bias"], view["summary_oneline"])
```

## 后续（B 档，未做）

1. 特征 / 原子事件层从 `_detect_spring` 试点抽出  
2. 报告渲染改为优先读 View  
3. `calculate_wyckoff_score` 输入 View  

现状：**单票 🧭 威科夫行与 wyckoff skill 卡已读 View**（`format_midline_display` / `to_wyckoff_state_view`）；仅少数 legacy 路径仍消费旧 dict。新 Agent/渲染优先 View。

## 非目标

- 线性强制 PS→SC→AR→… 唯一剧情  
- 威科夫成为整站交易大脑  
- AI 进入 `build_report` 必经路径  
