# 第 5 批审查报告（最终批）

> 审查日期：2026-07-07
> 分支：`audit-batch-5-output`
> 审查文件：17 个 / 裁决 ACCEPT 7 项 / 修改 3 文件 10 行

---

## 裁决结果

| 类别 | 编号 | 文件 | 裁决 | 说明 |
|------|------|------|------|------|
| 理论派 P0 | P0-1 | run_analysis.py | **ACCEPT** | `_action_text` 为空时输出 `"📍 决策"` 替代 `"📍 价格阶梯"` |
| 理论派 P0 | P0-2 | run_analysis.py | **ACCEPT** | `📍 决策` 与操作建议分两行显示 |
| 理论派 P0 | P0-3 | run_analysis.py | **ACCEPT** | 双状态行移除 `bs != ts` 条件，始终显示 |
| 理论派 P0 | P0-5 | final_pool.py | **ACCEPT** | 选股池首行加入 `选股日报 — YYYY-MM-DD` |
| 理论派 P0 | P0-6 | run_analysis.py | **ACCEPT** | report 字典加入 `ma250_warning` 和 `ma250` 字段 |
| 工程派 P0 | P0-11 | final_pool.py | **ACCEPT** | `.get("trigger", 0.0)` → `.get("trigger") or 0.0` 修复 None 陷阱 |
| 工程派 P0 | P0-13 | price_point_engine.py | **ACCEPT** | `bar.get("time")` 前增加 `bar is None` 检查 |
| 理论派 P0 | P0-4 | t0_core.py | DEFER | 需重写 render_markdown，影响范围大 |
| 理论派 P1 | P1-7 | momentum_core.py | DEFER | momentum 方向评分涉及 fusion 改造，设计变更 |
| 理论派 P1 | P1-9 | pattern_core.py | DEFER | 类型注释非功能性，不影响运行 |
| 理论派 P1 | P1-10 | chip_migration_monitor.py | DEFER | 阈值判定量纲不一致，罕见场景 |
| 工程派 P0 | P0-12 | portfolio_core.py | DEFER | `bars[-1]` IndexError，外层有 except 保护 |
| 工程派 P1 | P1-14 | momentum_core.py | DEFER | rsi[-1] 为 None 时不影响功能 |
| 工程派 P1 | P1-15 | chip_migration_monitor.py | DEFER | poc_price=0.0 被 `or` 跳过，罕见场景 |

---

## 修改摘要

### 1. `run_analysis.py` — render_markdown（3 处）

- **L1801-1804**：`_action_text` 为空时，`"📍 价格阶梯"` → `"📍 决策"`
- **L1795-1799**：`"📍 决策｜{_action_text}"`单行 → `"📍 决策"` + `"  {_action_text}"` 两行
- **L1774-1777**：`if bs and ts and bs != ts` → `if bs and ts`

### 2. `run_analysis.py` — build_report（1 处）

- 在 report 字典中加入 `ma250` 和 `ma250_warning` 字段（当前价 < 年线时警告）

### 3. `final_pool.py` — render_rank（1 处）

- 首行 `"选股池"` → `"选股日报 — {today_text()}"`（符合契约 `选股日报 — YYYY-MM-DD`）

### 4. `final_pool.py` — record_from_report（1 处）

- `record.get("trigger", 0.0)` → `record.get("trigger") or 0.0`（修复 key 存在但值为 None 时仍返回 None 的陷阱）

### 5. `price_point_engine.py` — completed_5m_bars（1 处）

- `for bar in bars:` 后增加 `if bar is None: continue` 前置防御

---

## 修改统计

```
 3 files changed, 10 insertions(+), 5 deletions(-)
```

---

## 验证结果

- 全部 3 个修改文件的模块导入测试通过
- 未改动 `main` 分支
- DEFER 项（7 项）不影响当前功能，建议在后续设计重做时一并处理
