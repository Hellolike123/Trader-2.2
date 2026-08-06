# 中线价位引擎 Review

| 项 | 内容 |
|----|------|
| 日期 | 2026-07-10 |
| 审查角色 | Reviewer（只读，未改业务代码；本文件为验收产出） |
| 规格真理 | `docs/midline-price-engine-plan.md`（含 §4 / §9 全 A 冻结） |
| 审查范围 | `midline_structure.py` / `mid_key_prices.py` / `run_analysis.py` 组装 / 相关单测 |
| 总判 | **APPROVE** |

---

| 规格 ID | 要求摘要 | 结果 | 证据 |
|---------|----------|------|------|
| E1 | 成功路径 `notes`/`engine` 含 weekly，不含 `daily_key_levels_proxy` | **PASS** | `build_midline_levels._pack` 固定 `engine=weekly_v1` 且 `notes` 前缀 `source={weekly_structure\|weekly_swing_only\|weekly_missing\|weekly_too_short}`（`midline_structure.py` L308–330）。成功分支 `source` 仅 `weekly_structure` / `weekly_swing_only`（L516–532）。全库主路径无 `daily_key_levels_proxy` 字符串产出；degraded 用 `degraded_daily_key_levels`。单测：`test_midline_structure.py::test_life_priority_up_seg_low`、`test_mid_key_prices.py::test_basic_structure_source`。 |
| E2 | 日线 key_levels 与周线结果刻意相反时，中线价 = 周线 | **PASS** | `test_report_mid_short_sources.py`：`_DAILY_KL.mid_support=40.0` vs 周 life `seg_low=48.0`；`TestMidShortPriceIsolation.test_mid_life_from_weekly_not_daily_mid_support` 断言 `life_line≈48`、≠40，渲染中线块无「生命线 40」。实现上 `build_midline_levels` / `build_mid_key_prices` 成功路径不读 `key_levels`（`mid_key_prices.py` L54–61）。 |
| E3 | `life_line` 的 components ∈ 闭枚举，且能从 fixture 反算到同一 float（2 位） | **PASS** | 闭枚举实现：`_STRUCTURE_COMPONENTS` + 实际写入的 `seg_low` / `last_down_stroke_end` / `zone_zh_bottom` / `weekly_swing_n20` 均属 §9.7。单测反算：`test_life_priority_up_seg_low` → 48.0/`seg_low`；`test_life_priority_down_stroke_when_no_up_seg` → 47.2/`last_down_stroke_end`；`test_life_zone_zh_bottom_not_center` → 44.44/`zone_zh_bottom`（诱饵 center 47.22 未命中）。`_round2` 统一两位。 |
| E4 | 周线不足 → insufficient，不填日线 mid_support | **PASS** | `len(bars)<MIN_WEEKLY(26)` → `quality=insufficient`、四价 None、`notes` 含 `weekly_too_short`（L347–358）；空 bars → `weekly_missing`（L334–345）。**不**走 `build_degraded_daily_key_levels`，除非 `MIDLINE_PRICE_DAILY_FALLBACK=true` 且由薄封装切入。单测：`test_insufficient_too_short` / `test_weekly_missing` / `test_omit_life_when_insufficient`。 |
| E5 | 短线 key_prices 数值/逻辑不被本改动破坏 | **PASS** | `key_prices.py` 不 import mid 模块；`midline_structure` / `mid_key_prices` 不写日线结构。交叉测 `test_short_key_prices_unchanged_by_weekly_mid`：`stop_sell=44`、`space_mid=40`（仍读日线 mid_support）。`run_analysis` 先 `build_key_prices` 再独立 `build_mid_key_prices`（约 L1522–1532）。回归依赖 `tests/test_key_prices.py`（见下方 pytest 说明）。 |
| E6 | 展示句式与 🧭 块不变（无 🌟、有解释半句） | **PASS** | `_pack` 句式：`生命线 X（破则中线转弱）` / `回踩区 A-B（到了才谈低吸）` / `压力 X（靠近只减不加）` / `目标 X（波段上看）` / 同价 `压力/目标`（L282–306）。`report_core` 中线块标「关键价（中线）」，无 🌟（L175–191）；🌟 仅在短线块。单测：`test_display_lines_format`、`TestRenderDualTrack.test_layout_b3c_b2a`。 |
| E7 | 出手仍不由中线 target 单独放行 | **PASS** | `mistery_gate.py` 无 `mid_key_prices` / `life_line` / mid `target` 引用；门控只读阶段×动能/RR/硬否决。`run_analysis` 中 `compute_mistery_gate` 入参不含 mid 四价。`test_conclusion_midline.py::test_execution_not_from_pretty_target_alone`：gate 观望时出手仍不买，与中线目标无关。符合 §0.3 / §9.10-4。 |
| E8 | 南网/华工：不锁旧样例价；锁 engine/source/components 与逻辑 | **PASS** | 单测华工 mock 锁 `engine=weekly_v1`、`source=weekly_structure`、`life=48`/`seg_low`，并显式拒绝日代理 `46.88`/`40.0`（`test_mid_key_prices.py::test_default_ignores_daily_key_levels`、`test_report_mid_short_sources`）。**未**锁旧 B4A 日代理价。本审查未跑真票盘后输出；逻辑锁已在 fixture 覆盖，真票目视属 M5 可选。 |
| E9 | 默认 fallback 关时传入 daily key_levels **必须被忽略**；成功 source 不含 daily | **PASS** | `_daily_fallback_enabled()` 默认读 env，缺省 `"false"`（L52–58）。`build_midline_levels` 签名收 `key_levels/stop/...` 但主路径从未读取（L239–244 后无引用）。`build_mid_key_prices` 仅当 flag 开且周线不足时 degraded（L39–52）。单测：`test_ignore_daily_key_levels_by_default`、`test_default_ignores_daily_key_levels`；flag 开 + 无周线 → `source=degraded_daily_key_levels`（`test_degraded_daily_when_flag_and_no_weekly`）。成功 `source` 无 daily 字样。 |

