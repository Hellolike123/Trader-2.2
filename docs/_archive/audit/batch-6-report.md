# 第 6 批审查报告（收尾批 — DEFER 清零）

> 审查日期：2026-07-07（夜）
> 分支：`audit-batch-6-final-defer`
> 修复文件：4 个 / DEFER-2 + DEFER-3 全部关闭 / 0 新增 DEFER

---

## 背景

第 5 批审查遗留 3 个 DEFER 项，其中 DEFER-1（bayesian 乘积规则）已先行修复合并。本批关闭剩余两项：

- **DEFER-2**：`hmm_regime.py` 2D 观察维度被常数广播退化
- **DEFER-3**：`t0_core.py` `render_markdown` 输出七段，未对齐 AGENTS.md 的四段契约

至此，Trader3.0 五批审查 + 收尾批的全部 DEFER 项清零。

---

## DEFER-2 — HMM 2D 序列输入

### 根因

`market_env.assess()` 将 `vol_trend`（标量：近 5 日均额 / 前 5 日均额）传给 `detect_regime`，`hmm_regime` 内部用 `np.full(len(returns), float(volume_ratio))` 广播为常数序列。2D 观察矩阵第二维全为同一值 → 2D HMM 退化为 1.5D，第二维无区分度，无法学到量能时序模式。

### 修复

1. **`hmm_regime.py`**
   - 新增 `_build_obs(returns, volume_ratio)`：`volume_ratio` 为 list/tuple/ndarray 时取与 returns 等长的最近部分作为第二维；为 float 时广播（向后兼容）；None 时 1D。
   - `fit` / `predict` / `fit_predict` 改用 `_build_obs` 构造观察矩阵；`obs_dim` 依据 `volume_ratio` 是否 None 切换，并每次 `_init_params()` 保证参数形状匹配。
   - `detect_regime` 缓存 key 支持序列型 `volume_ratio`（用其内容 hash 区分）。
   - `volume_ratio` 类型注解升级为 `float | List[float] | None`。
2. **`market_env.py`**
   - HMM 判定改用 `closes_vol`（close+volume 同时存在的 bars）对齐，构造每日量比序列 `vol_series[i] = volume[i] / MA5(volume)[i]`，与 `index_returns` 等长后传给 `detect_regime`。
   - 非正值兜底为 1.0，避免 inf/nan。

### 验证

- 1D / 标量 2D / 序列 2D 三条路径均正常返回。
- 序列输入：`mu.shape=(3,2)`、`cov.shape=(3,2,2)` → 2D 真正生效。
- 长度不足 / 含 None·NaN 的脏序列均安全兜底，无异常。

---

## DEFER-3 — T0 四段精简

### 根因

`render_markdown` 输出七个区块（头部 + 扫描 + 止盈/波动 + 资金异动 + 盘中动态 + 实时信号 + 止损），与 AGENTS.md「T0 输出精简为 4 部分（触发价 / 大单异动 / 操作建议 / 风控提醒）」不一致。

### 修复

1. **`t0_core.py`** — `render_markdown` 重写为四段：
   - `📌 触发价`：当前动作 + 止损价 + 低吸/高抛观察价 + 止盈 + ATR 波动（始终显示）
   - `💰 大单异动`（无 Tick 时 `💰 分时估算`）：资金流向（条件显示）
   - `📈 操作建议`：合并原「盘中动态」与「实时信号」两段（order_book / history / wyckoff / 筹码搬家）
   - `⚠️ 风控提醒`：止损退出/不再低吸 + data_status 提示（始终显示）
2. **`output-template.md`** — 同步更新为四段契约，保留「首行 🎯 T0」「含低吸/高抛/止损」「无 markdown 表格/标题/列表」约束。

### 验证

- 6 个场景（正常四段 / 今天不做 / 实时信号 / 数据不完整 / 极简四段 / mock 大单段）全部通过 `schema.validate_t0`。
- 首行 `🎯 T0`、关键词「低吸/高抛/止损」、无 banned 词均满足。

---

## 修改统计

```
 4 files changed, 161 insertions(+), 110 deletions(-)
   （.workbuddy/memory/2026-07-07.md 16 行为本期记录，本次 code 提交不含 memory）
```

## 验证结果

- `hmm_regime` / `market_env` / `t0_core` 模块导入测试通过
- HMM 2D 序列路径单元验证通过（mu/cov 为二维结构）
- T0 `validate_t0` 六场景校验全部通过
- 已合并 main，无冲突
