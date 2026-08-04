# 威科夫 epic — SC 失效链(F) + 周线新鲜度(D) + volume 单位(E) — Agent Handoff

> **status**: 待实现（上一 epic A/B/C/G 已合入 main；本 epic 为其文档化遗留）  
> **日期**: 2026-08-04  
> **外部法源**: WorkBuddy `wyckoff-sos-修复交接说明.md` Bug F/D/E（§4/§5/§6 + §9 验证清单）  
> **关联**: `wyckoff-sos-epic-bcg-handoff.md`（A/B/C/G，已完成）——该 handoff §review NEXT 明确「后续 epic：F（SC 失效文案）、D 周线、E volume 单位 — 勿混本 PR」  
> **产品/原典**: `docs/audit/wyckoff-original-concept-inventory.md`；`docs/designs/p1-split-core-seam-design.md`（数据入口归一原则）  
> **读者**: 实现 / 查 Agent（只读本文 + 代码锚点）

---

## 0. 30 秒摘要

1. **F（P1）SC 失效链断裂 + 误导文案**：`_detect_selling_climax` 用 `include_failed=True`（失效 SC 也亮灯），`_detect_ar` 用默认 `include_failed=False`（失效 SC 被跳过）→ AR 报「未检测到 SC，无法触发 AR」，与 SC 亮灯自相矛盾。修法：AR 锚缺失时探测「存在但失效」的 SC，输出失效态文案而非「未检测到 SC」。（ST 已 `include_failed=True`，b1f99e1 起，不动。）  
2. **D（P2）周线聚合滞后一天**：`fetch_weekly` 经 `get_day_scoped_bars` 按 fetch_date 自然日判新鲜，凌晨生成的周线缓存当天不再聚合盘中新 bar。修法：fetch_weekly 加周线专属新鲜度闸——缓存最后 bar 日期 < 日线最后 bar 日期 → 用 `_from_daily()` 重聚合覆盖写回。  
3. **E（P2）volume 单位差 100 倍**：sina/mootdx 周线 volume=手、腾讯日线=股，跨周期量比失真。修法：周线入口统一 ×100 归一到股（仅对 sina/mootdx 源），缓存带 unit 标记迁移旧缓存。  
4. **不改** fusion / 出手 / 池分道 / 渲染层主结构 / `get_day_scoped_bars` 通用函数。

---

## 1. 必须 / 禁止

### Bug F — SC 失效链（`wyckoff_events.py::_detect_ar`）

| # | 合同 |
|---|------|
| F-M1 | `_detect_ar` 在 `_find_sc_anchor()`（默认 include_failed=False）返回 None 后，必须用 `_find_sc_anchor(include_failed=True)` 再探测一次「存在但失效」的 SC |
| F-M2 | 存在失效 SC（anchor 带 `phase_a_failed` / `fail_reason`）→ `ar_signal=False`，`ar_reason` 显式写失效态文案（含「失效」字样，如「SC 已失效（Phase A 失败），链终止，须重新寻底」），**禁止**输出「未检测到 SC」 |
| F-M3 | 探测后仍无任何 SC → 维持原「未检测到 SC，无法触发 AR」语义 |
| F-M4 | SC 有效时 `_detect_ar` 行为完全不变（回归：ar_signal / ar_high / ar_bar_idx / sc_low / sc_bar_idx） |
| F-M5 | 失效态返回须带 `sc_low` / `sc_bar_idx`（透出 SC 位置供展示），字段结构与 `_ar_empty` 一致 |
| F-M6 | 有 pytest：失效 SC → 文案含「失效」；有效 SC → 原行为；无 SC → 原文案 |

| # | 禁止 |
|---|------|
| F-P1 | 不得让 AR 用失效 SC 触发 `ar_signal=True`（禁止软确认） |
| F-P2 | 不改 SC / AR 检测阈值、不改 `_find_sc_anchor` 逻辑（只新增 AR 侧探测调用） |
| F-P3 | 不改 fusion / 出手 / 池分道 / 渲染层主结构（渲染层已有 failed 态：`_display_chain_plain` / `PhaseAFail`） |

### Bug D — 周线新鲜度（`light_data.py::fetch_weekly`）

| # | 合同 |
|---|------|
| D-M1 | `fetch_weekly` 在 `get_day_scoped_bars` 返回后，检测「滞后」：缓存周线最后 bar 日期 < 日线最后 bar 日期 → 视为过期 |
| D-M1a | 日线须用 `fetch_qfq_daily(..., fresh=True)` 取（跳过同日文件/URL 缓存短路，强制触网拿盘中最新；网络全源失败回退非 fresh 缓存兜底）——否则凌晨预热同日缓存场景（WorkBuddy §4 原始报告）闸会拿旧日线误判「不滞后」 |
| D-M2 | 过期时用 `_from_daily(daily)` 重聚合（复用 fresh 日线，避免二次拉取）覆盖写回周线缓存（fetch_date=今天）并返回 |
| D-M3 | 无新数据（周末 / 日线未更新，最后 bar 日期相等）→ 复用缓存，不无谓重聚合 |
| D-M4 | 有 pytest：构造「周线缓存最后 bar=周一、日线最后 bar=周二」→ 重聚后周线最后 bar=周二；「日线最后 bar=周五」→ 复用；「凌晨预热：非 fresh 日线=周一、fresh 日线=周二」→ 仍重聚（Delta 1 回归） |

| # | 禁止 |
|---|------|
| D-P1 | 不改 `get_day_scoped_bars` / `cache_utils` 通用函数（日线同走，勿波及） |
| D-P2 | 不引入交易日历依赖（用日线最后 bar 日期对比即可，A 股周末/停牌自然归零） |
| D-P3 | 不改变 sina/mootdx 优先的常规路径（只在滞后时覆盖，行为向后兼容） |

