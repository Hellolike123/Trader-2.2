# 威科夫原典缺口与打分互斥修复（2026-07-16）

## 问题与处理

| 问题 | 处理 |
|------|------|
| SC↔SOW / Spring↔UT / LPS↔LPSY 对冲成假中性 50 分 | `_resolve_score_conflicts` 主叙事互斥 |
| LPSY 检测亮灯、打分才门控 | analysis 层无派发背景则灭灯 |
| 缺 PS / PSY / BU / UTAD | `wyckoff_events` 新增检测器 + 打分/展示 |
| 缺 Markup / Markdown 标签 | `wyckoff_phase` + `_PHASE_ORDER` |
| 缺因果目标 | TR 高度 1:1 投射（`cause_effect_*`，非完整 P&F） |
| AR 锚点窗过短 | BC/SC 扫描 5→15 根 |
| 分母 | `WYCKOFF_SCORE_MAX_ABS` 130→140 |

## 仍未做（有意）

| 项 | 原因 |
|----|------|
| 完整 P&F 点数图 | 工程量大；现用 TR 1:1 近似 |
| 个股 vs 大盘 RS | 需稳定大盘序列注入，未接数据管线 |
| Jump Across the Creek 专名 | 与强 SOS 重叠，暂用 SOS+BU/Markup 表达 |

## 文件

- `wyckoff_events.py` / `wyckoff_core.py` / `wyckoff_phase.py` / `config.py`
- `tests/test_wyckoff_original_gaps.py`
- `tests/fixtures/wyckoff_split_baseline.json`（有意刷新）
- `docs/audit/wyckoff-original-concept-inventory.md`（状态更新）

## 自测

```bash
export PYTHONPATH=02-共享模块-shared
python -m pytest 02-共享模块-shared/tests/test_wyckoff_*.py -q
```
