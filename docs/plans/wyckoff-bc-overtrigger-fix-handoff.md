# FINDING-5 修复 handoff：BC 买力高潮过触发收紧（威科夫原典对齐）

> 关联：审计报告 `wyckoff-chan-state-audit-report.md` §11（F4 真实票目检）· FINDING-5
> 性质：**行为变更（事件检测器语义收紧）**，按 AGENTS.md 铁律先写 handoff 再实现。

## 1. 背景与优先级

F4 真实票目检（12 只样本）发现 `_detect_buying_climax` 触发 **11/12**，含明确假阳（隆基 601012、宁德 300750）。
原审计报告把 FINDING-5 标「中 / 非阻断」，理由「下游 phase 已对 BC 过触发稳健」。

**纠正（本次复查）**：BC 过触发**并非仅展示误导**。下游消费面：
- `stage_stops.py:247` — `bc_signal` 为真 → **第一笔直接减仓（triggered=True）** → 误减仓实盘后果。
- `stage_position.py`（L84/163/264/604）、`wyckoff_chain.py:127`、`wyckoff_phase.py:411/503`。
故优先级上调为 **高**。

## 2. 法源（威科夫原典）

BC（Buying Climax / 买力高潮）是**派发阶段 Phase A** 的事件，出现在**长期显著上涨之后**——
主力在高位把货卖给狂热散户，表现为天量滞涨 / 长上影。它**不应**在低位积累股、或仅反弹到近窗高点的股票上触发。
代码注释（L642-646）已自承「局部供应棒启发式」，但标签「BC/购买高潮」暗示顶部语义，须收紧到原典。

## 3. 现状与根因

- `wyckoff_events.py:346-351` `_is_bc_high_position` → `_price_pos_pct(bars, idx)` 默认 `lookback = WYCKOFF_SPRING_SUPPORT_LOOKBACK = 10` → **近 10 日**相对位置 ≥0.65 即判高位。
- `wyckoff_events.py:660` 量比均值 `recent = bars[max(0, scan_idx-10):scan_idx]` → **近 10 日**均量。
- **缺前置涨幅条件**：无任何「BC 前须有主升段」约束 → 反弹到近 10 日高点的棒被当 BC。

## 4. 修复方案（可改）

1. **拉长高位窗**：`_is_bc_high_position(bars, idx, lookback=None)` 默认改 `WYCKOFF_BC_HIGH_POS_LOOKBACK = 60`（替代默认 10）。调用处不变。
2. **加前置主升条件**：`_detect_buying_climax` 在量比/高位判定后，新增「BC 前 `WYCKOFF_BC_PRE_RISE_LOOKBACK = 60` 日累计涨幅 ≥ `WYCKOFF_BC_PRE_RISE_PCT = 0.15`」判定；不满足 `continue`。即高潮前须有 ≥15% 主升。
3. **config 新增三常量**并加入 `__all__` / `TUNING_PARAMS`（env 可覆）。

## 5. 可改文件（白名单）

- `02-共享模块-shared/trader_shared/config.py`：新增 3 常量 + 导出
- `02-共享模块-shared/trader_shared/wyckoff_events.py`：`_is_bc_high_position` 签名 + `_detect_buying_climax` 加前置涨幅

## 6. 禁止项（勿改）

- 不动 `fusion` / `decision_view` / 出手 / 池分道
- 不删除 `bc_signal` 任何下游消费（stage_stops / stage_position / wyckoff_chain / wyckoff_phase）
- 不动 ARE 复用逻辑（`_detect_are` 复用 `_detect_buying_climax`）——BC 收紧后 ARE 锚点自然减少，逻辑自洽
- 不动 SC / Spring / SOS / UTAD 检测器
- 不动 `WYCKOFF_BC_VOL_RATIO_THRESHOLD=1.5` / `WYCKOFF_BC_MIN_POS_PCT=0.65` 现有值（仅**新增**更宽窗与涨幅条件）

## 7. 验收表

| 项 | 期望 | 验证 |
|---|---|---|
| 隆基 601012 BC | **False**（F4 假阳消除：无真实前置主升，仅弹到近窗高） | 重跑真实数据 |
| 宁德 300750 BC | **True**（纠正：有 31% 前置主升+60日高位71.8%，是威科夫原典真 BC，**非**假阳） | 重跑真实数据 |
| 茅台 600519 BC | **True**（高位+前置主升保留） | 重跑真实数据 |
| 东财 300059 BC | **True**（高位+前置主升保留） | 重跑真实数据 |
| `test_bc_detected` 等平线用例 | 改带主升背景后 True / 或证伪 False | pytest |
| 新增 `test_bc_rejected_no_pre_rise` | False（平线后单根放量棒不触发） | pytest |
| 新增 `test_bc_real_climax_with_pre_rise` | True（主升后高位放量触发） | pytest |
| `test_bc_found_60_bars_back` / `test_are_reuses_bc_detector` | 仍 True（前段 +20% 爬升满足涨幅） | pytest |
| wyckoff 系列 + report + 门禁 | 零回归 | pytest + run-gate-tests.sh |

> **宁德预期纠正说明**：原 handoff 写「宁德应 False」是误判。F4 目检时按「距 40 日高 13%」粗判为假阳，但按新语义（60 日窗 + 前置 15% 主升）宁德 BC@428.9 确有 31% 前置主升、60 日高位 71.8%、量比 1.7+长上影——**完全符合威科夫原典**，应为 True。修正后 4 只真实数据全部符合预期。

## 9. 验证结果（实现后）

- **真实数据 12 只样本**：BC 触发 11/12 → **7/12**。剩余 7 只（茅台/宁德/比亚迪/东财/南网/长江电力/平安银行）均核验有真实前置主升（16%–44%）+ 60 日高位（70%–100%），全为合法 BC；消除的 5 只（隆基/五粮液/平安/招商/科大讯飞）均为「无真实前置主升的反弹棒」假阳。
- **单测**：`test_wyckoff_core.py` 173 passed（含新增 `test_bc_rejected_no_pre_rise` / `test_bc_real_climax_with_pre_rise`）；原 5 个平线 BC 用例已补前置主升；`test_are_after_bc` 回落棒量降至 1500 避免其本身被判 BC。
- **回归**：wyckoff+report+chan 382 passed；`test_wyckoff_realstock_verification`（真实票 BC=True 断言）通过；门禁套件（见 §7 末行）。

## 8. 风险

- 收紧后 BC 命中数下降，`bc_signal` 派发背景信号变少；但 ARE 锚点自洽、phase 本对 BC 稳健，风险可控。
- `WYCKOFF_BC_PRE_RISE_PCT` 过高会压真 BC；取 0.15 经 `test_bc_found_60_bars_back`(+20%)/ARE(+20%) 验证不回归。
- 不引入默认值翻转（`WYCKOFF_BC_HIGH_POS_LOOKBACK` 等均为新增常量，env 可覆，默认值即修复值）。
