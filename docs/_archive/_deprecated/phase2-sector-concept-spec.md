# Spec: 板块数据接入评分 + 概念板块接入 (Phase 2)

## 背景

Phase 1 已通过 akshare 采集了个股所属**行业板块**数据（`extend_sector`），并在报告中展示。但采集来的板块数据**仅展示、未接入任何评分逻辑**。本规格要求：

1. 将行业板块数据接入融合层评分（个股 vs 板块相对强弱 + 板块排名）
2. 新增**概念板块**数据采集，并同样接入评分

## 设计约束

- 不删除任何现有返回字段（向后兼容）
- 新字段必须写入 `levels` 中间层，不能只嵌在 reason 字符串里
- 所有 akshare 调用保持懒加载 + 优雅降级
- 测试必须覆盖边界条件（空/最少/正常输入）

---

## 规格要求清单

### Part A: 行业板块接入评分

| ID | 要求 | 优先级 |
|----|------|--------|
| A1 | `extend_data.get_sector_data()` 填充 `stock_vs_sector` 字段（个股涨幅 - 板块涨幅），而非留空在 run_analysis 里算 | P0 |
| A2 | `merge_decisions()` 新增参数 `extend_sector: dict | None = None`，消费板块数据 | P0 |
| A3 | 个股涨 + 板块跌 → 板块相对走强 → fusion 置信度 +10%（封顶 1.0） | P0 |
| A4 | 个股跌 + 板块涨 → 板块相对走弱 → 若加权分>0 则减分 -0.1 | P0 |
| A5 | 板块排名前 10% (`sector_rank / sector_total <= 0.1`) → 主线板块 → confidence +5% | P1 |
| A6 | `assess_stage()` 利用板块数据做交叉验证：个股走强且板块走强 → 升级确认；个股走弱且板块走强 → 减分 | P1 |
| A7 | `build_report()` 调用 `merge_decisions()` 时传入 `extend_sector=snapshot.extend_sector` | P0 |
| A8 | 北向资金 `extend_northbound` 同步传入 `merge_decisions()`（Phase 1 已采集但未传） | P0 |

### Part B: 概念板块接入

| ID | 要求 | 优先级 |
|----|------|--------|
| B1 | `extend_data.get_concept_data(code)` 新增函数，调用 akshare `stock_board_concept_spot_em()` + `stock_board_concept_cons_em()` | P0 |
| B2 | `MarketSnapshot` 新增 `extend_concept: dict | None = None` 字段 | P0 |
| B3 | `_enrich_snapshot()` 新增第 8 路并行采集 `get_concept_data` | P0 |
| B4 | 概念数据返回结构：`{concept_list: [str], concept_change_pct: [float], concept_rank: {...}, status: str}` | P0 |
| B5 | `build_report()` 报告 dict 携带 `extend_concept` | P0 |
| B6 | `render_markdown()` 展示概念板块（名称 + 涨幅），数据不可用时隐藏 | P0 |
| B7 | `merge_decisions()` 新增参数 `extend_concept: dict | None = None`，消费概念板块数据（个股命中热点概念 → confidence +5%） | P1 |
| B8 | `build_report()` 调用 `merge_decisions()` 时传入 `extend_concept=snapshot.extend_concept` | P1 |

### Part C: 测试

| ID | 要求 | 优先级 |
|----|------|--------|
| C1 | `test_extend_data.py` 新增 `TestGetConceptData`（正常 / 不可用 / 空数据 / API异常） | P0 |
| C2 | `test_fusion_core.py` 新增板块相对强弱 + 概念命中测试用例 | P1 |
| C3 | `test_data_provider.py` 验证 `MarketSnapshot` 新字段 + `_enrich_snapshot` 8 路并行 | P1 |

---

## 实现注意事项

- `get_sector_data()` 的 `stock_vs_sector` 原留空、在 run_analysis 里用 `change_pct` 计算。改为在 extend_data 内填充需要个股涨幅——但 extend_data 拿不到个股涨幅。→ **妥协方案**：`get_sector_data` 仍返回板块数据，个股涨幅由 run_analysis / build_report 在调用处补充到 `stock_vs_sector` 字段；A3-A5 的 fusion 逻辑在 `merge_decisions` 内用传入的 `current_change_pct` 与板块涨幅计算相对强弱。
- 概念板块可能命中多个，需支持列表。
- 所有新数据在 `status != "正常"` 时跳过评分逻辑。

## 验收标准

- [ ] 个股跑赢板块时，fusion confidence 提升
- [ ] 个股跑输板块时，fusion 对正向 action 减分
- [ ] 概念板块命中热点时，confidence 提升
- [ ] 板块/概念数据缺失时，评分逻辑退化为原行为（不影响现有测试）
- [ ] 全量 pytest 通过
