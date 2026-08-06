# SOS 历史高价误判修复 handoff（方案 B）

> 状态：active（2026-08-06）
> 触发：德方纳米 wyckoff 日线 SOS 显示 70.09，现价 46.55——价没到却亮灯
> 法源：`wyckoff_events._try_sos_thrust` / `_detect_sos`（回扫）· `wyckoff-sos-single-day-handoff.md`

## 一、根因（实证）

- 德方纳米日线 SC 未亮 → `_detect_sos` 无 SC 地板（`min_tip_idx=None`）→ 回扫 120 根
- 回扫扫到 26 根前历史高位 70.09（当时现价 ~70），判定「收盘站上 TR 上沿 46.53」→ SOS
- 但 70.09 是**历史下跌途中的反弹阳线**，被当成「吸筹后强势突破」——假强势
- 同类防护只对「有 SC」生效（`_ok_idx(i>floor_i)`）；无 SC 场景漏
- TR 上沿 46.53 是当前箱体，70.09 远超 → 检测语义应为「站上箱体」，不是「远高于箱体」

## 二、方案（用户已拍板 B）

`_try_sos_thrust` 增加**价幅上限**：`sos_price ≤ tr_upper × 1.5`，超限拒绝：

```python
if c > tr_upper * WYCKOFF_SOS_MAX_PRICE_MULT:
    return _sos_empty(f"收盘{c:.2f}远超上沿{tr_upper:.2f}（×{WYCKOFF_SOS_MAX_PRICE_MULT:.1f}），历史高位反弹，非箱体突破")
```

- 常量 `WYCKOFF_SOS_MAX_PRICE_MULT = 1.5`（与 THRUST 常量同区）
- 检查插在「收盘未站上 TR 上沿」之后、量比检查之前（早退省算）
- 语义：SOS=站上箱体的突破；拒绝「远高于箱体的历史价反弹」

## 三、必须（验收表）

| # | 必须项 | 验收 |
|---|--------|------|
| 1 | 德方纳米日线 SOS 熄灭（不再亮 70.09） | 实跑 `final_wyckoff --target 德方纳米` SOS 灯 ○ |
| 2 | 正常近箱 SOS 不误杀（收盘 ≤1.5×上沿仍亮） | 造 bar 单测：close=1.2×upper 亮、2.0×upper 灭 |
| 3 | 不改 climb 路径（本次只 thrust；climb 无此症状） | 只动 `_try_sos_thrust` |
| 4 | 有 SC 地板场景行为不变 | 既有 SOS 测试全过 |
| 5 | 门禁全绿 | run-gate-tests.sh |

## 四、禁止

- 禁止改 SC 地板/回扫窗逻辑（方案 A 不在本次范围）
- 禁止改 `_try_sos_climb` / 其他事件检测
- 禁止放大 1.5 倍以上（语义漂移）

## 五、可改文件白名单

- `02-共享模块-shared/trader_shared/wyckoff_events.py`（`_try_sos_thrust` + 常量）
- `02-共享模块-shared/tests/test_wyckoff_*.py`（加单测）
- 本 handoff

## 六、执行顺序

1. 加常量 `WYCKOFF_SOS_MAX_PRICE_MULT=1.5` + `_try_sos_thrust` 价幅上限
2. 单测：close=1.2×upper 亮 / 2.0×upper 灭
3. 实跑德方纳米验证 SOS 熄灭（#1）
4. 门禁（#5）+ 既有 wyckoff 测试全过（#4）
5. 归档 handoff

## 七、执行结果（2026-08-06）

- **实现**：`config.WYCKOFF_SOS_MAX_PRICE_MULT=1.5`（env 可调）+ `_try_sos_thrust` 在「收盘未站上 TR 上沿」之后、量比之前加价幅上限：`c > tr_upper×1.5` → 拒绝「历史高位反弹」
- **单测**：`test_thrust_price_cap_blocks_remote_high`（_detect_sos 级，近箱亮/远箱灭）+ `test_thrust_price_cap_direct_remote_high`（_try_sos_thrust 直测 70.09 vs 46.53 拒绝、50 vs 46.53 放行）
- **实跑德方纳米**（#1）：SOS 灯 `●70.09` → **○ 熄灭**；日线本波「本波未成型｜无箱」，与现价 46.55 下跌状态一致 ✅
- **回归**：TestDetectSosThrust 9 passed（含既有 7 个）+ 全 wyckoff 213 passed + 门禁 **750 passed / 0 failed** ✅
- **范围**：只动 `_try_sos_thrust` + config 常量；climb / SC 地板 / 回扫窗零改动（#3/#4）✅
