# 威科夫南网 epic — TR(B) + 簇(C) + PhaseA 否决(G)

> **status**: impl_done（B TR fallback + C/G 簇 + A SOS 南网实证日线●）  
> **日期**: 2026-08-04  
> **用户批准**: SOP 选项 1（B→C/G→南网验收）  
> **外部法源**: WorkBuddy `wyckoff-sos-修复交接说明.md` Bug B/C/G  
> **关联**: `wyckoff-sos-single-day-handoff.md`（A，已实现；实票依赖 B）  
> **禁止**：改 fusion 公式 / 出手 / 池分道；软确认 ST；在 packages 复制引擎

---

## 0. 摘要

| Bug | 修法（v1） |
|-----|------------|
| **B** TR 被 SC 前高打断 → None | 主路径 grow 不变；失败则 **末端对齐滑窗 fallback**（`FALLBACK_MIN_WIDTH`）取质量最高且 amp/折返合格的窗 |
| **C** 60 日旧 UT→SOW 误 `distribution_confirmed` | 簇内找最后 SC；**SC 之后**才认 UT/SOW/支撑/SOS；另要求 SOW 落在近端 `CLUSTER_EVENT_FRESH_BARS` |
| **G** `accum_confirmed` ∧ `phase_a=failed` | `phase_a_range.status==failed` 时 **强制** 四簇布尔 False + 原因 |

---

## 1. 必须 / 禁止

### 必须

- M-B1：主 grow 逻辑行为兼容（既有宽 TR 仍优先）
- M-B2：主失败时可 fallback 检出「崩盘后短横盘+突破」类 TR（宽≥FALLBACK_MIN_WIDTH）
- M-B3：fallback 仍要 amp∈[min,max]、dir_changes≥2、分位边界
- M-C1：`distribution_confirmed` 不得仅由 SC **之前** 的 UT + 任意 SOW 构成
- M-C2：SOW 触发索引须在 scan 近端 fresh 窗内，否则不确认派发簇
- M-G1：`phase_a_status/ range.status == failed` → 四簇 confirmed/failed 全 False

### 禁止

- P1：用分位软箱冒充 L2 成熟箱 / 打开量度（成熟度合同不变）
- P2：为过南网把 `WYCKOFF_TR_MIN_WIDTH` 全局降到 <20（只允许 fallback 常量）
- P3：改 decision_view / fusion 权重
- P4：无测例合入

---

## 2. 常量

```python
WYCKOFF_TR_FALLBACK_MIN_WIDTH = 10     # fallback 滑窗最小宽
WYCKOFF_CLUSTER_EVENT_FRESH_BARS = 10  # SOW/确认事件近端新鲜度（相对 scan 末）
```

---

## 3. 可改白名单

- `config.py` — 上列常量  
- `wyckoff_events.py` — `_detect_trading_range`、`_detect_event_cluster`（+ 小 helper）  
- `wyckoff_core.py` — phase_a failed 后闸簇  
- `tests/test_wyckoff_core.py` — B/C/G 测例  
- 本文 + `workflows/sos-single-day-fix/` 进度

---

## 4. 验收

| ID | 期望 |
|----|------|
| B1 | 构造「高位→崩盘→≥10 根横盘→突破」→ TR 非 None，upper/lower 落在横盘带附近 |
| B2 | 原宽幅震荡 TR 仍可检出（回归） |
| C1 | 旧 UT + 中段 SOW + 末端上涨，且 SOW 距今很远 / 或 SC 在 UT 后 → `distribution_confirmed=False` |
| G1 | 注入 `phase_a failed` 后簇全 False |
| A | thrust 单测仍绿（round 量比） |

南网实票：`final_wyckoff.py --target 南网科技`（人工/有行情时）TR 非空、SOS 可亮、dist 不误确认。
