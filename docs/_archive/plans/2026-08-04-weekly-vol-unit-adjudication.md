# 周线 volume 单位裁决 handoff（#5 遗留）— 回退 FDE 轮 ×100，全源统一为「手」

- 日期: 2026-08-04
- 状态: 裁决（用户「继续」推进）→ 双 Agent 实施
- 法源: `docs/plans/wyckoff-sos-epic-fde-handoff.md`（E-M1~E-M5，本轮回退）、
  `docs/plans/wyckoff-epic-vol-phase-verif-handoff.md` §1 方向 A（实测修正）、
  `workflows/phase-scan-audit/README.md` §2（遗留裁决项）
- 读者: 写 Agent（实施 + commit）/ 查 Agent（独立对照，默认不改码）

## 0. 裁决结论

**回退 FDE 轮周线 ×100**：周线 sina/mootdx 出口不再 ×100，vol_unit 统一打 **"lot"（手）**，
全源（日线 + 周线）volume 单位统一为**手**。这是对 FDE 轮「腾讯日线=股」错误前提的最终修正。

## 1. 证据链（已实测核实）

1. **全源日线=手**（amount 交叉验证 amount≈vol×100×close + 腾讯实时 qfqday 与 mootdx
   缓存同量级：601398/600519/000001）→ 日线基准是「手」，不是「股」。
2. **周线原始源=手**（FDE 轮自己验证 sina 周线=手）。
3. **当前周线内部不一致**（正是「两条路径各说各话」）：
   - sina/mootdx 出口（E-M1）: ×100 → **股**
   - 聚合路径 `_from_daily`（E-M2）: 不乘 → **手**
   → 同一周线，不同数据源相差 100 倍；且与日线（手）均不一致。
4. **消费方全部是比值/相对量**（核查 `tr_baseline_volume`/`baseline_avg_vol` 全部用于
   量比 cur/baseline 或相对阈值，无绝对量阈值）→ 回退 ×100 **不影响任何检测器判定**。
5. A 股行情软件惯例：成交量单位=手。

## 2. 改动清单

### light_data.py `fetch_weekly`（修改）
- docstring E 段：更新为「2026-08-04 裁决回退：全源=手，不 ×100」。
- `_net()` sina 分支（E-M1）：**去掉 ×100**，改 `_stamp_vol_unit(fallback_bars, _DAILY_VOL_UNIT)`（"lot"）。
- `_net()` mootdx 分支（E-M1）：同上。
- `_from_daily()`（E-M2）：`_stamp_vol_unit_share(weekly)` → `_stamp_vol_unit(weekly, _DAILY_VOL_UNIT)`。
- `_stamp_vol_unit_share` 局部函数：删除（无引用）。
- E-M3 迁移：`if bars and not bars[0].get("vol_unit") == "share":` →
  `if bars and bars[0].get("vol_unit") != _DAILY_VOL_UNIT:`（旧 "share"=股 / 无标记=手 均
  强制回源重写为 lot=手，保证旧缓存不残留 ×100 值）。

### tests/test_light_data_weekly.py（修改）
- `_seed_weekly_cache(tagged=True)`：打 "share" → `"lot"`。
- E 组（test_e1/test_e1b）：`84498.17 × 100 == 8449817` 断言 → **不乘**（`== 84498.17`）+ `vol_unit == "lot"`。
- E-M2（test_e2）：`vol_unit == "share"` → `"lot"`（聚合路径值=日线求和，不乘，断言不变）。
- E-M3（test_e3）：tagged 标记 "share" → "lot"。
- D 组（test_d1/test_d3）：`bars[-1]["vol_unit"] == "share"` → `"lot"`。

### 文档（修改）
- `docs/plans/wyckoff-sos-epic-fde-handoff.md`：E 节顶部加「⚠️ 2026-08-04 裁决回退」标注
  （不删原文，标注被取代）。
- `workflows/phase-scan-audit/README.md` §2：遗留项状态改为「已裁决：回退 ×100」。
- `.workbuddy/memory/MEMORY.md` 数据源节：遗留标记更新为已回退。

## 3. 禁止

- 不改检测器逻辑（周线检测器全比值，回退零影响，勿顺手改）。
- 不改日线路径（已=手）、不动 `_fetch_mins_*` 共用函数、不动周线 lookback/窗口参数。
- 不删 FDE handoff 原文（标注取代即可）。

## 4. 验收

- `tests/test_light_data_weekly.py` 全绿（E/D 组断言已按「不乘 + lot」更新）。
- `test_wyckoff_*.py` 全量绿；门禁 `run-gate-tests.sh` 全绿；golden check 无漂移。
- 实票核验：`fetch_weekly` 拉 600519 周线，sina 出口 vol 不再 ×100（08-03 周 vol≈36,147 手量级）；
  写缓存带 `vol_unit="lot"`；旧 "share"/无标记缓存触发回源。
- commit message 附本 handoff 路径 + 对照项编号；**默认不 push**（裁决轮完成后由父 Agent 汇报）。

## 5. 双 Agent 分工

- 写 Agent：按 §2 实施 + 跑全部验收 + commit。
- 查 Agent：独立对照 §2 逐项 ✅/❌（重点：sina/mootdx 出口确不再乘、E-M3 语义、
  测试断言与缓存实际单位一致、未越界动检测器）；列必须再改。
- 父 Agent：查完修完 → 汇总汇报（是否 push 由父 Agent 征询）。
