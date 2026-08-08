# Report 标识字段 + Wyckoff 阶段状态机修复 — Agent Handoff

> **status**: active（2026-08-08）
> **范围**: report 顶层标识字段、渲染层空读兜底、死代码清理、安全 int、Wyckoff 跨日阶段状态机
> **禁止**: 改 fusion / decision_view / 出手 / 池分道；不改中线周线威科夫持久化（保持 False）

---

## 0. 问题

审计确认（附证据）：

1. `report["ts_code"] / report["code"]` 从未写入，渲染层三处读取恒为空串（assemble_stage.py:322 只写 symbol；short_midline.py:895/1391/1407 空读）。
2. `_mid_resist` 死代码且混用日线 key_prices / key_levels（short_midline.py:1827-1832 唯一引用）。
3. `_chan_dir2 = int(...)` 无兜底（short_midline.py:1523），direction 为字符串时渲染可崩。
4. `_PHASE_ORDER` 缺 `distribution_b`，且 `_transition_phase` 同方向分支在负值域判反（实测 a→c 卡 a、c→d 卡 c、c→markdown 卡 c、b→accumulation_a 被拦、c→a 回退反被放行）；无任何直接单测。

---

## 1. 必须行为

### 1.1 Report 标识字段

- `assemble_base_report` 的 report dict 写入 `ts_code`（= `sec.ts_code`）与 `code`（= `sec.code` 或 `ts_code` 去后缀裸码）；`symbol` 语义不变。
- 渲染层三处 `str(r.get("ts_code") or r.get("code") or "")` 追加 `or r.get("symbol") or ""` 兜底，旧缓存/手工 report 不再空 symbol。

### 1.2 死代码与安全 int

- 删除 `_mid_resist` 计算块（确认无其它引用）。
- `_chan_dir2` 改走 `_safe_int`，非数字返回 0，不抛异常。

### 1.3 Wyckoff 阶段状态机

- `_PHASE_ORDER` 增加 `distribution_b`，派发侧重排：`markdown=-5 / distribution_d=-4 / distribution_c=-3 / distribution_b=-2 / distribution_a=-1 / none=0`；积累侧 +1..5 不变。
- `_transition_phase` 同方向分支按深度 `|order|` 比较：同正 `new > old` 才升级，同负 `new < old` 才升级；回退保持旧状态。
- `distribution_b → distribution_c/d` 可升级；`distribution_b → accumulation_a` 可反向翻转。

---

## 2. 验收

| # | 测 |
|---|-----|
| A | `assemble_base_report` 产物含非空 `ts_code` / `code` / `symbol` |
| B | 旧 report（只有 symbol）渲染三处不空读、不崩 |
| C | `_mid_resist` 已删除且无引用 |
| D | `direction` 为 `"1" / "-1" / "看多" / None` 渲染不崩 |
| E | `_transition_phase`：a→c、c→d、c→markdown、b→c 升级；c→a 回退被拦；b→accumulation_a 翻转 |

```bash
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_wyckoff_phase_transition.py \
  02-共享模块-shared/tests/test_report_identity_fields.py \
  02-共享模块-shared/tests/test_report_mid_short_sources.py -q --tb=short
```

---

## 3. 可改 / 勿改

**可改**：`assemble_stage.py`、`report_renderer/short_midline.py`、`wyckoff_phase.py`、相关测试、本 handoff + `known-gaps.md`。

**勿改**：fusion / decision_view / 出手 / 池分道；中线周线 `use_persisted_phase` 保持 False；不改阶段机主枚举语义（只补缺失项与负值域方向）。
