# Batch 7 审计报告 — ATR/Supertrend/VWAP 展示增强（`90dd076`）

- **审查对象**：commit `90dd076`（feat: 报告新增 ATR/Supertrend/VWAP 展示增强）
- **Arbitrator 角色**：裁决 + 修改 + 测试 + 写报告
- **结论**：全部发现已裁决；6 项 ACCEPT 修复（2 项 P1+边界加固），0 项 REJECT，0 项 DOWNGRADE，0 项 DEFER。测试全绿。

---

## 一、P1-1 双重微调风险前置确认（关键）

在修复 P1-1 前，按裁决规则先确认 `build_report` 是否同时走 `analyze_all` 与显式 nudge：

- `run_analysis.py:603` `f_mom = pool.submit(momentum_strategy, ...)` —— 直接调 `momentum_strategy`，**不经** `MomentumPlugin.analyze`，故插件内部 nudge 不触发。
- `run_analysis.py:613-616` 显式 `momentum_result = apply_supertrend_nudge(momentum_result, _st_dir)` —— 这是 build_report 唯一的方案B 微调点。
- `build_report` 调融合用的是 `merge_decisions`（run_analysis.py:671），**不**调 `analyze_all`；`analyze_all` 仅被 `fusion_core.merge_decisions_via_plugins`（fusion_core.py:820，独立入口）调用。

**结论**：两条路径无交集。给 `analyze_all` 透传 `supertrend_direction` 不会造成 `build_report` 单票输出的双重微调。采用「让 analyze_all 透传 + 保持 build_report 显式 nudge」即可，统一语义、互不干扰。

---

## 二、裁决矩阵

| 来源 | 编号 | 严重度 | 裁决 | 说明 | 修改文件 / 行 |
|------|------|--------|------|------|---------------|
| 工程派 | P1-1 | P1 | **ACCEPT** | registry 路径方案B 未透传 `supertrend_direction`，导致经 analyze_all 的动量永不触发「只确认不否决」微调。已修复（inspect 按签名条件透传，避免破坏旧插件）。 | `plugin_registry.py:48-110`（analyze_all + `_plugin_accepts_supertrend_direction`） |
| 工程派 | P2-2 | P2 | **ACCEPT** | `calc_supertrend([])` 时 `atr_list[-1]` 抛 IndexError。已加空输入早返回，返回 neutral 契约结构。 | `indicator_math.py:170-182` |
| 理论派 | P2-1 | P2 | **ACCEPT** | 首根方向因 `basic_lower = close - mult*ATR` 恒为真，永远初始化为 up。改用标准 `(H+L)/2` 为中心构造上下轨，使首根方向比较有意义。 | `indicator_math.py:183-196` |
| 理论派 P2-1 后半 / 工程派 P2-3 | 空头轨道 | P2 | **ACCEPT** | `build_report` 仅存 `stop_long`，空头(direction=="down")时 `supertrend_stop` 为 None，渲染被跳过。改为按方向取活动轨道价（up→stop_long，down→stop_short）。 | `run_analysis.py:1148-1156` |
| 理论派 | P2-2 | P2 | **ACCEPT** | output-template 写方案B「+0.1」，代码为 `min(100.0, score+8)`（≈+0.08）。以代码 +8 为准同步文档。 | `references/output-template.md:10` |
| 工程派 | P2-4 | — | **REJECT(忽略)** | T+1 锁误报，不在本提交范围，按两派共识忽略。 | — |

> 无 P0 项。无 DOWNGRADE、无 DEFER。

---

## 三、修复护栏符合性自查

- ✅ 未新增第 4 个融合评委；未改 `get_regime_weights` / `_apply_main_force_weights`。
- ✅ VWAP 复用 `snapshot.bars_5m`（run_analysis.py:618 `calc_vwap(bars_5m, ...)`），未重拉行情。
- ✅ 偏离度 `*100` 转百分比保留（`calc_vwap` 不变）。
- ✅ ma250 警告 / T+1 锁 / 📍决策渲染均未触碰。
- ✅ 方案B 只确认不否决：`apply_supertrend_nudge` 同向 +8 封顶、反向 return 原值，逻辑未变。

---

## 四、补充测试

文件：`01-功能包-packages/trader/tests/test_indicator_enhancements.py`

- `test_supertrend_empty_input` — P2-2 空输入不崩，返回 neutral 契约。
- `test_supertrend_short_input_returns_neutral` — 单根输入安全返回 neutral。
- `test_supertrend_first_valid_bar_down` — P2-1 首根方向可正确初始化为 down（修复首根恒 up）。
- `test_plugin_accepts_supertrend_direction_detection` — inspect 探测签名正确性。
- `test_analyze_all_passes_supertrend_direction` — P1-1 透传 `supertrend_direction` 给 momentum，旧插件不被透传且不崩。
- `test_analyze_all_autocompute_supertrend_direction` — 未显式传入时 analyze_all 自动基于 bars 计算方向。

---

## 五、验证结果（pytest 输出摘要）

```
$ PYTHONPATH="02-共享模块-shared:01-功能包-packages/trader/scripts" \
  python -m pytest \
    01-功能包-packages/trader/tests/test_indicator_enhancements.py \
    01-功能包-packages/trader/tests/test_fusion_integration.py -q

26 passed in 0.18s
```

> 注：原验证命令给出的 `02-共享模块-shared/tests/test_fusion_integration.py` 路径不存在；经 glob 定位真实路径为 `01-功能包-packages/trader/tests/test_fusion_integration.py`，已用真实路径运行。

兼容性补充运行（证明旧 analyze_all 调用方不受影响）：

```
$ python -m pytest 02-共享模块-shared/tests/test_arch_refactoring.py -q
24 passed in 0.08s
```

**全部测试全绿，无回归，无 DEFER。**

---

## 六、结论

- 裁决：P1-1（ACCEPT）、P2-2（ACCEPT，空/短输入加固）、P2-1（ACCEPT，首根方向修复）、空头轨道（ACCEPT，渲染契约修复）、文档 P2-2（ACCEPT，+0.1→+8）、P2-4（REJECT 忽略）。
- 改动范围严格限定在 4 个文件（`indicator_math.py` / `plugin_registry.py` / `run_analysis.py` / `output-template.md`）+ 1 个测试文件，未触碰融合评委与展示护栏。
- 测试全绿，未触发任何 DEFER 分支。
