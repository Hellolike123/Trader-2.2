# A 股箱体灵敏度小步试验 — Handoff

> **状态**: done（已合入 `main`，PR #55）  
> **产品**：路 B —— **不改**「箱体=SC+AR+真ST」定义；只略松检测参数。  
> **样本**：南网科技 / 三花智控 / 顺丰控股 / 中航机载 / 德方纳米 / 顶点软件  
> **方法**：同行情 env A/B（松前默认 vs 试验默认）对照阶段/雏形/箱体/灯。

## 本试验默认值（相对 main）

| 参数 | 改前 | 试验 |
|------|------|------|
| `WYCKOFF_BC_VOL_RATIO_THRESHOLD`（SC/BC 量比） | 1.8 | **1.5** |
| 日线 SC `change_pct_max` | -2.0 | **-1.5**（`WYCKOFF_SC_CHANGE_PCT_MAX_DAILY`） |
| `WYCKOFF_SC_MAX_POS_PCT`（SC 近窗位置上限） | 等价 ~0.35 | **0.50** |
| `WYCKOFF_ST_SC_VOL_RATIO` | 0.72 | **0.80** |
| `WYCKOFF_ST_SC_PROXIMITY` | 0.03 | **0.045** |

禁止：没 ST 也写箱体；软确认 ST；fusion/出手改动。

## 6 票实盘对照（env A/B，同日行情）

| 票 | 周线 | 日线 | 有无 L2 箱体 |
|----|------|------|-------------|
| 南网科技 | 不变 L1 雏形（SC+AR 待 ST） | **L0 无事件 → L1 雏形（SC+AR 待 ST）** | 无 |
| 三花智控 | 不变 L0 failed（SC+ARE） | 不变 L0（compression） | 无 |
| 顺丰控股 | 不变 L0 failed | **无 SC → 认出 SC 但 Phase A 失效** | 无 |
| 中航机载 | 不变 L0 failed | 不变 L0 无事件 | 无 |
| 德方纳米 | L0 failed，**多亮 ARE** | 不变 L0（compression） | 无 |
| 顶点软件 | **仅 ARE → 多亮 SC 且 Phase A 失效** | 不变 L0（SOS 无箱） | 无 |

结论摘要：

1. **无人进入 L2「箱体」**（仍缺真 ST）—— 路 B 定义守住。  
2. **唯一正向雏形抬升**：南网科技日线 L0→L1（有 SC+AR，待 ST）。  
3. **副作用**：顺丰日线、顶点周线更容易认出 SC，但随即 Phase A 失效（更敏感 ≠ 更多箱）。  
4. 若还要更多箱体，下一步应专攻 **ST 回测判定**（仍禁软确认），而不是再大幅松 SC。

验收：6 票对照表；相关 pytest 绿；用户决定是否合入或回滚。