---

## 红线检查

对照规格 §9.10 / 任务红线：

| # | 红线 | 结果 | 证据 |
|---|------|------|------|
| 1 | 成功路径禁止日线 key_levels / `find_key_levels(daily)` / stop / stage_based 填四价 | **PASS** | 主路径仅 `weekly_bars` + `unwrap_chan` 笔段/zone + `find_swing_levels(weekly)`。`find_key_levels` 未 import。`stop`/`stage_based` 仅出现在 `build_degraded_daily_key_levels`。`run_analysis` 组装**不传** `key_levels`/`stop`（L1526–1531）。 |
| 2 | strokes 不是 bi；zone life 用 zh_bottom | **PASS** | 仅 `chan.get("strokes")`（L383）；全文无 `bi` 字段读取。`_last_valid_zone_zh_bottom` 只取 `valid` + `zh_bottom`（L218–228）；单测诱饵 `last_valid_zone_first_price`/center 未污染 life。 |
| 3 | 仅 `timeframe=="weekly"` 才用笔段 | **PASS** | `use_structure = (tf == "weekly")`（L376–377）；`daily_fallback` fixture → `weekly_swing_only` 且 life≠笔段 11.0（`test_non_weekly_timeframe_swing_only`）。与 `chanlun_strategy_midline` 在周不足时标 `daily_fallback` 的设计对齐：价引擎丢弃该笔段。 |
| 4 | 默认 fallback 关 | **PASS** | `MIDLINE_PRICE_DAILY_FALLBACK` 默认 false；见 E9。 |
| 5 | 短线零耦合 | **PASS** | 双轨数据流：日线 → `key_prices`；周线 → mid 引擎。模块无互相主路径调用。出手/门控不吃 mid target（E7）。 |

附加规格点（非独立 E 号，一并勾选）：

