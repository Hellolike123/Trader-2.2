# PRD: 重构阶段判定引擎 — 主力行为驱动

## 目标

重写 `stage_positioning.py` 的 `_detect_major_stage`，将当前以价格结构为中心（量价+MA+ATR 三维投票）的判定，替换为以**主力行为状态**为中心的判定架构。

## 现状问题

1. 量价关系 + MA 高度共线，实际只有约 1.5 路独立信息
2. 判定维度全是价格派生指标（量价、MA、ATR），没有直接观测主力行为
3. 系统已有 `main_force.py`（五阶段：吸筹/试盘/拉升/派发/砸盘）和 `wyckoff_core.py`（BC/Spring/Upthrust），但 `_detect_major_stage` 完全没使用
4. 用户真正关注的是"主力在干什么"，不是"价格在结构上什么位置"

## 方案：主力行为三层架构

### 第一层 — 主力行为主判定（权重 60%）

**输入：**
- `main_force_result`（来自 `main_force.detect_main_force_stage()`）：吸筹/试盘/拉升/派发/砸盘
- `wyckoff_result`（来自 `wyckoff_core`）：Spring/Upthrust/BC/背离信号
- 资金流向数据（`fund_flow_data.py`）：超大单/大单净流入

**判定逻辑：**

```
# main_force 有明确结果 → 直接使用
吸筹  → 蓄势
试盘  → 蓄势偏强（有主力活动但还没发力）
拉升  → 主升
派发  → 派发
砸盘  → 衰退

# main_force 置信度不足或无实时资金数据 → 用 Wyckoff + 量价判定
Spring + 缩量回踩支撑  → 蓄势偏强
Upthrust + 放量滞涨    → 派发
BC + 连续被动买入       → 主升（主力拉高出货前的拉升段）
量价背离 + 资金背离     → 确认主力行为方向
```

### 第二层 — 量价确认（权重 30%）

不独立判定了，而是**验证主力信号的真假**：
- main_force 说拉升 → 量价是否配合放量上涨？→ 不配合则降级为蓄势偏强
- main_force 说吸筹 → 量价缩量筑底还是继续放量下跌？→ 量价背离则降级
- Wyckoff Spring + 量价确认 → 高置信度积累期
- Wyckoff Upthrust + 量价不配合 → 高置信度派发期

### 第三层 — 结构兜底（权重 10%）

当主力数据和 Wyckoff 都不可用时（次新股/数据不足/异常行情）：
- 保留 `_assess_volume_price` 作兜底
- 简化 MA 方向判断（只输出 up/down/neutral）

### 融合规则

```
最终阶段 = main_force(60%) + 量价确认(30%) + 结构兜底(10%)

# 一致 → 直接输出
main_force=吸筹 + 量价缩量筑底 → 蓄势
main_force=拉升 + 量价放量上涨 → 主升
main_force=派发 + 量价背离     → 派发

# 不一致 → 量价验证降级
main_force=拉升 + 量价缩量 → 蓄势偏强（非主力真实拉升）
main_force=吸筹 + 量价放量下跌 → 蓄势偏弱（吸筹期走坏）
main_force=派发 + 量价缩量横盘 → 蓄势偏弱（可能是自然回调）
```

### 改动范围

- **主改** `02-共享模块-shared/trader_shared/stage_positioning.py`
- 新增：`_detect_main_force_stage()` — 主力行为判定
- 重写：`_detect_major_stage()` — 三层融合
- 保留：`_assess_volume_price()` — 只做量价确认层
- 可删除：`_assess_ma_structure()`、`_assess_atr_volatility()`
- 签名新增 `chan_result` 参数（默认 None，仅做兜底第三层用，向后兼容）

### 调用方需同步

| 位置 | 改动 |
|------|------|
| `assess_stage()` | 传入 `main_force_result`（已有参数） |
| `run_analysis.py:build_report()` | 传入 `main_force_result` + `chan_result`（已有变量） |

## 数据支持

池内 9 只票实测：
- `fund_flow_data.py` 可采集资金流向（东方财富 HTTP API）
- `main_force.py` 已经在跑五阶段
- Wyckoff 信号从 `wyckoff_core.py` 直接获取
- 所有数据源已在系统中就位，无需新增外部依赖

## 验收标准

1. `_detect_major_stage` 签名向后兼容（所有新参数默认 None）
2. 主力行为判定优先于结构判定（主力有数据时不用结构兜底）
3. 量价确认层能正确降级虚假主力信号
4. 输出阶段（蓄势/蓄势偏强/蓄势偏弱/主升/派发/衰退）的语义不变，下游消费模块零改动
5. 简化了代码结构（删除不必要的 MA/ATR 维度）
