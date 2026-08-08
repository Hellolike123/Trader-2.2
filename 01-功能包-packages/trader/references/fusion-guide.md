# Fusion Guide — 融合层字段解读

`merge_decisions()` 返回的融合字段解读规则。

> **产品边界**：出手 / 新开听 `decision_view`（共振 ∧ 策略 ∧ 纪律）。  
> `weighted_score` / `action` 仅仪表，不作总司令。

## 融合字段速查

| 字段 | 类型 | 范围 | 含义 |
|------|------|------|------|
| `weighted_score` | float | [-1.35, 1.35] | 融合加权分仪表。正=多方，负=空方 |
| `confidence` | float | [0, 1] | 综合置信度 |
| `action` | str | — | 仪表动作文案（由 weighted_score + regime 映射） |
| `regime` | str | 正常/偏弱/很差/未知 | 板块环境档（跟所属板块指数；面板 meta 不写，只进内部风控） |
| `hmm_regime` | str | bull/bear/range | HMM 前瞻大势状态 |
| `disagreement` | float | [0, 3] | 三路信号分歧度（max - min direction） |
| `signals_detail` | dict | — | **chan / momentum / vpf** 各自的 direction + confidence |
| `weights_used` | dict | — | 实际权重（键为 chan/momentum/vpf） |
| `fusion_input_path` | str | `cards` / `cards_failed` | 本次三席输入路径 |

## 输入路径（`FUSION_FROM_CARDS`）

短线三席：**缠论 + 动能 + 价量资金(VPF)**。日线威科夫**不进**短线加权。

| 模式 | 行为 |
|------|------|
| 缺省 / `cards` | **生产唯一路径**：意见卡 → `fusion_card_signals`；失败 → 中性占位（`fusion_input_path=cards_failed`） |
| `classic` / `compare` 等 | **已移除**：设置即 `ValueError`，不会走 cards（无 classic mapper / 无 `fusion_compare`） |

`fusion_input_path` 枚举：`cards` \| `cards_failed`。  
`weighted_score` / `action` / breakdown **仅仪表**；出手听 `decision_view`。

## 8 档阈值（weighted_score → 方向强度，仪表用语）

| weighted_score | 方向 | 输出用语 |
|----------------|------|---------|
| ≥ 0.40 | 强多 | 趋势明确，可持仓 |
| ≥ 0.25 | 偏多 | 偏多操作，轻仓试探 |
| ≥ 0.10 | 弱多 | 弱势偏多，等确认 |
| ≥ -0.05 | 中性 | 观望，等信号 |
| ≥ -0.12 | 弱空 | 弱势偏空，谨慎 |
| ≥ -0.25 | 偏空 | 偏空操作，逐步减仓 |
| ≥ -0.40 | 强空 | 趋势向下，回避 |
| < -0.40 | 极空 | 远离，等待企稳 |

## action 字段映射（score_to_action）

action 由 `score_to_action(weighted_score, disagreement, regime)` 生成：
- `disagreement > 1` 且无强信号 → 分歧降档映射
- `regime=偏弱` → 正阈值右移 +0.10（更难触发做多）
- `regime=很差` → 三席权重归零，分数偏中性/空仓侧（**不是**固定写死「暂不碰」）

**禁止用 action 字符串推断方向**。产品出手听 `decision_view`。

## 覆盖机制（Post-Processing Overrides）

action 生成后可能被以下机制覆盖（按优先级）：

1. **解禁风险一票否决**（unlock_veto）→ "空仓 (限售解禁风险)"
2. **资金连续流出一票否决**（fund_flow_outflow_veto）→ "资金流出，减仓观望"
3. **天量天价**（volume_warning climactic）→ "天量天价，减仓观望"
4. **高位修正**（pos_pct ≥ 0.8 + 观望类 action）→ "高位观望"

被覆盖后，`weighted_score` 和 `confidence` 仍保留原始值（不修改），仅 action 被改写。

## verbatim 模板（AI 不可改写）

build_report() 会生成 `fusion_verbatim` 字段，AI 输出时必须逐字引用，不可改写。

**仪表化**：主行是分数/regime/分歧 +「仅参考」，禁止 `🎯 {action}` 指令形主行（出手听 `decision_view`）。

格式：`{emoji} 加权{score}｜置信{confidence%}｜{regime}｜分歧{disagreement}｜仅参考`

emoji 由 weighted_score 决定：≥0.25 🟢 / ≥0.10 🟡 / ≥-0.05 ⚪ / ≥-0.12 🟠 / else 🔴

## 权重分配（chan / momentum / vpf）

### 默认权重（由 regime 决定；见 `fusion_regime.py`）
| regime | chan | momentum | vpf |
|--------|------|----------|-----|
| 正常 | 0.30 | 0.45 | 0.25 |
| 偏弱 | 0.50 | 0.15 | 0.35 |
| 很差 | 0.00 | 0.00 | 0.00 |
| 未知 | 0.30 | 0.45 | 0.25 |

### 场景偏置（覆盖默认）
| 场景 | chan | momentum | vpf |
|------|------|----------|-----|
| 低位突破 (pos_pct ≤ 0.3) | 0.44 | 0.20 | 0.36 |
| 高位超买 (pos_pct ≥ 0.7 + mom≥80) | 0.20 | 0.56 | 0.24 |
| 结构看空警告 | 0.44 | 0.20 | 0.36 |

### 主力行为修正（键为 vpf，不是 wyckoff）
| main_force_env | chan | momentum | vpf |
|----------------|------|----------|-----|
| accumulation (吸筹) | +0.00 | -0.10 | +0.10 |
| testing (试盘) | +0.00 | +0.00 | +0.00 |
| markup (拉升) | -0.05 | +0.10 | +0.00 |
| distribution (派发) | -0.10 | -0.05 | +0.10 |
| markdown (砸盘) | -0.15 | -0.10 | -0.10 |