### Bug E — volume 单位（`light_data.py` 周线入口）

| # | 合同 |
|---|------|
| E-M1 | sina / mootdx 周线 volume 在 light_data 数据入口统一 ×100 归一到「股」（与腾讯日线同单位）。**实现位置：`fetch_weekly._net()` 出口**（sina/mootdx 分支 return 前归一）——`_fetch_mins_fallback`/`_fetch_mins_mootdx` 是 5m/15m/30m/60m/weekly/monthly 共用函数，内部归一会误伤分钟线，故不在此二函数内改 |
| E-M2 | 归一只对 sina/mootdx 源；`_from_daily()` 聚合周线（腾讯日线=股）**不得**重复乘 |
| E-M3 | 缓存迁移：写入周线缓存时每根 bar 带 `vol_unit="share"` 标记；读取时发现无标记（旧手单位缓存）→ 视为过期强制回源重写；回源全源失败时**保留旧缓存兜底**（不得弃用旧数据返回空） |
| E-M4 | 归一后周线量比 / 基线均量与日线可比（南网 08-03 周线 vol ≈ 8449817，而非 84498） |
| E-M5 | 有 pytest：sina 构造行 volume ×100；聚合路径不乘；旧缓存（无标记）触发回源 |

| # | 禁止 |
|---|------|
| E-P1 | 不在 wyckoff_events / wyckoff_core 等检测器里做 ×100 补丁 |
| E-P2 | 不改日线 volume（腾讯=股 已是基准单位） |
| E-P3 | mootdx **日线** fallback 单位未验证 → out of scope（handoff 注明，勿顺手改） |

---

## 2. 字段合同

```text
# F — _detect_ar 失败态（ar_signal=False 时 ar_reason 三态互斥）
ar_reason = "数据不足"                                  # 既有
          | "未检测到 SC，无法触发 AR"                  # 真无 SC（既有）
          | "<失效态文案，须含『失效』字样>"            # 新增：SC 存在但 Phase A 失败
# 失效态仍透出：
sc_low: float | None       # 失效 SC 谷底（SSOT：棒最低价）
sc_bar_idx: int | None     # 失效 SC 位置
```

```text
# D — 周线新鲜度判定（fetch_weekly 内部，无新字段外泄）
过期 ⟺ 缓存最后 bar 日期 < 日线最后 bar 日期
覆盖写回格式与既有缓存一致：{"fetch_date": 今天, "rows": [...]}
```

```text
# E — 周线 bar 标记（light_data 写缓存前）
vol_unit: "share"    # 每根周线 bar 写入；sina/mootdx 归一后与聚合路径一致
# 读取：首根 bar 无 vol_unit → 旧格式缓存 → 强制回源
```

---

## 3. 可改文件白名单

| 文件 | 动作 |
|------|------|
| `02-共享模块-shared/trader_shared/wyckoff_events.py` | `_detect_ar` 失败态分支（F） |
| `02-共享模块-shared/trader_shared/light_data.py` | `fetch_weekly` 新鲜度闸（D，含 `fetch_qfq_daily`/`_fetch_qfq_daily_raw` 新增 `fresh` 可选参数——默认 False 对既有调用零影响）+ 周线 volume 归一与 `vol_unit` 标记（E） |
| `02-共享模块-shared/tests/test_wyckoff_core.py` | F 测例 |
| `02-共享模块-shared/tests/test_light_data_weekly.py` | D/E 测例（新建；离线 mock fetcher） |
| 本文 + `workflows/` 进度 | 文档 |

勿改：`get_day_scoped_bars` / `cache_utils` 通用函数、`wyckoff_core.py`、`wyckoff_render.py`、fusion / 出手 / 池分道、`indicator_math.py`。

---

## 4. 验收表

| ID | 场景 | 期望 |
|----|------|------|
| F1 | SC 失效 + AR 锚缺失（茅台型） | `ar_reason` 含「失效」，不含「未检测到 SC」；`ar_signal=False`；`sc_low`/`sc_bar_idx` 透出 |
| F2 | SC 有效 | AR 原行为（回归） |
| F3 | 无 SC | 「未检测到 SC，无法触发 AR」（回归） |
| D1 | 周线缓存最后 bar=周一、日线=周二 | 重聚合，周线最后 bar=周二 |
| D1a | 凌晨预热：非 fresh 日线=周一、fresh 日线=周二 | 仍重聚合（fresh 强制触网生效） |
| D2 | 周末：日线=周五、缓存=周五 | 复用缓存，不重聚合 |
| E1 | sina 周线（南网 08-03） | volume ≈ 8449817（×100 后） |
| E1b | mootdx 周线 | volume ×100 + `vol_unit` 标记 |
| E2 | 旧缓存（无 vol_unit） | 当天强制回源重写 |
| E3 | 日线量比 | 不变（回归） |
| E4 | 门禁 | `scripts/run-gate-tests.sh` 全绿 |

实票验证（有行情时人工）：`final_wyckoff.py --target 贵州茅台`（F，ar_reason 不再自相矛盾）；`--target 南网科技`（D/E，周线含最新交易日、vol 与日线同单位）。

---

## 5. 回归调用点（只验证、不改逻辑）

- F：`_detect_ar` → `wyckoff_core` AR 事件消费 + `wyckoff_render` 灯（失败态文案已有）
- D/E：`fetch_weekly` → `get_day_scoped_bars(CACHE_WEEKLY)` → 周线事件检测器（量比/基线均量）
- 全量门禁：`scripts/run-gate-tests.sh`（离线子集）

---

## 6. 回滚

`git revert` 实现 commit。E 的缓存标记无破坏性：新代码读旧缓存强制回源，回滚后旧缓存自然按 fetch_date 复用。