- §9.2 常量：`MIN_WEEKLY=26`、`SWING_N_*=20/12/40`、`MA_WEEKLY=20`、`TOUCH_TOL_PCT=0.015`、`UNBROKEN_PCT=0.03`、`SWING_HALF_WINDOW=3` — 与代码 L16–24 / 单测 `TestConstants` 一致。
- §9.3 生命线优先级命中即停、**无** `≤current*1.02` 过滤；`already_below_life` 在 notes — 已实现（L398–430、L311–312）。
- §9.4 回踩夹 life：`max(pb_lo, life_line)` — L451–455；单测 `test_pullback_clamped_to_life`。
- §9.5 P0 无 fib：压力/目标只从 up stroke/seg 或周摆动 — L472–510；无 fib 引用。
- §9.6 quality：`full` 需 life/resist 命中笔段/zone 组件；否则 partial / insufficient — L515–532。
- 威科夫 P0 不改写价：`del wyckoff_midline`（L247）。

---

## pytest 执行说明

请求命令：

```bash
PYTHONPATH=02-共享模块-shared python3 -m pytest \
  02-共享模块-shared/tests/test_midline_structure.py \
  02-共享模块-shared/tests/test_mid_key_prices.py \
  02-共享模块-shared/tests/test_report_mid_short_sources.py \
  02-共享模块-shared/tests/test_key_prices.py -q
```

静态审查后由主会话补跑 pytest：

```text
36 passed in 0.06s
（test_midline_structure / test_mid_key_prices / test_report_mid_short_sources / test_key_prices）
```

与静态 **APPROVE** 对齐，可合入。

---

## 阻断项

无。

未发现「成功路径仍读 daily key_levels 填四价」类规格直接 FAIL。

---

## 非阻断建议

1. **回踩摆动 component 命名**  
   近 12 周摆动低写入 `components.pullback_low="weekly_swing_n20"`（代码注释称归入 n20 族，§9.7 无独立 `weekly_swing_n12`）。功能正确，调试可观测性略糊。可选：扩展闭枚举为 `weekly_swing_n12` 或文档注明别名。

2. **degraded 路径 `engine` 仍为 `weekly_v1`**  
   `build_degraded_daily_key_levels` notes/engine 带 `engine=weekly_v1` 但 `source=degraded_daily_key_levels`。规格未强制 degraded 改 engine 名；为免运维误读，可改为 `engine=degraded_daily_v0`（纯展示，非红线）。

3. **报告亮点/风险的 resist 回退链**  
   `report_core.py` L291–296 在 mid 无 resist 时回退 `key_prices.swing_sell` / `key_levels.mid_resist`。**不**写入 `mid_key_prices` 四价，不构成 E1/红线失败；但风险文案可能短暂出现日线压力数字。可选：mid 不足时写「中线压力数据不足」而不回退日线。

4. **E8 真票目视**  
   建议盘后对南网/华工跑一次 `final_report`，人工确认 `mid_key_prices.engine/source/components` 与「价源≠日线 mid_support」；数字允许与旧样例不同。

5. **`**_extra` 静默日链**  
   当前 `**_extra` 不启用日链，符合 §9.9。保持即可；勿在额外 kwargs 中加隐式 daily 分支。

---

## 总判：APPROVE

Implementer 交付满足 `docs/midline-price-engine-plan.md` §4 E1–E9 与 §9.8/9.10 红线：

- 中线四价主路径为独立周线引擎（`weekly_v1` + `weekly_structure` / `weekly_swing_only`）；  
- 默认忽略日线 `key_levels`/`stop`；日链仅开关 degraded 且显式 `source=degraded_daily_key_levels`；  
- `strokes`/`zh_bottom`/`timeframe==weekly` 字段对齐正确；  
- 短线 `key_prices` 与出手门控零耦合。

**无必须修改的阻断条目。** 合并条件：本地 pytest 四文件全绿（见上）。非阻断建议可后续 P1 消化。
